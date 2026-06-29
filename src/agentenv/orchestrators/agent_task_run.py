import json
import tempfile
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agentenv.agents.loop import run_prompt_loop
from agentenv.agents.schema import AgentTaskView, PromptLoopResult, PromptLoopStatus
from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.models.client import ModelClient
from agentenv.models.config_schema import ModelConfig
from agentenv.models.schema import DecodingConfig
from agentenv.orchestrators.attempt import (
    AttemptResult,
    AttemptRun,
    AttemptStatus,
    run_patch_attempt,
)
from agentenv.orchestrators.attempt_io import AttemptArtifactPaths
from agentenv.orchestrators.attempt_io import write_attempt_artifacts
from agentenv.runners.diff_runner import hash_diff, render_directory_diff
from agentenv.tasks.validate import load_task_manifest


AGENT_RUN_ORCHESTRATOR_VERSION = "agent_task_run_v0"

AgentTaskRunStatus = Literal["scored", "agent_loop_failed", "orchestrator_error"]


class AgentTaskRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus | None
    candidate_patch_path: str | None
    candidate_patch_hash: str | None
    attempt_result: AttemptResult | None
    error_class: str | None
    error_message: str | None
    started_at: str = Field(min_length=1)
    ended_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    orchestrator_version: str = Field(min_length=1)


@dataclass(frozen=True)
class AgentTaskRunErrorDetails:
    error_class: str
    message: str
    traceback: str


@dataclass(frozen=True)
class AgentTaskRun:
    result: AgentTaskRunResult
    agent_task_view: AgentTaskView | None
    prompt_loop_result: PromptLoopResult | None
    candidate_patch: str
    attempt_run: AttemptRun | None
    error_details: AgentTaskRunErrorDetails | None = None


@dataclass(frozen=True)
class AgentTaskRunArtifactPaths:
    run_manifest_json: Path
    agent_task_run_json: Path
    decoding_config_json: Path | None
    model_config_json: Path | None
    agent_control_script_json: Path | None
    agent_task_view_json: Path | None
    prompt_loop_result_json: Path | None
    candidate_patch: Path | None
    error_txt: Path
    attempt_dir: Path | None
    attempt_artifacts: AttemptArtifactPaths | None


