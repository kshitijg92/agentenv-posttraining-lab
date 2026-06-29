import sys
from pathlib import Path

import pytest

from agentenv.runners.command_runner import run_process, run_shell
from agentenv.security.secrets import REDACTED_SECRET


CANARY = "agentenv-canary-secret-000000000000"


def test_run_process_scrubs_sensitive_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HF_TOKEN", CANARY)

    result = run_process(
        [
            sys.executable,
            "-c",
            'import os; print(os.getenv("HF_TOKEN", "missing"))',
        ],
        tmp_path,
        timeout_seconds=5,
    )

    assert result.stdout == "missing\n"
    assert CANARY not in result.stdout


def test_run_shell_redacts_sensitive_command_and_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", CANARY)
    command = f"{sys.executable} -c 'print(\"{CANARY}\")'"

    result = run_shell(command, tmp_path, timeout_seconds=5)

    assert result.command == [f"{sys.executable} -c 'print(\"{REDACTED_SECRET}\")'"]
    assert result.stdout == f"{REDACTED_SECRET}\n"
    assert CANARY not in result.stdout
