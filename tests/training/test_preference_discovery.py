from pathlib import Path

from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.candidates.builder import build_training_candidate_record
from agentenv.training.preferences.builder import (
    discover_preference_comparison_candidates_from_records,
)
from agentenv.trajectories.builder import build_trajectory_record_from_eval_attempt
from agentenv.trajectories.schema import (
    ReviewDecision,
    TrajectoryRecord,
    TrajectoryReviewRecord,
)


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")


def test_discovery_aggregates_same_actions_and_ignores_task_outcome_and_review(
    tmp_path: Path,
) -> None:
    source_specs: tuple[tuple[str, ReviewDecision | None], ...] = (
        ("agent-happy", "accepted"),
        ("agent-happy", None),
        ("agent-malformed", "rejected"),
    )
    trajectories: list[TrajectoryRecord] = []
    candidates = []
    for index, (policy, review_decision) in enumerate(source_specs):
        trajectory = _build_model_source_trajectory(
            tmp_path / f"source-{index}",
            policy=policy,
        )
        review = _build_review(trajectory, review_decision)
        candidate = build_training_candidate_record(trajectory, review)
        assert candidate.content_eligibility.preference_discovery_eligible
        trajectories.append(trajectory)
        candidates.append(candidate)

    assert trajectories[2].statuses.grade_state == "cannot_grade"
    records = discover_preference_comparison_candidates_from_records(
        candidates,
        trajectories,
    )

    assert len(records) == 1
    record = records[0]
    evidence_counts = sorted(
        (
            len(record.alternative_a.rollout_evidence),
            len(record.alternative_b.rollout_evidence),
        )
    )
    assert evidence_counts == [1, 2]
    source_review_states = {
        (
            evidence.source_trajectory_review_status,
            evidence.source_trajectory_review_decision,
        )
        for alternative in (record.alternative_a, record.alternative_b)
        for evidence in alternative.rollout_evidence
    }
    assert source_review_states == {
        ("reviewed", "accepted"),
        ("not_reviewed", None),
        ("reviewed", "rejected"),
    }
    assert all(
        evidence.source_type == "original_rollout"
        and evidence.continuation_provenance == "executed_source_trajectory"
        and (evidence.source_prompt_loop_result_ref.content_hash is not None)
        for alternative in (record.alternative_a, record.alternative_b)
        for evidence in alternative.rollout_evidence
    )


def _build_model_source_trajectory(
    out_dir: Path,
    *,
    policy: str,
) -> TrajectoryRecord:
    eval_run = run_eval_config(AGENT_CONTROL_CONFIG, policy, out_dir)
    trajectory = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )
    payload = trajectory.model_dump(mode="json")
    payload["identity"]["policy_id"] = "source-model"
    payload["policy"] = {
        "policy_id": "source-model",
        "policy_name": "source-model",
        "policy_spec": {
            "type": AGENT_MODEL_POLICY_TYPE,
            "model_config": "configs/models/source_model.yaml",
            "decoding_config": "configs/decoding/source_model.yaml",
            "attempts": 1,
            "replay": {"repeats": 0},
        },
    }
    return TrajectoryRecord.model_validate(payload)


def _build_review(
    trajectory: TrajectoryRecord,
    decision: ReviewDecision | None,
) -> TrajectoryReviewRecord:
    if decision is None:
        return TrajectoryReviewRecord(
            trajectory_id=trajectory.identity.trajectory_id,
            eval_attempt_id=trajectory.identity.eval_attempt_id,
            task_id=trajectory.identity.task_id,
            policy_id=trajectory.identity.policy_id,
            review_status="not_reviewed",
        )
    return TrajectoryReviewRecord(
        trajectory_id=trajectory.identity.trajectory_id,
        eval_attempt_id=trajectory.identity.eval_attempt_id,
        task_id=trajectory.identity.task_id,
        policy_id=trajectory.identity.policy_id,
        review_status="reviewed",
        review_id=f"review_{trajectory.identity.eval_attempt_id}",
        reviewer_id="reviewer_001",
        review_decision=decision,
    )
