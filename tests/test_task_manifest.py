from pathlib import Path

from agentenv.tasks.validate import load_task_manifest, validate_task_manifest_paths


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


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
