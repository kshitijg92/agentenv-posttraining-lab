import json
import os
import subprocess
import sys
from pathlib import Path


def test_missing_file_exits_with_missing_file_code(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jsonl"

    result = _run_cli(str(missing_path))

    assert result.returncode == 3
    assert "Traceback" not in result.stderr


def test_malformed_jsonl_exits_with_invalid_input_code(tmp_path: Path) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text('{"id": "r1", "status": "ok"}\n{"id":\n')

    result = _run_cli(str(input_path))

    assert result.returncode == 4
    assert "Traceback" not in result.stderr


def test_missing_required_field_exits_with_invalid_input_code(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text('{"id": "r1", "status": "ok"}\n{"id": "r2"}\n')

    result = _run_cli(str(input_path))

    assert result.returncode == 4
    assert "Traceback" not in result.stderr


def test_non_object_json_line_exits_with_invalid_input_code(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text('{"id": "r1", "status": "ok"}\n["not", "object"]\n')

    result = _run_cli(str(input_path))

    assert result.returncode == 4
    assert "Traceback" not in result.stderr


def test_non_string_field_exits_with_invalid_input_code(tmp_path: Path) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text('{"id": "r1", "status": "ok"}\n{"id": 2, "status": "ok"}\n')

    result = _run_cli(str(input_path))

    assert result.returncode == 4
    assert "Traceback" not in result.stderr


def test_duplicate_id_exits_with_invalid_input_code(tmp_path: Path) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"id": "r1", "status": "ok"}',
                '{"id": "r2", "status": "failed"}',
                '{"id": "r1", "status": "ok"}',
            ]
        )
        + "\n"
    )

    result = _run_cli(str(input_path))

    assert result.returncode == 4
    assert "Traceback" not in result.stderr


def test_usage_error_exits_with_usage_code() -> None:
    result = _run_cli()

    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_success_stdout_is_json_object(tmp_path: Path) -> None:
    input_path = tmp_path / "records.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"id": "r1", "status": "queued"}',
                '{"id": "r2", "status": "ok"}',
                '{"id": "r3", "status": "queued"}',
            ]
        )
        + "\n"
    )

    result = _run_cli(str(input_path))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"queued": 2, "ok": 1}


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
