import json
from pathlib import Path

from agentenv.controls.controls_run import expected_control_outcome, run_controls


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
TASK_IDS = {
    "preserve_cli_error_codes",
    "repair_config_precedence",
    "repair_jsonl_deduper",
    "toy_python_fix_001",
}
CONTROL_NAMES = {"oracle", "bad.noop", "bad.public_only"}
AGENT_CONTROL_NAMES = {
    "happy",
    "malformed",
    "recoverable",
}


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
    expected_scorer_count = len(TASK_IDS) * len(CONTROL_NAMES) * 2
    expected_agent_count = len(TASK_IDS) * len(AGENT_CONTROL_NAMES) * 2
    expected_record_count = expected_scorer_count + expected_agent_count
    assert len(control_run.records) == expected_record_count
    assert control_run.overall_match is True
    assert all(record.match for record in control_run.records)

    records = [
        json.loads(line)
        for line in (out_dir / "control_results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(records) == expected_record_count
    assert {record["task_id"] for record in records} == TASK_IDS
    assert {record["control_layer"] for record in records} == {"scorer", "agent"}
    assert {
        record["control_name"]
        for record in records
        if record["control_layer"] == "scorer"
    } == CONTROL_NAMES
    assert {
        record["control_name"]
        for record in records
        if record["control_layer"] == "agent"
    } == AGENT_CONTROL_NAMES
    assert {record["repeat_index"] for record in records} == {0, 1}
    assert all(record["match"] is True for record in records)

    records_by_control = {
        (
            record["control_layer"],
            record["task_id"],
            record["control_name"],
            record["repeat_index"],
        ): record
        for record in records
    }
    for task_id in TASK_IDS:
        for repeat_index in (0, 1):
            assert (
                records_by_control[("scorer", task_id, "oracle", repeat_index)][
                    "actual"
                ]["attempt_status"]
                == "PASS"
            )
            assert (
                records_by_control[("scorer", task_id, "bad.noop", repeat_index)][
                    "actual"
                ]["attempt_status"]
                == "HIDDEN_TEST_FAIL"
            )
            assert (
                records_by_control[
                    ("scorer", task_id, "bad.public_only", repeat_index)
                ]["actual"]["hidden_status"]
                == "FAIL"
            )
            assert (
                records_by_control[("agent", task_id, "happy", repeat_index)]["actual"][
                    "prompt_loop_status"
                ]
                == "completed"
            )
            assert (
                records_by_control[("agent", task_id, "malformed", repeat_index)][
                    "actual"
                ]["prompt_loop_status"]
                == "invalid_model_output"
            )
            recovery = records_by_control[
                ("agent", task_id, "recoverable", repeat_index)
            ]
            assert recovery["actual"]["prompt_loop_status"] == "completed"
            assert recovery["actual"]["tool_results"][0] == {
                "tool_name": "read_file",
                "status": "error",
                "error_class": "InvalidToolInput",
            }

    manifest = json.loads((out_dir / "control_run_manifest.json").read_text())
    assert manifest["artifact_version"] == "control_run_v0"
    assert manifest["repeats"] == 2
    assert manifest["record_count"] == expected_record_count
    assert len(manifest["records"]) == expected_record_count
    assert manifest["overall_match"] is True
    assert manifest["artifacts"] == {
        "agent_control_scripts": "agent_control_scripts",
        "report": "control_report.md",
        "results": "control_results.jsonl",
        "scorer_control_patches": "scorer_control_patches",
    }

    report = (out_dir / "control_report.md").read_text()
    assert "# Control Calibration" in report
    assert report.index("## Control Overview") < report.index("## Control Summary")
    assert (
        "| layer | control | tasks | records | matches | failures | status |" in report
    )
    assert "| agent | all controls | 4 | 24 | 24/24 | 0 | " in report
    assert "| agent | malformed | 4 | 8 | 8/8 | 0 | " in report
    assert "| scorer | all controls | 4 | 24 | 24/24 | 0 | " in report
    assert "| scorer | oracle | 4 | 8 | 8/8 | 0 | " in report
    assert "background-color: #dcfce7" in report
    assert (
        "| scorer | toy_python_fix_001 | oracle | 2 | 2/2 | "
        '{"attempt_status": "PASS", "hidden_status": "PASS", '
        '"public_status": "PASS"} |'
    ) in report
    assert (
        "| agent | toy_python_fix_001 | malformed | 2 | 2/2 | "
        '{"prompt_loop_status": "invalid_model_output"} |'
    ) in report
    assert ("| agent | toy_python_fix_001 | recoverable | 2 | 2/2 | ") in report

    for record in records:
        artifact_dir = out_dir / record["artifact_dir"]
        if record["control_layer"] == "scorer":
            assert (artifact_dir / "attempt.json").is_file()
            assert (artifact_dir / "trace.jsonl").is_file()
            assert (artifact_dir / "final.diff").is_file()
        else:
            assert (artifact_dir / "agent_task_run.json").is_file()
            assert (artifact_dir / "prompt_loop_result.json").is_file()
            assert (artifact_dir / "decoding_config.json").is_file()
            assert not (artifact_dir / "work").exists()
            assert not (artifact_dir / "agent_interaction_workspace").exists()
            assert not (artifact_dir / "scoring_workspace").exists()
