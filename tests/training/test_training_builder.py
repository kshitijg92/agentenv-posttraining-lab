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
    assert candidate.training_eligibility.analysis_allowed
    assert candidate.training_eligibility.is_analysis_only
    assert not candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
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
    assert not candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.is_analysis_only
    assert candidate.training_eligibility.positive_sft_reason == (
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
    assert not candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.negative_example_reason == (
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
    assert candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.is_trainable


@pytest.mark.parametrize("split", ["heldout_private", "public_calibration"])
def test_training_candidate_blocks_model_trajectory_on_non_training_split(
    tmp_path: Path,
    split: str,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-happy")
    trajectory = rebuild_trajectory(
        trajectory,
        source_provenance={"split": split},
    )
    review = build_reviewed_record(
        build_review_record_for_trajectory(trajectory),
        "accepted",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert candidate.training_eligibility.is_analysis_only
    assert not candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
        "split is not eligible for training"
    )


def test_training_candidate_blocks_leaked_model_trajectory(
    tmp_path: Path,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-happy")
    trajectory = rebuild_trajectory(
        trajectory,
        leakage={"hidden_validators_visible_to_model": True},
    )
    review = build_reviewed_record(
        build_review_record_for_trajectory(trajectory),
        "accepted",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert candidate.training_eligibility.is_analysis_only
    assert not candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
        "leakage detected in model-visible trajectory evidence"
    )


def test_training_candidate_blocks_orchestration_failure(
    tmp_path: Path,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-happy")
    trajectory = rebuild_trajectory(
        trajectory,
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
        reward_components={
            "public_validator_success": None,
            "hidden_validator_success": None,
            "model_output_format_valid": None,
            "model_tool_usage_valid": None,
            "orchestration_failure": True,
            "reward_hack_flag": None,
        },
    )
    review = build_reviewed_record(
        build_review_record_for_trajectory(trajectory),
        "accepted",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert candidate.training_eligibility.is_analysis_only
    assert not candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
        "trajectory contains an orchestration failure"
    )


def test_reward_hack_trajectory_is_negative_or_preference_data_not_positive_sft(
    tmp_path: Path,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-happy")
    trajectory = rebuild_trajectory(
        trajectory,
        statuses={
            "attempt_status": "INVALID_SHORTCUT",
            "public_status": "NOT_RUN",
            "hidden_status": "NOT_RUN",
            "grade_state": "scored_fail",
            "task_success": False,
        },
        reward_components={
            "public_validator_success": False,
            "hidden_validator_success": False,
            "reward_hack_flag": True,
        },
    )
    review = build_reward_hack_adjudicated_review(
        build_reviewed_record(
            build_review_record_for_trajectory(trajectory),
            "accepted",
        ),
        decision="cleared",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert not candidate.training_eligibility.positive_sft_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
        "reward-hack evidence forbids positive SFT"
    )
    assert candidate.training_eligibility.negative_example_allowed
    assert candidate.training_eligibility.preference_data_allowed


def test_confirmed_reward_hack_review_blocks_positive_sft(
    tmp_path: Path,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-happy")
    review = build_reward_hack_adjudicated_review(
        build_reviewed_record(
            build_review_record_for_trajectory(trajectory),
            "accepted",
        ),
        decision="confirmed",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert not candidate.training_eligibility.positive_sft_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
        "human review confirmed reward-hack evidence"
    )
    assert candidate.training_eligibility.preference_data_allowed


def test_cleared_reward_hack_review_does_not_block_positive_sft(
    tmp_path: Path,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-happy")
    review = build_reward_hack_adjudicated_review(
        build_reviewed_record(
            build_review_record_for_trajectory(trajectory),
            "accepted",
        ),
        decision="cleared",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert candidate.training_eligibility.positive_sft_allowed
    assert candidate.training_eligibility.preference_data_allowed


def test_training_candidate_blocks_missing_agent_evidence(
    tmp_path: Path,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-happy")
    trajectory = rebuild_trajectory(
        trajectory,
        artifacts={"agent_task_run_json": None},
    )
    review = build_reviewed_record(
        build_review_record_for_trajectory(trajectory),
        "accepted",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert candidate.training_eligibility.is_analysis_only
    assert not candidate.training_eligibility.positive_sft_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
        "required agent evidence is missing: agent_task_run_json"
    )


def test_training_candidate_allows_failed_model_trajectory_as_negative_only(
    tmp_path: Path,
) -> None:
    trajectory = build_agent_model_trajectory(tmp_path, policy="agent-malformed")
    review = build_reviewed_record(
        build_review_record_for_trajectory(trajectory),
        "accepted",
    )

    candidate = build_training_candidate_record(trajectory, review)

    assert not candidate.training_eligibility.positive_sft_allowed
    assert candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.preference_data_reason == (
        "preference data requires a gradable trajectory"
    )


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
    assert candidate.training_eligibility.analysis_allowed
    assert candidate.training_eligibility.is_analysis_only
    assert not candidate.training_eligibility.positive_sft_allowed
    assert not candidate.training_eligibility.negative_example_allowed
    assert not candidate.training_eligibility.preference_data_allowed
    assert candidate.training_eligibility.positive_sft_reason == (
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


def build_reward_hack_adjudicated_review(
    review: TrajectoryReviewRecord,
    *,
    decision: str,
) -> TrajectoryReviewRecord:
    payload = review.model_dump(mode="json")
    payload["reward_hack_review"] = {
        "review_status": "reviewed",
        "review_id": "reward_hack_review_001",
        "reviewer_id": "reward_reviewer_001",
        "review_decision": decision,
        "review_notes_ref": None,
    }
    return TrajectoryReviewRecord.model_validate(payload)


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


def build_agent_model_trajectory(
    tmp_path: Path,
    *,
    policy: str,
) -> TrajectoryRecord:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        policy,
        tmp_path / policy,
    )
    trajectory = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )
    return build_agent_model_trajectory_record(trajectory)


def rebuild_trajectory(
    trajectory: TrajectoryRecord,
    **section_updates: dict[str, object],
) -> TrajectoryRecord:
    payload = trajectory.model_dump(mode="json")
    for section, updates in section_updates.items():
        section_payload = payload[section]
        assert isinstance(section_payload, dict)
        section_payload.update(updates)
    return TrajectoryRecord.model_validate(payload)


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
