from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.training.positive_sft.schema import PositiveSFTReviewRecord


MESSAGE_ID = "message_00000000000000000000000000000001"


def _source(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_type": "original",
        "source_artifact_ref": {
            "path": "agent/attempt/prompt_loop_result.json",
            "content_hash": "xxh64:2222222222222222",
        },
    }
    payload.update(updates)
    return payload


def _record(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_training_candidate_record_hash": "xxh64:1111111111111111",
        "source": _source(),
        "review_status": "not_reviewed",
        "review_id": None,
        "reviewer_id": None,
        "review_decision": None,
        "review_notes_ref": None,
        "last_approved_assistant_message_id": None,
    }
    payload.update(updates)
    return payload


def test_positive_sft_review_accepts_unreviewed_source() -> None:
    review = PositiveSFTReviewRecord.model_validate(_record())

    assert review.source.source_type == "original"
    assert review.last_approved_assistant_message_id is None


def test_accepted_review_requires_assistant_message_boundary() -> None:
    with pytest.raises(
        ValidationError,
        match="accepted positive-SFT reviews require an approved assistant",
    ):
        PositiveSFTReviewRecord.model_validate(
            _record(
                review_status="reviewed",
                review_id="review_001",
                reviewer_id="reviewer_001",
                review_decision="accepted",
            )
        )


def test_accepted_review_authorizes_one_boundary() -> None:
    review = PositiveSFTReviewRecord.model_validate(
        _record(
            review_status="reviewed",
            review_id="review_001",
            reviewer_id="reviewer_001",
            review_decision="accepted",
            last_approved_assistant_message_id=MESSAGE_ID,
        )
    )

    assert review.last_approved_assistant_message_id == MESSAGE_ID


@pytest.mark.parametrize("decision", ["rejected", "needs_followup"])
def test_non_accepted_review_cannot_authorize_boundary(decision: str) -> None:
    with pytest.raises(
        ValidationError,
        match="non-accepted positive-SFT reviews cannot authorize",
    ):
        PositiveSFTReviewRecord.model_validate(
            _record(
                review_status="reviewed",
                review_id="review_001",
                reviewer_id="reviewer_001",
                review_decision=decision,
                last_approved_assistant_message_id=MESSAGE_ID,
            )
        )


def test_review_source_must_be_hash_pinned() -> None:
    with pytest.raises(ValidationError, match="source artifact must be hash-pinned"):
        PositiveSFTReviewRecord.model_validate(
            _record(
                source=_source(
                    source_artifact_ref={
                        "path": "agent/attempt/prompt_loop_result.json",
                        "content_hash": None,
                    }
                )
            )
        )


def test_repaired_source_pins_repair_and_review_records() -> None:
    review = PositiveSFTReviewRecord.model_validate(
        _record(
            source=_source(
                source_type="repaired",
                repair_id="repair_001",
                source_training_candidate_repair_record_hash=("xxh64:3333333333333333"),
                source_training_candidate_repair_review_record_hash=(
                    "xxh64:4444444444444444"
                ),
                repair_review_id="repair_review_001",
            )
        )
    )

    assert review.source.source_type == "repaired"
    assert review.source.repair_id == "repair_001"
