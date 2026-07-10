import shutil
import tempfile
from pathlib import Path

from agentenv.runners.command_runner import CommandResult, run_shell
from agentenv.tasks.schema import PublicCheck


def run_public_check(
    command: str,
    workspace: Path,
    timeout_seconds: int,
    *,
    runner_temp_root: Path | None = None,
) -> CommandResult:
    workspace = workspace.resolve()
    if runner_temp_root is None:
        with tempfile.TemporaryDirectory(
            prefix="agentenv-public-check-runner-temp-"
        ) as raw_runner_temp_root:
            resolved_runner_temp_root = Path(raw_runner_temp_root).resolve()
            _validate_runner_temp_root(workspace, resolved_runner_temp_root)
            return _run_public_check_with_temp_root(
                command=command,
                workspace=workspace,
                timeout_seconds=timeout_seconds,
                runner_temp_root=resolved_runner_temp_root,
            )

    runner_temp_root = runner_temp_root.resolve()
    _validate_runner_temp_root(workspace, runner_temp_root)
    _reset_runner_temp_root(runner_temp_root)
    return _run_public_check_with_temp_root(
        command=command,
        workspace=workspace,
        timeout_seconds=timeout_seconds,
        runner_temp_root=runner_temp_root,
    )


def run_public_checks(
    workspace: Path,
    public_checks: list[PublicCheck],
    timeout_seconds: int,
) -> list[CommandResult]:
    return [
        run_public_check(check.command, workspace, timeout_seconds)
        for check in public_checks
    ]


def _run_public_check_with_temp_root(
    *,
    command: str,
    workspace: Path,
    timeout_seconds: int,
    runner_temp_root: Path,
) -> CommandResult:
    return run_shell(
        command,
        workspace,
        timeout_seconds,
        env_overrides={
            "TMPDIR": str(runner_temp_root),
            "TMP": str(runner_temp_root),
            "TEMP": str(runner_temp_root),
        },
    )


def _validate_runner_temp_root(workspace: Path, runner_temp_root: Path) -> None:
    if runner_temp_root == Path("/"):
        raise ValueError("runner_temp_root cannot be the filesystem root")
    if runner_temp_root.is_relative_to(workspace) or workspace.is_relative_to(
        runner_temp_root
    ):
        raise ValueError("runner_temp_root must not overlap the workspace")


def _reset_runner_temp_root(runner_temp_root: Path) -> None:
    if runner_temp_root.exists():
        shutil.rmtree(runner_temp_root)
    runner_temp_root.mkdir(parents=True)
