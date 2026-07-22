from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from agentenv.hashing import hash_file
from agentenv.models.input_protocol import (
    load_model_input_protocol,
    render_model_input,
    render_model_input_with_generation_ownership,
)
from agentenv.models.schema import MessageWithoutMetadata
from agentenv.training.preferences.hashing import (
    build_preference_pair_id,
    hash_preference_pair_record,
)
from agentenv.training.preferences.materialization.builder import (
    DPO_TRAINING_MATERIALIZER_VERSION,
    materialize_dpo_preference_pair_inputs,
)
from agentenv.training.preferences.materialization.schema import (
    TRAINER_IGNORE_INDEX,
)
from agentenv.training.preferences.materialization.source_reconstruction import (
    DPOPreferencePairMaterializationInput,
)
from agentenv.training.preferences.schema import PreferencePairRecord


PROTOCOL_PATH = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)


@dataclass
class _BackendTokenizer:
    normalizer: Any = None


class _CharacterTokenizer:
    is_fast = True

    def __init__(self) -> None:
        self.backend_tokenizer = _BackendTokenizer()
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
        raise RuntimeError("private chosen or rejected content")


def test_materializer_builds_one_pair_with_an_identical_masked_prompt() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)
    pair = _pair_input()
    tokenizer = _CharacterTokenizer()

    record = materialize_dpo_preference_pair_inputs(
        [pair],
        protocol=protocol,
        tokenizer=tokenizer,
        max_sequence_length=10_000,
    )[0]

    assert record.status == "completed"
    prompt_text = render_model_input(
        protocol,
        pair.context_messages,
        mode="generation",
    )
    chosen_rendered = render_model_input_with_generation_ownership(
        protocol,
        (*pair.context_messages, pair.chosen_action),
        mode="completed_transcript",
    )
    rejected_rendered = render_model_input_with_generation_ownership(
        protocol,
        (*pair.context_messages, pair.rejected_action),
        mode="completed_transcript",
    )
    assert tokenizer.call_count == 2
    assert record.shared_prompt_token_count == len(prompt_text)
    assert (
        record.chosen_input_ids[: record.shared_prompt_token_count]
        == (record.rejected_input_ids[: record.shared_prompt_token_count])
    )
    assert all(
        label == TRAINER_IGNORE_INDEX
        for label in record.chosen_labels[: record.shared_prompt_token_count]
    )
    assert all(
        label == TRAINER_IGNORE_INDEX
        for label in record.rejected_labels[: record.shared_prompt_token_count]
    )
    assert record.chosen_input_ids == [
        ord(character) for character in chosen_rendered.text
    ]
    assert record.rejected_input_ids == [
        ord(character) for character in rejected_rendered.text
    ]

    chosen_span = chosen_rendered.model_generated_spans[-1]
    assert chosen_span.start == len(prompt_text)
    assert record.chosen_response_token_count == chosen_span.end - chosen_span.start
    assert all(
        record.chosen_labels[index] == record.chosen_input_ids[index]
        for index in range(chosen_span.start, chosen_span.end)
    )
    assert all(
        label == TRAINER_IGNORE_INDEX
        for label in record.chosen_labels[chosen_span.end :]
    )
    earlier_assistant_index = chosen_rendered.text.index(
        pair.context_messages[2].content
    )
    assert record.chosen_labels[earlier_assistant_index] == TRAINER_IGNORE_INDEX
    assert record.source_preference_pair_id == pair.source_pair.preference_pair_id
    assert record.source_preference_pair_record_hash == hash_preference_pair_record(
        pair.source_pair
    )
    assert record.model_input_protocol_hash == hash_file(PROTOCOL_PATH)
    assert record.materializer_version == DPO_TRAINING_MATERIALIZER_VERSION


def test_materializer_fails_the_whole_pair_when_either_branch_is_overlength() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    record = materialize_dpo_preference_pair_inputs(
        [_pair_input()],
        protocol=protocol,
        tokenizer=_CharacterTokenizer(),
        max_sequence_length=1,
    )[0]

    assert record.status == "failed"
    assert record.failure_kind == "sequence_length_exceeded"
    assert record.observed_chosen_sequence_length is not None
    assert record.observed_rejected_sequence_length is not None
    assert record.observed_chosen_sequence_length > 1
    assert record.observed_rejected_sequence_length > 1


def test_materializer_redacts_unknown_pair_content_on_runtime_error() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    record = materialize_dpo_preference_pair_inputs(
        [_pair_input()],
        protocol=protocol,
        tokenizer=_RaisingTokenizer(),
        max_sequence_length=10_000,
    )[0]

    assert record.status == "failed"
    assert record.failure_kind == "materialization_error"
    assert record.observed_chosen_sequence_length is None
    assert record.observed_rejected_sequence_length is None
    assert record.error_class == "RuntimeError"
    assert record.error_message == (
        "DPO pair materialization failed with RuntimeError."
    )
    assert "private" not in record.error_message


def test_materializer_returns_one_atomic_result_per_pair_in_source_order() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)
    pairs = [_pair_input(identity_suffix="1"), _pair_input(identity_suffix="2")]

    records = materialize_dpo_preference_pair_inputs(
        pairs,
        protocol=protocol,
        tokenizer=_CharacterTokenizer(),
        max_sequence_length=10_000,
    )

    assert [record.source_preference_pair_id for record in records] == [
        pair.source_pair.preference_pair_id for pair in pairs
    ]


def _pair_input(*, identity_suffix: str = "0") -> DPOPreferencePairMaterializationInput:
    context_messages = (
        MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000001",
            role="system",
            content="Use one JSON action per turn.",
        ),
        MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000002",
            role="user",
            content="Inspect and fix the code.",
        ),
        MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000003",
            role="assistant",
            content=(
                '{"action":"tool_call","tool_name":"read_file",'
                '"arguments":{"path":"src/app.py"}}'
            ),
            tool_call_id="tool_call_001",
        ),
        MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000004",
            role="tool",
            content='{"status":"ok"}',
            name="read_file",
            tool_call_id="tool_call_001",
        ),
    )
    candidate_hash = f"xxh64:{identity_suffix * 16}"
    adjudication_hash = f"xxh64:{(identity_suffix + '1')[-1] * 16}"
    comparison_candidate_id = f"preference_comparison_{identity_suffix}"
    pair_id = build_preference_pair_id(
        comparison_candidate_id=comparison_candidate_id,
        source_preference_comparison_candidate_record_hash=candidate_hash,
        source_preference_adjudication_record_hash=adjudication_hash,
    )
    source_pair = PreferencePairRecord.model_validate(
        {
            "preference_pair_id": pair_id,
            "source": {
                "comparison_candidate_id": comparison_candidate_id,
                "source_preference_comparison_candidate_record_hash": candidate_hash,
                "source_preference_adjudication_record_hash": adjudication_hash,
            },
        }
    )
    return DPOPreferencePairMaterializationInput(
        source_pair=source_pair,
        context_messages=context_messages,
        chosen_action=MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000005",
            role="assistant",
            content='{"action":"final_answer","text":"done"}',
        ),
        rejected_action=MessageWithoutMetadata(
            message_id="message_00000000000000000000000000000006",
            role="assistant",
            content=(
                '{"action":"tool_call","tool_name":"read_file",'
                '"arguments":{"path":"src/app.py"}}'
            ),
        ),
    )
