import json
import tempfile
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from agentenv.agents.loop import PrivateReferenceGuard
from agentenv.agents.loop import run_prompt_loop
from agentenv.agents.schema import AgentTaskView, PromptLoopResult, PromptLoopStatus
from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.manifests import (
    AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    AGENT_ATTEMPT_ARTIFACT_REFS,
    AgentTaskRunManifest,
)
from agentenv.artifacts.payloads import (
    DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION,
    MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION,
    DecodingConfigProvenance,
    ModelConfigProvenance,
)
from agentenv.controls.agent_control_scripts import AgentControlScriptCase
from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.ids import new_agent_attempt_id
from agentenv.models.client import ModelClient
from agentenv.models.config_schema import ModelConfig
from agentenv.models.schema import DecodingConfig
from agentenv.orchestrators.agent_task_schema import (
    AgentTaskRunResult,
    AgentTaskRunStatus,
)
from agentenv.orchestrators.attempt import (
    AttemptResult,
    AttemptRun,
    AttemptStatus,
    run_patch_attempt,
)
from agentenv.orchestrators.attempt_io import AttemptArtifactPaths
from agentenv.orchestrators.attempt_io import write_attempt_artifacts
from agentenv.runners.diff_runner import hash_diff, render_directory_diff
from agentenv.security.secrets import redact_jsonable, redact_secrets
from agentenv.tasks.validate import load_task_manifest


