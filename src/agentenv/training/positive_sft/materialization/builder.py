from collections.abc import Sequence
from pathlib import Path

from agentenv.hashing import hash_directory, hash_file, hash_json
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    render_model_input_with_generation_ownership,
)
from agentenv.training.positive_sft.materialization.schema import (
    TRAINER_IGNORE_INDEX,
    CompletedPositiveSFTTrainingMaterializationRecord,
    FailedPositiveSFTTrainingMaterializationRecord,
    PositiveSFTTrainingMaterializationRecord,
)
from agentenv.training.tokenization import (
    MaterializationTokenizer,
    content_safe_materialization_error_message,
    tokenize_model_input_with_ownership,
)
from agentenv.training.positive_sft.schema import PositiveSFTExampleRecord


POSITIVE_SFT_TRAINING_MATERIALIZER_VERSION = "positive_sft_training_materializer_v0"


def compute_positive_sft_training_materializer_code_hash() -> str:
    agentenv_source_root = Path(__file__).resolve().parents[3]
    return hash_directory(agentenv_source_root)


def materialize_positive_sft_examples(
    examples: Sequence[PositiveSFTExampleRecord],
    *,
    protocol: LoadedModelInputProtocol,
    tokenizer: MaterializationTokenizer,
    max_sequence_length: int,
) -> tuple[PositiveSFTTrainingMaterializationRecord, ...]:
    if type(max_sequence_length) is not int or max_sequence_length <= 0:
        raise ValueError("max_sequence_length must be a positive integer")

    protocol_hash = hash_file(protocol.source_path)
    materializer_code_hash = compute_positive_sft_training_materializer_code_hash()
    return tuple(
        _materialize_positive_sft_example(
            example,
            protocol=protocol,
            tokenizer=tokenizer,
            max_sequence_length=max_sequence_length,
            protocol_hash=protocol_hash,
            materializer_code_hash=materializer_code_hash,
        )
        for example in examples
    )


def _materialize_positive_sft_example(
    example: PositiveSFTExampleRecord,
    *,
    protocol: LoadedModelInputProtocol,
    tokenizer: MaterializationTokenizer,
    max_sequence_length: int,
    protocol_hash: str,
    materializer_code_hash: str,
) -> PositiveSFTTrainingMaterializationRecord:
    common_fields = {
        "source_positive_sft_example_id": example.example_id,
        "source_positive_sft_example_record_hash": hash_json(
            example.model_dump(mode="json")
        ),
        "model_input_protocol_id": protocol.record.protocol_id,
        "model_input_protocol_hash": protocol_hash,
        "serialization_mode": "completed_transcript",
        "max_sequence_length": max_sequence_length,
        "materializer_version": POSITIVE_SFT_TRAINING_MATERIALIZER_VERSION,
        "materializer_code_hash": materializer_code_hash,
    }
    try:
        rendered = render_model_input_with_generation_ownership(
            protocol,
            example.messages,
            mode="completed_transcript",
        )
        tokenized = tokenize_model_input_with_ownership(
            tokenizer,
            rendered_text=rendered.text,
            model_generated_spans=rendered.model_generated_spans,
            trainer_ignore_index=TRAINER_IGNORE_INDEX,
        )
    except Exception as exc:
        return FailedPositiveSFTTrainingMaterializationRecord(
            **common_fields,
            status="failed",
            failure_kind="materialization_error",
            observed_sequence_length=None,
            error_class=type(exc).__name__,
            error_message=content_safe_materialization_error_message(
                exc,
                operation="Positive-SFT materialization",
            ),
        )

    sequence_length = len(tokenized.input_ids)
    if sequence_length > max_sequence_length:
        return FailedPositiveSFTTrainingMaterializationRecord(
            **common_fields,
            status="failed",
            failure_kind="sequence_length_exceeded",
            observed_sequence_length=sequence_length,
            error_class="SequenceLengthExceededError",
            error_message=(
                "Canonical completed transcript exceeds max_sequence_length; "
                f"observed_sequence_length={sequence_length}, "
                f"max_sequence_length={max_sequence_length}"
            ),
        )

    supervised_token_count = sum(
        label != TRAINER_IGNORE_INDEX for label in tokenized.labels
    )
    return CompletedPositiveSFTTrainingMaterializationRecord(
        **common_fields,
        status="completed",
        input_ids=list(tokenized.input_ids),
        labels=list(tokenized.labels),
        sequence_length=sequence_length,
        supervised_token_count=supervised_token_count,
        ignored_token_count=sequence_length - supervised_token_count,
    )
