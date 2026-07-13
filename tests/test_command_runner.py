import shlex
import subprocess
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


def test_run_process_applies_non_sensitive_env_overrides_and_scrubs_sensitive_ones(
    tmp_path: Path,
) -> None:
    runner_temp = tmp_path / "runner-temp"
    result = run_process(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                'print(os.getenv("TMPDIR", "missing")); '
                'print(os.getenv("HF_TOKEN", "missing"))'
            ),
        ],
        tmp_path,
        timeout_seconds=5,
        env_overrides={
            "TMPDIR": str(runner_temp),
            "HF_TOKEN": CANARY,
        },
    )

    assert result.stdout == f"{runner_temp}\nmissing\n"


def test_run_shell_timeout_kills_descendant_processes(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    child_script = tmp_path / "child.py"
    child_script.write_text(
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()))\n"
        "time.sleep(30)\n"
    )
    parent_script = tmp_path / "parent.py"
    parent_script.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n"
        "time.sleep(30)\n"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        run_shell(
            shlex.join(
                [
                    sys.executable,
                    str(parent_script),
                    str(child_script),
                    str(child_pid_path),
                ]
            ),
            tmp_path,
            timeout_seconds=1,
        )

    child_pid = int(child_pid_path.read_text())
    child_stat_path = Path(f"/proc/{child_pid}/stat")
    if child_stat_path.exists():
        assert child_stat_path.read_text().split()[2] == "Z"
