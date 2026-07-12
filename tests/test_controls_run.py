from dataclasses import replace
import json
from pathlib import Path

from agentenv.artifacts.manifests import load_control_calibration_manifest
from agentenv.artifacts.payloads import load_control_calibration_result_records
from agentenv.controls import controls_run as controls_run_module
from agentenv.controls.controls_run import expected_control_outcome, run_controls


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
TASK_IDS = {
    "preserve_cli_error_codes",
    "repair_config_precedence",
    "repair_duration_parser",
    "repair_header_merge",
    "repair_jsonl_deduper",
    "repair_query_encoding",
    "repair_record_chunking",
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


def test_flake_detection_normalizes_ellipsized_pytest_tmp_paths() -> None:
    reference = (
        "CompletedProcess(args=['...pytest-1022/test_a0/input.jsonl'], returncode=0)"
    )
    actual = (
        "CompletedProcess(args=['...pytest-1024/test_a0/input.jsonl'], returncode=0)"
    )
    assert controls_run_module._normalize_text(reference, None) == (
        controls_run_module._normalize_text(actual, None)
    )

    reference_without_first_char = (
        "CompletedProcess(args=['...ytest-1022/test_a0/input.jsonl'], returncode=0)"
    )
    actual_without_first_char = (
        "CompletedProcess(args=['...ytest-1024/test_a0/input.jsonl'], returncode=0)"
    )
    assert controls_run_module._normalize_text(reference_without_first_char, None) == (
        controls_run_module._normalize_text(actual_without_first_char, None)
    )


def test_run_controls_writes_manifest_jsonl_report_and_attempt_artifacts(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "controls"

    control_run = run_controls(TASK_PACK, repeats=2, out_dir=out_dir)

    assert control_run.repeats == 2
    assert control_run.public_check_idempotency_repeats == 2
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
    loaded_records = load_control_calibration_result_records(
        out_dir / "control_results.jsonl"
    )
    assert len(loaded_records) == expected_record_count
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
            happy_actual = records_by_control[
                ("agent", task_id, "happy", repeat_index)
            ]["actual"]
            assert happy_actual["agent_attempt_id"].startswith("agent_attempt_")
            assert "run_id" not in happy_actual
            assert "agent_run_id" not in happy_actual
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
            happy = records_by_control[("agent", task_id, "happy", repeat_index)]
            malformed = records_by_control[
                ("agent", task_id, "malformed", repeat_index)
            ]
            assert "tool_results" not in happy["expected"]
            assert "tool_results" not in malformed["expected"]
            assert {
                "tool_name": "read_file",
                "status": "error",
                "error_class": "InvalidToolInput",
            } in recovery["expected"]["tool_results"]
            assert recovery["actual"]["tool_results"][0] == {
                "tool_name": "read_file",
                "status": "error",
                "error_class": "InvalidToolInput",
            }

    manifest = json.loads((out_dir / "manifest.json").read_text())
    loaded_manifest = load_control_calibration_manifest(out_dir / "manifest.json")
    assert loaded_manifest.control_run_id == control_run.control_run_id
    assert loaded_manifest.record_count == expected_record_count
    assert manifest["artifact_type"] == "control_calibration"
    assert manifest["artifact_schema_version"] == "control_calibration_artifact_v3"
    assert manifest["runtime_provenance"] == control_run.runtime_provenance.model_dump(
        mode="json"
    )
    assert manifest["task_hashes"] == control_run.task_hashes.model_dump(mode="json")
    assert {task["task_id"] for task in manifest["task_hashes"]["selected_tasks"]} == (
        TASK_IDS
    )
    assert manifest["repeats"] == 2
    assert manifest["record_count"] == expected_record_count
    assert len(manifest["records"]) == expected_record_count
    assert manifest["records"] == records
    assert manifest["overall_match"] is True
    flake_detection = manifest["flake_detection"]
    assert flake_detection["schema_version"] == "control_flake_detection_v1"
    assert flake_detection["status"] == "stable"
    assert flake_detection["repeats"] == 2
    assert flake_detection["groups_checked"] == (
        len(TASK_IDS) * len(CONTROL_NAMES) + len(TASK_IDS) * len(AGENT_CONTROL_NAMES)
    )
    assert flake_detection["drifted_groups"] == 0
    assert len(flake_detection["public_check_idempotency"]) == len(TASK_IDS)
    assert {
        calibration["task_id"]
        for calibration in flake_detection["public_check_idempotency"]
    } == TASK_IDS
    assert all(
        calibration["status"] == "IDEMPOTENT"
        for calibration in flake_detection["public_check_idempotency"]
    )
    assert all(
        calibration["repeat_count"] == 2
        for calibration in flake_detection["public_check_idempotency"]
    )
    assert set(flake_detection["groups"]) == {"scorer", "agent"}
    scorer_flake_groups = flake_detection["groups"]["scorer"]
    agent_flake_groups = flake_detection["groups"]["agent"]
    assert {
        (group["task_id"], group["control_name"]) for group in scorer_flake_groups
    } == {
        (task_id, control_name)
        for task_id in TASK_IDS
        for control_name in CONTROL_NAMES
    }
    assert {
        (group["task_id"], group["control_name"]) for group in agent_flake_groups
    } == {
        (task_id, control_name)
        for task_id in TASK_IDS
        for control_name in AGENT_CONTROL_NAMES
    }
    toy_oracle_flake_group = next(
        group
        for group in scorer_flake_groups
        if group["task_id"] == "toy_python_fix_001"
        and group["control_name"] == "oracle"
    )
    assert toy_oracle_flake_group["status"] == "stable"
    assert toy_oracle_flake_group["reference_repeat_index"] == 0
    assert toy_oracle_flake_group["drifted_repeats"] == []
    assert toy_oracle_flake_group["individual_drift_details"] == {}
    assert toy_oracle_flake_group["items_compared"]["normalization"] == (
        "scorer_artifact_normalization_v0"
    )
    assert {
        file_record["path"]
        for file_record in toy_oracle_flake_group["items_compared"]["files"]
    } == {
        "attempt.json",
        "error.txt",
        "final.diff",
        "manifest.json",
        "stderr.txt",
        "stdout.txt",
        "trace.jsonl",
    }
    assert all(
        file_record["normalized_hash"].startswith("xxh64:")
        for file_record in toy_oracle_flake_group["items_compared"]["files"]
    )
    toy_malformed_agent_flake_group = next(
        group
        for group in agent_flake_groups
        if group["task_id"] == "toy_python_fix_001"
        and group["control_name"] == "malformed"
    )
    assert toy_malformed_agent_flake_group["status"] == "stable"
    assert toy_malformed_agent_flake_group["reference_repeat_index"] == 0
    assert toy_malformed_agent_flake_group["drifted_repeats"] == []
    assert toy_malformed_agent_flake_group["individual_drift_details"] == {}
    assert toy_malformed_agent_flake_group["items_compared"]["normalization"] == (
        "agent_artifact_normalization_v0"
    )
    assert {
        file_record["path"]
        for file_record in toy_malformed_agent_flake_group["items_compared"]["files"]
    } == {
        "agent_control_script.json",
        "agent_task_run.json",
        "agent_task_view.json",
        "decoding_config.json",
        "error.txt",
        "prompt_loop_result.json",
        "manifest.json",
    }
    toy_happy_agent_flake_group = next(
        group
        for group in agent_flake_groups
        if group["task_id"] == "toy_python_fix_001" and group["control_name"] == "happy"
    )
    assert {
        file_record["path"]
        for file_record in toy_happy_agent_flake_group["items_compared"]["files"]
    } == {
        "agent_control_script.json",
        "agent_task_run.json",
        "agent_task_view.json",
        "attempt/attempt.json",
        "attempt/error.txt",
        "attempt/final.diff",
        "attempt/manifest.json",
        "attempt/stderr.txt",
        "attempt/stdout.txt",
        "attempt/trace.jsonl",
        "candidate.patch",
        "decoding_config.json",
        "error.txt",
        "prompt_loop_result.json",
        "manifest.json",
    }
    assert all(
        file_record["normalized_hash"].startswith("xxh64:")
        for file_record in toy_happy_agent_flake_group["items_compared"]["files"]
    )
    assert manifest["artifacts"] == {
        "agent_control_scripts": "agent_control_scripts",
        "report": "control_report.md",
        "results": "control_results.jsonl",
        "public_check_idempotency": "public_check_idempotency",
        "scorer_control_patches": "scorer_control_patches",
    }

    report = (out_dir / "control_report.md").read_text()
    assert "# Control Calibration" in report
    assert report.index("## Summary") < report.index("## Flake Detection")
    assert report.index("## Flake Detection") < report.index(
        "## Scorer Control Overview"
    )
    assert report.index("## Scorer Control Overview") < report.index(
        "## Agent Control Overview"
    )
    assert report.index("## Scorer Control Summary") < report.index(
        "## Agent Control Summary"
    )
    assert report.index("## Scorer Record Details") < report.index(
        "## Agent Record Details"
    )
    assert "| control | tasks | records | matches | failures | status |" in report
    assert "| scope | stability | groups checked | drifted groups |" in report
    assert (
        f"| overall | stable | {len(TASK_IDS) * (len(CONTROL_NAMES) + len(AGENT_CONTROL_NAMES))} "
        "| 0 |"
    ) in report
    assert f"| scorer | stable | {len(TASK_IDS) * len(CONTROL_NAMES)} | 0 |" in report
    assert (
        f"| agent | stable | {len(TASK_IDS) * len(AGENT_CONTROL_NAMES)} | 0 |" in report
    )
    assert (
        "Per-file normalized hashes and drift details are in `manifest.json`."
    ) in report
    assert (
        f"| all controls | {len(TASK_IDS)} | {expected_scorer_count} | "
        f"{expected_scorer_count}/{expected_scorer_count} | 0 | "
    ) in report
    per_control_record_count = len(TASK_IDS) * 2
    assert (
        f"| malformed | {len(TASK_IDS)} | {per_control_record_count} | "
        f"{per_control_record_count}/{per_control_record_count} | 0 | "
    ) in report
    assert (
        f"| oracle | {len(TASK_IDS)} | {per_control_record_count} | "
        f"{per_control_record_count}/{per_control_record_count} | 0 | "
    ) in report
    assert "background-color: #dcfce7" in report
    assert ("| toy_python_fix_001 | oracle | 2 | 2/2 | PASS | PASS | PASS |") in report
    assert (
        "| toy_python_fix_001 | malformed | 2 | 2/2 | invalid_model_output |  |"
    ) in report
    assert ("| toy_python_fix_001 | recoverable | 2 | 2/2 | completed | ") in report
    assert (
        "| task_id | control | repeat | expected_attempt | actual_attempt | "
        "expected_public | actual_public | expected_hidden | actual_hidden | "
        "error_class | final_diff_hash | match | artifact_dir |"
    ) in report
    assert (
        "| task_id | control | repeat | expected_prompt_loop | actual_agent_run | "
        "actual_prompt_loop | expected_tool_results | actual_tool_results | "
        "nested_attempt | nested_public | nested_hidden | error_class | match | "
        "artifact_dir |"
    ) in report
    assert (
        "| toy_python_fix_001 | malformed | 1 | invalid_model_output | "
        "agent_loop_failed | invalid_model_output |  | [] |  |  |  | "
        "MalformedModelOutput | PASS | "
        "agent_control_scripts/toy_python_fix_001__malformed__repeat_001 |"
    ) in report

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
            assert (artifact_dir / "agent_control_script.json").is_file()
            assert not (artifact_dir / "work").exists()
            assert not (artifact_dir / "agent_interaction_workspace").exists()
            assert not (artifact_dir / "scoring_workspace").exists()

    for calibration in control_run.public_check_idempotency:
        assert calibration.status == "IDEMPOTENT"
        assert not Path(calibration.normalization_context.workspace_root).exists()
        assert not Path(calibration.normalization_context.runner_temp_root).exists()
        for run in calibration.runs:
            assert run.stdout is not None
            assert run.stderr is not None
            assert (out_dir / run.stdout.path).is_file()
            assert (out_dir / run.stderr.path).is_file()

    drifted_agent_error = (
        out_dir
        / "agent_control_scripts"
        / "toy_python_fix_001__malformed__repeat_002"
        / "error.txt"
    )
    original_agent_error = drifted_agent_error.read_text()
    drifted_agent_error.write_text(original_agent_error + "\nDRIFT\n")
    agent_drifted_flake_detection = controls_run_module._build_flake_detection(
        task_pack_path=control_run.task_pack_path,
        repeats=control_run.repeats,
        records=control_run.records,
        public_check_idempotency=control_run.public_check_idempotency,
    )
    assert agent_drifted_flake_detection.status == "drifted"
    assert agent_drifted_flake_detection.drifted_groups == 1
    agent_drifted_group = next(
        group
        for group in agent_drifted_flake_detection.groups.agent
        if group.task_id == "toy_python_fix_001" and group.control_name == "malformed"
    )
    assert agent_drifted_group.status == "drifted"
    assert agent_drifted_group.drifted_repeats == [1]
    agent_file_drifts = agent_drifted_group.individual_drift_details["1"].files
    assert len(agent_file_drifts) == 1
    agent_file_drift = agent_file_drifts[0]
    assert agent_file_drift.path == "error.txt"
    assert agent_file_drift.status == "changed"
    assert agent_file_drift.actual_hash is not None
    assert agent_file_drift.actual_hash.startswith("xxh64:")
    assert (
        replace(
            control_run, flake_detection=agent_drifted_flake_detection
        ).overall_match
        is False
    )
    drifted_agent_error.write_text(original_agent_error)

    drifted_stdout = (
        out_dir
        / "scorer_control_patches"
        / "toy_python_fix_001__oracle__repeat_002"
        / "stdout.txt"
    )
    drifted_stdout.write_text(drifted_stdout.read_text() + "\nDRIFT\n")
    drifted_flake_detection = controls_run_module._build_flake_detection(
        task_pack_path=control_run.task_pack_path,
        repeats=control_run.repeats,
        records=control_run.records,
        public_check_idempotency=control_run.public_check_idempotency,
    )
    assert drifted_flake_detection.status == "drifted"
    assert drifted_flake_detection.drifted_groups == 1
    drifted_group = next(
        group
        for group in drifted_flake_detection.groups.scorer
        if group.task_id == "toy_python_fix_001" and group.control_name == "oracle"
    )
    assert drifted_group.status == "drifted"
    assert drifted_group.drifted_repeats == [1]
    file_drifts = drifted_group.individual_drift_details["1"].files
    assert len(file_drifts) == 1
    file_drift = file_drifts[0]
    assert file_drift.path == "stdout.txt"
    assert file_drift.status == "changed"
    assert file_drift.reference_hash == next(
        file_record.normalized_hash
        for file_record in drifted_group.items_compared.files
        if file_record.path == "stdout.txt"
    )
    assert file_drift.actual_hash is not None
    assert file_drift.actual_hash.startswith("xxh64:")
    assert file_drift.actual_hash != file_drift.reference_hash
    assert (
        replace(control_run, flake_detection=drifted_flake_detection).overall_match
        is False
    )
