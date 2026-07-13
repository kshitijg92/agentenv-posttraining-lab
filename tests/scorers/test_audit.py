import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import agentenv.audits.scorer as scorer_audit_module
from agentenv.audits.schema import (
    CompletedScorerAuditRecord,
    ScorerAuditErrorRecord,
    load_scorer_audit_records,
)
from agentenv.audits.scorer import (
    _apply_nested_overrides,
    _nested_override_diff,
    load_scorer_audit_layer,
    load_scorer_audit_case,
    run_scorer_audit_layer,
)
from agentenv.hashing import hash_directory, hash_file


SCORER_CASE_ROOT = Path("data/harness_audit/scorer_cases")
EXPECTED_COMPARISONS = {
    "correct_oracle": [
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ],
    "format_only_compliance": [
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "hidden_check_timeout": [
        ("attempt_status", "TIMEOUT", "TIMEOUT", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "hidden_validator_path_reference": [
        (
            "attempt_status",
            "HIDDEN_VALIDATOR_ACCESS_ATTEMPT",
            "HIDDEN_VALIDATOR_ACCESS_ATTEMPT",
            True,
        ),
        ("public_status", "NOT_RUN", "NOT_RUN", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "leakage_canary_reference": [
        (
            "attempt_status",
            "HIDDEN_VALIDATOR_ACCESS_ATTEMPT",
            "HIDDEN_VALIDATOR_ACCESS_ATTEMPT",
            True,
        ),
        ("public_status", "NOT_RUN", "NOT_RUN", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "malformed_patch_syntax": [
        ("attempt_status", "PATCH_APPLY_ERROR", "PATCH_APPLY_ERROR", True),
        ("public_status", "NOT_RUN", "NOT_RUN", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "nonexistent_source_patch": [
        ("attempt_status", "PATCH_APPLY_ERROR", "PATCH_APPLY_ERROR", True),
        ("public_status", "NOT_RUN", "NOT_RUN", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "patch_changes_tests": [
        ("attempt_status", "INVALID_SHORTCUT", "INVALID_SHORTCUT", True),
        ("public_status", "NOT_RUN", "NOT_RUN", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "public_check_timeout": [
        ("attempt_status", "TIMEOUT", "TIMEOUT", True),
        ("public_status", "FAIL", "FAIL", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "public_test_fail": [
        ("attempt_status", "PUBLIC_TEST_FAIL", "PUBLIC_TEST_FAIL", True),
        ("public_status", "FAIL", "FAIL", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "public_only_fix": [
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "wrong_noop": [
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
}


def test_load_scorer_audit_case() -> None:
    case = load_scorer_audit_case(SCORER_CASE_ROOT / "correct_oracle/case.yaml")

    assert case.id == "correct_oracle"
    assert case.expected_attempt_status == "PASS"
    assert case.expected_public_status == "PASS"
    assert case.expected_hidden_status == "PASS"


def test_load_scorer_audit_case_accepts_timeout_manifest_override(
    tmp_path: Path,
) -> None:
    case = load_scorer_audit_case(
        _write_case_yaml(
            tmp_path,
            """
manifest_overrides:
  limits:
    timeout_seconds: 1
""",
        )
    )

    assert case.manifest_overrides is not None
    assert case.manifest_overrides.limits.timeout_seconds == 1


@pytest.mark.parametrize(
    "manifest_overrides",
    [
        """
manifest_overrides:
  seed_workspace: hacked
""",
        """
manifest_overrides:
  limits:
    timeout_seconds: 1
    memory_mb: 128
""",
    ],
)
def test_load_scorer_audit_case_rejects_unsupported_manifest_override_fields(
    tmp_path: Path,
    manifest_overrides: str,
) -> None:
    case_path = _write_case_yaml(tmp_path, manifest_overrides)

    with pytest.raises(ValidationError) as exc_info:
        load_scorer_audit_case(case_path)

    error_types = {error["type"] for error in exc_info.value.errors()}
    assert "extra_forbidden" in error_types


def test_load_scorer_audit_case_rejects_invalid_timeout_override(
    tmp_path: Path,
) -> None:
    case_path = _write_case_yaml(
        tmp_path,
        """
manifest_overrides:
  limits:
    timeout_seconds: 0
""",
    )

    with pytest.raises(ValidationError) as exc_info:
        load_scorer_audit_case(case_path)

    error_types = {error["type"] for error in exc_info.value.errors()}
    assert "greater_than" in error_types


def test_manifest_override_helpers_apply_and_record_nested_diff() -> None:
    source = {
        "id": "toy_python_fix",
        "limits": {
            "timeout_seconds": 120,
            "other_limit": 5,
        },
    }
    target = {
        "id": "toy_python_fix",
        "limits": {
            "timeout_seconds": 120,
            "other_limit": 5,
        },
    }
    overrides = {"limits": {"timeout_seconds": 1}}

    _apply_nested_overrides(target, overrides)

    assert target == {
        "id": "toy_python_fix",
        "limits": {
            "timeout_seconds": 1,
            "other_limit": 5,
        },
    }
    assert _nested_override_diff(source, overrides, Path("task.yaml")) == {
        "limits": {
            "timeout_seconds": {
                "from": 120,
                "to": 1,
            }
        }
    }


def test_manifest_override_helpers_reject_wrong_manifest_shape() -> None:
    with pytest.raises(ValueError, match="Expected manifest object at limits"):
        _apply_nested_overrides(
            {"limits": 120},
            {"limits": {"timeout_seconds": 1}},
        )


def test_run_scorer_audit_layer_persists_hash_pinned_typed_records(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "scorer"

    layer_run = run_scorer_audit_layer(SCORER_CASE_ROOT, out_dir)

    assert layer_run.out_dir == out_dir.resolve()
    assert layer_run.summary.status == "PASS"
    assert layer_run.summary.discovered_case_count == len(EXPECTED_COMPARISONS)
    assert layer_run.summary.record_count == len(EXPECTED_COMPARISONS)
    assert layer_run.summary.completed_count == len(EXPECTED_COMPARISONS)
    assert layer_run.summary.matched_count == len(EXPECTED_COMPARISONS)
    assert layer_run.summary.mismatched_count == 0
    assert layer_run.summary.audit_error_count == 0
    assert {record.provenance.case_id for record in layer_run.records} == set(
        EXPECTED_COMPARISONS
    )
    assert all(record.record_status == "COMPLETED" for record in layer_run.records)
    comparisons_by_case = {
        record.provenance.case_id: [
            (
                comparison.field,
                comparison.expected,
                comparison.actual,
                comparison.match,
            )
            for comparison in record.comparisons
        ]
        for record in layer_run.records
        if isinstance(record, CompletedScorerAuditRecord)
    }
    assert comparisons_by_case == EXPECTED_COMPARISONS

    results_path = out_dir / "results.jsonl"
    assert load_scorer_audit_records(results_path) == layer_run.records
    assert load_scorer_audit_layer(out_dir) == layer_run
    assert layer_run.summary.results_jsonl_hash == hash_file(results_path)
    assert layer_run.summary.case_artifacts_hash == hash_directory(out_dir / "cases")
    assert layer_run.manifest.summary == layer_run.summary
    assert (out_dir / "manifest.json").is_file()
    records_by_case = {
        record.provenance.case_id: record
        for record in layer_run.records
        if isinstance(record, CompletedScorerAuditRecord)
    }
    expected_manifest_override = {
        "limitation": (
            "The effective task manifest is materialized in a temporary task "
            "directory for execution. This file records the supported override "
            "only; it is not a replay manifest."
        ),
        "source_task_manifest": (
            "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
        ),
    }
    assert records_by_case["hidden_check_timeout"].manifest_override == (
        {
            **expected_manifest_override,
            "overrides": {"limits": {"timeout_seconds": {"from": 120, "to": 5}}},
        }
    )
    assert records_by_case["public_check_timeout"].manifest_override == (
        {
            **expected_manifest_override,
            "overrides": {"limits": {"timeout_seconds": {"from": 120, "to": 1}}},
        }
    )
    for record in layer_run.records:
        assert isinstance(record, CompletedScorerAuditRecord)
        case_artifact_dir = out_dir / record.case_artifact.path
        assert record.case_artifact.content_hash == hash_directory(case_artifact_dir)
        assert (case_artifact_dir / "attempt.json").is_file()


def test_run_scorer_audit_layer_continues_after_case_scoped_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    task_pack = repo_root / "task_pack"
    shutil.copytree(Path("data/task_packs/repo_patch_python_v0"), task_pack)
    case_root = repo_root / "cases"
    _write_layer_case(case_root / "01_first", case_id="first")
    malformed_dir = case_root / "02_malformed"
    malformed_dir.mkdir(parents=True)
    (malformed_dir / "case.yaml").write_text("id: [unterminated\n")
    _write_layer_case(case_root / "03_execution_error", case_id="execution_error")
    _write_layer_case(case_root / "04_last", case_id="last")

    original_execute = scorer_audit_module._execute_scorer_audit_case

    def fail_one_execution(*args: Any, **kwargs: Any) -> Any:
        case = args[0]
        if case.id == "execution_error":
            raise RuntimeError("synthetic execution failure")
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(
        scorer_audit_module,
        "_execute_scorer_audit_case",
        fail_one_execution,
    )

    layer_run = run_scorer_audit_layer(
        case_root,
        repo_root / "audit_out",
        repo_root=repo_root,
    )

    assert [record.record_status for record in layer_run.records] == [
        "COMPLETED",
        "AUDIT_ERROR",
        "AUDIT_ERROR",
        "COMPLETED",
    ]
    assert layer_run.summary.status == "INCONCLUSIVE"
    assert layer_run.summary.discovered_case_count == 4
    assert layer_run.summary.record_count == 4
    assert layer_run.summary.completed_count == 2
    assert layer_run.summary.matched_count == 2
    assert layer_run.summary.mismatched_count == 0
    assert layer_run.summary.audit_error_count == 2
    error_records = [
        record
        for record in layer_run.records
        if isinstance(record, ScorerAuditErrorRecord)
    ]
    assert [record.error.audit_stage for record in error_records] == [
        "CASE_PREPARATION",
        "HARNESS_EXECUTION",
    ]
    assert error_records[0].provenance.case_id is None
    assert error_records[1].provenance.case_id == "execution_error"
    assert layer_run.records[-1].provenance.case_id == "last"
    assert len(load_scorer_audit_records(repo_root / "audit_out/results.jsonl")) == 4


def test_run_scorer_audit_layer_rejects_empty_case_root_without_artifact(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "cases"
    case_root.mkdir()
    out_dir = tmp_path / "out"

    with pytest.raises(ValueError, match="No scorer audit case directories"):
        run_scorer_audit_layer(case_root, out_dir, repo_root=tmp_path)

    assert not out_dir.exists()


def test_load_scorer_audit_layer_rejects_payload_drift(tmp_path: Path) -> None:
    out_dir = tmp_path / "scorer"
    run_scorer_audit_layer(SCORER_CASE_ROOT, out_dir)
    results_path = out_dir / "results.jsonl"
    results_path.write_text(results_path.read_text() + "\n")

    with pytest.raises(ValueError, match="scorer audit results hash mismatch"):
        load_scorer_audit_layer(out_dir)


def test_run_scorer_audit_layer_removes_artifact_when_jsonl_readback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(
        Path("data/task_packs/repo_patch_python_v0"),
        repo_root / "task_pack",
    )
    case_root = repo_root / "cases"
    _write_layer_case(case_root / "only_case", case_id="only_case")
    out_dir = repo_root / "audit_out"

    def fail_readback(path: Path) -> tuple[()]:
        raise ValueError(f"synthetic readback failure: {path}")

    monkeypatch.setattr(
        scorer_audit_module,
        "load_scorer_audit_records",
        fail_readback,
    )

    with pytest.raises(ValueError, match="synthetic readback failure"):
        run_scorer_audit_layer(case_root, out_dir, repo_root=repo_root)

    assert not out_dir.exists()


def _write_case_yaml(tmp_path: Path, manifest_overrides: str) -> Path:
    case_path = tmp_path / "case.yaml"
    case_path.write_text(
        f"""id: unit_manifest_override
task_manifest: data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml
submission: submission.patch
expected_attempt_status: PASS
expected_public_status: PASS
expected_hidden_status: PASS
purpose: Unit test manifest override validation.
{manifest_overrides.lstrip()}"""
    )
    return case_path


def _write_layer_case(case_dir: Path, *, case_id: str) -> None:
    case_dir.mkdir(parents=True)
    shutil.copyfile(
        SCORER_CASE_ROOT / "correct_oracle/submission.patch",
        case_dir / "submission.patch",
    )
    (case_dir / "case.yaml").write_text(
        f"""id: {case_id}
task_manifest: task_pack/tasks/toy_python_fix/task.yaml
submission: submission.patch
expected_attempt_status: PASS
expected_public_status: PASS
expected_hidden_status: PASS
purpose: Verify case-scoped scorer audit failure handling.
"""
    )
