import copy
from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.trajectories.schema import LeakageEvidence, TrajectoryRecord


def _artifact(path: str) -> dict[str, str]:
    return {"path": path, "content_hash": "xxh64:abc123"}


def _base_record_payload() -> dict[str, Any]:
    return {
        "schema_version": "trajectory_record_v0",
        "identity": {
            "trajectory_id": "traj_001",
            "run_id": "eval_run_001",
            "task_id": "repair_jsonl_deduper",
            "policy_id": "agent-happy",
            "attempt_index": 0,
            "attempt_id": "attempt_001",
        },
        "source_provenance": {
            "task_id": "repair_jsonl_deduper",
            "split": "dev",
            "scoring_contract": "scoring_contract_v0",
            "task_manifest_path": (
                "data/task_packs/repo_patch_python_v0/tasks/"
                "repair_jsonl_deduper/task.yaml"
            ),
            "task_manifest_hash": "xxh64:taskmanifest",
            "splits_lock_path": "data/task_packs/repo_patch_python_v0/splits.lock.json",
            "splits_lock_hash": "xxh64:splits",
            "eval_config_path": "configs/eval/eval_quality_gate_repo_patch_python_v0.yaml",
            "eval_config_hash": "xxh64:evalconfig",
        },
        "policy": {
            "policy_id": "agent-happy",
            "policy_name": "agent-happy",
            "policy_spec": {
                "type": "agent_control_script",
                "control": "happy",
                "attempts": 1,
                "replay": {"repeats": 0},
            },
        },
        "statuses": {
            "agent_task_run_status": "scored",
            "prompt_loop_status": "completed",
            "attempt_status": "PASS",
            "public_status": "PASS",
            "hidden_status": "PASS",
            "grade_state": "scored_pass",
            "task_success": True,
        },
        "artifacts": {
            "eval_run_path": "experiments/runs/eval_quality_gate_repo_patch_python_v0",
            "eval_matrix_json": _artifact("eval_matrix.json"),
            "run_manifest_json": _artifact("run_manifest.json"),
            "agent_task_run_json": _artifact("agent_task_run.json"),
            "prompt_loop_result_json": _artifact("prompt_loop_result.json"),
            "candidate_patch": _artifact("candidate.patch"),
            "attempt_json": _artifact("attempt/attempt.json"),
            "trace_jsonl": _artifact("attempt/trace.jsonl"),
            "stdout": _artifact("attempt/stdout.txt"),
            "stderr": _artifact("attempt/stderr.txt"),
            "error_txt": _artifact("error.txt"),
            "final_diff": _artifact("attempt/final.diff"),
        },
        "reward_components": {
            "reward_config_hash": "xxh64:rewardconfig",
            "reward_code_hash": "xxh64:rewardcode",
            "public_validator_success": True,
            "hidden_validator_success": True,
            "model_output_format_valid": True,
            "model_tool_usage_valid": True,
            "orchestration_failure": False,
            "reward_hack_flag": False,
        },
        "leakage": {
            "canary_hash": "xxh64:canary",
            "canary_leaked": False,
            "hidden_validators_visible_to_model": False,
            "leakage_check_version": "leakage_check_v0",
        },
        "training_eligibility": {
            "analysis_allowed": True,
            "positive_sft_allowed": True,
            "negative_example_allowed": False,
            "preference_data_allowed": True,
            "eligibility_reason": "dev successful no-shortcut trajectory",
        },
        "review": {
            "review_status": "not_reviewed",
            "review_id": None,
            "reviewer_id": None,
            "review_decision": None,
            "review_notes_ref": None,
        },
    }


def _record_payload(**updates: Any) -> dict[str, Any]:
    payload = _base_record_payload()
    for section, section_updates in updates.items():
        if isinstance(section_updates, dict) and isinstance(payload[section], dict):
            payload[section].update(section_updates)
        else:
            payload[section] = section_updates
    return payload


def test_trajectory_record_accepts_successful_agent_attempt() -> None:
    record = TrajectoryRecord.model_validate(_base_record_payload())

    assert record.identity.trajectory_id == "traj_001"
    assert record.source_provenance.scoring_contract == "scoring_contract_v0"
    assert record.statuses.task_success is True
    assert record.reward_components.reward_version == "reward_components_v0"
    assert record.training_eligibility.positive_sft_allowed is True


def test_trajectory_record_accepts_cannot_grade_record() -> None:
    payload = _record_payload(
        identity={"attempt_id": None},
        statuses={
            "agent_task_run_status": "agent_loop_failed",
            "prompt_loop_status": "max_turns_exceeded",
            "attempt_status": None,
            "public_status": None,
            "hidden_status": None,
            "grade_state": "cannot_grade",
            "task_success": False,
        },
        reward_components={
            "public_validator_success": None,
            "hidden_validator_success": None,
            "orchestration_failure": False,
        },
        training_eligibility={
            "positive_sft_allowed": False,
            "negative_example_allowed": True,
            "preference_data_allowed": False,
            "eligibility_reason": "agent loop did not produce a scorable patch",
        },
    )

    record = TrajectoryRecord.model_validate(payload)

    assert record.statuses.grade_state == "cannot_grade"
    assert record.statuses.task_success is False
    assert record.statuses.attempt_status is None


