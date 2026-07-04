from pathlib import Path
from subprocess import TimeoutExpired

import pytest

import agentenv.orchestrators.attempt as attempt_module
from agentenv.orchestrators.attempt import (
    SCORER_ATTEMPT_ORCHESTRATOR_VERSION,
    AttemptResult,
    run_patch_attempt,
)
from agentenv.runners.command_runner import CommandResult


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_attempt_result_schema() -> None:
    result = AttemptResult(
        run_id="run_001",
        task_id="toy_python_fix_001",
        task_manifest_path="data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml",
        attempt_id="attempt_001",
        submission_path="controls/scorer_control_patches/oracle.patch",
        status="PASS",
        public_status="PASS",
        hidden_status="PASS",
        error_class=None,
        started_at="2026-06-19T00:00:00Z",
        ended_at="2026-06-19T00:00:01Z",
        duration_ms=1000,
        final_diff_hash="abc123",
        orchestrator_version=SCORER_ATTEMPT_ORCHESTRATOR_VERSION,
    )

    assert result.status == "PASS"
    assert result.task_manifest_path.endswith("toy_python_fix/task.yaml")
    assert result.public_status == "PASS"
    assert result.hidden_status == "PASS"


@pytest.mark.parametrize(
    ("patch_path", "expected_status", "expected_public", "expected_hidden"),
    [
        ("controls/scorer_control_patches/oracle.patch", "PASS", "PASS", "PASS"),
        ("controls/scorer_control_patches/bad_noop.patch", "HIDDEN_TEST_FAIL", "PASS", "FAIL"),
        ("controls/scorer_control_patches/bad_public_only.patch", "HIDDEN_TEST_FAIL", "PASS", "FAIL"),
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
    assert result.orchestrator_version == SCORER_ATTEMPT_ORCHESTRATOR_VERSION
    assert result.status == expected_status
    assert result.public_status == expected_public
    assert result.hidden_status == expected_hidden
    assert result.final_diff_hash is not None
    assert result.final_diff_hash.startswith("xxh64:")
    assert attempt_run.command_results

    if patch_path == "controls/scorer_control_patches/bad_noop.patch":
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
        TOY_TASK_MANIFEST.parent / "controls/scorer_control_patches/oracle.patch",
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
    assert attempt_run.result.final_diff_hash is None
    assert attempt_run.final_diff == ""
    assert attempt_run.commands == []


def test_run_patch_attempt_rejects_public_test_edit_before_patch_apply(
    tmp_path: Path,
) -> None:
    patch_path = tmp_path / "malformed_modify_public_test.patch"
    patch_path.write_text(
        """diff --git a/tests/test_public.py b/tests/test_public.py
--- a/tests/test_public.py
+++ b/tests/test_public.py
@@ definitely not a valid patch hunk
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
    assert attempt_run.final_diff == ""
    assert attempt_run.commands == []


def test_run_patch_attempt_rejects_hidden_validator_reference_before_patch_apply(
    tmp_path: Path,
) -> None:
    patch_path = tmp_path / "hidden_reference.patch"
    patch_path.write_text(
        """diff --git a/src/mathlib.py b/src/mathlib.py
--- a/src/mathlib.py
+++ b/src/mathlib.py
@@ malformed but mentions hidden_tests
"""
    )

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        patch_path,
        workspace_parent=tmp_path / "workspace_parent",
    )

    assert attempt_run.result.status == "HIDDEN_VALIDATOR_ACCESS_ATTEMPT"
    assert attempt_run.result.public_status == "NOT_RUN"
    assert attempt_run.result.hidden_status == "NOT_RUN"
    assert attempt_run.result.error_class == "HiddenValidatorReference"
    assert attempt_run.final_diff == ""
    assert attempt_run.commands == []


def test_hidden_validator_reference_takes_precedence_over_public_test_edit(
    tmp_path: Path,
) -> None:
    patch_path = tmp_path / "hidden_reference_and_public_test_edit.patch"
    patch_path.write_text(
        """diff --git a/tests/test_public.py b/tests/test_public.py
--- a/tests/test_public.py
+++ b/tests/test_public.py
@@ malformed but mentions hidden_tests
"""
    )

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        patch_path,
        workspace_parent=tmp_path / "workspace_parent",
    )

    assert attempt_run.result.status == "HIDDEN_VALIDATOR_ACCESS_ATTEMPT"
    assert attempt_run.result.error_class == "HiddenValidatorReference"
    assert attempt_run.final_diff == ""
    assert attempt_run.commands == []


def test_run_patch_attempt_reports_patch_apply_timeout_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise TimeoutExpired(cmd="git apply", timeout=1)

    monkeypatch.setattr(attempt_module, "apply_patch_file", raise_timeout)

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/scorer_control_patches/oracle.patch",
        workspace_parent=tmp_path,
    )

    assert attempt_run.result.status == "TIMEOUT"
    assert attempt_run.result.public_status == "NOT_RUN"
    assert attempt_run.result.hidden_status == "NOT_RUN"
    assert attempt_run.result.error_class == "PatchApplyTimeout"
    assert attempt_run.commands == []


def test_run_patch_attempt_reports_public_check_timeout_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise TimeoutExpired(cmd="pytest public", timeout=1)

    monkeypatch.setattr(attempt_module, "run_public_checks", raise_timeout)

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/scorer_control_patches/oracle.patch",
        workspace_parent=tmp_path,
    )

    assert attempt_run.result.status == "TIMEOUT"
    assert attempt_run.result.public_status == "FAIL"
    assert attempt_run.result.hidden_status == "NOT_RUN"
    assert attempt_run.result.error_class == "PublicCheckTimeout"
    assert [command.phase for command in attempt_run.commands] == ["patch_apply"]


def test_run_patch_attempt_reports_hidden_validation_timeout_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def public_check_passes(*args: object, **kwargs: object) -> list[CommandResult]:
        return [
            CommandResult(
                command=["pytest", "public"],
                returncode=0,
                stdout="",
                stderr="",
            )
        ]

    def raise_timeout(*args: object, **kwargs: object) -> None:
        raise TimeoutExpired(cmd="pytest hidden", timeout=1)

    monkeypatch.setattr(attempt_module, "run_public_checks", public_check_passes)
    monkeypatch.setattr(attempt_module, "run_hidden_pytest_validators", raise_timeout)

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/scorer_control_patches/oracle.patch",
        workspace_parent=tmp_path,
    )

    assert attempt_run.result.status == "TIMEOUT"
    assert attempt_run.result.public_status == "PASS"
    assert attempt_run.result.hidden_status == "FAIL"
    assert attempt_run.result.error_class == "HiddenValidationTimeout"
    assert [command.phase for command in attempt_run.commands] == [
        "patch_apply",
        "public_check",
    ]
