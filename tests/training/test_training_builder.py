from pathlib import Path

from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.builder import build_training_candidate_records
from agentenv.trajectories.export import export_trajectory_records_from_eval_artifact
from agentenv.trajectories.review import (
    TrajectoryReviewArtifact,
    initialize_trajectory_review_artifact,
    write_trajectory_review_records_jsonl,
)
from agentenv.trajectories.schema import ReviewDecision, TrajectoryReviewRecord


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")


def test_build_training_candidate_records_blocks_pending_review(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )

    candidates = build_training_candidate_records(trajectory_export_dir, review_dir)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.review_status == "not_reviewed"
    assert candidate.review_decision is None
    assert candidate.final_eligibility.analysis_allowed
    assert candidate.final_eligibility.is_analysis_only
    assert not candidate.final_eligibility.positive_sft_allowed
    assert not candidate.final_eligibility.negative_example_allowed
    assert not candidate.final_eligibility.preference_data_allowed
    assert candidate.final_eligibility.positive_sft_reason == (
        "trajectory has not been reviewed"
    )


def test_build_training_candidate_records_allows_accepted_positive_sft_candidate(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    write_single_review_decision(review_artifact, "accepted")

    candidates = build_training_candidate_records(trajectory_export_dir, review_dir)

    candidate = candidates[0]
    assert candidate.review_status == "reviewed"
    assert candidate.review_id == "review_001"
    assert candidate.reviewer_id == "kshitij"
    assert candidate.review_decision == "accepted"
    assert candidate.final_eligibility.positive_sft_allowed
    assert not candidate.final_eligibility.negative_example_allowed
    assert candidate.final_eligibility.preference_data_allowed
    assert candidate.final_eligibility.is_trainable
    assert candidate.final_eligibility.positive_sft_reason == (
        "accepted human review; mechanically eligible for positive SFT"
    )


def test_build_training_candidate_records_preserves_mechanical_negative_path(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-malformed",
    )
    write_single_review_decision(review_artifact, "accepted")

    candidates = build_training_candidate_records(trajectory_export_dir, review_dir)

    candidate = candidates[0]
    assert candidate.review_decision == "accepted"
    assert not candidate.final_eligibility.positive_sft_allowed
    assert candidate.final_eligibility.negative_example_allowed
    assert not candidate.final_eligibility.preference_data_allowed
    assert candidate.final_eligibility.negative_example_reason == (
        "accepted human review; mechanically eligible for negative example"
    )


def test_build_training_candidate_records_rejected_review_blocks_training_paths(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    write_single_review_decision(review_artifact, "rejected")

    candidates = build_training_candidate_records(trajectory_export_dir, review_dir)

    candidate = candidates[0]
    assert candidate.review_decision == "rejected"
    assert candidate.final_eligibility.analysis_allowed
    assert candidate.final_eligibility.is_analysis_only
    assert not candidate.final_eligibility.positive_sft_allowed
    assert not candidate.final_eligibility.negative_example_allowed
    assert not candidate.final_eligibility.preference_data_allowed
    assert candidate.final_eligibility.positive_sft_reason == (
        "human review rejected trajectory"
    )


def build_review_fixture(
    tmp_path: Path,
    *,
    policy: str,
) -> tuple[Path, Path, TrajectoryReviewArtifact]:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        policy,
        tmp_path / "eval-run",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        tmp_path / "trajectory-export",
    )
    review_artifact = initialize_trajectory_review_artifact(
        trajectory_export.out_dir,
        tmp_path / "trajectory-review",
    )
    return trajectory_export.out_dir, review_artifact.out_dir, review_artifact


def write_single_review_decision(
    review_artifact: TrajectoryReviewArtifact,
    decision: ReviewDecision,
) -> None:
    review = build_reviewed_record(review_artifact.reviews[0], decision)
    write_trajectory_review_records_jsonl(
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"],
        (review,),
    )


def build_reviewed_record(
    review: TrajectoryReviewRecord,
    decision: ReviewDecision,
) -> TrajectoryReviewRecord:
    return review.model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "kshitij",
            "review_decision": decision,
        }
    )