def test_task_success_requires_scored_pass_grade_state() -> None:
    payload = _record_payload(
        statuses={
            "attempt_status": "HIDDEN_TEST_FAIL",
            "public_status": "PASS",
            "hidden_status": "FAIL",
            "grade_state": "scored_fail",
            "task_success": True,
        },
        training_eligibility={"positive_sft_allowed": False},
    )

    with pytest.raises(
        ValidationError,
        match="task_success=true requires grade_state=scored_pass",
    ):
        TrajectoryRecord.model_validate(payload)


def test_cannot_grade_forbids_task_success() -> None:
    payload = _record_payload(
        statuses={
            "attempt_status": None,
            "public_status": None,
            "hidden_status": None,
            "grade_state": "cannot_grade",
            "task_success": True,
        },
        training_eligibility={"positive_sft_allowed": False},
    )

    with pytest.raises(
        ValidationError,
        match="grade_state=cannot_grade requires task_success=false",
    ):
        TrajectoryRecord.model_validate(payload)


def test_positive_sft_requires_task_success() -> None:
    payload = _record_payload(
        statuses={
            "attempt_status": "HIDDEN_TEST_FAIL",
            "public_status": "PASS",
            "hidden_status": "FAIL",
            "grade_state": "scored_fail",
            "task_success": False,
        },
        training_eligibility={
            "positive_sft_allowed": True,
            "eligibility_reason": "bad positive SFT gate",
        },
    )

    with pytest.raises(
        ValidationError,
        match="positive_sft_allowed=true requires task_success=true",
    ):
        TrajectoryRecord.model_validate(payload)


@pytest.mark.parametrize("split", ["heldout_private", "public_calibration"])
def test_positive_sft_forbidden_for_non_trainable_splits(split: str) -> None:
    payload = _record_payload(source_provenance={"split": split})

    with pytest.raises(
        ValidationError,
        match=(
            "positive_sft_allowed=true is forbidden for heldout_private "
            "and public_calibration splits"
        ),
    ):
        TrajectoryRecord.model_validate(payload)


def test_leakage_evidence_rejects_raw_canary_text() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LeakageEvidence.model_validate(
            {
                "canary_hash": "xxh64:canary",
                "canary_leaked": False,
                "hidden_validators_visible_to_model": False,
                "leakage_check_version": "leakage_check_v0",
                "raw_canary": "CANARY_PRIVATE_TEXT",
            }
        )


def test_positive_sft_forbids_leakage() -> None:
    payload = _record_payload(leakage={"canary_leaked": True})

    with pytest.raises(
        ValidationError,
        match="positive_sft_allowed=true forbids canary leakage",
    ):
        TrajectoryRecord.model_validate(payload)


def test_not_reviewed_records_cannot_include_review_details() -> None:
    payload = _record_payload(review={"reviewer_id": "kshitij"})

    with pytest.raises(
        ValidationError,
        match="not_reviewed records cannot include review details",
    ):
        TrajectoryRecord.model_validate(payload)


def test_reviewed_records_require_review_decision() -> None:
    payload = _record_payload(
        review={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "kshitij",
            "review_decision": None,
        }
    )

    with pytest.raises(
        ValidationError,
        match="reviewed records require review_decision",
    ):
        TrajectoryRecord.model_validate(payload)


def test_reviewed_records_accept_review_decision_enum() -> None:
    payload = _record_payload(
        review={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "kshitij",
            "review_decision": "accepted",
            "review_notes_ref": _artifact("review_notes.jsonl"),
        }
    )

    record = TrajectoryRecord.model_validate(payload)

    assert record.review.review_decision == "accepted"


def test_reviewed_records_reject_freeform_review_decision() -> None:
    payload = _record_payload(
        review={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "kshitij",
            "review_decision": "looks pretty good to me",
        }
    )

    with pytest.raises(ValidationError, match="Input should be"):
        TrajectoryRecord.model_validate(payload)


def test_identity_and_provenance_task_ids_must_match() -> None:
    payload = _record_payload(identity={"task_id": "other_task"})

    with pytest.raises(
        ValidationError,
        match="identity.task_id must match source_provenance.task_id",
    ):
        TrajectoryRecord.model_validate(payload)


def test_helper_payloads_do_not_share_mutable_state() -> None:
    first = _base_record_payload()
    second = copy.deepcopy(first)
    second["identity"]["trajectory_id"] = "traj_002"

    assert first["identity"]["trajectory_id"] == "traj_001"
    assert second["identity"]["trajectory_id"] == "traj_002"
