from pathlib import Path

from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_prepare_agent_workspace_copies_only_seed_workspace(tmp_path: Path) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path,
    )

    assert (workspace.path / "src/mathlib.py").is_file()
    assert (workspace.path / "tests/test_public.py").is_file()
    assert not (workspace.path / "hidden_tests/test_behavior.py").exists()
    assert not (workspace.path / "controls/scorer_control_patches/oracle.patch").exists()
