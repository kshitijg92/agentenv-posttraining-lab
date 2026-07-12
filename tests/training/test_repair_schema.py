from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.training.repair_schema import (
    TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION,
    RepairedTranscriptArtifact,
    TrainingCandidateRepairRecord,
    TrainingCandidateRepairReviewRecord,
)


def _block_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "tool_name": "read_file",
        "arguments_hash": "xxh64:arguments",
        "baseline_tool_call_id": "tool_call_0001",
        "redundant_tool_call_ids": ["tool_call_0002"],
        "redundant_call_count": 1,
        "stable_workspace_hash": "xxh64:workspace",
        "normalized_observation_hash": "xxh64:observation",
        "public_check_index": None,
    }
    payload.update(updates)
    return payload


def _assessment_payload(
    *,
    blocks: list[dict[str, Any]],
    detector_version: str = "mechanical_redundancy_detector_v0",
    detector_code_hash: str = "xxh64:detector",
) -> dict[str, Any]:
    return {
        "detector_version": detector_version,
        "detector_code_hash": detector_code_hash,
        "evaluation_status": "complete",
        "blocks": blocks,
        "error_class": None,
        "error_message": None,
    }


def _repair_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "training_candidate_repair_record_v0",
        "repair_id": "repair_001",
        "trajectory_id": "trajectory_001",
        "eval_attempt_id": "eval_attempt_001",
        "source_training_candidate_record_hash": "xxh64:4444444444444444",
        "repair_artifact_type": "transcript",
        "repair_status": "completed",
        "original_artifact_ref": {
            "path": "agent/attempt_001/prompt_loop_result.json",
            "content_hash": "xxh64:original",
        },
        "repaired_artifact_ref": {
            "path": "transcripts/repair_001.json",
            "content_hash": "xxh64:repaired",
        },
        "repairer_version": "mechanical_redundancy_repairer_v0",
        "repairer_code_hash": "xxh64:repairer",
        "repair": {
            "repair_method": "mechanical_redundancy_deletion",
            "original_mechanical_redundancy_assessment": _assessment_payload(
                blocks=[_block_payload()]
            ),
            "after_repair_mechanical_redundancy_assessment": (
                _assessment_payload(blocks=[])
            ),
            "cannot_complete_reason": None,
        },
        "error_class": None,
        "error_message": None,
    }
    payload.update(updates)
    return payload


def _cannot_complete_payload() -> dict[str, Any]:
    payload = _repair_payload(
        repair_status="cannot_complete",
        repaired_artifact_ref=None,
    )
    payload["repair"]["after_repair_mechanical_redundancy_assessment"] = None
    payload["repair"]["cannot_complete_reason"] = (
        "matching tool-result message is absent"
    )
    return payload


def _repair_error_payload() -> dict[str, Any]:
    payload = _repair_payload(
        repair_status="repair_error",
        repaired_artifact_ref=None,
        error_class="OSError",
        error_message="failed to persist repaired transcript",
    )
    payload["repair"]["after_repair_mechanical_redundancy_assessment"] = None
    return payload


def test_completed_repair_record_accepts_validated_derivative() -> None:
    record = TrainingCandidateRepairRecord.model_validate(_repair_payload())

    assert record.schema_version == TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION
    assert record.repair_status == "completed"
    assert record.repaired_artifact_ref is not None
    assert record.repair.after_repair_mechanical_redundancy_assessment is not None
    assert record.repair.after_repair_mechanical_redundancy_assessment.blocks == []


def test_repaired_transcript_artifact_is_a_root_message_list() -> None:
    artifact = RepairedTranscriptArtifact.model_validate(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": '{"action":"final_answer"}'},
        ]
    )

    assert [message.role for message in artifact.root] == [
        "system",
        "user",
        "assistant",
    ]


def test_repaired_transcript_artifact_rejects_empty_list() -> None:
    with pytest.raises(
        ValidationError,
        match="repaired transcript artifacts must not be empty",
    ):
        RepairedTranscriptArtifact.model_validate([])


