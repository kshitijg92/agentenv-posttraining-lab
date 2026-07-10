import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentenv.security.secrets import redact_secrets, scrubbed_subprocess_env


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
    env_overrides: Mapping[str, str] | None = None,
) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        env=_subprocess_env(env_overrides),
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(
        command=[redact_secrets(part) for part in command],
        returncode=completed.returncode,
        stdout=redact_secrets(completed.stdout),
        stderr=redact_secrets(completed.stderr),
    )


def run_shell(
    command: str,
    cwd: Path,
    timeout_seconds: int,
    env_overrides: Mapping[str, str] | None = None,
) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        env=_subprocess_env(env_overrides),
        shell=True,
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(
        command=[redact_secrets(command)],
        returncode=completed.returncode,
        stdout=redact_secrets(completed.stdout),
        stderr=redact_secrets(completed.stderr),
    )


def _subprocess_env(env_overrides: Mapping[str, str] | None) -> dict[str, str]:
    env = dict(os.environ)
    if env_overrides is not None:
        env.update(env_overrides)
    return scrubbed_subprocess_env(env)
