import os
import signal
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
    completed = _run_in_process_group(
        command,
        cwd=cwd,
        env=_subprocess_env(env_overrides),
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
    completed = _run_in_process_group(
        command,
        cwd=cwd,
        env=_subprocess_env(env_overrides),
        shell=True,
        timeout=timeout_seconds,
    )
    return CommandResult(
        command=[redact_secrets(command)],
        returncode=completed.returncode,
        stdout=redact_secrets(completed.stdout),
        stderr=redact_secrets(completed.stderr),
    )


def _run_in_process_group(
    command: list[str] | str,
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    shell: bool = False,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        shell=shell,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_process_group(process)
        stdout, stderr = process.communicate()
        redacted_command: list[str] | str
        if isinstance(command, str):
            redacted_command = redact_secrets(command)
        else:
            redacted_command = [redact_secrets(part) for part in command]
        raise subprocess.TimeoutExpired(
            cmd=redacted_command,
            timeout=timeout,
            output=redact_secrets(stdout),
            stderr=redact_secrets(stderr),
        ) from exc
    return subprocess.CompletedProcess(
        args=command,
        returncode=process.wait(),
        stdout=stdout,
        stderr=stderr,
    )


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        if process.poll() is None:
            process.kill()


def _subprocess_env(env_overrides: Mapping[str, str] | None) -> dict[str, str]:
    env = dict(os.environ)
    if env_overrides is not None:
        env.update(env_overrides)
    return scrubbed_subprocess_env(env)
