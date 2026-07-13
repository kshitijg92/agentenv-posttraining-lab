import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.agents.prompts import (
    AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION,
    compute_agent_task_initial_prompt_builder_code_hash,
)
from agentenv.artifacts.payloads import (
    DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION,
    EVAL_TASK_HASHES_SCHEMA_VERSION,
    MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION,
    REPLAY_RESULT_SCHEMA_VERSION,
    TASK_HASH_REPORT_SCHEMA_VERSION,
    ControlCalibrationResultRecord,
    EvalTaskHashes,
    ReplayComparisonRecord,
    ReplayResult,
    TaskHashReport,
    load_agent_control_script_artifact,
    load_agent_task_run_result,
    load_agent_task_view,
    load_attempt_result,
    load_control_calibration_result_records,
    load_control_flake_detection,
    load_decoding_config_provenance,
    load_eval_task_hashes,
    load_model_config_provenance,
    load_prompt_loop_result,
    load_replay_comparison_records,
    load_replay_result,
    load_task_hash_report,
)
from agentenv.controls.agent_control_scripts import AGENT_CONTROL_SCRIPT_SCHEMA_VERSION
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.attempt import AttemptResult


def test_existing_pydantic_payload_loaders_accept_current_shapes(
    tmp_path: Path,
) -> None:
    attempt_path = _write_json(tmp_path / "attempt.json", _attempt_result())
    agent_run_path = _write_json(tmp_path / "agent_task_run.json", _agent_task_run())
    task_view_path = _write_json(tmp_path / "agent_task_view.json", _agent_task_view())
    prompt_loop_path = _write_json(
        tmp_path / "prompt_loop_result.json",
        _prompt_loop_result(),
    )
    control_script_path = _write_json(
        tmp_path / "agent_control_script.json",
        _agent_control_script(),
    )

    assert isinstance(load_attempt_result(attempt_path), AttemptResult)
    assert isinstance(load_agent_task_run_result(agent_run_path), AgentTaskRunResult)
    assert load_agent_task_view(task_view_path).task_id == "task_001"
    assert load_prompt_loop_result(prompt_loop_path).status == "completed"
    assert (
        load_agent_control_script_artifact(control_script_path).schema_version
        == AGENT_CONTROL_SCRIPT_SCHEMA_VERSION
    )


def test_attempt_result_rejects_false_pass_status(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "attempt.json",
        {
            **_attempt_result(),
            "hidden_status": "FAIL",
        },
    )

    with pytest.raises(
        ValidationError,
        match="PASS attempts require public and hidden PASS",
    ):
        load_attempt_result(path)


def test_attempt_result_rejects_pass_without_final_diff_hash(
    tmp_path: Path,
) -> None:
    path = _write_json(
        tmp_path / "attempt.json",
        {
            **_attempt_result(),
            "final_diff_hash": None,
        },
    )

    with pytest.raises(ValidationError, match="PASS attempts require final_diff_hash"):
        load_attempt_result(path)


def test_attempt_result_rejects_bool_duration_ms(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "attempt.json",
        {
            **_attempt_result(),
            "duration_ms": True,
        },
    )

    with pytest.raises(ValidationError, match="valid integer"):
        load_attempt_result(path)


def test_agent_task_run_result_rejects_unscored_nested_attempt(
    tmp_path: Path,
) -> None:
    payload = {
        **_agent_task_run(),
        "status": "agent_loop_failed",
        "prompt_loop_status": "model_error",
        "error_class": "ProviderHTTPError",
        "error_message": "provider failed",
    }
    path = _write_json(tmp_path / "agent_task_run.json", payload)

    with pytest.raises(
        ValidationError,
        match="unscored agent task runs cannot include attempt_result",
    ):
        load_agent_task_run_result(path)


def test_agent_task_run_result_rejects_loop_failure_with_completed_prompt_loop(
    tmp_path: Path,
) -> None:
    payload = {
        **_agent_task_run(),
        "status": "agent_loop_failed",
        "attempt_result": None,
        "candidate_patch_path": None,
        "candidate_patch_hash": None,
        "error_class": "UnexpectedError",
        "error_message": "failed after loop",
    }
    path = _write_json(tmp_path / "agent_task_run.json", payload)

    with pytest.raises(
        ValidationError,
        match="agent loop failures cannot have completed prompt loop",
    ):
        load_agent_task_run_result(path)