def test_cannot_complete_record_requires_reason_without_output() -> None:
    record = TrainingCandidateRepairRecord.model_validate(_cannot_complete_payload())

    assert record.repair_status == "cannot_complete"
    assert record.repaired_artifact_ref is None
    assert record.repair.cannot_complete_reason is not None


def test_repair_error_record_requires_typed_error_without_output() -> None:
    record = TrainingCandidateRepairRecord.model_validate(_repair_error_payload())

    assert record.repair_status == "repair_error"
    assert record.repaired_artifact_ref is None
    assert record.error_class == "OSError"


@pytest.mark.parametrize(
    "field_name", ["original_artifact_ref", "repaired_artifact_ref"]
)
def test_repair_artifact_refs_are_hash_pinned(field_name: str) -> None:
    payload = _repair_payload()
    payload[field_name].pop("content_hash")

    with pytest.raises(
        ValidationError, match=f"{field_name} must be content-hash pinned"
    ):
        TrainingCandidateRepairRecord.model_validate(payload)


def test_repair_record_requires_source_candidate_content_hash() -> None:
    with pytest.raises(ValidationError):
        TrainingCandidateRepairRecord.model_validate(
            _repair_payload(source_training_candidate_record_hash="not-a-hash")
        )


def test_completed_repair_requires_changed_artifact_content() -> None:
    payload = _repair_payload()
    payload["repaired_artifact_ref"]["content_hash"] = "xxh64:original"

    with pytest.raises(
        ValidationError,
        match="completed repair content must differ from the original artifact",
    ):
        TrainingCandidateRepairRecord.model_validate(payload)


def test_repair_requires_complete_original_assessment_with_blocks() -> None:
    payload = _repair_payload()
    payload["repair"]["original_mechanical_redundancy_assessment"] = (
        _assessment_payload(blocks=[])
    )

    with pytest.raises(
        ValidationError,
        match="repair records require detected mechanical-redundancy blocks",
    ):
        TrainingCandidateRepairRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("assessment_update", "match"),
    [
        (
            {"blocks": [_block_payload()]},
            "completed repairs require zero after-repair redundancy blocks",
        ),
        (
            {"detector_code_hash": "xxh64:different"},
            "before- and after-repair assessments must use the same detector",
        ),
    ],
)
def test_completed_repair_requires_clean_matching_after_assessment(
    assessment_update: dict[str, Any],
    match: str,
) -> None:
    payload = _repair_payload()
    after_assessment = payload["repair"][
        "after_repair_mechanical_redundancy_assessment"
    ]
    after_assessment.update(assessment_update)

    with pytest.raises(ValidationError, match=match):
        TrainingCandidateRepairRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("payload_update", "repair_update", "match"),
    [
        (
            {"repaired_artifact_ref": None},
            {},
            "completed repairs require repaired_artifact_ref",
        ),
        (
            {},
            {"after_repair_mechanical_redundancy_assessment": None},
            "completed repairs require an after-repair mechanical-redundancy assessment",
        ),
        (
            {"error_class": "Unexpected", "error_message": "unexpected"},
            {},
            "completed repairs cannot include error details",
        ),
        (
            {},
            {"cannot_complete_reason": "not applicable"},
            "completed repairs cannot include cannot_complete_reason",
        ),
    ],
)
def test_completed_repair_rejects_inconsistent_status_fields(
    payload_update: dict[str, Any],
    repair_update: dict[str, Any],
    match: str,
) -> None:
    payload = _repair_payload(**payload_update)
    payload["repair"].update(repair_update)

    with pytest.raises(ValidationError, match=match):
        TrainingCandidateRepairRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("payload_update", "repair_update", "match"),
    [
        (
            {},
            {"cannot_complete_reason": None},
            "cannot_complete repairs require cannot_complete_reason",
        ),
        (
            {
                "repaired_artifact_ref": {
                    "path": "transcripts/partial.json",
                    "content_hash": "xxh64:partial",
                }
            },
            {},
            "cannot_complete repairs cannot include repaired_artifact_ref",
        ),
        (
            {},
            {
                "after_repair_mechanical_redundancy_assessment": (
                    _assessment_payload(blocks=[])
                )
            },
            "cannot_complete repairs cannot include an after-repair assessment",
        ),
        (
            {"error_class": "Unexpected", "error_message": "unexpected"},
            {},
            "cannot_complete repairs cannot include error details",
        ),
    ],
)
def test_cannot_complete_rejects_inconsistent_status_fields(
    payload_update: dict[str, Any],
    repair_update: dict[str, Any],
    match: str,
) -> None:
    payload = _cannot_complete_payload()
    payload.update(payload_update)
    payload["repair"].update(repair_update)

    with pytest.raises(ValidationError, match=match):
        TrainingCandidateRepairRecord.model_validate(payload)