def run_agent_task_attempt(
    task_manifest_path: Path,
    model_client: ModelClient,
    decoding_config: DecodingConfig,
    workspace_parent: Path | None = None,
) -> AgentTaskRun:
    task_manifest_path = task_manifest_path.resolve()
    run_id = f"agent_task_run_{uuid4().hex}"
    started_at = _utc_now()
    started_timer = perf_counter()
    run_root = _run_root(workspace_parent, run_id)

    agent_task_view: AgentTaskView | None = None
    prompt_loop_result: PromptLoopResult | None = None
    candidate_patch = ""
    candidate_patch_path: Path | None = None
    attempt_run: AttemptRun | None = None

    try:
        manifest = load_task_manifest(task_manifest_path)
        agent_interaction_workspace = prepare_agent_workspace(
            manifest,
            task_manifest_path,
            workspace_parent=run_root / "agent_interaction_workspace",
        )
        agent_task_view = AgentTaskView(
            task_id=manifest.id,
            instruction=manifest.instruction,
            workspace_path=agent_interaction_workspace.path,
            allowed_tools=list(manifest.allowed_tools),
            public_checks=[check.command for check in manifest.public_checks],
            max_turns=manifest.limits.max_turns,
            timeout_seconds=manifest.limits.timeout_seconds,
            network=manifest.limits.network,
        )
        prompt_loop_result = run_prompt_loop(
            agent_task_view,
            model_client,
            decoding_config,
        )

        if prompt_loop_result.status != "completed":
            return AgentTaskRun(
                result=_result(
                    run_id=run_id,
                    task_id=manifest.id,
                    task_manifest_path=task_manifest_path,
                    status="agent_loop_failed",
                    prompt_loop_status=prompt_loop_result.status,
                    candidate_patch_path=None,
                    candidate_patch_hash=None,
                    attempt_result=None,
                    error_class=prompt_loop_result.error_class,
                    error_message=prompt_loop_result.error_message,
                    started_at=started_at,
                    started_timer=started_timer,
                ),
                agent_task_view=agent_task_view,
                prompt_loop_result=prompt_loop_result,
                candidate_patch=candidate_patch,
                attempt_run=None,
            )

        candidate_patch = render_directory_diff(
            agent_interaction_workspace.task_dir / manifest.seed_workspace,
            agent_interaction_workspace.path,
        )
        candidate_patch_path = run_root / "candidate.patch"
        candidate_patch_path.write_text(candidate_patch)
        attempt_run = run_patch_attempt(
            task_manifest_path,
            candidate_patch_path,
            workspace_parent=run_root / "scoring_workspace",
        )

        return AgentTaskRun(
            result=_result(
                run_id=run_id,
                task_id=manifest.id,
                task_manifest_path=task_manifest_path,
                status="scored",
                prompt_loop_status=prompt_loop_result.status,
                candidate_patch_path=candidate_patch_path,
                candidate_patch_hash=hash_diff(candidate_patch),
                attempt_result=attempt_run.result,
                error_class=None,
                error_message=None,
                started_at=started_at,
                started_timer=started_timer,
            ),
            agent_task_view=agent_task_view,
            prompt_loop_result=prompt_loop_result,
            candidate_patch=candidate_patch,
            attempt_run=attempt_run,
        )
    except Exception as exc:
        task_id = (
            agent_task_view.task_id
            if agent_task_view is not None
            else "unknown_task"
        )
        return AgentTaskRun(
            result=_result(
                run_id=run_id,
                task_id=task_id,
                task_manifest_path=task_manifest_path,
                status="orchestrator_error",
                prompt_loop_status=(
                    prompt_loop_result.status
                    if prompt_loop_result is not None
                    else None
                ),
                candidate_patch_path=candidate_patch_path,
                candidate_patch_hash=(
                    hash_diff(candidate_patch)
                    if candidate_patch_path is not None
                    else None
                ),
                attempt_result=attempt_run.result if attempt_run is not None else None,
                error_class=type(exc).__name__,
                error_message=str(exc),
                started_at=started_at,
                started_timer=started_timer,
            ),
            agent_task_view=agent_task_view,
            prompt_loop_result=prompt_loop_result,
            candidate_patch=candidate_patch,
            attempt_run=attempt_run,
            error_details=_exception_details(exc),
        )


def run_and_persist_agent_task_attempt_to_dir(
    task_manifest_path: Path,
    model_client: ModelClient,
    decoding_config: DecodingConfig,
    out_dir: Path,
    *,
    agent_control_script: BaseModel | dict[str, Any] | None = None,
    model_config_provenance: dict[str, Any] | None = None,
    decoding_config_provenance: dict[str, Any] | None = None,
) -> AgentTaskRun:
    agent_task_run = run_agent_task_attempt(
        task_manifest_path,
        model_client,
        decoding_config,
    )
    write_agent_task_run_artifacts(
        agent_task_run,
        out_dir,
        decoding_config=decoding_config,
        agent_control_script=agent_control_script,
        model_config_provenance=model_config_provenance,
        decoding_config_provenance=decoding_config_provenance,
    )
    return agent_task_run