AGENT_TASK_RUN_ORCHESTRATOR_VERSION = "agent_task_run_orchestrator_v0"


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
    manifest_json: Path
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
    agent_attempt_id = new_agent_attempt_id()
    started_at = _utc_now()
    started_timer = perf_counter()
    run_root = _run_root(workspace_parent, agent_attempt_id)

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
            private_reference_guard=PrivateReferenceGuard.from_task_manifest(manifest),
        )

        if prompt_loop_result.status != "completed":
            run_status: AgentTaskRunStatus = (
                "orchestrator_error"
                if prompt_loop_result.status == "orchestrator_error"
                else "agent_loop_failed"
            )
            return AgentTaskRun(
                result=_result(
                    agent_attempt_id=agent_attempt_id,
                    task_id=manifest.id,
                    task_manifest_path=task_manifest_path,
                    status=run_status,
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
        candidate_patch_path = run_root / AGENT_ATTEMPT_ARTIFACT_REFS["candidate_patch"]
        candidate_patch_path.write_text(candidate_patch)
        attempt_run = run_patch_attempt(
            task_manifest_path,
            candidate_patch_path,
            workspace_parent=run_root / "scoring_workspace",
        )

        return AgentTaskRun(
            result=_result(
                agent_attempt_id=agent_attempt_id,
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
            agent_task_view.task_id if agent_task_view is not None else "unknown_task"
        )
        return AgentTaskRun(
            result=_result(
                agent_attempt_id=agent_attempt_id,
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
    agent_control_script: AgentControlScriptCase | dict[str, Any] | None = None,
    model_config_provenance: ModelConfigProvenance | dict[str, Any] | None = None,
    decoding_config_provenance: DecodingConfigProvenance | dict[str, Any] | None = None,
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
    agent_control_script: AgentControlScriptCase | dict[str, Any] | None = None,
    model_config_provenance: ModelConfigProvenance | dict[str, Any] | None = None,
    decoding_config_provenance: DecodingConfigProvenance | dict[str, Any] | None = None,
) -> AgentTaskRunArtifactPaths:
    out_dir = prepare_artifact_output_dir(out_dir)
    validated_agent_control_script = _validated_agent_control_script_artifact(
        agent_control_script
    )
    validated_model_config_provenance = _validated_model_config_provenance_artifact(
        model_config_provenance
    )
    validated_decoding_config_provenance = (
        _validated_decoding_config_provenance_artifact(
            decoding_config_provenance
            if decoding_config_provenance is not None
            else (
                generated_decoding_config_provenance_artifact(decoding_config)
                if decoding_config is not None
                else None
            )
        )
    )
    manifest_path = out_dir / MANIFEST_FILENAME
    agent_task_run_path = out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["agent_task_run"]
    decoding_config_path = (
        out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["decoding_config"]
        if validated_decoding_config_provenance is not None
        else None
    )
    model_config_path = (
        out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["model_config"]
        if validated_model_config_provenance is not None
        else None
    )
    agent_control_script_path = (
        out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["agent_control_script"]
        if validated_agent_control_script is not None
        else None
    )
    agent_task_view_path = (
        out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["agent_task_view"]
        if agent_task_run.agent_task_view is not None
        else None
    )
    prompt_loop_result_path = (
        out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["prompt_loop_result"]
        if agent_task_run.prompt_loop_result is not None
        else None
    )
    candidate_patch_path = (
        out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["candidate_patch"]
        if agent_task_run.result.candidate_patch_hash is not None
        else None
    )
    error_path = out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["error"]
    attempt_dir = (
        out_dir / AGENT_ATTEMPT_ARTIFACT_REFS["attempt"]
        if agent_task_run.attempt_run is not None
        else None
    )

    agent_task_run_path.write_text(_redacted_model_json(agent_task_run.result))
    if (
        decoding_config_path is not None
        and validated_decoding_config_provenance is not None
    ):
        decoding_config_path.write_text(
            _redacted_model_json(validated_decoding_config_provenance)
        )
    if model_config_path is not None and validated_model_config_provenance is not None:
        model_config_path.write_text(
            _redacted_model_json(validated_model_config_provenance)
        )
    if (
        agent_control_script_path is not None
        and validated_agent_control_script is not None
    ):
        agent_control_script_path.write_text(
            _redacted_model_json(validated_agent_control_script)
        )
    agent_task_view = agent_task_run.agent_task_view
    if agent_task_view_path is not None and agent_task_view is not None:
        agent_task_view_path.write_text(_redacted_model_json(agent_task_view))
    prompt_loop_result = agent_task_run.prompt_loop_result
    if prompt_loop_result_path is not None and prompt_loop_result is not None:
        prompt_loop_result_path.write_text(_redacted_model_json(prompt_loop_result))
    if candidate_patch_path is not None:
        candidate_patch_path.write_text(agent_task_run.candidate_patch)
    error_path.write_text(redact_secrets(_error_text(agent_task_run)))

    attempt_artifacts = (
        write_attempt_artifacts(agent_task_run.attempt_run, attempt_dir)
        if agent_task_run.attempt_run is not None and attempt_dir is not None
        else None
    )
    manifest_path.write_text(
        _manifest_json(
            agent_task_run,
            include_decoding_config=validated_decoding_config_provenance is not None,
            include_model_config=validated_model_config_provenance is not None,
            include_agent_control_script=validated_agent_control_script is not None,
        )
    )

    return AgentTaskRunArtifactPaths(
        manifest_json=manifest_path,
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
        return _redacted_model_json(value)
    return json.dumps(redact_jsonable(value), indent=2, sort_keys=True) + "\n"


def _validated_agent_control_script_artifact(
    value: AgentControlScriptCase | dict[str, Any] | None,
) -> AgentControlScriptCase | None:
    if value is None:
        return None
    return AgentControlScriptCase.model_validate(_jsonable_payload(value))


def _validated_model_config_provenance_artifact(
    value: ModelConfigProvenance | dict[str, Any] | None,
) -> ModelConfigProvenance | None:
    if value is None:
        return None
    return ModelConfigProvenance.model_validate(value)


def _validated_decoding_config_provenance_artifact(
    value: DecodingConfigProvenance | dict[str, Any] | None,
) -> DecodingConfigProvenance | None:
    if value is None:
        return None
    return DecodingConfigProvenance.model_validate(value)


def _jsonable_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _redacted_model_json(value: BaseModel) -> str:
    return json.dumps(redact_jsonable(value.model_dump(mode="json")), indent=2) + "\n"


def model_config_provenance_artifact(
    *,
    model_config: ModelConfig,
    model_config_path: Path,
    model_config_hash: str,
) -> ModelConfigProvenance:
    return ModelConfigProvenance.model_validate(
        {
            "schema_version": MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION,
            "source_path": str(model_config_path),
            "source_hash": model_config_hash,
            "config": redact_jsonable(json.loads(model_config.model_dump_json())),
        }
    )


def decoding_config_provenance_artifact(
    *,
    decoding_config: DecodingConfig,
    decoding_config_path: Path,
    decoding_config_hash: str,
) -> DecodingConfigProvenance:
    return DecodingConfigProvenance.model_validate(
        {
            "schema_version": DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION,
            "source_path": str(decoding_config_path),
            "source_hash": decoding_config_hash,
            "config": redact_jsonable(json.loads(decoding_config.model_dump_json())),
        }
    )


def generated_decoding_config_provenance_artifact(
    decoding_config: DecodingConfig,
) -> DecodingConfigProvenance:
    return DecodingConfigProvenance.model_validate(
        {
            "schema_version": DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION,
            "source_path": None,
            "source_hash": None,
            "config": redact_jsonable(json.loads(decoding_config.model_dump_json())),
        }
    )


def _run_root(workspace_parent: Path | None, agent_attempt_id: str) -> Path:
    if workspace_parent is None:
        return Path(tempfile.mkdtemp(prefix=f"agentenv-{agent_attempt_id}-")).resolve()

    workspace_parent.mkdir(parents=True, exist_ok=True)
    return workspace_parent.resolve()


def _result(
    *,
    agent_attempt_id: str,
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
        agent_attempt_id=agent_attempt_id,
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
        orchestrator_version=AGENT_TASK_RUN_ORCHESTRATOR_VERSION,
    )


def _exception_details(exc: Exception) -> AgentTaskRunErrorDetails:
    return AgentTaskRunErrorDetails(
        error_class=type(exc).__name__,
        message=str(exc),
        traceback="".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
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


def _manifest_json(
    agent_task_run: AgentTaskRun,
    *,
    include_decoding_config: bool,
    include_model_config: bool,
    include_agent_control_script: bool,
) -> str:
    artifacts: dict[str, str] = {
        "agent_task_run": AGENT_ATTEMPT_ARTIFACT_REFS["agent_task_run"],
        "error": AGENT_ATTEMPT_ARTIFACT_REFS["error"],
    }
    if include_decoding_config:
        artifacts["decoding_config"] = AGENT_ATTEMPT_ARTIFACT_REFS["decoding_config"]
    if include_model_config:
        artifacts["model_config"] = AGENT_ATTEMPT_ARTIFACT_REFS["model_config"]
    if include_agent_control_script:
        artifacts["agent_control_script"] = AGENT_ATTEMPT_ARTIFACT_REFS[
            "agent_control_script"
        ]
    if agent_task_run.agent_task_view is not None:
        artifacts["agent_task_view"] = AGENT_ATTEMPT_ARTIFACT_REFS["agent_task_view"]
    if agent_task_run.prompt_loop_result is not None:
        artifacts["prompt_loop_result"] = AGENT_ATTEMPT_ARTIFACT_REFS[
            "prompt_loop_result"
        ]
    if agent_task_run.result.candidate_patch_hash is not None:
        artifacts["candidate_patch"] = AGENT_ATTEMPT_ARTIFACT_REFS["candidate_patch"]
    if agent_task_run.attempt_run is not None:
        artifacts["attempt"] = AGENT_ATTEMPT_ARTIFACT_REFS["attempt"]

    manifest = AgentTaskRunManifest(
        artifact_type=ArtifactType.AGENT_ATTEMPT,
        artifact_schema_version=AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        orchestrator_version=agent_task_run.result.orchestrator_version,
        agent_attempt_id=agent_task_run.result.agent_attempt_id,
        task_id=agent_task_run.result.task_id,
        task_manifest_path=agent_task_run.result.task_manifest_path,
        status=agent_task_run.result.status,
        prompt_loop_status=agent_task_run.result.prompt_loop_status,
        attempt_status=_attempt_status(agent_task_run.result.attempt_result),
        artifacts=artifacts,
    )
    return _redacted_model_json(manifest)


def _attempt_status(attempt_result: AttemptResult | None) -> AttemptStatus | None:
    if attempt_result is None:
        return None
    return attempt_result.status


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
