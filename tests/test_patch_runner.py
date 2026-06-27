from pathlib import Path

from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.runners.patch_runner import apply_patch_file
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_apply_oracle_patch_to_prepared_workspace(tmp_path: Path) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path,
    )

    result = apply_patch_file(
        workspace.path,
        workspace.task_dir / manifest.controls.scorer_control_patches.oracle,
        timeout_seconds=manifest.limits.timeout_seconds,
    )

    assert result.returncode == 0
    mathlib = (workspace.path / "src/mathlib.py").read_text()
    assert "raise ValueError" in mathlib
    assert "return float(numerator / denominator)" in mathlib


def test_empty_patch_is_successful_noop(tmp_path: Path) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path,
    )

    result = apply_patch_file(
        workspace.path,
        workspace.task_dir / manifest.controls.scorer_control_patches.bad.noop,
        timeout_seconds=manifest.limits.timeout_seconds,
    )

    assert result.returncode == 0
    assert "return numerator // denominator" in (
        workspace.path / "src/mathlib.py"
    ).read_text()
