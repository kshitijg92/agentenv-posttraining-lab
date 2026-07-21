from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from agentenv.training.preferences.materialization.schema import (
    DPOTrainingMaterializationRecord,
)


MATERIALIZATION_ADAPTER = TypeAdapter(DPOTrainingMaterializationRecord)


def _record(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_preference_pair_id": "preference_pair_aaaaaaaaaaaaaaaa",
        "source_preference_pair_record_hash": "xxh64:1111111111111111",
        "model_input_protocol_id": "qwen2_5_coder_3b_agentenv_json",
        "model_input_protocol_hash": "xxh64:2222222222222222",
        "serialization_mode": "shared_context_next_action",
        "max_sequence_length": 12,
        "materializer_version": "dpo_training_materializer_v0",
        "materializer_code_hash": "xxh64:3333333333333333",
        "status": "completed",
        "shared_prompt_token_count": 4,
        "chosen_input_ids": [151644, 100, 151645, 151644, 200, 201, 151645, 198],
        "chosen_labels": [-100, -100, -100, -100, 200, 201, 151645, -100],
        "chosen_sequence_length": 8,
        "chosen_response_token_count": 3,
        "rejected_input_ids": [151644, 100, 151645, 151644, 300, 151645, 198],
        "rejected_labels": [-100, -100, -100, -100, 300, 151645, -100],
        "rejected_sequence_length": 7,
        "rejected_response_token_count": 2,
    }
    payload.update(updates)
    return payload


def _failed_record(**updates: Any) -> dict[str, Any]:
    payload = _record(
        status="failed",
        failure_kind="materialization_error",
        observed_chosen_sequence_length=None,
        observed_rejected_sequence_length=None,
        error_class="TemplateRenderError",
        error_message="Pinned chat template could not render a preference pair.",
    )
    for field_name in (
        "shared_prompt_token_count",
        "chosen_input_ids",
        "chosen_labels",
        "chosen_sequence_length",
        "chosen_response_token_count",
        "rejected_input_ids",
        "rejected_labels",
        "rejected_sequence_length",
        "rejected_response_token_count",
    ):
        payload.pop(field_name)
    payload.update(updates)
    return payload


def test_completed_pair_materialization_has_two_response_only_label_sets() -> None:
    record = MATERIALIZATION_ADAPTER.validate_python(_record())

    assert record.status == "completed"
    assert record.shared_prompt_token_count == 4
    assert record.chosen_response_token_count == 3
    assert record.rejected_response_token_count == 2


def test_completed_pair_requires_identical_shared_prompt_tokens() -> None:
    with pytest.raises(ValidationError, match="identical shared-prompt token ids"):
        MATERIALIZATION_ADAPTER.validate_python(
            _record(rejected_input_ids=[151644, 999, 151645, 151644, 300, 151645, 198])
        )


@pytest.mark.parametrize("branch", ["chosen", "rejected"])
def test_completed_pair_masks_every_shared_prompt_token(branch: str) -> None:
    payload = _record()
    labels = list(payload[f"{branch}_labels"])
    labels[1] = 100

    with pytest.raises(ValidationError, match="shared-prompt label"):
        MATERIALIZATION_ADAPTER.validate_python(_record(**{f"{branch}_labels": labels}))


@pytest.mark.parametrize("branch", ["chosen", "rejected"])
def test_completed_pair_scores_every_response_token(branch: str) -> None:
    payload = _record()
    labels = list(payload[f"{branch}_labels"])
    labels[payload["shared_prompt_token_count"]] = -100

    with pytest.raises(ValidationError, match="response label"):
        MATERIALIZATION_ADAPTER.validate_python(_record(**{f"{branch}_labels": labels}))


@pytest.mark.parametrize("branch", ["chosen", "rejected"])
def test_completed_pair_masks_post_response_template_tokens(branch: str) -> None:
    payload = _record()
    labels = list(payload[f"{branch}_labels"])
    labels[-1] = payload[f"{branch}_input_ids"][-1]

    with pytest.raises(ValidationError, match="post-response template label"):
        MATERIALIZATION_ADAPTER.validate_python(_record(**{f"{branch}_labels": labels}))


def test_completed_pair_rejects_identical_response_tokens() -> None:
    with pytest.raises(ValidationError, match="response token ids must differ"):
        MATERIALIZATION_ADAPTER.validate_python(
            _record(
                rejected_input_ids=[
                    151644,
                    100,
                    151645,
                    151644,
                    200,
                    201,
                    151645,
                    198,
                ],
                rejected_labels=[
                    -100,
                    -100,
                    -100,
                    -100,
                    200,
                    201,
                    151645,
                    -100,
                ],
                rejected_sequence_length=8,
                rejected_response_token_count=3,
            )
        )


def test_completed_pair_rejects_a_half_materialized_branch() -> None:
    payload = _record()
    payload.pop("rejected_labels")

    with pytest.raises(ValidationError):
        MATERIALIZATION_ADAPTER.validate_python(payload)


def test_sequence_length_failure_accounts_for_both_branches() -> None:
    record = MATERIALIZATION_ADAPTER.validate_python(
        _failed_record(
            failure_kind="sequence_length_exceeded",
            observed_chosen_sequence_length=13,
            observed_rejected_sequence_length=11,
            error_class="SequenceLengthExceededError",
            error_message="At least one branch exceeds max_sequence_length.",
        )
    )

    assert record.status == "failed"
    assert record.observed_chosen_sequence_length == 13
    assert record.observed_rejected_sequence_length == 11


@pytest.mark.parametrize(
    ("chosen_length", "rejected_length"),
    [(None, 13), (13, None), (12, 12)],
)
def test_sequence_length_failure_requires_two_lengths_and_one_over_limit(
    chosen_length: int | None,
    rejected_length: int | None,
) -> None:
    with pytest.raises(ValidationError, match="sequence-length failures require"):
        MATERIALIZATION_ADAPTER.validate_python(
            _failed_record(
                failure_kind="sequence_length_exceeded",
                observed_chosen_sequence_length=chosen_length,
                observed_rejected_sequence_length=rejected_length,
            )
        )


def test_materialization_error_cannot_include_partial_branch_lengths() -> None:
    with pytest.raises(ValidationError, match="cannot claim observed branch lengths"):
        MATERIALIZATION_ADAPTER.validate_python(
            _failed_record(observed_chosen_sequence_length=7)
        )


def test_materialization_record_does_not_select_a_reference_model() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MATERIALIZATION_ADAPTER.validate_python(
            _record(reference_model_id="qwen-reference")
        )
