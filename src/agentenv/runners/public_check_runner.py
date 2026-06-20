from pathlib import Path

from agentenv.runners.command_runner import CommandResult, run_shell
from agentenv.tasks.schema import PublicCheck


def run_public_checks(
    workspace: Path,
    public_checks: list[PublicCheck],
    timeout_seconds: int,
) -> list[CommandResult]:
    return [
        run_shell(check.command, workspace, timeout_seconds)
        for check in public_checks
    ]
