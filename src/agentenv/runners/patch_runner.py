from pathlib import Path

from agentenv.runners.command_runner import CommandResult, run_process


def apply_patch_file(
    workspace: Path,
    patch_path: Path,
    timeout_seconds: int,
) -> CommandResult:
    if not patch_path.read_text().strip():
        return CommandResult(
            command=["git", "apply", str(patch_path)],
            returncode=0,
            stdout="",
            stderr="",
        )

    return run_process(
        ["git", "apply", str(patch_path)],
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