def test_task_hash_payload_loaders_validate_schema_versions(tmp_path: Path) -> None:
    eval_hash_path = _write_json(
        tmp_path / "eval_task_hashes.json", _eval_task_hashes()
    )
    report_path = _write_json(tmp_path / "task_hash_report.json", _task_hash_report())

    assert isinstance(load_eval_task_hashes(eval_hash_path), EvalTaskHashes)
    assert isinstance(load_task_hash_report(report_path), TaskHashReport)

    bad_path = _write_json(
        tmp_path / "bad_eval_task_hashes.json",
        {**_eval_task_hashes(), "schema_version": "eval_task_hashes_v999"},
    )
    with pytest.raises(ValidationError, match="Input should be"):
        load_eval_task_hashes(bad_path)


def test_replay_and_control_payload_loaders(tmp_path: Path) -> None:
    replay_result_path = _write_json(tmp_path / "replay_result.json", _replay_result())
    replay_jsonl_path = _write_jsonl(
        tmp_path / "replay_results.jsonl",
        [_replay_comparison_record()],
    )
    control_jsonl_path = _write_jsonl(
        tmp_path / "control_results.jsonl",
        [_control_calibration_record()],
    )

    assert isinstance(load_replay_result(replay_result_path), ReplayResult)
    replay_records = load_replay_comparison_records(replay_jsonl_path)
    assert isinstance(replay_records[0], ReplayComparisonRecord)
    control_records = load_control_calibration_result_records(control_jsonl_path)
    assert isinstance(control_records[0], ControlCalibrationResultRecord)


def test_control_payload_rejects_shape_that_does_not_match_layer(
    tmp_path: Path,
) -> None:
    record = _control_calibration_record()
    record["control_layer"] = "scorer"
    path = _write_jsonl(tmp_path / "control_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="scorer controls require scorer expected payload",
    ):
        load_control_calibration_result_records(path)


def test_control_payload_rejects_false_match_summary(tmp_path: Path) -> None:
    record = _control_calibration_record()
    record["actual"]["agent_run_status"] = "agent_loop_failed"
    record["actual"]["prompt_loop_status"] = "max_turns_exceeded"
    record["actual"]["attempt_status"] = None
    record["actual"]["public_status"] = None
    record["actual"]["hidden_status"] = None
    record["actual"]["error_class"] = "MaxTurnsExceeded"
    path = _write_jsonl(tmp_path / "control_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="match must reflect expected and actual payloads",
    ):
        load_control_calibration_result_records(path)


def test_control_payload_rejects_false_pass_terminal_state(tmp_path: Path) -> None:
    record = {
        "control_run_id": "controls_001",
        "task_id": "task_001",
        "control_layer": "scorer",
        "control_name": "oracle",
        "repeat_index": 0,
        "artifact_dir": "scorer_control_patches/task_001__oracle__repeat_001",
        "expected": {
            "attempt_status": "PASS",
            "public_status": "PASS",
            "hidden_status": "PASS",
        },
        "actual": {
            "scorer_attempt_id": "scorer_attempt_001",
            "attempt_status": "PASS",
            "public_status": "PASS",
            "hidden_status": "PASS",
            "final_diff_hash": "xxh64:diff",
            "error_class": "UnexpectedError",
        },
        "match": True,
    }
    path = _write_jsonl(tmp_path / "control_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="PASS attempts cannot include error_class",
    ):
        load_control_calibration_result_records(path)


def test_control_payload_rejects_pass_without_final_diff_hash(
    tmp_path: Path,
) -> None:
    record = {
        "control_run_id": "controls_001",
        "task_id": "task_001",
        "control_layer": "scorer",
        "control_name": "oracle",
        "repeat_index": 0,
        "artifact_dir": "scorer_control_patches/task_001__oracle__repeat_001",
        "expected": {
            "attempt_status": "PASS",
            "public_status": "PASS",
            "hidden_status": "PASS",
        },
        "actual": {
            "scorer_attempt_id": "scorer_attempt_001",
            "attempt_status": "PASS",
            "public_status": "PASS",
            "hidden_status": "PASS",
            "final_diff_hash": None,
            "error_class": None,
        },
        "match": True,
    }
    path = _write_jsonl(tmp_path / "control_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="PASS scorer controls require final_diff_hash",
    ):
        load_control_calibration_result_records(path)


