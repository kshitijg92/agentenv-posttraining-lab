from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.training.schema import (
    TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION,
    FinalTrainingEligibility,
    TrainingCandidateRecord,
)


def _eligibility_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "analysis_allowed": True,
        "analysis_reason": "trajectory is available for analysis",
        "positive_sft_allowed": True,
        "positive_sft_reason": "accepted successful agent trajectory",
        "negative_example_allowed": False,
        "negative_example_reason": "trajectory succeeded",
        "preference_data_allowed": True,
        "preference_data_reason": "accepted gradable trajectory",
    }
    payload.update(updates)
    return payload


def _candidate_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "training_candidate_record_v0",
        "trajectory_id": "trajectory_001",
        "eval_attempt_id": "eval_attempt_001",
        "task_id": "repair_jsonl_deduper",
        "policy_id": "agent-happy",
        "review_status": "reviewed",
        "review_id": "review_001",
        "reviewer_id": "kshitij",
        "review_decision": "accepted",
        "final_eligibility": _eligibility_payload(),
    }
    payload.update(updates)
    return payload


def test_training_candidate_record_accepts_reviewed_candidate() -> None:
    record = TrainingCandidateRecord.model_validate(_candidate_payload())

    assert record.schema_version == TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
    assert record.trajectory_id == "trajectory_001"
    assert record.review_id == "review_001"
    assert record.review_decision == "accepted"
    assert record.final_eligibility.is_trainable
    assert not record.final_eligibility.is_analysis_only
    assert not record.final_eligibility.is_not_trainable


def test_final_training_eligibility_exposes_analysis_only_utility() -> None:
    eligibility = FinalTrainingEligibility.model_validate(
        _eligibility_payload(
            positive_sft_allowed=False,
            positive_sft_reason="not a positive SFT target",
            preference_data_allowed=False,
            preference_data_reason="not a preference candidate",
        )
    )

    assert not eligibility.is_trainable
    assert eligibility.is_analysis_only
    assert not eligibility.is_not_trainable


def test_final_training_eligibility_exposes_not_trainable_utility() -> None:
    eligibility = FinalTrainingEligibility.model_validate(
        _eligibility_payload(
            analysis_allowed=False,
            analysis_reason="source artifact failed validation",
            positive_sft_allowed=False,
            positive_sft_reason="source artifact failed validation",
            preference_data_allowed=False,
            preference_data_reason="source artifact failed validation",
        )
    )

    assert not eligibility.is_trainable
    assert not eligibility.is_analysis_only
    assert eligibility.is_not_trainable


def test_training_candidate_rejects_training_paths_without_accepted_review() -> None:
    payload = _candidate_payload(
        review_status="reviewed",
        review_decision="rejected",
    )

    with pytest.raises(
        ValidationError,
        match="training-eligible candidates require accepted human review",
    ):
        TrainingCandidateRecord.model_validate(payload)


def test_training_candidate_accepts_rejected_analysis_only_candidate() -> None:
    payload = _candidate_payload(
        review_decision="rejected",
        final_eligibility=_eligibility_payload(
            positive_sft_allowed=False,
            positive_sft_reason="human review rejected trajectory",
            negative_example_allowed=False,
            negative_example_reason="human review rejected trajectory",
            preference_data_allowed=False,
            preference_data_reason="human review rejected trajectory",
        ),
    )

    record = TrainingCandidateRecord.model_validate(payload)

    assert record.review_decision == "rejected"
    assert record.final_eligibility.is_analysis_only


def test_not_reviewed_candidate_cannot_include_review_details() -> None:
    payload = _candidate_payload(
        review_status="not_reviewed",
        review_id="review_001",
        reviewer_id=None,
        review_decision=None,
        final_eligibility=_eligibility_payload(
            positive_sft_allowed=False,
            positive_sft_reason="trajectory has not been reviewed",
            negative_example_allowed=False,
            negative_example_reason="trajectory has not been reviewed",
            preference_data_allowed=False,
            preference_data_reason="trajectory has not been reviewed",
        ),
    )

    with pytest.raises(
        ValidationError,
        match="not_reviewed training candidates cannot include review details",
    ):
        TrainingCandidateRecord.model_validate(payload)


def test_reviewed_candidate_requires_review_decision() -> None:
    payload = _candidate_payload(review_decision=None)

    with pytest.raises(
        ValidationError,
        match="reviewed training candidates require review_decision",
    ):
        TrainingCandidateRecord.model_validate(payload)


def test_training_candidate_rejects_extra_fields() -> None:
    payload = _candidate_payload(embedded_trajectory={"unexpected": True})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TrainingCandidateRecord.model_validate(payload)


def test_final_training_eligibility_requires_path_reasons() -> None:
    payload = _eligibility_payload(positive_sft_reason="")

    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        FinalTrainingEligibility.model_validate(payload)
