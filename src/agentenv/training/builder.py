from pathlib import Path

from agentenv.training.schema import (
    FinalTrainingEligibility,
    TrainingCandidateRecord,
)
from agentenv.trajectories.review import validate_trajectory_review_artifact
from agentenv.trajectories.schema import TrajectoryRecord, TrajectoryReviewRecord


def build_training_candidate_records(
    trajectory_export_dir: Path,
    review_dir: Path,
) -> tuple[TrainingCandidateRecord, ...]:
    validation = validate_trajectory_review_artifact(
        trajectory_export_dir,
        review_dir,
    )
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
        final_eligibility=build_final_training_eligibility(trajectory, review),
    )


def build_final_training_eligibility(
    trajectory: TrajectoryRecord,
    review: TrajectoryReviewRecord,
) -> FinalTrainingEligibility:
    if review.review_status != "reviewed" or review.review_decision != "accepted":
        review_block_reason = build_review_block_reason(review)
        return FinalTrainingEligibility(
            analysis_allowed=trajectory.training_eligibility.analysis_allowed,
            analysis_reason=build_analysis_reason(
                trajectory,
                fallback_reason=review_block_reason,
            ),
            positive_sft_allowed=False,
            positive_sft_reason=review_block_reason,
            negative_example_allowed=False,
            negative_example_reason=review_block_reason,
            preference_data_allowed=False,
            preference_data_reason=review_block_reason,
        )

    return FinalTrainingEligibility(
        analysis_allowed=trajectory.training_eligibility.analysis_allowed,
        analysis_reason=build_analysis_reason(trajectory),
        positive_sft_allowed=trajectory.training_eligibility.positive_sft_allowed,
        positive_sft_reason=build_mechanical_path_reason(
            path_label="positive SFT",
            allowed=trajectory.training_eligibility.positive_sft_allowed,
            mechanical_reason=trajectory.training_eligibility.eligibility_reason,
        ),
        negative_example_allowed=trajectory.training_eligibility.negative_example_allowed,
        negative_example_reason=build_mechanical_path_reason(
            path_label="negative example",
            allowed=trajectory.training_eligibility.negative_example_allowed,
            mechanical_reason=trajectory.training_eligibility.eligibility_reason,
        ),
        preference_data_allowed=trajectory.training_eligibility.preference_data_allowed,
        preference_data_reason=build_mechanical_path_reason(
            path_label="preference data",
            allowed=trajectory.training_eligibility.preference_data_allowed,
            mechanical_reason=trajectory.training_eligibility.eligibility_reason,
        ),
    )


def build_review_block_reason(review: TrajectoryReviewRecord) -> str:
    if review.review_status == "not_reviewed":
        return "trajectory has not been reviewed"
    if review.review_decision == "rejected":
        return "human review rejected trajectory"
    if review.review_decision == "needs_followup":
        return "human review requires follow-up"
    return "human review did not accept trajectory"


def build_analysis_reason(
    trajectory: TrajectoryRecord,
    *,
    fallback_reason: str | None = None,
) -> str:
    if not trajectory.training_eligibility.analysis_allowed:
        return (
            "underlying trajectory is not analysis eligible: "
            f"{trajectory.training_eligibility.eligibility_reason}"
        )
    if fallback_reason is not None:
        return f"trajectory remains analysis-eligible; {fallback_reason}"
    return "trajectory is available for analysis"


def build_mechanical_path_reason(
    *,
    path_label: str,
    allowed: bool,
    mechanical_reason: str,
) -> str:
    if allowed:
        return f"accepted human review; mechanically eligible for {path_label}"
    return f"underlying trajectory is not {path_label} eligible: {mechanical_reason}"