def test_control_payload_rejects_scored_agent_without_scorer_statuses(
    tmp_path: Path,
) -> None:
    record = _control_calibration_record()
    record["actual"]["attempt_status"] = None
    path = _write_jsonl(tmp_path / "control_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="scored agent controls require scorer statuses",
    ):
        load_control_calibration_result_records(path)


def test_control_payload_accepts_scored_agent_with_failed_scorer_status(
    tmp_path: Path,
) -> None:
    record = _control_calibration_record()
    record["actual"]["attempt_status"] = "HIDDEN_TEST_FAIL"
    record["actual"]["public_status"] = "PASS"
    record["actual"]["hidden_status"] = "FAIL"
    record["actual"]["error_class"] = None
    path = _write_jsonl(tmp_path / "control_results.jsonl", [record])

    loaded = load_control_calibration_result_records(path)

    assert loaded[0].actual.attempt_status == "HIDDEN_TEST_FAIL"


def test_control_payload_rejects_agent_loop_failed_with_completed_loop(
    tmp_path: Path,
) -> None:
    record = _control_calibration_record()
    record["actual"]["agent_run_status"] = "agent_loop_failed"
    record["actual"]["error_class"] = "UnexpectedError"
    record["actual"]["attempt_status"] = None
    record["actual"]["public_status"] = None
    record["actual"]["hidden_status"] = None
    path = _write_jsonl(tmp_path / "control_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="agent loop failures cannot have completed prompt loop",
    ):
        load_control_calibration_result_records(path)


def test_flake_detection_group_rejects_contradictory_drift_details(
    tmp_path: Path,
) -> None:
    payload = _control_flake_detection()
    payload["groups"]["agent"][0]["drifted_repeats"] = [1]
    path = _write_json(tmp_path / "flake_detection.json", payload)

    with pytest.raises(
        ValidationError,
        match="individual_drift_details keys must match drifted_repeats",
    ):
        load_control_flake_detection(path)


def test_flake_detection_group_rejects_drift_outside_repeats(
    tmp_path: Path,
) -> None:
    payload = _control_flake_detection()
    payload["groups"]["agent"][0]["status"] = "drifted"
    payload["groups"]["agent"][0]["drifted_repeats"] = [2]
    payload["groups"]["agent"][0]["individual_drift_details"] = {
        "2": {
            "files": [
                {
                    "path": "manifest.json",
                    "status": "changed",
                    "reference_hash": "xxh64:reference",
                    "actual_hash": "xxh64:actual",
                }
            ]
        }
    }
    payload["status"] = "drifted"
    payload["drifted_groups"] = 1
    path = _write_json(tmp_path / "flake_detection.json", payload)

    with pytest.raises(
        ValidationError,
        match="drifted_repeats must be less than repeats",
    ):
        load_control_flake_detection(path)


def test_replay_result_rejects_inconsistent_counts(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "replay_result.json",
        {**_replay_result(), "matched_attempts": 2},
    )

    with pytest.raises(
        ValidationError,
        match="matched_attempts \\+ mismatched_attempts must equal attempt_count",
    ):
        load_replay_result(path)


def test_replay_result_rejects_bool_attempt_count(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "replay_result.json",
        {
            **_replay_result(),
            "attempt_count": True,
        },
    )

    with pytest.raises(ValidationError, match="valid integer"):
        load_replay_result(path)


def test_replay_result_rejects_false_pass_summary(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "replay_result.json",
        {
            **_replay_result(),
            "status": "PASS",
            "matched_attempts": 0,
            "mismatched_attempts": 1,
        },
    )

    with pytest.raises(
        ValidationError,
        match="PASS replay results cannot include mismatches or errors",
    ):
        load_replay_result(path)


def test_replay_result_rejects_zero_attempt_pass(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "replay_result.json",
        {
            **_replay_result(),
            "attempt_count": 0,
            "matched_attempts": 0,
        },
    )

    with pytest.raises(
        ValidationError,
        match="PASS replay results require attempts",
    ):
        load_replay_result(path)


def test_replay_comparison_rejects_false_match_summary(tmp_path: Path) -> None:
    record = _replay_comparison_record()
    record["field_matches"]["status"] = False
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="matched must reflect field and artifact matches",
    ):
        load_replay_comparison_records(path)


