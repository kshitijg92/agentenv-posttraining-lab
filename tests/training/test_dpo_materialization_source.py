from datetime import UTC, datetime
from pathlib import Path

import pytest

from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.hashing import hash_file
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.candidates.builder import build_training_candidate_record
from agentenv.training.preferences.builder import (
    discover_preference_comparison_candidates_from_records,
)
from agentenv.training.preferences.hashing import (
    build_preference_pair_id,
    hash_preference_adjudication_record,
    hash_preference_comparison_candidate_record,
)
from agentenv.training.preferences.materialization.source_reconstruction import (
    reconstruct_dpo_preference_pair_inputs_from_records,
)
from agentenv.training.preferences.schema import (
    PreferenceAdjudicationRecord,
    PreferenceComparisonCandidateRecord,
    PreferencePairRecord,
)
from agentenv.trajectories.builder import build_trajectory_record_from_eval_attempt
from agentenv.trajectories.schema import (
    ReviewDecision,
    TrajectoryRecord,
    TrajectoryReviewRecord,
)


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
RUBRIC_PATH = Path(
    "configs/training/preference_rubrics/overall_action_preference_v0.md"
)


def test_reconstruction_keeps_one_pair_and_validates_aggregated_occurrences(
    tmp_path: Path,
) -> None:
    source_specs: tuple[tuple[str, ReviewDecision], ...] = (
        ("agent-happy", "accepted"),
        ("agent-happy", "accepted"),
        ("agent-malformed", "rejected"),
    )
    trajectories: list[TrajectoryRecord] = []
    candidates = []
    for index, (policy, review_decision) in enumerate(source_specs):
        trajectory = _build_model_source_trajectory(
            tmp_path / f"source-{index}",
            policy=policy,
        )
        candidate = build_training_candidate_record(
            trajectory,
            _build_review(trajectory, review_decision),
        )
        trajectories.append(trajectory)
        candidates.append(candidate)

    comparison = discover_preference_comparison_candidates_from_records(
        candidates,
        trajectories,
    )[0]
    chosen = max(
        (comparison.alternative_a, comparison.alternative_b),
        key=lambda alternative: len(alternative.rollout_evidence),
    )
    assert len(chosen.rollout_evidence) == 2
    adjudication = _preferred_adjudication(comparison, chosen.alternative_id)
    pair = _pair(comparison, adjudication)

    inputs = reconstruct_dpo_preference_pair_inputs_from_records(
        pairs=(pair,),
        comparisons=(comparison,),
        adjudications=(adjudication,),
        training_candidates=tuple(candidates),
        trajectories=tuple(trajectories),
    )

    assert len(inputs) == 1
    materialization_input = inputs[0]
    assert materialization_input.source_pair == pair
    assert materialization_input.chosen_action.content == chosen.assistant_content
    assert materialization_input.rejected_action.content != chosen.assistant_content
    assert [message.role for message in materialization_input.context_messages] == [
        "system",
        "user",
    ]


def test_reconstruction_rejects_drift_in_any_aggregated_source_occurrence(
    tmp_path: Path,
) -> None:
    trajectories = [
        _build_model_source_trajectory(
            tmp_path / f"source-{index}",
            policy=policy,
        )
        for index, policy in enumerate(
            ("agent-happy", "agent-happy", "agent-malformed")
        )
    ]
    candidates = [
        build_training_candidate_record(
            trajectory,
            _build_review(trajectory, "accepted"),
        )
        for trajectory in trajectories
    ]
    comparison = discover_preference_comparison_candidates_from_records(
        candidates,
        trajectories,
    )[0]
    chosen = max(
        (comparison.alternative_a, comparison.alternative_b),
        key=lambda alternative: len(alternative.rollout_evidence),
    )
    adjudication = _preferred_adjudication(comparison, chosen.alternative_id)
    pair = _pair(comparison, adjudication)

    drifted_evidence = chosen.rollout_evidence[-1]
    drifted_trajectory = next(
        trajectory
        for trajectory in trajectories
        if trajectory.identity.trajectory_id == drifted_evidence.trajectory_id
    )
    prompt_loop_ref = drifted_trajectory.artifacts.prompt_loop_result_json
    assert prompt_loop_ref is not None
    prompt_loop_path = (
        Path(drifted_trajectory.artifacts.eval_run_path) / prompt_loop_ref.path
    )
    prompt_loop_path.write_text(prompt_loop_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        reconstruct_dpo_preference_pair_inputs_from_records(
            pairs=(pair,),
            comparisons=(comparison,),
            adjudications=(adjudication,),
            training_candidates=tuple(candidates),
            trajectories=tuple(trajectories),
        )


def _preferred_adjudication(
    comparison: PreferenceComparisonCandidateRecord,
    preferred_alternative_id: str,
) -> PreferenceAdjudicationRecord:
    return PreferenceAdjudicationRecord.model_validate(
        {
            "source": {
                "comparison_candidate_id": comparison.comparison_candidate_id,
                "source_preference_comparison_candidate_record_hash": (
                    hash_preference_comparison_candidate_record(comparison)
                ),
                "alternative_a_id": comparison.alternative_a.alternative_id,
                "alternative_b_id": comparison.alternative_b.alternative_id,
            },
            "rubric_provenance": {
                "adjudication_scope": "overall_action_preference",
                "rubric_id": "overall_action_preference",
                "rubric_version": "overall_action_preference_v0",
                "rubric_ref": {
                    "path": str(RUBRIC_PATH),
                    "content_hash": hash_file(RUBRIC_PATH),
                },
            },
            "review_status": "reviewed",
            "review_id": "preference_review_001",
            "reviewer_provenance": {
                "reviewer_type": "human",
                "reviewer_id": "reviewer_001",
            },
            "review_decision": "preferred",
            "preferred_alternative_id": preferred_alternative_id,
            "decision_reason": "The chosen action is preferable under the rubric.",
            "reviewed_at_utc": datetime.now(UTC),
        }
    )


def _pair(
    comparison: PreferenceComparisonCandidateRecord,
    adjudication: PreferenceAdjudicationRecord,
) -> PreferencePairRecord:
    comparison_hash = hash_preference_comparison_candidate_record(comparison)
    adjudication_hash = hash_preference_adjudication_record(adjudication)
    return PreferencePairRecord.model_validate(
        {
            "preference_pair_id": build_preference_pair_id(
                comparison_candidate_id=comparison.comparison_candidate_id,
                source_preference_comparison_candidate_record_hash=comparison_hash,
                source_preference_adjudication_record_hash=adjudication_hash,
            ),
            "source": {
                "comparison_candidate_id": comparison.comparison_candidate_id,
                "source_preference_comparison_candidate_record_hash": (comparison_hash),
                "source_preference_adjudication_record_hash": adjudication_hash,
            },
        }
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
    decision: ReviewDecision,
) -> TrajectoryReviewRecord:
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
