import json
from pathlib import Path

from agentenv.scorers.audit import load_scorer_audit_case, run_scorer_audit


SCORER_CASE_ROOT = Path("data/harness_audit/scorer_cases")


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

    assert len(results) == 1
    result = results[0]
    assert result.case.id == "correct_oracle"
    assert result.overall_match is True
    assert [
        (comparison.field, comparison.expected, comparison.actual, comparison.match)
        for comparison in result.comparisons
    ] == [
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ]

    jsonl_path = out_dir / "scorer_audit_results.jsonl"
    markdown_path = out_dir / "scorer_audit.md"
    attempt_dir = out_dir / "attempts/correct_oracle"

    assert jsonl_path.is_file()
    assert markdown_path.is_file()
    assert (attempt_dir / "attempt.json").is_file()
    assert (attempt_dir / "trace.jsonl").is_file()
    assert (attempt_dir / "final.diff").is_file()

    records = [
        json.loads(line)
        for line in jsonl_path.read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["case_id"] == "correct_oracle"
    assert records[0]["overall_match"] is True
    assert records[0]["attempt_artifact_dir"] == "attempts/correct_oracle"

    markdown = markdown_path.read_text()
    assert "| correct_oracle | PASS | attempts/correct_oracle |" in markdown
    assert "| correct_oracle | attempt_status | PASS | PASS | PASS |" in markdown
