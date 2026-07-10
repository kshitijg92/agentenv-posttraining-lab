from pathlib import Path

import pytest

import agentenv.runners.public_check_runner as public_check_runner_module
from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.runners.command_runner import CommandResult
from agentenv.runners.patch_runner import apply_patch_file
from agentenv.runners.public_check_runner import run_public_check, run_public_checks
from agentenv.tasks.schema import PublicCheck
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_public_checks_receive_fresh_external_runner_temp_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    observed_roots: list[Path] = []

    def fake_run_shell(
        command: str,
        cwd: Path,
        timeout_seconds: int,
        env_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        assert cwd == workspace
        assert timeout_seconds == 30
        assert env_overrides is not None
        runner_temp_root = Path(env_overrides["TMPDIR"])
        assert env_overrides["TMP"] == str(runner_temp_root)
        assert env_overrides["TEMP"] == str(runner_temp_root)
        assert runner_temp_root.is_dir()
        assert not runner_temp_root.is_relative_to(workspace)
        (runner_temp_root / "command-owned-temp.txt").write_text(command)
        observed_roots.append(runner_temp_root)
        return CommandResult(
            command=[command],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(
        public_check_runner_module,
        "run_shell",
        fake_run_shell,
    )

    results = run_public_checks(
        workspace,
        [
            PublicCheck(command="first", are_tests_idempotent=True),
            PublicCheck(command="second", are_tests_idempotent=True),
        ],
        timeout_seconds=30,
    )

    assert [result.command for result in results] == [["first"], ["second"]]
    assert len(set(observed_roots)) == 2
    assert all(not runner_temp_root.exists() for runner_temp_root in observed_roots)


@pytest.mark.parametrize("runner_temp_relative_path", [".", "workspace/tmp"])
def test_public_check_rejects_runner_temp_root_overlapping_workspace(
    tmp_path: Path,
    runner_temp_relative_path: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ValueError, match="must not overlap the workspace"):
        run_public_check(
            "true",
            workspace,
            timeout_seconds=30,
            runner_temp_root=tmp_path / runner_temp_relative_path,
        )


@pytest.mark.parametrize(
    "patch_path",
    [
        "controls/scorer_control_patches/oracle.patch",
        "controls/scorer_control_patches/bad_noop.patch",
        "controls/scorer_control_patches/bad_public_only.patch",
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