def write_agent_task_run_artifacts(
    agent_task_run: AgentTaskRun,
    out_dir: Path,
    *,
    decoding_config: DecodingConfig | None = None,
    agent_control_script: BaseModel | dict[str, Any] | None = None,
    model_config_provenance: dict[str, Any] | None = None,
    decoding_config_provenance: dict[str, Any] | None = None,
) -> AgentTaskRunArtifactPaths:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path = out_dir / "run_manifest.json"
    agent_task_run_path = out_dir / "agent_task_run.json"
    decoding_config_path = (
        out_dir / "decoding_config.json" if decoding_config is not None else None
    )
    model_config_path = (
        out_dir / "model_config.json"
        if model_config_provenance is not None
        else None
    )
    agent_control_script_path = (
        out_dir / "agent_control_script.json"
        if agent_control_script is not None
        else None
    )
    agent_task_view_path = (
        out_dir / "agent_task_view.json"
        if agent_task_run.agent_task_view is not None
        else None
    )
    prompt_loop_result_path = (
        out_dir / "prompt_loop_result.json"
        if agent_task_run.prompt_loop_result is not None
        else None
    )
    candidate_patch_path = (
        out_dir / "candidate.patch"
        if agent_task_run.result.candidate_patch_hash is not None
        else None
    )
    error_path = out_dir / "error.txt"
    attempt_dir = out_dir / "attempt" if agent_task_run.attempt_run is not None else None

    agent_task_run_path.write_text(agent_task_run.result.model_dump_json(indent=2) + "\n")
    if decoding_config_path is not None and decoding_config is not None:
        decoding_artifact = (
            decoding_config_provenance
            if decoding_config_provenance is not None
            else generated_decoding_config_provenance_artifact(decoding_config)
        )
        decoding_config_path.write_text(
            json.dumps(decoding_artifact, indent=2, sort_keys=True) + "\n"
        )
    if model_config_path is not None and model_config_provenance is not None:
        model_config_path.write_text(
            json.dumps(model_config_provenance, indent=2, sort_keys=True) + "\n"
        )
    if agent_control_script_path is not None and agent_control_script is not None:
        agent_control_script_path.write_text(_json_artifact(agent_control_script))
    agent_task_view = agent_task_run.agent_task_view
    if agent_task_view_path is not None and agent_task_view is not None:
        agent_task_view_path.write_text(agent_task_view.model_dump_json(indent=2) + "\n")
    prompt_loop_result = agent_task_run.prompt_loop_result
    if prompt_loop_result_path is not None and prompt_loop_result is not None:
        prompt_loop_result_path.write_text(
            prompt_loop_result.model_dump_json(indent=2) + "\n"
        )
    if candidate_patch_path is not None:
        candidate_patch_path.write_text(agent_task_run.candidate_patch)
    error_path.write_text(_error_text(agent_task_run))

    attempt_artifacts = (
        write_attempt_artifacts(agent_task_run.attempt_run, attempt_dir)
        if agent_task_run.attempt_run is not None and attempt_dir is not None
        else None
    )
    run_manifest_path.write_text(
        _run_manifest_json(
            agent_task_run,
            include_decoding_config=decoding_config is not None,
            include_model_config=model_config_provenance is not None,
            include_agent_control_script=agent_control_script is not None,
        )
    )

    return AgentTaskRunArtifactPaths(
        run_manifest_json=run_manifest_path,
        agent_task_run_json=agent_task_run_path,
        decoding_config_json=decoding_config_path,
        model_config_json=model_config_path,
        agent_control_script_json=agent_control_script_path,
        agent_task_view_json=agent_task_view_path,
        prompt_loop_result_json=prompt_loop_result_path,
        candidate_patch=candidate_patch_path,
        error_txt=error_path,
        attempt_dir=attempt_dir,
        attempt_artifacts=attempt_artifacts,
    )


def _json_artifact(value: BaseModel | dict[str, Any]) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json(indent=2) + "\n"
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def model_config_provenance_artifact(
    *,
    model_config: ModelConfig,
    model_config_path: Path,
    model_config_hash: str,
) -> dict[str, Any]:
    return {
        "source_path": str(model_config_path),
        "source_hash": model_config_hash,
        "config": json.loads(model_config.model_dump_json()),
    }


def decoding_config_provenance_artifact(
    *,
    decoding_config: DecodingConfig,
    decoding_config_path: Path,
    decoding_config_hash: str,
) -> dict[str, Any]:
    return {
        "source_path": str(decoding_config_path),
        "source_hash": decoding_config_hash,
        "config": json.loads(decoding_config.model_dump_json()),
    }


def generated_decoding_config_provenance_artifact(
    decoding_config: DecodingConfig,
) -> dict[str, Any]:
    return {
        "source_path": None,
        "source_hash": None,
        "config": json.loads(decoding_config.model_dump_json()),
    }