def test_replay_comparison_rejects_partial_field_evidence(tmp_path: Path) -> None:
    record = _replay_comparison_record()
    record["field_matches"] = {"status": True}
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="agent replay comparisons require the full agent field set",
    ):
        load_replay_comparison_records(path)


def test_replay_comparison_rejects_partial_artifact_evidence(tmp_path: Path) -> None:
    record = _replay_comparison_record()
    record["artifact_matches"] = {"manifest.json": True}
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="missing required artifact evidence",
    ):
        load_replay_comparison_records(path)


def test_replay_comparison_rejects_escaping_artifact_ref(tmp_path: Path) -> None:
    record = _replay_comparison_record()
    record["source_artifact_ref"] = "../outside"
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(ValidationError, match="parent traversal"):
        load_replay_comparison_records(path)


def test_replay_comparison_accepts_current_dir_source_artifact_ref(
    tmp_path: Path,
) -> None:
    record = _replay_comparison_record()
    record["source_artifact_ref"] = "."
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    loaded = load_replay_comparison_records(path)

    assert loaded[0].source_artifact_ref == "."


def test_replay_comparison_rejects_current_dir_replay_artifact_ref(
    tmp_path: Path,
) -> None:
    record = _replay_comparison_record()
    record["replay_artifact_ref"] = "."
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(ValidationError, match="parent traversal"):
        load_replay_comparison_records(path)


def test_replay_comparison_rejects_escaping_artifact_match_key(
    tmp_path: Path,
) -> None:
    record = _replay_comparison_record()
    record["artifact_matches"]["../outside"] = True
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(ValidationError, match="parent traversal"):
        load_replay_comparison_records(path)


def test_replay_comparison_rejects_unknown_agent_artifact_match_key(
    tmp_path: Path,
) -> None:
    record = _replay_comparison_record()
    record["artifact_matches"]["bogus.txt"] = True
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(ValidationError, match="unknown artifact evidence"):
        load_replay_comparison_records(path)


def test_replay_comparison_accepts_agent_model_config_artifact_match_key(
    tmp_path: Path,
) -> None:
    record = _replay_comparison_record()
    record["artifact_matches"]["model_config.json"] = False
    record["matched"] = False
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    loaded = load_replay_comparison_records(path)

    assert loaded[0].artifact_matches["model_config.json"] is False
    assert loaded[0].matched is False


def test_replay_comparison_rejects_missing_typed_ids(tmp_path: Path) -> None:
    record = _replay_comparison_record()
    record["source_agent_attempt_id"] = None
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(
        ValidationError,
        match="agent replay comparisons require agent attempt ids",
    ):
        load_replay_comparison_records(path)


def test_replay_comparison_rejects_empty_evidence_maps(tmp_path: Path) -> None:
    record = _replay_comparison_record()
    record["field_matches"] = {}
    path = _write_jsonl(tmp_path / "replay_results.jsonl", [record])

    with pytest.raises(ValidationError, match="at least 1 item"):
        load_replay_comparison_records(path)


def test_task_hash_report_rejects_inconsistent_split_counts(tmp_path: Path) -> None:
    report = _task_hash_report()
    report["split_counts"]["dev"] = 0
    path = _write_json(tmp_path / "task_hash_report.json", report)

    with pytest.raises(ValidationError, match="split_counts must match task records"):
        load_task_hash_report(path)


def test_config_provenance_payloads_are_versioned(tmp_path: Path) -> None:
    model_path = _write_json(
        tmp_path / "model_config.json",
        _model_config_provenance(),
    )
    decoding_path = _write_json(
        tmp_path / "decoding_config.json",
        _decoding_config_provenance(source_path=None, source_hash=None),
    )

    assert load_model_config_provenance(model_path).source_hash == "xxh64:model"
    assert load_decoding_config_provenance(decoding_path).source_path is None

    missing_schema_path = _write_json(
        tmp_path / "missing_schema.json",
        {
            "source_path": "configs/model.yaml",
            "source_hash": "xxh64:model",
            "config": _model_config(),
        },
    )
    with pytest.raises(ValidationError, match="schema_version"):
        load_model_config_provenance(missing_schema_path)


def test_decoding_config_provenance_requires_source_pair(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "decoding_config.json",
        _decoding_config_provenance(
            source_path="configs/decoding.yaml",
            source_hash=None,
        ),
    )

    with pytest.raises(
        ValidationError,
        match="source_path and source_hash must both be set or both null",
    ):
        load_decoding_config_provenance(path)


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _write_jsonl(path: Path, payloads: list[object]) -> Path:
    path.write_text(
        "".join(json.dumps(payload, sort_keys=True) + "\n" for payload in payloads)
    )
    return path


