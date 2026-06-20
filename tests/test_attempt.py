from pathlib import Path

import pytest

from agentenv.orchestrators.attempt import AttemptResult, run_patch_attempt


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_patch_attempt_result_schema() -> None:
    result = AttemptResult(
        run_id="run_001",
        task_id="toy_python_fix_001",
        task_manifest_path="data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml",
        attempt_id="attempt_001",
        submission_path="controls/oracle.patch",
        status="PASS",
        public_status="PASS",
        hidden_status="PASS",
        error_class=None,
        started_at="2026-06-19T00:00:00Z",
        ended_at="2026-06-19T00:00:01Z",
        duration_ms=1000,
        final_diff_hash="abc123",
        orchestrator_version="attempt_v0",
    )

    assert result.status == "PASS"
    assert result.task_manifest_path.endswith("toy_python_fix/task.yaml")
    assert result.public_status == "PASS"
    assert result.hidden_status == "PASS"


@pytest.mark.parametrize(
    ("patch_path", "expected_status", "expected_public", "expected_hidden"),
    [
        ("controls/oracle.patch", "PASS", "PASS", "PASS"),
        ("controls/bad_noop.patch", "HIDDEN_TEST_FAIL", "PASS", "FAIL"),
        ("controls/bad_public_only.patch", "HIDDEN_TEST_FAIL", "PASS", "FAIL"),
    ],
)
def test_run_patch_attempt_distinguishes_controls(
    tmp_path: Path,
    patch_path: str,
    expected_status: str,
    expected_public: str,
    expected_hidden: str,
) -> None:
    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / patch_path,
        workspace_parent=tmp_path,
    )
    result = attempt_run.result

    assert result.task_id == "toy_python_fix_001"
    assert result.task_manifest_path.endswith("toy_python_fix/task.yaml")
    assert result.status == expected_status
    assert result.public_status == expected_public
    assert result.hidden_status == expected_hidden
    assert result.final_diff_hash is not None
    assert result.final_diff_hash.startswith("xxh64:")
    assert attempt_run.command_results

    if patch_path == "controls/bad_noop.patch":
        assert attempt_run.final_diff == ""
    else:
        assert "src/mathlib.py" in attempt_run.final_diff
