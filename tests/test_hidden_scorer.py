from pathlib import Path

import pytest

from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.runners.patch_runner import apply_patch_file
from agentenv.scorers.pytest_hidden import run_hidden_pytest_validators
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


@pytest.mark.parametrize(
    ("patch_path", "expected_passed"),
    [
        ("controls/oracle.patch", True),
        ("controls/bad_noop.patch", False),
        ("controls/bad_public_only.patch", False),
    ],
)
def test_hidden_scorer_distinguishes_controls(
    tmp_path: Path,
    patch_path: str,
    expected_passed: bool,
) -> None:
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

    hidden_results = run_hidden_pytest_validators(
        workspace.path,
        workspace.task_dir,
        manifest.hidden_validators,
        timeout_seconds=manifest.limits.timeout_seconds,
    )

    assert patch_result.returncode == 0
    assert hidden_results
    assert all(result.passed for result in hidden_results) is expected_passed
    assert not (workspace.path / "hidden_tests").exists()