def _run_root(workspace_parent: Path | None, run_id: str) -> Path:
    if workspace_parent is None:
        return Path(tempfile.mkdtemp(prefix=f"agentenv-{run_id}-")).resolve()

    workspace_parent.mkdir(parents=True, exist_ok=True)
    return workspace_parent.resolve()


def _result(
    *,
    run_id: str,
    task_id: str,
    task_manifest_path: Path,
    status: AgentTaskRunStatus,
    prompt_loop_status: PromptLoopStatus | None,
    candidate_patch_path: Path | None,
    candidate_patch_hash: str | None,
    attempt_result: AttemptResult | None,
    error_class: str | None,
    error_message: str | None,
    started_at: str,
    started_timer: float,
) -> AgentTaskRunResult:
    return AgentTaskRunResult(
        run_id=run_id,
        task_id=task_id,
        task_manifest_path=str(task_manifest_path),
        status=status,
        prompt_loop_status=prompt_loop_status,
        candidate_patch_path=(
            str(candidate_patch_path) if candidate_patch_path is not None else None
        ),
        candidate_patch_hash=candidate_patch_hash,
        attempt_result=attempt_result,
        error_class=error_class,
        error_message=error_message,
        started_at=started_at,
        ended_at=_utc_now(),
        duration_ms=int((perf_counter() - started_timer) * 1000),
        orchestrator_version=AGENT_RUN_ORCHESTRATOR_VERSION,
    )


def _exception_details(exc: Exception) -> AgentTaskRunErrorDetails:
    return AgentTaskRunErrorDetails(
        error_class=type(exc).__name__,
        message=str(exc),
        traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )


def _error_text(agent_task_run: AgentTaskRun) -> str:
    if agent_task_run.error_details is None:
        return ""

    return (
        f"Error class: {agent_task_run.error_details.error_class}\n"
        f"Message: {agent_task_run.error_details.message}\n"
        "\n"
        "Traceback:\n"
        f"{agent_task_run.error_details.traceback}"
    )


def _run_manifest_json(
    agent_task_run: AgentTaskRun,
    *,
    include_decoding_config: bool,
    include_model_config: bool,
    include_agent_control_script: bool,
) -> str:
    artifacts: dict[str, str] = {
        "agent_task_run": "agent_task_run.json",
        "error": "error.txt",
    }
    if include_decoding_config:
        artifacts["decoding_config"] = "decoding_config.json"
    if include_model_config:
        artifacts["model_config"] = "model_config.json"
    if include_agent_control_script:
        artifacts["agent_control_script"] = "agent_control_script.json"
    if agent_task_run.agent_task_view is not None:
        artifacts["agent_task_view"] = "agent_task_view.json"
    if agent_task_run.prompt_loop_result is not None:
        artifacts["prompt_loop_result"] = "prompt_loop_result.json"
    if agent_task_run.result.candidate_patch_hash is not None:
        artifacts["candidate_patch"] = "candidate.patch"
    if agent_task_run.attempt_run is not None:
        artifacts["attempt"] = "attempt/"

    return (
        AgentTaskRunManifest(
            artifact_version="agent_task_run_artifacts_v0",
            orchestrator_version=agent_task_run.result.orchestrator_version,
            run_id=agent_task_run.result.run_id,
            task_id=agent_task_run.result.task_id,
            task_manifest_path=agent_task_run.result.task_manifest_path,
            status=agent_task_run.result.status,
            prompt_loop_status=agent_task_run.result.prompt_loop_status,
            attempt_status=_attempt_status(agent_task_run.result.attempt_result),
            artifacts=artifacts,
        ).model_dump_json(indent=2)
        + "\n"
    )


class AgentTaskRunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_version: str = Field(min_length=1)
    orchestrator_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus | None
    attempt_status: AttemptStatus | None
    artifacts: dict[str, str]


def _attempt_status(attempt_result: AttemptResult | None) -> AttemptStatus | None:
    if attempt_result is None:
        return None
    return attempt_result.status


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
