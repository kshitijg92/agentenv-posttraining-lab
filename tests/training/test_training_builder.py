from pathlib import Path

import pytest

from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.builder import (
    build_training_candidate_record,
    build_training_candidate_records,
)
from agentenv.trajectories.builder import build_trajectory_record_from_eval_attempt
from agentenv.trajectories.export import export_trajectory_records_from_eval_artifact
from agentenv.trajectories.review import (
    TrajectoryReviewArtifact,
    initialize_trajectory_review_artifact,
    write_trajectory_review_records_jsonl,
)
from agentenv.trajectories.schema import (
    ReviewDecision,
    TrajectoryRecord,
    TrajectoryReviewRecord,
)


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
HARNESS_AUDIT_DIR = Path("/unit/harness-audit")
CONTROL_CALIBRATION_DIR = Path("/unit/control-calibration")


@pytest.fixture(autouse=True)
def _use_stub_training_export_gates(stub_training_export_gates) -> None:
    assert stub_training_export_gates.harness_audit_gate.status == "PASS"


def test_build_training_candidate_records_blocks_pending_review(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )

    candidates = build_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )

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


def test_build_training_candidate_records_blocks_accepted_agent_control_training_paths(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    write_single_review_decision(review_artifact, "accepted")

    candidates = build_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )

    candidate = candidates[0]
    assert candidate.review_status == "reviewed"
    assert candidate.review_id == "review_001"
    assert candidate.reviewer_id == "kshitij"
    assert candidate.review_decision == "accepted"
    assert not candidate.final_eligibility.positive_sft_allowed
    assert not candidate.final_eligibility.negative_example_allowed
    assert not candidate.final_eligibility.preference_data_allowed
    assert candidate.final_eligibility.is_analysis_only
    assert candidate.final_eligibility.positive_sft_reason == (
        "policy is not model-generated training data"
    )


def test_build_training_candidate_records_blocks_accepted_agent_control_negative_path(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-malformed",
    )
    write_single_review_decision(review_artifact, "accepted")

    candidates = build_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )

    candidate = candidates[0]
    assert candidate.review_decision == "accepted"
    assert not candidate.final_eligibility.positive_sft_allowed
    assert not candidate.final_eligibility.negative_example_allowed
    assert not candidate.final_eligibility.preference_data_allowed
    assert candidate.final_eligibility.negative_example_reason == (
        "policy is not model-generated training data"
    )


def test_build_training_candidate_record_allows_accepted_agent_model_training_paths(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "eval-run",
    )
    trajectory = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )
    agent_model_trajectory = build_agent_model_trajectory_record(trajectory)
    review = build_reviewed_record(
        build_review_record_for_trajectory(agent_model_trajectory),
        "accepted",
    )

    candidate = build_training_candidate_record(agent_model_trajectory, review)

    assert candidate.policy_id == "local-model"
    assert candidate.review_decision == "accepted"
    assert candidate.final_eligibility.positive_sft_allowed
    assert not candidate.final_eligibility.negative_example_allowed
    assert candidate.final_eligibility.preference_data_allowed
    assert candidate.final_eligibility.is_trainable


def test_build_training_candidate_records_rejected_review_blocks_training_paths(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    write_single_review_decision(review_artifact, "rejected")

    candidates = build_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )

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


def build_agent_model_trajectory_record(
    trajectory: TrajectoryRecord,
) -> TrajectoryRecord:
    payload = trajectory.model_dump(mode="json")
    payload["identity"]["policy_id"] = "local-model"
    payload["policy"] = {
        "policy_id": "local-model",
        "policy_name": "local-model",
        "policy_spec": {
            "type": AGENT_MODEL_POLICY_TYPE,
            "model_config": "configs/models/local_model.yaml",
            "decoding_config": "configs/decoding/local_model.yaml",
            "attempts": 1,
            "replay": {"repeats": 0},
        },
    }
    return type(trajectory).model_validate(payload)


def build_review_record_for_trajectory(
    trajectory: TrajectoryRecord,
) -> TrajectoryReviewRecord:
    return TrajectoryReviewRecord(
        trajectory_id=trajectory.identity.trajectory_id,
        eval_attempt_id=trajectory.identity.eval_attempt_id,
        task_id=trajectory.identity.task_id,
        policy_id=trajectory.identity.policy_id,
        review_status="not_reviewed",
    )
