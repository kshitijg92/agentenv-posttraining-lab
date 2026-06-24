from pathlib import Path
import shutil

import pytest

from agentenv.tasks.validate import (
    load_task_manifest,
    validate_task_manifest_paths,
    validate_task_pack,
)


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TASK_PACK = Path("data/task_packs/repo_patch_python_v0")


def test_toy_python_fix_manifest_loads() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    assert manifest.id == "toy_python_fix_001"
    assert manifest.domain == "repo_patch_python"
    assert manifest.split == "practice"
    assert manifest.controls.bad.noop == "controls/bad_noop.patch"
    assert manifest.controls.bad.public_only == "controls/bad_public_only.patch"


def test_toy_python_fix_manifest_paths_are_valid() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    validate_task_manifest_paths(manifest, TOY_TASK_MANIFEST)


def test_repo_patch_python_task_pack_validates() -> None:
    result = validate_task_pack(TASK_PACK)

    assert result.task_pack_id == "repo_patch_python_v0"
    assert result.task_count == 4


def test_task_pack_validation_rejects_missing_required_file(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    (task_pack / "tasks/toy_python_fix/task_card.md").unlink()

    with pytest.raises(ValueError, match="required task file task_card.md"):
        validate_task_pack(task_pack)


def test_task_pack_validation_rejects_workspace_private_marker(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    source_file = task_pack / "tasks/toy_python_fix/workspace_seed/src/mathlib.py"
    source_file.write_text(source_file.read_text() + "\n# hidden_tests\n")

    with pytest.raises(ValueError, match="Private task marker 'hidden_tests'"):
        validate_task_pack(task_pack)


def test_task_pack_validation_rejects_split_mismatch(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    splits_lock = task_pack / "splits.lock.json"
    splits_lock.write_text(
        splits_lock.read_text().replace('"toy_python_fix_001"', '"missing_task"')
    )

    with pytest.raises(ValueError, match="missing from splits.lock.json"):
        validate_task_pack(task_pack)


def test_task_pack_validation_rejects_hidden_public_duplicate(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    public_test = task_pack / "tasks/toy_python_fix/workspace_seed/tests/test_public.py"
    hidden_test = task_pack / "tasks/toy_python_fix/hidden_tests/test_behavior.py"
    hidden_test.write_text(public_test.read_text())

    with pytest.raises(ValueError, match="duplicates public test"):
        validate_task_pack(task_pack)


def _copy_task_pack(tmp_path: Path) -> Path:
    task_pack = tmp_path / "repo_patch_python_v0"
    shutil.copytree(TASK_PACK, task_pack)
    return task_pack
