import json
from pathlib import Path

from agentenv.orchestrators.controls_run import expected_control_outcome, run_controls


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
TASK_IDS = {"repair_jsonl_deduper", "toy_python_fix_001"}
CONTROL_NAMES = {"oracle", "bad.noop", "bad.public_only"}


def test_expected_control_outcome_is_inferred_from_control_name() -> None:
    oracle = expected_control_outcome("oracle")
    bad_noop = expected_control_outcome("bad.noop")
    bad_public_only = expected_control_outcome("bad.public_only")

    assert (
        oracle.expected_attempt_status,
        oracle.expected_public_status,
        oracle.expected_hidden_status,
    ) == ("PASS", "PASS", "PASS")
    assert (
        bad_noop.expected_attempt_status,
        bad_noop.expected_public_status,
        bad_noop.expected_hidden_status,
    ) == ("HIDDEN_TEST_FAIL", "PASS", "FAIL")
    assert (
        bad_public_only.expected_attempt_status,
        bad_public_only.expected_public_status,
        bad_public_only.expected_hidden_status,
    ) == ("HIDDEN_TEST_FAIL", "PASS", "FAIL")


def test_run_controls_writes_manifest_jsonl_report_and_attempt_artifacts(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "controls"

    control_run = run_controls(TASK_PACK, repeats=2, out_dir=out_dir)

    assert control_run.repeats == 2
    expected_attempt_count = len(TASK_IDS) * len(CONTROL_NAMES) * 2
    assert len(control_run.attempts) == expected_attempt_count
    assert control_run.overall_match is True
    assert all(attempt.match for attempt in control_run.attempts)

    records = [
        json.loads(line)
        for line in (out_dir / "control_results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == expected_attempt_count
    assert {record["task_id"] for record in records} == TASK_IDS
    assert {record["control"] for record in records} == CONTROL_NAMES
    assert {record["repeat_index"] for record in records} == {0, 1}
    assert all(record["match"] is True for record in records)

    records_by_control = {
        (record["task_id"], record["control"], record["repeat_index"]): record
        for record in records
    }
    for task_id in TASK_IDS:
        for repeat_index in (0, 1):
            assert (
                records_by_control[(task_id, "oracle", repeat_index)]["actual"][
                    "attempt_status"
                ]
                == "PASS"
            )
            assert (
                records_by_control[(task_id, "bad.noop", repeat_index)]["actual"][
                    "attempt_status"
                ]
                == "HIDDEN_TEST_FAIL"
            )
            assert (
                records_by_control[(task_id, "bad.public_only", repeat_index)][
                    "actual"
                ]["hidden_status"]
                == "FAIL"
            )

    manifest = json.loads((out_dir / "control_run_manifest.json").read_text())
    assert manifest["artifact_version"] == "control_run_v0"
    assert manifest["repeats"] == 2
    assert manifest["attempt_count"] == expected_attempt_count
    assert manifest["overall_match"] is True
    assert manifest["artifacts"] == {
        "attempts": "attempts",
        "report": "control_report.md",
        "results": "control_results.jsonl",
    }

    report = (out_dir / "control_report.md").read_text()
    assert "# Control Calibration" in report
    assert (
        "| toy_python_fix_001 | oracle | 2 | 2/2 | "
        "attempt_status: PASS; public_status: PASS; hidden_status: PASS |"
    ) in report
    assert (
        "| toy_python_fix_001 | bad.noop | 2 | 2/2 | "
        "attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; "
        "hidden_status: FAIL |"
    ) in report
    assert (
        "| toy_python_fix_001 | bad.public_only | 2 | 2/2 | "
        "attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; "
        "hidden_status: FAIL |"
    ) in report
    assert (
        "| repair_jsonl_deduper | oracle | 2 | 2/2 | "
        "attempt_status: PASS; public_status: PASS; hidden_status: PASS |"
    ) in report

    for record in records:
        attempt_dir = out_dir / record["attempt_artifact_dir"]
        assert (attempt_dir / "attempt.json").is_file()
        assert (attempt_dir / "trace.jsonl").is_file()
        assert (attempt_dir / "final.diff").is_file()
