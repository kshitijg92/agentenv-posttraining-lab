from pathlib import Path

from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.training.schema import (
    TrainingCandidateRecord,
    TrainingEligibility,
)
from agentenv.training.gates import (
    TrainingExportGateValidation,
    validate_training_export_gates,
)
from agentenv.trajectories.review import (
    TrajectoryReviewValidation,
    validate_trajectory_review_artifact,
)
from agentenv.trajectories.schema import TrajectoryRecord, TrajectoryReviewRecord


NON_TRAINING_SPLITS = frozenset({"heldout_private", "public_calibration"})
REQUIRED_TRAINING_AGENT_ARTIFACT_FIELDS = (
    "agent_task_run_json",
    "agent_task_view_json",
    "prompt_loop_result_json",
    "decoding_config_json",
)


def build_training_candidate_records(
    trajectory_export_dir: Path,
    review_dir: Path,
    *,
    harness_audit_dir: Path,
    control_calibration_dir: Path,
) -> tuple[TrainingCandidateRecord, ...]:
    validation = validate_trajectory_review_artifact(
        trajectory_export_dir,
        review_dir,
    )
    gate_validation = validate_training_export_gates(
        validation,
        harness_audit_dir=harness_audit_dir,
        control_calibration_dir=control_calibration_dir,
    )
    return build_training_candidate_records_from_review_validation(
        validation,
        gate_validation=gate_validation,
    )


def build_training_candidate_records_from_review_validation(
    validation: TrajectoryReviewValidation,
    *,
    gate_validation: TrainingExportGateValidation,
) -> tuple[TrainingCandidateRecord, ...]:
    if gate_validation.harness_audit_gate.status != "PASS" or (
        not gate_validation.control_calibration_gate.overall_match
        or gate_validation.control_calibration_gate.flake_detection_status != "stable"
    ):
        raise ValueError("Training candidate construction requires validated gates")
    review_by_trajectory_id = {
        review.trajectory_id: review for review in validation.review_artifact.reviews
    }
    return tuple(
        build_training_candidate_record(
            trajectory,
            review_by_trajectory_id[trajectory.identity.trajectory_id],
        )
        for trajectory in validation.source_export.records
    )


def build_training_candidate_record(
    trajectory: TrajectoryRecord,
    review: TrajectoryReviewRecord,
) -> TrainingCandidateRecord:
    return TrainingCandidateRecord(
        trajectory_id=trajectory.identity.trajectory_id,
        eval_attempt_id=trajectory.identity.eval_attempt_id,
        task_id=trajectory.identity.task_id,
        policy_id=trajectory.identity.policy_id,
        review_status=review.review_status,
        review_id=review.review_id,
        reviewer_id=review.reviewer_id,
        review_decision=review.review_decision,
        training_eligibility=build_training_eligibility(trajectory, review),
    )


def build_training_eligibility(
    trajectory: TrajectoryRecord,
    review: TrajectoryReviewRecord,
) -> TrainingEligibility:
    if review.review_status != "reviewed" or review.review_decision != "accepted":
        review_block_reason = build_review_block_reason(review)
        return TrainingEligibility(
            analysis_allowed=True,
            analysis_reason=f"trajectory remains analysis-eligible; {review_block_reason}",
            positive_sft_allowed=False,
            positive_sft_reason=review_block_reason,
            negative_example_allowed=False,
            negative_example_reason=review_block_reason,
            preference_data_allowed=False,
            preference_data_reason=review_block_reason,
        )

    common_block_reason = build_common_training_block_reason(trajectory)
    positive_sft_block_reason = common_block_reason or build_positive_sft_block_reason(
        trajectory
    )
    negative_example_block_reason = (
        common_block_reason or build_negative_example_block_reason(trajectory)
    )
    preference_data_block_reason = (
        common_block_reason or build_preference_data_block_reason(trajectory)
    )

    return TrainingEligibility(
        analysis_allowed=True,
        analysis_reason="trajectory is available for analysis",
        positive_sft_allowed=positive_sft_block_reason is None,
        positive_sft_reason=build_training_path_reason(
            path_label="positive SFT",
            block_reason=positive_sft_block_reason,
        ),
        negative_example_allowed=negative_example_block_reason is None,
        negative_example_reason=build_training_path_reason(
            path_label="negative example",
            block_reason=negative_example_block_reason,
        ),
        preference_data_allowed=preference_data_block_reason is None,
        preference_data_reason=build_training_path_reason(
            path_label="preference data",
            block_reason=preference_data_block_reason,
        ),
    )


def build_common_training_block_reason(trajectory: TrajectoryRecord) -> str | None:
    if trajectory.policy.policy_spec.type != AGENT_MODEL_POLICY_TYPE:
        return "policy is not model-generated training data"
    if trajectory.source_provenance.split in NON_TRAINING_SPLITS:
        return "split is not eligible for training"
    if (
        trajectory.leakage.canary_leaked
        or trajectory.leakage.hidden_validators_visible_to_model
    ):
        return "leakage detected in model-visible trajectory evidence"
    if trajectory.reward_components.orchestration_failure:
        return "trajectory contains an orchestration failure"

    missing_evidence = list_missing_training_agent_evidence(trajectory)
    if missing_evidence:
        return f"required agent evidence is missing: {', '.join(missing_evidence)}"
    return None


def list_missing_training_agent_evidence(
    trajectory: TrajectoryRecord,
) -> tuple[str, ...]:
    missing: list[str] = []
    if trajectory.identity.agent_attempt_id is None:
        missing.append("agent_attempt_id")
    if trajectory.statuses.agent_task_run_status is None:
        missing.append("agent_task_run_status")
    missing.extend(
        field_name
        for field_name in REQUIRED_TRAINING_AGENT_ARTIFACT_FIELDS
        if getattr(trajectory.artifacts, field_name) is None
    )
    return tuple(missing)


def build_positive_sft_block_reason(trajectory: TrajectoryRecord) -> str | None:
    if trajectory.reward_components.reward_hack_flag:
        return "reward-hack evidence forbids positive SFT"
    if not trajectory.statuses.task_success:
        return "positive SFT requires task success"
    if trajectory.statuses.agent_task_run_status != "scored":
        return "positive SFT requires a scored agent trajectory"
    return None


def build_negative_example_block_reason(trajectory: TrajectoryRecord) -> str | None:
    if trajectory.statuses.task_success:
        return "negative examples require an unsuccessful trajectory"
    return None


def build_preference_data_block_reason(trajectory: TrajectoryRecord) -> str | None:
    if trajectory.statuses.grade_state == "cannot_grade":
        return "preference data requires a gradable trajectory"
    if trajectory.statuses.agent_task_run_status != "scored":
        return "preference data requires a scored agent trajectory"
    return None


def build_review_block_reason(review: TrajectoryReviewRecord) -> str:
    if review.review_status == "not_reviewed":
        return "trajectory has not been reviewed"
    if review.review_decision == "rejected":
        return "human review rejected trajectory"
    if review.review_decision == "needs_followup":
        return "human review requires follow-up"
    return "human review did not accept trajectory"


def build_training_path_reason(
    *,
    path_label: str,
    block_reason: str | None,
) -> str:
    if block_reason is None:
        return f"accepted human review; trajectory evidence permits {path_label}"
    return block_reason
