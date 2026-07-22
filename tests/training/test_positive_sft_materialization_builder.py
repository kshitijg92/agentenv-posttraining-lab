from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pytest
from tokenizers import normalizers

from agentenv.hashing import hash_file, hash_json
from agentenv.models.input_protocol import (
    ModelGeneratedCharacterSpan,
    load_model_input_protocol,
    render_model_input_with_generation_ownership,
)
from agentenv.training.positive_sft.identity import build_positive_sft_example_id
from agentenv.training.positive_sft.materialization.builder import (
    POSITIVE_SFT_TRAINING_MATERIALIZER_VERSION,
    materialize_positive_sft_examples,
)
from agentenv.training.positive_sft.materialization.schema import (
    TRAINER_IGNORE_INDEX,
)
from agentenv.training.tokenization import (
    TokenOwnershipBoundaryCrossingError,
    TokenizerOutputContractError,
    tokenize_model_input_with_ownership,
)
from agentenv.training.positive_sft.schema import PositiveSFTExampleRecord


PROTOCOL_PATH = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)


@dataclass
class _BackendTokenizer:
    normalizer: Any = None


class _CharacterTokenizer:
    is_fast = True

    def __init__(self, *, normalizer: Any = None) -> None:
        self.backend_tokenizer = _BackendTokenizer(normalizer)
        self.call_count = 0

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        return_offsets_mapping: bool,
    ) -> dict[str, object]:
        assert add_special_tokens is False
        assert return_offsets_mapping is True
        self.call_count += 1
        return {
            "input_ids": [ord(character) for character in text],
            "offset_mapping": [
                (character_index, character_index + 1)
                for character_index in range(len(text))
            ],
        }

    def decode(
        self,
        token_ids: Sequence[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        assert skip_special_tokens is False
        assert clean_up_tokenization_spaces is False
        return "".join(chr(token_id) for token_id in token_ids)


class _RaisingTokenizer(_CharacterTokenizer):
    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        return_offsets_mapping: bool,
    ) -> dict[str, object]:
        raise RuntimeError("private transcript fragment")


class _StaticTokenizer:
    is_fast = True

    def __init__(
        self,
        *,
        input_ids: list[int],
        offsets: list[tuple[int, int]],
        decoded_text: str,
    ) -> None:
        self.backend_tokenizer = _BackendTokenizer()
        self._input_ids = input_ids
        self._offsets = offsets
        self._decoded_text = decoded_text

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        return_offsets_mapping: bool,
    ) -> dict[str, object]:
        return {
            "input_ids": self._input_ids,
            "offset_mapping": self._offsets,
        }

    def decode(
        self,
        token_ids: Sequence[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        return self._decoded_text


def test_materializer_tokenizes_full_transcript_once_and_uses_owned_spans() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)
    example = _example()
    tokenizer = _CharacterTokenizer()

    records = materialize_positive_sft_examples(
        [example],
        protocol=protocol,
        tokenizer=tokenizer,
        max_sequence_length=10_000,
    )

    assert len(records) == 1
    record = records[0]
    assert record.status == "completed"
    rendered = render_model_input_with_generation_ownership(
        protocol,
        example.messages,
        mode="completed_transcript",
    )
    expected_labels = [
        ord(character)
        if any(
            span.start <= index < span.end for span in rendered.model_generated_spans
        )
        else TRAINER_IGNORE_INDEX
        for index, character in enumerate(rendered.text)
    ]
    assert tokenizer.call_count == 1
    assert record.input_ids == [ord(character) for character in rendered.text]
    assert record.labels == expected_labels
    assert record.sequence_length == len(rendered.text)
    assert record.supervised_token_count == sum(
        label != TRAINER_IGNORE_INDEX for label in expected_labels
    )
    assert record.ignored_token_count == sum(
        label == TRAINER_IGNORE_INDEX for label in expected_labels
    )
    assert record.source_positive_sft_example_id == example.example_id
    assert record.source_positive_sft_example_record_hash == hash_json(
        example.model_dump(mode="json")
    )
    assert record.model_input_protocol_id == protocol.record.protocol_id
    assert record.model_input_protocol_hash == hash_file(PROTOCOL_PATH)
    assert record.materializer_version == POSITIVE_SFT_TRAINING_MATERIALIZER_VERSION

    assistant_header_start = rendered.text.index("<|im_start|>assistant\n")
    assert all(
        label == TRAINER_IGNORE_INDEX
        for label in record.labels[
            assistant_header_start : assistant_header_start
            + len("<|im_start|>assistant\n")
        ]
    )
    tool_content_start = rendered.text.index('{"status":"ok"}')
    assert all(
        label == TRAINER_IGNORE_INDEX
        for label in record.labels[
            tool_content_start : tool_content_start + len('{"status":"ok"}')
        ]
    )
    first_assistant_end = rendered.text.index(
        "<|im_end|>",
        assistant_header_start,
    )
    assert record.labels[first_assistant_end] == ord("<")


def test_materializer_persists_overlength_as_failed_result() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    record = materialize_positive_sft_examples(
        [_example()],
        protocol=protocol,
        tokenizer=_CharacterTokenizer(),
        max_sequence_length=1,
    )[0]

    assert record.status == "failed"
    assert record.failure_kind == "sequence_length_exceeded"
    assert record.observed_sequence_length is not None
    assert record.observed_sequence_length > record.max_sequence_length
    assert record.error_class == "SequenceLengthExceededError"


def test_materializer_persists_normalization_drift_without_content() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)
    private_content = 'private e\u0301 {"action":"final_answer"}'

    record = materialize_positive_sft_examples(
        [_example(final_assistant_content=private_content)],
        protocol=protocol,
        tokenizer=_CharacterTokenizer(normalizer=normalizers.NFC()),
        max_sequence_length=10_000,
    )[0]

    assert record.status == "failed"
    assert record.failure_kind == "materialization_error"
    assert record.observed_sequence_length is None
    assert record.error_class == ("TokenizerNormalizationChangedRenderedTextError")
    assert private_content not in record.error_message
    assert "private" not in record.error_message