def _attempt_result() -> dict[str, Any]:
    return {
        "scorer_attempt_id": "scorer_attempt_001",
        "task_id": "task_001",
        "task_manifest_path": "tasks/task_001/task.yaml",
        "submission_path": "submission.patch",
        "status": "PASS",
        "public_status": "PASS",
        "hidden_status": "PASS",
        "error_class": None,
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:01Z",
        "duration_ms": 1,
        "final_diff_hash": "xxh64:diff",
        "orchestrator_version": "scorer_attempt_orchestrator_v0",
    }


def _agent_task_run() -> dict[str, Any]:
    return {
        "agent_attempt_id": "agent_attempt_001",
        "task_id": "task_001",
        "task_manifest_path": "tasks/task_001/task.yaml",
        "status": "scored",
        "prompt_loop_status": "completed",
        "candidate_patch_path": "candidate.patch",
        "candidate_patch_hash": "xxh64:candidate",
        "attempt_result": _attempt_result(),
        "error_class": None,
        "error_message": None,
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:01Z",
        "duration_ms": 1,
        "orchestrator_version": "agent_task_run_orchestrator_v0",
    }


def _agent_task_view() -> dict[str, Any]:
    return {
        "task_id": "task_001",
        "instruction": "Fix the bug.",
        "workspace_path": "/tmp/workspace",
        "allowed_tools": ["terminal"],
        "public_checks": ["uv run pytest tests/test_public.py"],
        "max_turns": 3,
        "timeout_seconds": 30,
        "network": "off",
    }


def _prompt_loop_result() -> dict[str, Any]:
    return {
        "task_id": "task_001",
        "prompt_builder_version": AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION,
        "prompt_builder_code_hash": compute_agent_task_initial_prompt_builder_code_hash(),
        "status": "completed",
        "turns_executed": 0,
        "duration_ms": 1,
        "token_usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        },
        "messages": [],
        "model_responses": [],
        "tool_results": [],
        "error_class": None,
        "error_message": None,
    }


def _agent_control_script() -> dict[str, Any]:
    return {
        "schema_version": AGENT_CONTROL_SCRIPT_SCHEMA_VERSION,
        "script": {
            "steps": [
                {
                    "output_text": '{"action":"final_answer","text":"done"}',
                    "finish_reason": "stop_criteria_met",
                    "error_class": None,
                }
            ]
        },
        "expected_result": {
            "prompt_loop_status": "completed",
            "tool_results": None,
        },
    }


def _required_task_file() -> dict[str, Any]:
    return {
        "path": "task.yaml",
        "kind": "file",
        "hash": "xxh64:file",
    }


def _eval_task_hashes() -> dict[str, Any]:
    return {
        "schema_version": EVAL_TASK_HASHES_SCHEMA_VERSION,
        "task_pack_id": "repo_patch_python_v0",
        "selected_task_hash_set": "xxh64:selected",
        "selected_tasks": [
            {
                "task_id": "task_001",
                "split": "dev",
                "task_record_hash": "xxh64:task",
                "task_yaml_hash": "xxh64:yaml",
                "required_task_files_hash": "xxh64:required",
                "full_task_dir_hash": "xxh64:full",
                "required_task_files": [_required_task_file()],
            }
        ],
    }


def _task_hash_report() -> dict[str, Any]:
    return {
        "schema_version": TASK_HASH_REPORT_SCHEMA_VERSION,
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "git_sha_or_unknown": "unknown",
        "task_pack_id": "repo_patch_python_v0",
        "task_pack_path": "data/task_packs/repo_patch_python_v0",
        "task_count": 1,
        "manifest_yaml_hash": "xxh64:manifest",
        "splits_lock_hash": "xxh64:splits",
        "split_counts": {
            "practice": 0,
            "dev": 1,
            "heldout_private": 0,
            "public_calibration": 0,
        },
        "tasks": [
            {
                "task_id": "task_001",
                "split": "dev",
                "task_yaml_hash": "xxh64:yaml",
                "instruction_normalized_hash": "xxh64:instruction",
                "visible_tests_normalized_hash": None,
                "required_task_files_hash": "xxh64:required",
                "full_task_dir_hash": "xxh64:full",
                "extra_task_files": [],
                "manifest_path": "tasks/task_001/task.yaml",
                "required_task_files": [_required_task_file()],
                "task_record_hash": "xxh64:task",
            }
        ],
        "pack_record_hash": "xxh64:pack",
    }


