import copy
from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.trajectories.schema import (
    LeakageEvidence,
    TrajectoryRecord,
    TrajectoryReviewRecord,
    list_reward_component_signal_field_names,
)


def _artifact(path: str) -> dict[str, str]:
    return {"path": path, "content_hash": "xxh64:abc123"}


def _base_record_payload() -> dict[str, Any]:
    return {
        "schema_version": "trajectory_record_v0",
        "identity": {
            "trajectory_id": "traj_001",
            "eval_suite_id": "eval_suite_001",
            "eval_run_id": "eval_run_001",
            "eval_attempt_id": "eval_attempt_001",
            "task_id": "repair_jsonl_deduper",
            "policy_id": "agent-happy",
            "attempt_index": 0,
            "agent_attempt_id": "agent_attempt_001",
            "scorer_attempt_id": "scorer_attempt_001",
            "replay_run_id": None,
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
            "eval_suite_json": _artifact("eval_suite.json"),
            "manifest_json": _artifact("manifest.json"),
            "agent_task_run_json": _artifact("agent_task_run.json"),
            "agent_task_view_json": _artifact("agent_task_view.json"),
            "prompt_loop_result_json": _artifact("prompt_loop_result.json"),
            "decoding_config_json": _artifact("decoding_config.json"),
            "model_config_json": None,
            "agent_control_script_json": _artifact("agent_control_script.json"),
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
        },
        "reward_hack_detection": {
            "detector_version": "reward_hack_detector_v0",
            "check_catalogue_hash": "xxh64:catalogue",
            "evaluation_status": "complete",
            "finding_classification": "not_detected",
            "check_results": [
                {
                    "exploit_check_id": "no_op_patch.submitted_patch_text",
                    "exploit_classification": "no_op_patch",
                    "check_status": "not_detected",
                    "finding_classification": None,
                    "evidence_artifacts": [],
                    "error_class": None,
                    "error_message": None,
                }
            ],
        },
        "leakage": {
            "canary_hash": "xxh64:canary",
            "canary_leaked": False,
            "hidden_validators_visible_to_model": False,
            "leakage_check_version": "leakage_check_v0",
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
    assert record.identity.eval_run_id == "eval_run_001"
    assert record.identity.eval_attempt_id == "eval_attempt_001"
    assert record.identity.agent_attempt_id == "agent_attempt_001"
    assert record.identity.scorer_attempt_id == "scorer_attempt_001"
    assert record.source_provenance.scoring_contract == "scoring_contract_v0"
    assert record.statuses.task_success is True
    assert record.reward_components.reward_version == "reward_components_v0"
    assert "training_eligibility" not in record.model_dump(mode="json")


def test_reward_component_signal_field_names_are_derived_from_schema() -> None:
    assert list_reward_component_signal_field_names() == (
        "public_validator_success",
        "hidden_validator_success",
        "model_output_format_valid",
        "model_tool_usage_valid",
        "orchestration_failure",
    )


def test_trajectory_record_accepts_missing_eval_suite_id() -> None:
    payload = _record_payload(identity={"eval_suite_id": None})

    record = TrajectoryRecord.model_validate(payload)

    assert record.identity.eval_suite_id is None


def test_trajectory_record_accepts_scorer_only_attempt() -> None:
    payload = _record_payload(
        identity={"agent_attempt_id": None},
        statuses={
            "agent_task_run_status": None,
            "prompt_loop_status": None,
        },
        artifacts={
            "agent_task_run_json": None,
            "agent_task_view_json": None,
            "prompt_loop_result_json": None,
            "decoding_config_json": None,
            "model_config_json": None,
            "agent_control_script_json": None,
            "candidate_patch": None,
        },
        reward_components={
            "model_output_format_valid": None,
            "model_tool_usage_valid": None,
        },
    )

    record = TrajectoryRecord.model_validate(payload)

    assert record.identity.agent_attempt_id is None
    assert record.identity.scorer_attempt_id == "scorer_attempt_001"
    assert record.statuses.task_success is True


def test_trajectory_record_rejects_embedded_training_eligibility() -> None:
    payload = _base_record_payload()
    payload["training_eligibility"] = {
        "analysis_allowed": True,
        "positive_sft_allowed": True,
    }

    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        TrajectoryRecord.model_validate(payload)


def test_scored_agent_trajectory_requires_candidate_patch_ref() -> None:
    payload = _record_payload(
        artifacts={"candidate_patch": None},
    )

    with pytest.raises(
        ValidationError,
        match="scored agent trajectories require candidate_patch",
    ):
        TrajectoryRecord.model_validate(payload)


def test_trajectory_record_rejects_scorer_only_record_with_agent_artifacts() -> None:
    payload = _record_payload(
        identity={"agent_attempt_id": None},
        statuses={
            "agent_task_run_status": None,
            "prompt_loop_status": None,
        },
    )

    with pytest.raises(
        ValidationError,
        match="agent artifact refs require identity.agent_attempt_id",
    ):
        TrajectoryRecord.model_validate(payload)


def test_trajectory_record_accepts_cannot_grade_record() -> None:
    payload = _record_payload(
        identity={
            "scorer_attempt_id": None,
            "replay_run_id": "replay_run_001",
        },
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
    )

    record = TrajectoryRecord.model_validate(payload)

    assert record.statuses.grade_state == "cannot_grade"
    assert record.statuses.task_success is False
    assert record.statuses.attempt_status is None
    assert record.identity.scorer_attempt_id is None
    assert record.identity.replay_run_id == "replay_run_001"


def test_task_success_requires_scored_pass_grade_state() -> None:
    payload = _record_payload(
        statuses={
            "attempt_status": "HIDDEN_TEST_FAIL",
            "public_status": "PASS",
            "hidden_status": "FAIL",
            "grade_state": "scored_fail",
            "task_success": True,
        },
    )

    with pytest.raises(
        ValidationError,
        match="task_success=true requires grade_state=scored_pass",
    ):
        TrajectoryRecord.model_validate(payload)


def test_statuses_reject_scored_agent_with_non_completed_prompt_loop() -> None:
    payload = _record_payload(
        statuses={
            "prompt_loop_status": "model_error",
            "grade_state": "scored_pass",
            "task_success": True,
        }
    )

    with pytest.raises(
        ValidationError,
        match="scored agent trajectories require completed prompt loop",
    ):
        TrajectoryRecord.model_validate(payload)


def test_statuses_reject_agent_loop_failed_with_completed_prompt_loop() -> None:
    payload = _record_payload(
        statuses={
            "agent_task_run_status": "agent_loop_failed",
            "prompt_loop_status": "completed",
            "attempt_status": None,
            "public_status": None,
            "hidden_status": None,
            "grade_state": "cannot_grade",
            "task_success": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="agent loop failures cannot have completed prompt loop",
    ):
        TrajectoryRecord.model_validate(payload)


def test_statuses_reject_inconsistent_attempt_checks() -> None:
    payload = _record_payload(
        statuses={
            "attempt_status": "PUBLIC_TEST_FAIL",
            "public_status": "PASS",
            "hidden_status": "NOT_RUN",
            "grade_state": "scored_fail",
            "task_success": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="PUBLIC_TEST_FAIL attempts have inconsistent check statuses",
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
    )

    with pytest.raises(
        ValidationError,
        match="grade_state=cannot_grade requires task_success=false",
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


def test_artifact_refs_reject_parent_traversal() -> None:
    payload = _record_payload(
        artifacts={
            "manifest_json": _artifact("../manifest.json"),
        }
    )

    with pytest.raises(ValidationError, match="parent traversal"):
        TrajectoryRecord.model_validate(payload)


def test_reward_orchestration_failure_cannot_contradict_terminal_status() -> None:
    payload = _record_payload(
        reward_components={"orchestration_failure": True},
    )

    with pytest.raises(
        ValidationError,
        match="orchestration_failure must reflect orchestrator terminal statuses",
    ):
        TrajectoryRecord.model_validate(payload)


def test_reward_orchestration_failure_must_reflect_terminal_status() -> None:
    payload = _record_payload(
        identity={"scorer_attempt_id": None},
        statuses={
            "agent_task_run_status": "orchestrator_error",
            "prompt_loop_status": None,
            "attempt_status": None,
            "public_status": None,
            "hidden_status": None,
            "grade_state": "cannot_grade",
            "task_success": False,
        },
        artifacts={
            "candidate_patch": None,
            "attempt_json": None,
            "trace_jsonl": None,
            "stdout": None,
            "stderr": None,
            "final_diff": None,
        },
        reward_components={
            "public_validator_success": None,
            "hidden_validator_success": None,
            "model_output_format_valid": None,
            "model_tool_usage_valid": None,
            "orchestration_failure": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="orchestration_failure must reflect orchestrator terminal statuses",
    ):
        TrajectoryRecord.model_validate(payload)


def test_reward_validator_success_must_reflect_statuses() -> None:
    payload = _record_payload(
        statuses={
            "attempt_status": "HIDDEN_TEST_FAIL",
            "public_status": "PASS",
            "hidden_status": "FAIL",
            "grade_state": "scored_fail",
            "task_success": False,
        },
        reward_components={
            "public_validator_success": True,
            "hidden_validator_success": True,
        },
    )

    with pytest.raises(
        ValidationError,
        match="hidden_validator_success must reflect hidden_status",
    ):
        TrajectoryRecord.model_validate(payload)


def test_reward_model_output_format_must_reflect_prompt_loop_status() -> None:
    payload = _record_payload(
        identity={"scorer_attempt_id": None},
        statuses={
            "agent_task_run_status": "agent_loop_failed",
            "prompt_loop_status": "invalid_model_output",
            "attempt_status": None,
            "public_status": None,
            "hidden_status": None,
            "grade_state": "cannot_grade",
            "task_success": False,
        },
        artifacts={
            "candidate_patch": None,
            "attempt_json": None,
            "trace_jsonl": None,
            "stdout": None,
            "stderr": None,
            "final_diff": None,
        },
        reward_components={
            "public_validator_success": None,
            "hidden_validator_success": None,
            "model_output_format_valid": True,
            "model_tool_usage_valid": None,
        },
    )

    with pytest.raises(
        ValidationError,
        match="model_output_format_valid must reflect prompt_loop_status",
    ):
        TrajectoryRecord.model_validate(payload)


def test_reward_tool_usage_must_reflect_prompt_loop_status() -> None:
    payload = _record_payload(
        identity={"scorer_attempt_id": None},
        statuses={
            "agent_task_run_status": "agent_loop_failed",
            "prompt_loop_status": "terminal_tool_error",
            "attempt_status": None,
            "public_status": None,
            "hidden_status": None,
            "grade_state": "cannot_grade",
            "task_success": False,
        },
        artifacts={
            "candidate_patch": None,
            "attempt_json": None,
            "trace_jsonl": None,
            "stdout": None,
            "stderr": None,
            "final_diff": None,
        },
        reward_components={
            "public_validator_success": None,
            "hidden_validator_success": None,
            "model_output_format_valid": True,
            "model_tool_usage_valid": True,
        },
    )

    with pytest.raises(
        ValidationError,
        match="model_tool_usage_valid must reflect prompt_loop_status",
    ):
        TrajectoryRecord.model_validate(payload)


def test_detected_reward_hack_requires_present_hash_pinned_evidence() -> None:
    payload = _record_payload(
        reward_hack_detection={
            "evaluation_status": "complete",
            "finding_classification": "ambiguous",
            "check_results": [
                {
                    "exploit_check_id": "no_op_patch.submitted_patch_text",
                    "exploit_classification": "no_op_patch",
                    "check_status": "detected",
                    "finding_classification": "ambiguous",
                    "evidence_artifacts": ["missing_artifact"],
                    "error_class": None,
                    "error_message": None,
                }
            ],
        }
    )

    with pytest.raises(
        ValidationError,
        match="reward-hack evidence must reference a present trajectory artifact",
    ):
        TrajectoryRecord.model_validate(payload)


def _base_review_payload() -> dict[str, Any]:
    return {
        "schema_version": "trajectory_review_v0",
        "trajectory_id": "traj_001",
        "eval_attempt_id": "eval_attempt_001",
        "task_id": "repair_jsonl_deduper",
        "policy_id": "agent-happy",
        "review_status": "not_reviewed",
        "review_id": None,
        "reviewer_id": None,
        "review_decision": None,
        "review_notes_ref": None,
        "reward_hack_review": None,
    }


def _review_payload(**updates: Any) -> dict[str, Any]:
    payload = _base_review_payload()
    payload.update(updates)
    return payload


def test_trajectory_record_rejects_embedded_review() -> None:
    payload = _base_record_payload()
    payload["review"] = _base_review_payload()

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TrajectoryRecord.model_validate(payload)


def test_not_reviewed_records_cannot_include_review_details() -> None:
    payload = _review_payload(reviewer_id="kshitij")

    with pytest.raises(
        ValidationError,
        match="not_reviewed records cannot include review details",
    ):
        TrajectoryReviewRecord.model_validate(payload)


def test_reviewed_records_require_review_decision() -> None:
    payload = _review_payload(
        review_status="reviewed",
        review_id="review_001",
        reviewer_id="kshitij",
        review_decision=None,
    )

    with pytest.raises(
        ValidationError,
        match="reviewed records require review_decision",
    ):
        TrajectoryReviewRecord.model_validate(payload)


def test_reviewed_records_accept_review_decision_enum() -> None:
    payload = _review_payload(
        review_status="reviewed",
        review_id="review_001",
        reviewer_id="kshitij",
        review_decision="accepted",
        review_notes_ref=_artifact("review_notes.jsonl"),
    )

    record = TrajectoryReviewRecord.model_validate(payload)

    assert record.review_decision == "accepted"


def test_reward_hack_review_rejects_details_while_not_reviewed() -> None:
    payload = _review_payload(
        reward_hack_review={
            "review_status": "not_reviewed",
            "review_id": "reward_hack_review_001",
            "reviewer_id": None,
            "review_decision": None,
            "review_notes_ref": None,
        }
    )

    with pytest.raises(
        ValidationError,
        match="not_reviewed reward-hack reviews cannot include review details",
    ):
        TrajectoryReviewRecord.model_validate(payload)


def test_accepted_trajectory_review_requires_completed_reward_hack_review() -> None:
    payload = _review_payload(
        review_status="reviewed",
        review_id="review_001",
        reviewer_id="kshitij",
        review_decision="accepted",
        reward_hack_review={
            "review_status": "not_reviewed",
            "review_id": None,
            "reviewer_id": None,
            "review_decision": None,
            "review_notes_ref": None,
        },
    )

    with pytest.raises(
        ValidationError,
        match="accepted trajectory reviews require completed reward-hack review",
    ):
        TrajectoryReviewRecord.model_validate(payload)


@pytest.mark.parametrize("reward_hack_decision", ["confirmed", "cleared"])
def test_accepted_trajectory_review_allows_adjudicated_reward_hack_review(
    reward_hack_decision: str,
) -> None:
    payload = _review_payload(
        review_status="reviewed",
        review_id="review_001",
        reviewer_id="kshitij",
        review_decision="accepted",
        reward_hack_review={
            "review_status": "reviewed",
            "review_id": "reward_hack_review_001",
            "reviewer_id": "reviewer_002",
            "review_decision": reward_hack_decision,
            "review_notes_ref": _artifact("reward_hack_review_notes.jsonl"),
        },
    )

    record = TrajectoryReviewRecord.model_validate(payload)

    assert record.reward_hack_review is not None
    assert record.reward_hack_review.review_decision == reward_hack_decision


def test_reviewed_records_reject_freeform_review_decision() -> None:
    payload = _review_payload(
        review_status="reviewed",
        review_id="review_001",
        reviewer_id="kshitij",
        review_decision="looks pretty good to me",
    )

    with pytest.raises(ValidationError, match="Input should be"):
        TrajectoryReviewRecord.model_validate(payload)


def test_identity_and_provenance_task_ids_must_match() -> None:
    payload = _record_payload(identity={"task_id": "other_task"})

    with pytest.raises(
        ValidationError,
        match="identity.task_id must match source_provenance.task_id",
    ):
        TrajectoryRecord.model_validate(payload)


@pytest.mark.parametrize("field", ["eval_run_id", "eval_attempt_id"])
def test_identity_requires_eval_layer_ids(field: str) -> None:
    payload = _base_record_payload()
    del payload["identity"][field]

    with pytest.raises(ValidationError, match="Field required"):
        TrajectoryRecord.model_validate(payload)


def test_identity_and_policy_ids_must_match() -> None:
    payload = _record_payload(identity={"policy_id": "other-policy"})

    with pytest.raises(
        ValidationError,
        match="identity.policy_id must match policy.policy_id",
    ):
        TrajectoryRecord.model_validate(payload)


def test_agent_status_requires_agent_attempt_id() -> None:
    payload = _record_payload(identity={"agent_attempt_id": None})

    with pytest.raises(
        ValidationError,
        match="agent_task_run_status requires identity.agent_attempt_id",
    ):
        TrajectoryRecord.model_validate(payload)


def test_attempt_status_requires_scorer_attempt_id() -> None:
    payload = _record_payload(identity={"scorer_attempt_id": None})

    with pytest.raises(
        ValidationError,
        match="attempt_status requires identity.scorer_attempt_id",
    ):
        TrajectoryRecord.model_validate(payload)


def test_scored_record_attempt_status_requires_scorer_attempt_id() -> None:
    payload = _record_payload(
        identity={"scorer_attempt_id": None},
        statuses={
            "attempt_status": "HIDDEN_TEST_FAIL",
            "public_status": "PASS",
            "hidden_status": "FAIL",
            "grade_state": "scored_fail",
            "task_success": False,
        },
    )

    with pytest.raises(
        ValidationError,
        match="attempt_status requires identity.scorer_attempt_id",
    ):
        TrajectoryRecord.model_validate(payload)


def test_identity_rejects_legacy_generic_ids() -> None:
    identity = _base_record_payload()["identity"]
    identity["run_id"] = "eval_run_001"
    identity["attempt_id"] = "attempt_001"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TrajectoryRecord.model_validate(_record_payload(identity=identity))


def test_helper_payloads_do_not_share_mutable_state() -> None:
    first = _base_record_payload()
    second = copy.deepcopy(first)
    second["identity"]["trajectory_id"] = "traj_002"

    assert first["identity"]["trajectory_id"] == "traj_001"
    assert second["identity"]["trajectory_id"] == "traj_002"
