import json
import os
import subprocess
import sys
from pathlib import Path


def test_valid_file_prints_status_counts(tmp_path: Path) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"id": "r1", "status": "ok"}',
                '{"id": "r2", "status": "failed"}',
                '{"id": "r3", "status": "ok"}',
            ]
        )
        + "\n"
    )

    result = _run_cli(str(input_path))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"ok": 2, "failed": 1}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return subprocess.run(
        [sys.executable, "-m", "validate_records", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