def _replay_result() -> dict[str, Any]:
    return {
        "schema_version": REPLAY_RESULT_SCHEMA_VERSION,
        "replay_run_id": "replay_run_001",
        "status": "PASS",
        "attempt_count": 1,
        "matched_attempts": 1,
        "mismatched_attempts": 0,
        "error_count": 0,
    }


def _replay_comparison_record() -> dict[str, Any]:
    return {
        "comparison_type": "agent_task_run",
        "task_id": "task_001",
        "source_eval_attempt_id": "eval_attempt_001",
        "source_agent_attempt_id": "agent_attempt_source",
        "replayed_agent_attempt_id": "agent_attempt_replayed",
        "source_artifact_ref": "attempts/task_001__attempt_001",
        "source_artifact_path": "/tmp/source",
        "replay_artifact_ref": "attempts/task_001__attempt_001",
        "replay_artifact_path": "/tmp/replay",
        "matched": True,
        "field_matches": {
            "status": True,
            "prompt_loop_status": True,
            "attempt_status": True,
            "candidate_patch_hash": True,
            "error_class": True,
            "error_message": True,
        },
        "artifact_matches": {
            "manifest.json": True,
            "agent_task_run.json": True,
            "error.txt": True,
            "decoding_config.json": True,
            "agent_control_script.json": True,
        },
    }


def _control_calibration_record() -> dict[str, Any]:
    return {
        "control_run_id": "controls_001",
        "task_id": "task_001",
        "control_layer": "agent",
        "control_name": "happy",
        "repeat_index": 0,
        "artifact_dir": "agent_control_scripts/task_001__happy__repeat_001",
        "expected": {
            "prompt_loop_status": "completed",
        },
        "actual": {
            "agent_attempt_id": "agent_attempt_001",
            "agent_run_status": "scored",
            "prompt_loop_status": "completed",
            "tool_results": [],
            "attempt_status": "PASS",
            "public_status": "PASS",
            "hidden_status": "PASS",
            "error_class": None,
        },
        "match": True,
    }


def _control_flake_detection() -> dict[str, Any]:
    return {
        "schema_version": "control_flake_detection_v1",
        "status": "stable",
        "repeats": 2,
        "groups_checked": 1,
        "drifted_groups": 0,
        "groups": {
            "scorer": [],
            "agent": [
                {
                    "task_id": "task_001",
                    "control_name": "happy",
                    "status": "stable",
                    "reference_repeat_index": 0,
                    "drifted_repeats": [],
                    "items_compared": {
                        "normalization": "agent_artifact_normalization_v0",
                        "files": [
                            {
                                "path": "manifest.json",
                                "normalized_hash": "xxh64:manifest",
                            }
                        ],
                    },
                    "individual_drift_details": {},
                }
            ],
        },
        "public_check_idempotency": [],
    }


def _model_config() -> dict[str, Any]:
    return {
        "version": "model_config_v0",
        "provider": "openai_compatible_chat",
        "model_id": "unit-model",
        "api_key_env": None,
        "base_url_env": None,
        "capabilities": {
            "token_usage": "unavailable",
            "supports_seed": False,
            "supports_stop": True,
            "supports_top_k": False,
        },
        "prompt_adapter": None,
        "agent_action_format": "prompt_only",
        "provider_runtime_probe": None,
    }


def _decoding_config() -> dict[str, Any]:
    return {
        "strategy": "greedy",
        "temperature": 0.0,
        "top_p": 1.0,
        "top_k": None,
        "max_new_tokens": 128,
        "num_return_sequences": 1,
        "seed": None,
        "stop": [],
        "timeout_seconds": 30,
    }


def _model_config_provenance() -> dict[str, Any]:
    return {
        "schema_version": MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION,
        "source_path": "configs/models/unit.yaml",
        "source_hash": "xxh64:model",
        "config": _model_config(),
        "provider_runtime": None,
    }


def _decoding_config_provenance(
    *,
    source_path: str | None,
    source_hash: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION,
        "source_path": source_path,
        "source_hash": source_hash,
        "config": _decoding_config(),
    }
