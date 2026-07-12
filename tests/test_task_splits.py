import json
from pathlib import Path
import shutil

import pytest
from typer.testing import CliRunner

from agentenv.cli import app
from agentenv.tasks.splits import check_splits_lock


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")


def test_check_splits_lock_accepts_current_task_pack() -> None:
    result = check_splits_lock(TASK_PACK / "splits.lock.json")

    assert result.task_pack_id == "repo_patch_python_v0"
    assert result.task_count == 8
    assert result.split_counts == {
        "practice": 1,
        "dev": 7,
        "heldout_private": 0,
        "public_calibration": 0,
    }


def test_check_splits_lock_rejects_duplicate_split_assignment(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    splits_path = task_pack / "splits.lock.json"
    raw_splits = json.loads(splits_path.read_text())
    raw_splits["dev"].append("toy_python_fix_001")
    splits_path.write_text(json.dumps(raw_splits))

    with pytest.raises(ValueError, match="appears in both 'practice' and 'dev'"):
        check_splits_lock(splits_path)


def test_check_splits_lock_rejects_task_missing_from_lock(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    splits_path = task_pack / "splits.lock.json"
    raw_splits = json.loads(splits_path.read_text())
    raw_splits["dev"].remove("repair_jsonl_deduper")
    splits_path.write_text(json.dumps(raw_splits))

    with pytest.raises(
        ValueError,
        match="Task manifests missing from splits.lock.json: repair_jsonl_deduper",
    ):
        check_splits_lock(splits_path)


def test_check_splits_lock_rejects_unknown_locked_task_id(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    splits_path = task_pack / "splits.lock.json"
    raw_splits = json.loads(splits_path.read_text())
    raw_splits["heldout_private"].append("missing_task")
    splits_path.write_text(json.dumps(raw_splits))

    with pytest.raises(
        ValueError,
        match="splits.lock.json references missing task ids: missing_task",
    ):
        check_splits_lock(splits_path)


def test_check_splits_lock_rejects_manifest_split_mismatch(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    manifest_path = task_pack / "tasks/toy_python_fix/task.yaml"
    manifest_path.write_text(
        manifest_path.read_text().replace("split: practice", "split: dev")
    )

    with pytest.raises(
        ValueError,
        match=(
            "Task toy_python_fix_001 manifest split 'dev' does not match "
            "splits.lock.json split 'practice'"
        ),
    ):
        check_splits_lock(task_pack / "splits.lock.json")


def test_check_splits_cli_reports_split_counts() -> None:
    result = CliRunner().invoke(
        app,
        [
            "tasks",
            "check-splits",
            "data/task_packs/repo_patch_python_v0/splits.lock.json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "valid" in result.output
    assert "repo_patch_python_v0" in result.output
    assert "tasks=8" in result.output
    assert "practice=1" in result.output
    assert "dev=7" in result.output


def _copy_task_pack(tmp_path: Path) -> Path:
    task_pack = tmp_path / "repo_patch_python_v0"
    shutil.copytree(TASK_PACK, task_pack)
    return task_pack
