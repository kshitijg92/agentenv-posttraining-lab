from pathlib import Path

import pytest

import agentenv.orchestrators.attempt as attempt_module
from agentenv.orchestrators.attempt import AttemptResult, run_patch_attempt


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_attempt_result_schema() -> None:
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


def test_run_patch_attempt_surfaces_unexpected_exception_as_orchestrator_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_workspace_error(*args: object, **kwargs: object) -> None:
        raise ValueError("synthetic workspace failure")

    monkeypatch.setattr(
        attempt_module,
        "prepare_agent_workspace",
        raise_workspace_error,
    )

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/oracle.patch",
        workspace_parent=tmp_path,
    )

    assert attempt_run.result.status == "ORCHESTRATOR_ERROR"
    assert attempt_run.result.public_status == "NOT_RUN"
    assert attempt_run.result.hidden_status == "NOT_RUN"
    assert attempt_run.result.error_class == "ValueError"
    assert attempt_run.error_details is not None
    assert attempt_run.error_details.message == "synthetic workspace failure"
    assert "raise_workspace_error" in attempt_run.error_details.traceback
    assert attempt_run.commands == []


def test_run_patch_attempt_rejects_patch_that_modifies_public_tests(
    tmp_path: Path,
) -> None:
    patch_path = tmp_path / "modify_public_test.patch"
    patch_path.write_text(
        """diff --git a/tests/test_public.py b/tests/test_public.py
--- a/tests/test_public.py
+++ b/tests/test_public.py
@@ -2,4 +2,4 @@ from mathlib import normalize_ratio
 
 
 def test_simple_positive_ratio() -> None:
-    assert normalize_ratio(6, 3) == 2.0
+    assert normalize_ratio(6, 3) == 99.0
"""
    )

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        patch_path,
        workspace_parent=tmp_path / "workspace_parent",
    )

    assert attempt_run.result.status == "INVALID_SHORTCUT"
    assert attempt_run.result.public_status == "NOT_RUN"
    assert attempt_run.result.hidden_status == "NOT_RUN"
    assert attempt_run.result.error_class == "PublicTestModified"
    assert attempt_run.result.final_diff_hash is not None
    assert "tests/test_public.py" in attempt_run.final_diff
    assert [command.phase for command in attempt_run.commands] == ["patch_apply"]
