from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from agentenv.training.positive_sft.materialization.schema import (
    PositiveSFTMaterializationRecord,
)


MATERIALIZATION_ADAPTER = TypeAdapter(PositiveSFTMaterializationRecord)


def _record(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_positive_sft_example_id": "positive_sft_example_aaaaaaaaaaaaaaaa",
        "source_positive_sft_example_record_hash": "xxh64:1111111111111111",
        "model_input_protocol_id": "qwen2_5_coder_3b_agentenv_json",
        "model_input_protocol_hash": "xxh64:2222222222222222",
        "serialization_mode": "completed_transcript",
        "max_sequence_length": 8,
        "materializer_version": "positive_sft_materializer_v0",
        "materializer_code_hash": "xxh64:3333333333333333",
        "status": "completed",
        "input_ids": [151644, 100, 151645, 151644, 200, 151645],
        "labels": [-100, -100, -100, -100, 200, 151645],
        "sequence_length": 6,
        "supervised_token_count": 2,
        "ignored_token_count": 4,
    }
    payload.update(updates)
    return payload


def test_completed_materialization_persists_trainer_style_labels() -> None:
    record = MATERIALIZATION_ADAPTER.validate_python(_record())

    assert record.status == "completed"
    assert record.sequence_length == 6
    assert record.supervised_token_count == 2
    assert record.ignored_token_count == 4


def test_completed_materialization_requires_aligned_token_and_label_lengths() -> None:
    with pytest.raises(ValidationError, match="must have the same length"):
        MATERIALIZATION_ADAPTER.validate_python(
            _record(labels=[-100, -100, -100])
        )


def test_completed_materialization_rejects_non_trainer_label() -> None:
    with pytest.raises(ValidationError, match="corresponding input token id"):
        MATERIALIZATION_ADAPTER.validate_python(
            _record(labels=[-100, -100, -100, -100, 999, 151645])
        )


def test_completed_materialization_requires_supervised_tokens() -> None:
    with pytest.raises(ValidationError, match="supervised_token_count"):
        MATERIALIZATION_ADAPTER.validate_python(
            _record(
                labels=[-100, -100, -100, -100, -100, -100],
                supervised_token_count=2,
                ignored_token_count=4,
            )
        )


def test_completed_materialization_cannot_exceed_sequence_limit() -> None:
    payload = _record(
        input_ids=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        labels=[-100, -100, -100, -100, -100, -100, -100, 8, 9],
        sequence_length=9,
        supervised_token_count=2,
        ignored_token_count=7,
    )
    with pytest.raises(ValidationError, match="cannot exceed max_sequence_length"):
        MATERIALIZATION_ADAPTER.validate_python(payload)


def test_sequence_length_failure_preserves_observed_length() -> None:
    payload = _record(
        status="failed",
        failure_kind="sequence_length_exceeded",
        observed_sequence_length=9,
        error_class="SequenceLengthExceededError",
        error_message="Rendered sequence has 9 tokens; maximum is 8.",
    )
    for field_name in (
        "input_ids",
        "labels",
        "sequence_length",
        "supervised_token_count",
        "ignored_token_count",
    ):
        payload.pop(field_name)

    record = MATERIALIZATION_ADAPTER.validate_python(payload)

    assert record.status == "failed"
    assert record.observed_sequence_length == 9


@pytest.mark.parametrize("observed_length", [None, 8])
def test_sequence_length_failure_requires_length_above_limit(
    observed_length: int | None,
) -> None:
    payload = _record(
        status="failed",
        failure_kind="sequence_length_exceeded",
        observed_sequence_length=observed_length,
        error_class="SequenceLengthExceededError",
        error_message="Sequence did not fit.",
    )
    for field_name in (
        "input_ids",
        "labels",
        "sequence_length",
        "supervised_token_count",
        "ignored_token_count",
    ):
        payload.pop(field_name)

    with pytest.raises(ValidationError, match="sequence-length failures require"):
        MATERIALIZATION_ADAPTER.validate_python(payload)


def test_runtime_materialization_failure_is_distinct_from_overlength() -> None:
    payload = _record(
        status="failed",
        failure_kind="materialization_error",
        observed_sequence_length=None,
        error_class="TemplateRenderError",
        error_message="Pinned chat template could not render the transcript.",
    )
    for field_name in (
        "input_ids",
        "labels",
        "sequence_length",
        "supervised_token_count",
        "ignored_token_count",
    ):
        payload.pop(field_name)

    record = MATERIALIZATION_ADAPTER.validate_python(payload)

    assert record.status == "failed"
    assert record.failure_kind == "materialization_error"
