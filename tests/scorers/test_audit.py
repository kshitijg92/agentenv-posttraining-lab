import json
from pathlib import Path

from agentenv.scorers.audit import load_scorer_audit_case, run_scorer_audit


SCORER_CASE_ROOT = Path("data/harness_audit/scorer_cases")
EXPECTED_COMPARISONS = {
    "correct_oracle": [
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
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
    "patch_changes_tests": [
        ("attempt_status", "INVALID_SHORTCUT", "INVALID_SHORTCUT", True),
        ("public_status", "NOT_RUN", "NOT_RUN", True),
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

    markdown = markdown_path.read_text()
    assert "| correct_oracle | PASS | attempts/correct_oracle |" in markdown
    assert "| correct_oracle | attempt_status | PASS | PASS | PASS |" in markdown
    assert (
        "| correct_oracle | hidden_status | PASS | PASS | PASS |\n"
        "|  |  |  |  |  |\n"
        "| hidden_validator_path_reference | attempt_status | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | PASS |"
    ) in markdown
    assert (
        "| leakage_canary_reference | attempt_status | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | "
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT | PASS |"
    ) in markdown
    assert "| patch_changes_tests | PASS | attempts/patch_changes_tests |" in markdown
    assert (
        "| patch_changes_tests | hidden_status | NOT_RUN | NOT_RUN | PASS |\n"
        "|  |  |  |  |  |\n"
        "| public_only_fix | attempt_status | HIDDEN_TEST_FAIL | "
        "HIDDEN_TEST_FAIL | PASS |"
    ) in markdown
    assert "| public_only_fix | PASS | attempts/public_only_fix |" in markdown
    assert "| wrong_noop | PASS | attempts/wrong_noop |" in markdown
    assert (
        "| wrong_noop | attempt_status | HIDDEN_TEST_FAIL | "
        "HIDDEN_TEST_FAIL | PASS |"
    ) in markdown
