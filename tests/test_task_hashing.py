import json
from pathlib import Path
import shutil
from typing import Any

from typer.testing import CliRunner

from agentenv.cli import app
from agentenv.tasks.hashing import build_eval_task_hashes, build_task_hash_report


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")


def test_task_hash_report_contains_pack_and_task_hashes() -> None:
    report = build_task_hash_report(TASK_PACK).payload.model_dump(mode="json")

    assert report["schema_version"] == "task_hash_report_v0"
    assert report["task_pack_id"] == "repo_patch_python_v0"
    assert report["task_count"] == 14
    assert report["manifest_yaml_hash"].startswith("xxh64:")
    assert report["splits_lock_hash"].startswith("xxh64:")
    assert report["pack_record_hash"].startswith("xxh64:")

    task = _task_record(report, "toy_python_fix_001")
    assert task["split"] == "practice"
    assert task["task_yaml_hash"].startswith("xxh64:")
    assert task["instruction_normalized_hash"].startswith("xxh64:")
    assert task["visible_tests_normalized_hash"].startswith("xxh64:")
    assert task["required_task_files_hash"].startswith("xxh64:")
    assert task["full_task_dir_hash"].startswith("xxh64:")
    assert task["task_record_hash"].startswith("xxh64:")
    assert task["extra_task_files"] == []
    assert {record["path"] for record in task["required_task_files"]} >= {
        "task.yaml",
        "seed_workspace",
        "hidden_tests",
    }


def test_task_hash_report_is_stable_for_unchanged_task_pack() -> None:
    first = build_task_hash_report(TASK_PACK).payload.model_dump(mode="json")
    second = build_task_hash_report(TASK_PACK).payload.model_dump(mode="json")

    assert first["pack_record_hash"] == second["pack_record_hash"]
    first_tasks = {task["task_id"]: task["task_record_hash"] for task in first["tasks"]}
    second_tasks = {
        task["task_id"]: task["task_record_hash"] for task in second["tasks"]
    }
    assert first_tasks == second_tasks


def test_required_task_file_change_updates_task_hash(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    before = build_task_hash_report(task_pack).payload.model_dump(mode="json")

    task_card = task_pack / "tasks/toy_python_fix/task_card.md"
    task_card.write_text(task_card.read_text() + "\nAdditional note.\n")
    after = build_task_hash_report(task_pack).payload.model_dump(mode="json")

    before_task = _task_record(before, "toy_python_fix_001")
    after_task = _task_record(after, "toy_python_fix_001")
    assert (
        before_task["required_task_files_hash"]
        != (after_task["required_task_files_hash"])
    )
    assert before_task["task_record_hash"] != after_task["task_record_hash"]
    assert before["pack_record_hash"] != after["pack_record_hash"]


def test_extra_task_file_changes_full_task_dir_hash_only(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    before = build_task_hash_report(task_pack).payload.model_dump(mode="json")

    extra_file = task_pack / "tasks/toy_python_fix/notes.txt"
    extra_file.write_text("extra task-local note\n")
    after = build_task_hash_report(task_pack).payload.model_dump(mode="json")

    before_task = _task_record(before, "toy_python_fix_001")
    after_task = _task_record(after, "toy_python_fix_001")
    assert after_task["extra_task_files"] == ["notes.txt"]
    assert (
        before_task["required_task_files_hash"]
        == (after_task["required_task_files_hash"])
    )
    assert before_task["full_task_dir_hash"] != after_task["full_task_dir_hash"]
    assert before_task["task_record_hash"] != after_task["task_record_hash"]


def test_noisy_cache_files_do_not_change_task_hash(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    before = build_task_hash_report(task_pack).payload.model_dump(mode="json")

    cache_dir = task_pack / "tasks/toy_python_fix/seed_workspace/__pycache__"
    cache_dir.mkdir()
    (cache_dir / "generated.pyc").write_bytes(b"cache bytes")
    after = build_task_hash_report(task_pack).payload.model_dump(mode="json")

    assert (
        _task_record(before, "toy_python_fix_001")["task_record_hash"]
        == (_task_record(after, "toy_python_fix_001")["task_record_hash"])
    )


def test_eval_task_hash_set_ignores_unused_task(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    before = build_eval_task_hashes(task_pack, ["toy_python_fix_001"]).model_dump(
        mode="json"
    )

    unused_task = task_pack / "tasks/unused_toy_copy"
    shutil.copytree(task_pack / "tasks/toy_python_fix", unused_task)
    manifest_path = unused_task / "task.yaml"
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "id: toy_python_fix_001",
            "id: unused_toy_copy",
        )
    )
    after = build_eval_task_hashes(task_pack, ["toy_python_fix_001"]).model_dump(
        mode="json"
    )

    assert before["selected_task_hash_set"] == after["selected_task_hash_set"]
    assert before["selected_tasks"] == after["selected_tasks"]


def test_eval_task_hashes_include_required_task_file_records() -> None:
    task_hashes = build_eval_task_hashes(TASK_PACK, ["toy_python_fix_001"]).model_dump(
        mode="json"
    )

    selected_task = task_hashes["selected_tasks"][0]
    assert selected_task["task_id"] == "toy_python_fix_001"
    assert selected_task["required_task_files_hash"].startswith("xxh64:")
    assert selected_task["full_task_dir_hash"].startswith("xxh64:")
    assert {record["path"] for record in selected_task["required_task_files"]} >= {
        "task.yaml",
        "seed_workspace",
        "hidden_tests",
    }


def test_eval_task_hash_set_changes_when_selected_task_changes(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    before = build_eval_task_hashes(task_pack, ["toy_python_fix_001"]).model_dump(
        mode="json"
    )

    task_card = task_pack / "tasks/toy_python_fix/task_card.md"
    task_card.write_text(task_card.read_text() + "\nSelected task changed.\n")
    after = build_eval_task_hashes(task_pack, ["toy_python_fix_001"]).model_dump(
        mode="json"
    )

    assert before["selected_task_hash_set"] != after["selected_task_hash_set"]


def test_task_hash_cli_writes_report(tmp_path: Path) -> None:
    out_path = tmp_path / "task_hashes.json"

    result = CliRunner().invoke(
        app,
        [
            "tasks",
            "hash",
            "data/task_packs/repo_patch_python_v0",
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "hashed repo_patch_python_v0 tasks=14" in result.output
    assert out_path.is_file()
    report = json.loads(out_path.read_text())
    assert report["schema_version"] == "task_hash_report_v0"
    assert report["pack_record_hash"].startswith("xxh64:")


def _task_record(report: dict[str, Any], task_id: str) -> dict[str, Any]:
    tasks = report["tasks"]
    assert isinstance(tasks, list)
    for task in tasks:
        assert isinstance(task, dict)
        if task["task_id"] == task_id:
            return task
    raise AssertionError(f"task not found: {task_id}")


def _copy_task_pack(tmp_path: Path) -> Path:
    task_pack = tmp_path / "repo_patch_python_v0"
    shutil.copytree(TASK_PACK, task_pack)
    return task_pack
