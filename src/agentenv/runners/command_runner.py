import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_process(
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_shell(
    command: str,
    cwd: Path,
    timeout_seconds: int,
) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        shell=True,
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(
        command=[command],
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
