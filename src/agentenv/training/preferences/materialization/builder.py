from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agentenv.hashing import hash_directory, hash_file
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    ModelGeneratedCharacterSpan,
    render_model_input,
    render_model_input_with_generation_ownership,
)
from agentenv.models.schema import MessageWithoutMetadata
from agentenv.training.preferences.hashing import hash_preference_pair_record
from agentenv.training.preferences.materialization.schema import (
    TRAINER_IGNORE_INDEX,
    CompletedDPOTrainingMaterializationRecord,
    DPOTrainingMaterializationRecord,
    FailedDPOTrainingMaterializationRecord,
)
from agentenv.training.preferences.materialization.source_reconstruction import (
    DPOPreferencePairMaterializationInput,
)
from agentenv.training.tokenization import (
    ContentSafeMaterializationError,
    MaterializationTokenizer,
    TokenizedModelInput,
    content_safe_materialization_error_message,
    tokenize_model_input_with_ownership,
)


DPO_TRAINING_MATERIALIZER_VERSION = "dpo_training_materializer_v0"


class DPOCanonicalPromptMismatchError(ContentSafeMaterializationError):
    pass


class DPOResponseOwnershipError(ContentSafeMaterializationError):
    pass


class DPOBranchLabelLayoutError(ContentSafeMaterializationError):
    pass


@dataclass(frozen=True)
class _TokenizedDPOBranch:
    tokenized: TokenizedModelInput
    prompt_token_count: int
    response_token_count: int


def compute_dpo_training_materializer_code_hash() -> str:
    agentenv_source_root = Path(__file__).resolve().parents[3]
    return hash_directory(agentenv_source_root)


def materialize_dpo_preference_pair_inputs(
    pairs: Sequence[DPOPreferencePairMaterializationInput],
    *,
    protocol: LoadedModelInputProtocol,
    tokenizer: MaterializationTokenizer,
    max_sequence_length: int,
) -> tuple[DPOTrainingMaterializationRecord, ...]:
    if type(max_sequence_length) is not int or max_sequence_length <= 0:
        raise ValueError("max_sequence_length must be a positive integer")

    protocol_hash = hash_file(protocol.source_path)
    materializer_code_hash = compute_dpo_training_materializer_code_hash()
    return tuple(
        _materialize_dpo_preference_pair(
            pair,
            protocol=protocol,
            tokenizer=tokenizer,
            max_sequence_length=max_sequence_length,
            protocol_hash=protocol_hash,
            materializer_code_hash=materializer_code_hash,
        )
        for pair in pairs
    )


def _materialize_dpo_preference_pair(
    pair: DPOPreferencePairMaterializationInput,
    *,
    protocol: LoadedModelInputProtocol,
    tokenizer: MaterializationTokenizer,
    max_sequence_length: int,
    protocol_hash: str,
    materializer_code_hash: str,
) -> DPOTrainingMaterializationRecord:
    common_fields = {
        "source_preference_pair_id": pair.source_pair.preference_pair_id,
        "source_preference_pair_record_hash": hash_preference_pair_record(
            pair.source_pair
        ),
        "model_input_protocol_id": protocol.record.protocol_id,
        "model_input_protocol_hash": protocol_hash,
        "serialization_mode": "shared_context_next_action",
        "max_sequence_length": max_sequence_length,
        "materializer_version": DPO_TRAINING_MATERIALIZER_VERSION,
        "materializer_code_hash": materializer_code_hash,
    }
    try:
        prompt_text = render_model_input(
            protocol,
            pair.context_messages,
            mode="generation",
        )
        chosen = _render_and_tokenize_branch(
            protocol=protocol,
            tokenizer=tokenizer,
            context_messages=pair.context_messages,
            action=pair.chosen_action,
            prompt_text=prompt_text,
        )
        rejected = _render_and_tokenize_branch(
            protocol=protocol,
            tokenizer=tokenizer,
            context_messages=pair.context_messages,
            action=pair.rejected_action,
            prompt_text=prompt_text,
        )
        _validate_shared_tokenized_prompt(chosen, rejected)
    except Exception as exc:
        return FailedDPOTrainingMaterializationRecord(
            **common_fields,
            status="failed",
            failure_kind="materialization_error",
            observed_chosen_sequence_length=None,
            observed_rejected_sequence_length=None,
            error_class=type(exc).__name__,
            error_message=content_safe_materialization_error_message(
                exc,
                operation="DPO pair materialization",
            ),
        )

    chosen_length = len(chosen.tokenized.input_ids)
    rejected_length = len(rejected.tokenized.input_ids)
    if max(chosen_length, rejected_length) > max_sequence_length:
        return FailedDPOTrainingMaterializationRecord(
            **common_fields,
            status="failed",
            failure_kind="sequence_length_exceeded",
            observed_chosen_sequence_length=chosen_length,
            observed_rejected_sequence_length=rejected_length,
            error_class="SequenceLengthExceededError",
            error_message=(
                "At least one canonical DPO branch exceeds max_sequence_length; "
                f"observed_chosen_sequence_length={chosen_length}, "
                f"observed_rejected_sequence_length={rejected_length}, "
                f"max_sequence_length={max_sequence_length}"
            ),
        )

    return CompletedDPOTrainingMaterializationRecord(
        **common_fields,
        status="completed",
        shared_prompt_token_count=chosen.prompt_token_count,
        chosen_input_ids=list(chosen.tokenized.input_ids),
        chosen_labels=list(chosen.tokenized.labels),
        chosen_sequence_length=chosen_length,
        chosen_response_token_count=chosen.response_token_count,
        rejected_input_ids=list(rejected.tokenized.input_ids),
        rejected_labels=list(rejected.tokenized.labels),
        rejected_sequence_length=rejected_length,
        rejected_response_token_count=rejected.response_token_count,
    )


