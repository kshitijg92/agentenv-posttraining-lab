import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.scorers.audit import (
    _apply_nested_overrides,
    _nested_override_diff,
    load_scorer_audit_case,
    run_scorer_audit,
)


SCORER_CASE_ROOT = Path("data/harness_audit/scorer_cases")
EXPECTED_COMPARISONS = {
    "correct_oracle": [
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
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
  workspace_seed: hacked
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


def test_run_scorer_audit_writes_jsonl_markdown_and_attempt_artifacts(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "scorer_audit"

    results = run_scorer_audit(SCORER_CASE_ROOT, out_dir)

    expected_case_ids = list(EXPECTED_COMPARISONS)
    assert [result.case.id for result in results] == expected_case_ids
    assert all(result.overall_match for result in results)
    comparisons_by_case = {
        result.case.id: [
            (comparison.field, comparison.expected, comparison.actual, comparison.match)
            for comparison in result.comparisons
        ]
        for result in results
    }
    assert comparisons_by_case == EXPECTED_COMPARISONS

    jsonl_path = out_dir / "scorer_audit_results.jsonl"
    markdown_path = out_dir / "scorer_audit.md"

    assert jsonl_path.is_file()
    assert markdown_path.is_file()
    for case_id in expected_case_ids:
        attempt_dir = out_dir / "attempts" / case_id
        assert (attempt_dir / "attempt.json").is_file()
        assert (attempt_dir / "trace.jsonl").is_file()
        assert (attempt_dir / "final.diff").is_file()
    assert (out_dir / "attempts/hidden_check_timeout/manifest_override.json").is_file()
    assert (out_dir / "attempts/public_check_timeout/manifest_override.json").is_file()

    records = [
        json.loads(line)
        for line in jsonl_path.read_text().splitlines()
        if line.strip()
    ]
    assert [record["case_id"] for record in records] == expected_case_ids
    assert all(record["overall_match"] is True for record in records)
    assert [record["attempt_artifact_dir"] for record in records] == [
        f"attempts/{case_id}" for case_id in expected_case_ids
    ]
    records_by_case = {record["case_id"]: record for record in records}
    expected_manifest_override = {
        "limitation": (
            "The effective task manifest is materialized in a temporary task "
            "directory for execution. This file records the supported override "
            "only; it is not a replay manifest."
        ),
        "overrides": {
            "limits": {
                "timeout_seconds": {
                    "from": 120,
                    "to": 1,
                }
            }
        },
        "source_task_manifest": (
            "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
        ),
    }
    assert records_by_case["hidden_check_timeout"]["manifest_override"] == (
        expected_manifest_override
    )
    assert records_by_case["public_check_timeout"]["manifest_override"] == (
        expected_manifest_override
    )

    markdown = markdown_path.read_text()
    assert "| correct_oracle | PASS | attempts/correct_oracle |" in markdown
    assert "| correct_oracle | attempt_status | PASS | PASS | PASS |" in markdown
    assert (
        "| correct_oracle | hidden_status | PASS | PASS | PASS |\n"
        "|  |  |  |  |  |\n"
        "| hidden_check_timeout | attempt_status | TIMEOUT | "
        "TIMEOUT | PASS |"
    ) in markdown
    assert (
        "| hidden_validator_path_reference | attempt_status | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | PASS |"
    ) in markdown
    assert (
        "| leakage_canary_reference | attempt_status | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | PASS |"
    ) in markdown
    assert (
        "| malformed_patch_syntax | attempt_status | PATCH_APPLY_ERROR | "
        "PATCH_APPLY_ERROR | PASS |"
    ) in markdown
    assert (
        "| nonexistent_source_patch | attempt_status | PATCH_APPLY_ERROR | "
        "PATCH_APPLY_ERROR | PASS |"
    ) in markdown
    assert "| patch_changes_tests | PASS | attempts/patch_changes_tests |" in markdown
    assert (
        "| patch_changes_tests | hidden_status | NOT_RUN | NOT_RUN | PASS |\n"
        "|  |  |  |  |  |\n"
        "| public_check_timeout | attempt_status | TIMEOUT | "
        "TIMEOUT | PASS |"
    ) in markdown
    assert (
        "| public_check_timeout | PASS | attempts/public_check_timeout |"
    ) in markdown
    assert "| public_only_fix | PASS | attempts/public_only_fix |" in markdown
    assert (
        "| public_only_fix | attempt_status | HIDDEN_TEST_FAIL | "
        "HIDDEN_TEST_FAIL | PASS |"
    ) in markdown
    assert "| hidden_check_timeout | PASS | attempts/hidden_check_timeout |" in markdown
    assert "| wrong_noop | PASS | attempts/wrong_noop |" in markdown
    assert (
        "| wrong_noop | attempt_status | HIDDEN_TEST_FAIL | "
        "HIDDEN_TEST_FAIL | PASS |"
    ) in markdown


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