def test_materializer_redacts_unknown_runtime_error_content() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    record = materialize_positive_sft_examples(
        [_example()],
        protocol=protocol,
        tokenizer=_RaisingTokenizer(),
        max_sequence_length=10_000,
    )[0]

    assert record.status == "failed"
    assert record.failure_kind == "materialization_error"
    assert record.error_class == "RuntimeError"
    assert record.error_message == (
        "Positive-SFT materialization failed with RuntimeError."
    )
    assert "private transcript fragment" not in record.error_message


def test_materializer_returns_exactly_one_result_per_source_in_source_order() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)
    examples = [_example(identity_suffix="1"), _example(identity_suffix="2")]

    records = materialize_positive_sft_examples(
        examples,
        protocol=protocol,
        tokenizer=_CharacterTokenizer(),
        max_sequence_length=10_000,
    )

    assert [record.source_positive_sft_example_id for record in records] == [
        example.example_id for example in examples
    ]


def test_materializer_rejects_invalid_sequence_policy_before_building_rows() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    with pytest.raises(ValueError, match="positive integer"):
        materialize_positive_sft_examples(
            [],
            protocol=protocol,
            tokenizer=_CharacterTokenizer(),
            max_sequence_length=0,
        )


def test_token_label_mapping_rejects_ownership_boundary_crossing() -> None:
    tokenizer = _StaticTokenizer(
        input_ids=[1],
        offsets=[(0, 2)],
        decoded_text="ca",
    )

    with pytest.raises(TokenOwnershipBoundaryCrossingError):
        tokenize_model_input_with_ownership(
            tokenizer,
            rendered_text="ca",
            model_generated_spans=[ModelGeneratedCharacterSpan(start=1, end=2)],
            trainer_ignore_index=TRAINER_IGNORE_INDEX,
        )