def _render_and_tokenize_branch(
    *,
    protocol: LoadedModelInputProtocol,
    tokenizer: MaterializationTokenizer,
    context_messages: Sequence[MessageWithoutMetadata],
    action: MessageWithoutMetadata,
    prompt_text: str,
) -> _TokenizedDPOBranch:
    rendered = render_model_input_with_generation_ownership(
        protocol,
        (*context_messages, action),
        mode="completed_transcript",
    )
    if not rendered.text.startswith(prompt_text):
        raise DPOCanonicalPromptMismatchError(
            "Completed DPO branch does not begin with the canonical generation prompt"
        )
    response_span = _select_compared_response_span(
        rendered.model_generated_spans,
        prompt_character_count=len(prompt_text),
    )
    tokenized = tokenize_model_input_with_ownership(
        tokenizer,
        rendered_text=rendered.text,
        model_generated_spans=(response_span,),
        trainer_ignore_index=TRAINER_IGNORE_INDEX,
    )
    prompt_token_count, response_token_count = _measure_label_layout(tokenized.labels)
    return _TokenizedDPOBranch(
        tokenized=tokenized,
        prompt_token_count=prompt_token_count,
        response_token_count=response_token_count,
    )


def _select_compared_response_span(
    spans: Sequence[ModelGeneratedCharacterSpan],
    *,
    prompt_character_count: int,
) -> ModelGeneratedCharacterSpan:
    matches = [span for span in spans if span.start == prompt_character_count]
    if len(matches) != 1:
        raise DPOResponseOwnershipError(
            "Canonical completed branch must contain exactly one model-owned "
            "response span beginning at the generation-prompt boundary"
        )
    if any(span.start > prompt_character_count for span in spans):
        raise DPOResponseOwnershipError(
            "Canonical completed branch contains multiple post-prompt model-owned spans"
        )
    return matches[0]


def _measure_label_layout(labels: Sequence[int]) -> tuple[int, int]:
    try:
        response_start = next(
            index for index, label in enumerate(labels) if label != TRAINER_IGNORE_INDEX
        )
    except StopIteration as exc:  # guarded by the shared tokenizer contract
        raise DPOBranchLabelLayoutError(
            "Canonical DPO branch contains no scored response tokens"
        ) from exc

    response_end = response_start
    while response_end < len(labels) and (labels[response_end] != TRAINER_IGNORE_INDEX):
        response_end += 1
    if any(label != TRAINER_IGNORE_INDEX for label in labels[response_end:]):
        raise DPOBranchLabelLayoutError(
            "Canonical DPO response labels must form one contiguous span"
        )
    return response_start, response_end - response_start


def _validate_shared_tokenized_prompt(
    chosen: _TokenizedDPOBranch,
    rejected: _TokenizedDPOBranch,
) -> None:
    if chosen.prompt_token_count != rejected.prompt_token_count:
        raise DPOCanonicalPromptMismatchError(
            "Chosen and rejected branches produce different prompt token counts"
        )
    prompt_end = chosen.prompt_token_count
    if (
        chosen.tokenized.input_ids[:prompt_end]
        != (rejected.tokenized.input_ids[:prompt_end])
    ):
        raise DPOCanonicalPromptMismatchError(
            "Chosen and rejected branches produce different prompt token ids"
        )
