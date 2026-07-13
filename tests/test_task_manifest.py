import json
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
    assert manifest.allowed_tools == [
        "list_files",
        "read_file",
        "write_file",
        "run_tests",
    ]
    assert len(manifest.public_checks) == 1
    assert manifest.public_checks[0].are_tests_idempotent is True
    assert manifest.controls.scorer_control_patches.bad.noop == (
        "controls/scorer_control_patches/bad_noop.patch"
    )
    assert manifest.controls.scorer_control_patches.bad.public_only == (
        "controls/scorer_control_patches/bad_public_only.patch"
    )
    assert manifest.controls.agent_control_scripts.happy == (
        "controls/agent_control_scripts/happy_path.json"
    )
    assert manifest.controls.agent_control_scripts.malformed == (
        "controls/agent_control_scripts/malformed_json.json"
    )
    assert manifest.controls.agent_control_scripts.recoverable == (
        "controls/agent_control_scripts/bad_tool_input_then_recovery.json"
    )


def test_toy_python_fix_manifest_paths_are_valid() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    validate_task_manifest_paths(manifest, TOY_TASK_MANIFEST)


def test_repo_patch_python_task_pack_validates() -> None:
    result = validate_task_pack(TASK_PACK)

    assert result.task_pack_id == "repo_patch_python_v0"
    assert result.task_count == 20


def test_task_pack_validation_rejects_missing_required_file(tmp_path: Path) -> None:
    task_pack = _copy_task_pack(tmp_path)
    (task_pack / "tasks/toy_python_fix/task_card.md").unlink()

    with pytest.raises(ValueError, match="required task file task_card.md"):
        validate_task_pack(task_pack)


def test_task_pack_validation_rejects_workspace_private_marker(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    source_file = task_pack / "tasks/toy_python_fix/seed_workspace/src/mathlib.py"
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


def test_task_pack_validation_rejects_duplicate_leakage_canary(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    manifest_path = task_pack / "tasks/repair_jsonl_deduper/task.yaml"
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "CANARY_REPAIR_JSONL_DEDUPER_PRIVATE",
            "CANARY_TOY_PY_FIX_001_PRIVATE",
        )
    )

    with pytest.raises(ValueError, match="Duplicate leakage_canary"):
        validate_task_pack(task_pack)


def test_task_pack_validation_rejects_hidden_public_duplicate(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    public_test = task_pack / "tasks/toy_python_fix/seed_workspace/tests/test_public.py"
    hidden_test = task_pack / "tasks/toy_python_fix/hidden_tests/test_behavior.py"
    hidden_test.write_text(public_test.read_text())

    with pytest.raises(ValueError, match="duplicates public test"):
        validate_task_pack(task_pack)


def test_task_pack_validation_rejects_legacy_allowed_tools(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    manifest_path = task_pack / "tasks/toy_python_fix/task.yaml"
    manifest_path.write_text(
        manifest_path.read_text().replace(
            'allowed_tools: ["list_files", "read_file", "write_file", "run_tests"]',
            'allowed_tools: ["shell", "edit", "pytest"]',
        )
    )

    with pytest.raises(ValueError, match="read_file"):
        validate_task_pack(task_pack)


def test_task_manifest_requires_public_check_idempotence_declaration(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    manifest_path = task_pack / "tasks/toy_python_fix/task.yaml"
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "    are_tests_idempotent: true\n",
            "",
        )
    )

    with pytest.raises(ValueError, match="are_tests_idempotent"):
        load_task_manifest(manifest_path)


def test_task_pack_validation_rejects_invalid_agent_control_script(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    control_path = (
        task_pack
        / "tasks/toy_python_fix/controls/agent_control_scripts/happy_path.json"
    )
    raw_control = json.loads(control_path.read_text())
    raw_control["schema_version"] = "agent_control_script_v1"
    control_path.write_text(json.dumps(raw_control))

    with pytest.raises(ValueError, match="Invalid agent control script"):
        validate_task_pack(task_pack)


def test_task_pack_validation_rejects_missing_agent_control_manifest_reference(
    tmp_path: Path,
) -> None:
    task_pack = _copy_task_pack(tmp_path)
    manifest_path = task_pack / "tasks/toy_python_fix/task.yaml"
    manifest_path.write_text(
        manifest_path.read_text().replace(
            """  agent_control_scripts:
    happy: controls/agent_control_scripts/happy_path.json
    malformed: controls/agent_control_scripts/malformed_json.json
    recoverable: controls/agent_control_scripts/bad_tool_input_then_recovery.json
""",
            "",
        )
    )

    with pytest.raises(ValueError, match="agent_control_scripts"):
        validate_task_pack(task_pack)


def _copy_task_pack(tmp_path: Path) -> Path:
    task_pack = tmp_path / "repo_patch_python_v0"
    shutil.copytree(TASK_PACK, task_pack)
    return task_pack
