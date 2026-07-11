from pathlib import Path

from agentenv.artifacts.payloads import ControlFlakeDetection, EvalTaskHashes
from agentenv.audits.runtime import (
    capture_harness_runtime_provenance,
    harness_repo_root,
)
from agentenv.controls.controls_run import ControlRecord, ControlRun
from agentenv.controls.reporting import render_control_report


def test_render_control_report_from_control_run_dataclasses(tmp_path: Path) -> None:
    out_dir = tmp_path / "controls"
    control_run = ControlRun(
        control_run_id="controls_test",
        task_pack_path=Path("/repo/task_pack"),
        out_dir=out_dir,
        repeats=2,
        public_check_idempotency_repeats=2,
        created_at="2026-07-01T00:00:00Z",
        runtime_provenance=capture_harness_runtime_provenance(harness_repo_root()),
        task_hashes=EvalTaskHashes.model_validate(
            {
                "schema_version": "eval_task_hashes_v0",
                "task_pack_id": "unit_task_pack",
                "selected_task_hash_set": "xxh64:task-set",
                "selected_tasks": [
                    {
                        "task_id": "task_a",
                        "split": "practice",
                        "task_record_hash": "xxh64:task-record",
                        "task_yaml_hash": "xxh64:task-yaml",
                        "required_task_files_hash": "xxh64:required",
                        "full_task_dir_hash": "xxh64:full",
                        "required_task_files": [],
                    }
                ],
            }
        ),
        records=[
            ControlRecord(
                task_id="task_a",
                control_layer="scorer",
                control_name="oracle",
                repeat_index=0,
                artifact_dir=out_dir
                / "scorer_control_patches/task_a__oracle__repeat_001",
                expected={
                    "attempt_status": "PASS",
                    "public_status": "PASS",
                    "hidden_status": "PASS",
                },
                actual={
                    "attempt_status": "PASS",
                    "public_status": "PASS",
                    "hidden_status": "PASS",
                    "error_class": None,
                    "final_diff_hash": "xxh64:abc",
                },
                match=True,
            ),
            ControlRecord(
                task_id="task_a",
                control_layer="agent",
                control_name="malformed",
                repeat_index=0,
                artifact_dir=out_dir
                / "agent_control_scripts/task_a__malformed__repeat_001",
                expected={
                    "prompt_loop_status": "invalid_model_output",
                },
                actual={
                    "agent_run_status": "agent_loop_failed",
                    "prompt_loop_status": "invalid_model_output",
                    "tool_results": [],
                    "attempt_status": None,
                    "public_status": None,
                    "hidden_status": None,
                    "error_class": "MalformedModelOutput",
                },
                match=True,
            ),
        ],
        flake_detection=ControlFlakeDetection.model_validate(
            {
                "schema_version": "control_flake_detection_v1",
                "status": "drifted",
                "repeats": 2,
                "groups_checked": 2,
                "drifted_groups": 1,
                "groups": {
                    "scorer": [
                        {
                            "task_id": "task_a",
                            "control_name": "oracle",
                            "status": "drifted",
                            "reference_repeat_index": 0,
                            "drifted_repeats": [1],
                            "items_compared": {
                                "normalization": "test_normalization_v0",
                                "files": [
                                    {
                                        "path": "attempt.json",
                                        "normalized_hash": "xxh64:reference",
                                    }
                                ],
                            },
                            "individual_drift_details": {
                                "1": {
                                    "files": [
                                        {
                                            "path": "attempt.json",
                                            "status": "changed",
                                            "reference_hash": "xxh64:reference",
                                            "actual_hash": "xxh64:actual",
                                        }
                                    ]
                                }
                            },
                        }
                    ],
                    "agent": [
                        {
                            "task_id": "task_a",
                            "control_name": "malformed",
                            "status": "stable",
                            "reference_repeat_index": 0,
                            "drifted_repeats": [],
                            "items_compared": {
                                "normalization": "test_normalization_v0",
                                "files": [
                                    {
                                        "path": "agent_task_run.json",
                                        "normalized_hash": "xxh64:stable",
                                    }
                                ],
                            },
                            "individual_drift_details": {},
                        }
                    ],
                },
                "public_check_idempotency": [],
            }
        ),
    )

    report = render_control_report(control_run)

    assert report.startswith("# Control Calibration\n")
    assert "- Control run ID: controls_test" in report
    assert "- Overall: FAIL" in report
    assert report.index("## Flake Detection") < report.index(
        "## Scorer Control Overview"
    )
    assert "| overall | drifted | 2 | 1 |" in report
    assert "| scorer | drifted | 1 | 1 |" in report
    assert "| agent | stable | 1 | 0 |" in report
    assert (
        "Per-file normalized hashes and drift details are in `manifest.json`."
    ) in report
    assert "| all controls | 1 | 1 | 1/1 | 0 | " in report
    assert "| oracle | 1 | 1 | 1/1 | 0 | " in report
    assert "| malformed | 1 | 1 | 1/1 | 0 | " in report
    assert "| task_a | oracle | 1 | 1/1 | PASS | PASS | PASS |" in report
    assert "| task_a | malformed | 1 | 1/1 | invalid_model_output |  |" in report
    assert (
        "| task_a | oracle | 1 | PASS | PASS | PASS | PASS | PASS | PASS |  | "
        "xxh64:abc | PASS | scorer_control_patches/task_a__oracle__repeat_001 |"
    ) in report
    assert (
        "| task_a | malformed | 1 | invalid_model_output | agent_loop_failed | "
        "invalid_model_output |  | [] |  |  |  | MalformedModelOutput | PASS | "
        "agent_control_scripts/task_a__malformed__repeat_001 |"
    ) in report