@pytest.mark.parametrize("missing_field", ["error_class", "error_message"])
def test_repair_error_requires_complete_error_details(missing_field: str) -> None:
    payload = _repair_error_payload()
    payload[missing_field] = None

    with pytest.raises(
        ValidationError,
        match="repair_error records require error_class and error_message",
    ):
        TrainingCandidateRepairRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("payload_update", "repair_update", "match"),
    [
        (
            {
                "repaired_artifact_ref": {
                    "path": "transcripts/partial.json",
                    "content_hash": "xxh64:partial",
                }
            },
            {},
            "repair_error records cannot include repaired_artifact_ref",
        ),
        (
            {},
            {
                "after_repair_mechanical_redundancy_assessment": (
                    _assessment_payload(blocks=[])
                )
            },
            "repair_error records cannot include an after-repair assessment",
        ),
        (
            {},
            {"cannot_complete_reason": "not applicable"},
            "repair_error records cannot include cannot_complete_reason",
        ),
    ],
)
def test_repair_error_rejects_inconsistent_status_fields(
    payload_update: dict[str, Any],
    repair_update: dict[str, Any],
    match: str,
) -> None:
    payload = _repair_error_payload()
    payload.update(payload_update)
    payload["repair"].update(repair_update)

    with pytest.raises(ValidationError, match=match):
        TrainingCandidateRepairRecord.model_validate(payload)


def test_repair_review_accepts_pending_record() -> None:
    review = TrainingCandidateRepairReviewRecord(
        repair_id="repair_001",
        source_training_candidate_repair_record_hash="xxh64:5555555555555555",
        review_status="not_reviewed",
    )

    assert review.review_decision is None


def test_repair_review_accepts_reviewed_decision() -> None:
    review = TrainingCandidateRepairReviewRecord(
        repair_id="repair_001",
        source_training_candidate_repair_record_hash="xxh64:5555555555555555",
        review_status="reviewed",
        review_id="review_001",
        reviewer_id="reviewer",
        review_decision="accepted",
    )

    assert review.review_decision == "accepted"


def test_pending_repair_review_rejects_review_details() -> None:
    with pytest.raises(
        ValidationError,
        match="not_reviewed repair reviews cannot include review details",
    ):
        TrainingCandidateRepairReviewRecord(
            repair_id="repair_001",
            source_training_candidate_repair_record_hash="xxh64:5555555555555555",
            review_status="not_reviewed",
            review_id="review_001",
        )


@pytest.mark.parametrize(
    "missing_field", ["review_id", "reviewer_id", "review_decision"]
)
def test_reviewed_repair_review_requires_complete_decision(
    missing_field: str,
) -> None:
    payload: dict[str, str | None] = {
        "repair_id": "repair_001",
        "source_training_candidate_repair_record_hash": ("xxh64:5555555555555555"),
        "review_status": "reviewed",
        "review_id": "review_001",
        "reviewer_id": "reviewer",
        "review_decision": "accepted",
    }
    payload[missing_field] = None

    with pytest.raises(ValidationError):
        TrainingCandidateRepairReviewRecord.model_validate(payload)
