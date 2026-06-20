from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from subprocess import TimeoutExpired
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.runners.command_runner import CommandResult
from agentenv.runners.diff_runner import hash_diff, render_directory_diff
from agentenv.runners.patch_runner import apply_patch_file
from agentenv.runners.public_check_runner import run_public_checks
from agentenv.scorers.pytest_hidden import run_hidden_pytest_validators
from agentenv.tasks.validate import load_task_manifest


ORCHESTRATOR_VERSION = "attempt_v0"

AttemptStatus = Literal[
    "PASS",
    "PATCH_APPLY_ERROR",
    "PUBLIC_TEST_FAIL",
    "HIDDEN_TEST_FAIL",
    "ORCHESTRATOR_ERROR",
    "SCORER_ERROR",
    "TIMEOUT",
]

CheckStatus = Literal["PASS", "FAIL", "NOT_RUN"]
CommandPhase = Literal["patch_apply", "public_check", "hidden_score"]


class AttemptResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    submission_path: str = Field(min_length=1)
    status: AttemptStatus
    public_status: CheckStatus
    hidden_status: CheckStatus
    error_class: str | None
    started_at: str = Field(min_length=1)
    ended_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    final_diff_hash: str | None
    orchestrator_version: str = Field(min_length=1)


@dataclass(frozen=True)
class AttemptCommand:
    phase: CommandPhase
    name: str
    result: CommandResult


@dataclass(frozen=True)
class AttemptRun:
    result: AttemptResult
    commands: list[AttemptCommand]
    final_diff: str

    @property
    def command_results(self) -> list[CommandResult]:
        return [command.result for command in self.commands]


@dataclass(frozen=True)
class AttemptContext:
    run_id: str
    task_id: str
    task_manifest_path: Path
    attempt_id: str
    submission_path: Path
    started_at: str
    started_timer: float


def run_patch_attempt(
    task_manifest_path: Path,
    submission_path: Path,
    workspace_parent: Path | None = None,
) -> AttemptRun:
    task_manifest_path = task_manifest_path.resolve()
    submission_path = submission_path.resolve()
    started_at = _utc_now()
    started_timer = perf_counter()
    manifest = load_task_manifest(task_manifest_path)
    context = AttemptContext(
        run_id=f"run_{uuid4().hex}",
        task_id=manifest.id,
        task_manifest_path=task_manifest_path,
        attempt_id=f"attempt_{uuid4().hex}",
        submission_path=submission_path,
        started_at=started_at,
        started_timer=started_timer,
    )
    commands: list[AttemptCommand] = []
    final_diff = ""
    final_diff_hash: str | None = None

    try:
        workspace = prepare_agent_workspace(
            manifest,
            task_manifest_path,
            workspace_parent=workspace_parent,
        )

        patch_result = apply_patch_file(
            workspace.path,
            submission_path,
            timeout_seconds=manifest.limits.timeout_seconds,
        )
        commands.append(
            AttemptCommand(
                phase="patch_apply",
                name="submission_patch",
                result=patch_result,
            )
        )
        final_diff = render_directory_diff(
            workspace.task_dir / manifest.workspace_seed,
            workspace.path,
        )
        final_diff_hash = hash_diff(final_diff)
        if patch_result.returncode != 0:
            return _finish_attempt(
                context=context,
                commands=commands,
                final_diff=final_diff,
                status="PATCH_APPLY_ERROR",
                public_status="NOT_RUN",
                hidden_status="NOT_RUN",
                error_class="PatchApplyError",
                final_diff_hash=final_diff_hash,
            )

        public_results = run_public_checks(
            workspace.path,
            manifest.public_checks,
            timeout_seconds=manifest.limits.timeout_seconds,
        )
        commands.extend(
            AttemptCommand(
                phase="public_check",
                name=f"public_check_{index}",
                result=public_result,
            )
            for index, public_result in enumerate(public_results)
        )
        if not all(result.returncode == 0 for result in public_results):
            return _finish_attempt(
                context=context,
                commands=commands,
                final_diff=final_diff,
                status="PUBLIC_TEST_FAIL",
                public_status="FAIL",
                hidden_status="NOT_RUN",
                error_class="PublicCheckFailed",
                final_diff_hash=final_diff_hash,
            )

        hidden_results = run_hidden_pytest_validators(
            workspace.path,
            workspace.task_dir,
            manifest.hidden_validators,
            timeout_seconds=manifest.limits.timeout_seconds,
        )
        commands.extend(
            AttemptCommand(
                phase="hidden_score",
                name=hidden_result.validator_id,
                result=hidden_result.command_result,
            )
            for hidden_result in hidden_results
        )
        if not all(result.passed for result in hidden_results):
            return _finish_attempt(
                context=context,
                commands=commands,
                final_diff=final_diff,
                status="HIDDEN_TEST_FAIL",
                public_status="PASS",
                hidden_status="FAIL",
                error_class="HiddenCheckFailed",
                final_diff_hash=final_diff_hash,
            )

        return _finish_attempt(
            context=context,
            commands=commands,
            final_diff=final_diff,
            status="PASS",
            public_status="PASS",
            hidden_status="PASS",
            error_class=None,
            final_diff_hash=final_diff_hash,
        )
    except TimeoutExpired:
        return _finish_attempt(
            context=context,
            commands=commands,
            final_diff=final_diff,
            status="TIMEOUT",
            public_status="NOT_RUN",
            hidden_status="NOT_RUN",
            error_class="TimeoutExpired",
            final_diff_hash=final_diff_hash,
        )


def _finish_attempt(
    *,
    context: AttemptContext,
    commands: list[AttemptCommand],
    final_diff: str,
    status: AttemptStatus,
    public_status: CheckStatus,
    hidden_status: CheckStatus,
    error_class: str | None,
    final_diff_hash: str | None,
) -> AttemptRun:
    ended_at = _utc_now()
    duration_ms = int((perf_counter() - context.started_timer) * 1000)
    result = AttemptResult(
        run_id=context.run_id,
        task_id=context.task_id,
        task_manifest_path=str(context.task_manifest_path),
        attempt_id=context.attempt_id,
        submission_path=str(context.submission_path),
        status=status,
        public_status=public_status,
        hidden_status=hidden_status,
        error_class=error_class,
        started_at=context.started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        final_diff_hash=final_diff_hash,
        orchestrator_version=ORCHESTRATOR_VERSION,
    )
    return AttemptRun(result=result, commands=commands, final_diff=final_diff)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
