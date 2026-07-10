from pathlib import Path
from subprocess import TimeoutExpired

import pytest

import agentenv.controls.public_check_idempotency_runner as runner_module
import agentenv.runners.public_check_runner as public_check_runner_module
from agentenv.controls.public_check_idempotency_runner import (
    run_declared_public_check_idempotency_calibrations,
)
from agentenv.controls.public_check_idempotency_schema import (
    CompletedPublicCheckRun,
    FailedPublicCheckRun,
)
from agentenv.hashing import hash_file
from agentenv.runners.command_runner import CommandResult
from agentenv.tasks.schema import PublicCheck
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def _run_calibrations(
    tmp_path: Path,
    *,
    repeat_count: int = 2,
) -> tuple[Path, list[runner_module.PublicCheckIdempotencyCalibration]]:
    artifact_root = tmp_path / "control-artifact"
    calibrations = run_declared_public_check_idempotency_calibrations(
        task_manifest_path=TOY_TASK_MANIFEST,
        artifact_root=artifact_root,
        output_dir=artifact_root / "public_check_idempotency",
        repeat_count=repeat_count,
    )
    return artifact_root, calibrations


def test_runner_calibrates_true_declarations_on_one_shared_seed_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspaces: list[Path] = []
    runner_temp_roots: list[Path] = []

    def fake_run_shell(
        command: str,
        cwd: Path,
        timeout_seconds: int,
        env_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        assert command == "uv run --quiet --frozen pytest tests/test_public.py"
        assert timeout_seconds == 120
        assert env_overrides is not None
        runner_temp_root = Path(env_overrides["TMPDIR"])
        assert env_overrides["TMP"] == str(runner_temp_root)
        assert env_overrides["TEMP"] == str(runner_temp_root)
        assert runner_temp_root.is_dir()
        sentinel = runner_temp_root / "previous-run.txt"
        assert not sentinel.exists()
        sentinel.write_text("created by this run\n")
        workspaces.append(cwd)
        runner_temp_roots.append(runner_temp_root)
        return CommandResult(
            command=[command],
            returncode=0,
            stdout=f"workspace={cwd}\n1 passed in 0.12s\n",
            stderr=f"temp={runner_temp_root}\n",
        )

    monkeypatch.setattr(public_check_runner_module, "run_shell", fake_run_shell)

    artifact_root, calibrations = _run_calibrations(tmp_path)

    assert len(calibrations) == 1
    calibration = calibrations[0]
    assert calibration.task_id == "toy_python_fix_001"
    assert calibration.task_manifest_hash == hash_file(TOY_TASK_MANIFEST)
    assert calibration.public_check_index == 0
    assert calibration.command == "uv run --quiet --frozen pytest tests/test_public.py"
    assert calibration.repeat_count == 2
    assert calibration.status == "IDEMPOTENT"
    assert calibration.non_idempotency_reasons == []
    assert workspaces[0] == workspaces[1]
    assert runner_temp_roots[0] == runner_temp_roots[1]
    assert not Path(calibration.normalization_context.workspace_root).exists()
    assert not Path(calibration.normalization_context.runner_temp_root).exists()

    completed_runs = [
        run for run in calibration.runs if isinstance(run, CompletedPublicCheckRun)
    ]
    assert len(completed_runs) == 2
    assert {
        run.canonical_workspace_hash_before for run in completed_runs
    } == {completed_runs[0].canonical_workspace_hash_after}
    assert len({run.normalized_result_hash for run in completed_runs}) == 1
    for run in completed_runs:
        stdout_path = artifact_root / run.stdout.path
        stderr_path = artifact_root / run.stderr.path
        assert stdout_path.is_file()
        assert stderr_path.is_file()
        assert run.stdout.content_hash == hash_file(stdout_path)
        assert run.stderr.content_hash == hash_file(stderr_path)


def test_runner_records_workspace_state_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    call_count = 0

    def mutating_run_shell(
        command: str,
        cwd: Path,
        timeout_seconds: int,
        env_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        del timeout_seconds
        del env_overrides
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            (cwd / "generated.txt").write_text("mutation\n")
        return CommandResult(command=[command], returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(
        public_check_runner_module,
        "run_shell",
        mutating_run_shell,
    )

    _, calibrations = _run_calibrations(tmp_path)

    assert calibrations[0].status == "NON_IDEMPOTENT"
    assert calibrations[0].non_idempotency_reasons == ["WORKSPACE_STATE_DRIFT"]


def test_runner_records_normalized_result_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outputs = iter(["first\n", "second\n"])

    def drifting_run_shell(
        command: str,
        cwd: Path,
        timeout_seconds: int,
        env_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        del cwd
        del timeout_seconds
        del env_overrides
        return CommandResult(
            command=[command],
            returncode=0,
            stdout=next(outputs),
            stderr="",
        )

    monkeypatch.setattr(
        public_check_runner_module,
        "run_shell",
        drifting_run_shell,
    )

    _, calibrations = _run_calibrations(tmp_path)

    assert calibrations[0].status == "NON_IDEMPOTENT"
    assert calibrations[0].non_idempotency_reasons == [
        "NORMALIZED_RESULT_DRIFT"
    ]


def test_runner_records_timeout_with_hash_pinned_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    responses: list[object] = [
        TimeoutExpired(
            cmd="public-check",
            timeout=30,
            output=b"partial stdout\n",
            stderr=None,
        ),
        CommandResult(
            command=["public-check"],
            returncode=0,
            stdout="completed\n",
            stderr="",
        ),
    ]

    def timeout_then_complete(
        command: str,
        cwd: Path,
        timeout_seconds: int,
        env_overrides: dict[str, str] | None = None,
    ) -> CommandResult:
        del command
        del cwd
        del timeout_seconds
        del env_overrides
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, CommandResult)
        return response

    monkeypatch.setattr(
        public_check_runner_module,
        "run_shell",
        timeout_then_complete,
    )

    artifact_root, calibrations = _run_calibrations(tmp_path)

    calibration = calibrations[0]
    assert calibration.status == "INCONCLUSIVE"
    failed_run = calibration.runs[0]
    assert isinstance(failed_run, FailedPublicCheckRun)
    assert failed_run.failure_mode == "TIMEOUT"
    assert failed_run.stdout is not None
    assert (artifact_root / failed_run.stdout.path).read_text() == "partial stdout\n"
    assert failed_run.stderr is None


def test_runner_skips_false_declarations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    false_manifest = manifest.model_copy(
        update={
            "public_checks": [
                PublicCheck(command="true", are_tests_idempotent=False)
            ]
        }
    )
    monkeypatch.setattr(runner_module, "load_task_manifest", lambda _: false_manifest)

    def unexpected_run(*args: object, **kwargs: object) -> CommandResult:
        del args
        del kwargs
        raise AssertionError("false declarations must not execute")

    monkeypatch.setattr(
        public_check_runner_module,
        "run_shell",
        unexpected_run,
    )

    artifact_root, calibrations = _run_calibrations(tmp_path)

    assert calibrations == []
    assert list((artifact_root / "public_check_idempotency").iterdir()) == []


@pytest.mark.parametrize("repeat_count", [0, 1])
def test_runner_requires_at_least_two_repeats(
    tmp_path: Path,
    repeat_count: int,
) -> None:
    with pytest.raises(ValueError, match="repeat_count must be at least 2"):
        _run_calibrations(tmp_path, repeat_count=repeat_count)