def test_token_label_mapping_requires_complete_source_coverage() -> None:
    tokenizer = _StaticTokenizer(
        input_ids=[1],
        offsets=[(0, 1)],
        decoded_text="ab",
    )

    with pytest.raises(TokenizerOutputContractError, match="do not cover"):
        tokenize_model_input_with_ownership(
            tokenizer,
            rendered_text="ab",
            model_generated_spans=[ModelGeneratedCharacterSpan(start=0, end=1)],
            trainer_ignore_index=TRAINER_IGNORE_INDEX,
        )


def _example(
    *,
    identity_suffix: str = "0",
    final_assistant_content: str = '{"action":"final_answer","text":"done Ω"}',
) -> PositiveSFTExampleRecord:
    candidate_hash = f"xxh64:{identity_suffix * 16}"
    source_artifact_hash = f"xxh64:{(identity_suffix + '1')[:1] * 16}"
    review_hash = f"xxh64:{(identity_suffix + '2')[:1] * 16}"
    example_id = build_positive_sft_example_id(
        source_type="original",
        source_training_candidate_record_hash=candidate_hash,
        source_artifact_content_hash=source_artifact_hash,
        source_positive_sft_review_record_hash=review_hash,
    )
    final_message_id = "message_00000000000000000000000000000005"
    return PositiveSFTExampleRecord.model_validate(
        {
            "example_id": example_id,
            "provenance_ids": {
                "trajectory_id": f"trajectory_{identity_suffix}",
                "eval_suite_id": None,
                "eval_run_id": f"eval_run_{identity_suffix}",
                "eval_attempt_id": f"eval_attempt_{identity_suffix}",
                "agent_attempt_id": f"agent_attempt_{identity_suffix}",
                "task_id": "task_001",
                "policy_id": "policy_001",
            },
            "prompt_provenance": {
                "prompt_builder_version": "prompt_builder_v0",
                "prompt_builder_code_hash": "xxh64:aaaaaaaaaaaaaaaa",
            },
            "review_provenance": {
                "source_positive_sft_review_record_hash": review_hash,
                "positive_sft_review_id": f"review_{identity_suffix}",
                "last_approved_assistant_message_id": final_message_id,
            },
            "source_provenance": {
                "source_type": "original",
                "source_training_candidate_record_hash": candidate_hash,
                "source_artifact_ref": {
                    "path": "prompt_loop_result.json",
                    "content_hash": source_artifact_hash,
                },
                "task_outcome_provenance": "executed_source_trajectory",
            },
            "task_input": {
                "task_id": "task_001",
                "instruction": "Inspect and fix the code.",
                "allowed_tools": ["read_file"],
                "public_checks": ["pytest -q"],
                "max_turns": 8,
                "timeout_seconds": 120,
                "network": "off",
            },
            "messages": [
                {
                    "message_id": "message_00000000000000000000000000000001",
                    "role": "system",
                    "content": "Use one JSON action per turn.",
                },
                {
                    "message_id": "message_00000000000000000000000000000002",
                    "role": "user",
                    "content": "Inspect and fix the code.",
                },
                {
                    "message_id": "message_00000000000000000000000000000003",
                    "role": "assistant",
                    "content": (
                        '{"action":"tool_call","tool_name":"read_file",'
                        '"arguments":{"path":"src/a.py"}}'
                    ),
                    "tool_call_id": "tool_call_001",
                },
                {
                    "message_id": "message_00000000000000000000000000000004",
                    "role": "tool",
                    "content": '{"status":"ok"}',
                    "name": "read_file",
                    "tool_call_id": "tool_call_001",
                },
                {
                    "message_id": final_message_id,
                    "role": "assistant",
                    "content": final_assistant_content,
                },
            ],
        }
    )
