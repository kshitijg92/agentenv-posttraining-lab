from pathlib import Path

import pytest

from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.runners.patch_runner import apply_patch_file
from agentenv.runners.public_check_runner import run_public_checks
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


@pytest.mark.parametrize(
    "patch_path",
    [
        "controls/oracle.patch",
        "controls/bad_noop.patch",
        "controls/bad_public_only.patch",
    ],
)
def test_controls_pass_public_checks(tmp_path: Path, patch_path: str) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path,
    )
    patch_result = apply_patch_file(
        workspace.path,
        workspace.task_dir / patch_path,
        timeout_seconds=manifest.limits.timeout_seconds,
    )

    public_results = run_public_checks(
        workspace.path,
        manifest.public_checks,
        timeout_seconds=manifest.limits.timeout_seconds,
    )

    assert patch_result.returncode == 0
    assert public_results
    assert all(result.returncode == 0 for result in public_results)
