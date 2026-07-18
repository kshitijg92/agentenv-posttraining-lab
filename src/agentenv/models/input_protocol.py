import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, cast

import yaml
from transformers.utils.chat_template_utils import render_jinja_template

from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.models.input_protocol_schema import (
    ModelInputProtocol,
    ModelInputSerializationMode,
)
from agentenv.models.schema import MessageWithoutMetadata


@dataclass(frozen=True)
class LoadedModelInputProtocol:
    source_path: Path
    record: ModelInputProtocol
    chat_template: str
    generation_ownership_template: str


@dataclass(frozen=True)
class ModelGeneratedCharacterSpan:
    start: int
    end: int


@dataclass(frozen=True)
class RenderedModelInputWithOwnership:
    text: str
    model_generated_spans: tuple[ModelGeneratedCharacterSpan, ...]


def load_model_input_protocol(path: Path) -> LoadedModelInputProtocol:
    source_path = path.resolve()
    raw_record = yaml.safe_load(source_path.read_text())
    if not isinstance(raw_record, dict):
        raise ValueError(f"Expected YAML mapping at {source_path}")
    record = ModelInputProtocol.model_validate(raw_record)

    template_path = resolve_relative_artifact_ref(
        source_path.parent,
        record.chat_template.local_snapshot_ref,
    )
    template = _load_hash_pinned_template(
        template_path,
        expected_hash=record.chat_template.sha256,
        artifact_name="Chat-template",
    )
    ownership_template_path = resolve_relative_artifact_ref(
        source_path.parent,
        record.generation_ownership.annotated_template_ref,
    )
    ownership_template = _load_hash_pinned_template(
        ownership_template_path,
        expected_hash=record.generation_ownership.sha256,
        artifact_name="Generation-ownership template",
    )

    return LoadedModelInputProtocol(
        source_path=source_path,
        record=record,
        chat_template=template,
        generation_ownership_template=ownership_template,
    )


def render_model_input(
    protocol: LoadedModelInputProtocol,
    messages: Sequence[MessageWithoutMetadata],
    *,
    mode: ModelInputSerializationMode,
) -> str:
    _validate_render_request(protocol, messages, mode=mode)
    rendered, _ = _render_template(
        protocol.chat_template,
        messages,
        mode=mode,
        track_model_generation=False,
    )
    return rendered


def render_model_input_with_generation_ownership(
    protocol: LoadedModelInputProtocol,
    messages: Sequence[MessageWithoutMetadata],
    *,
    mode: ModelInputSerializationMode,
) -> RenderedModelInputWithOwnership:
    _validate_render_request(protocol, messages, mode=mode)
    canonical_text, _ = _render_template(
        protocol.chat_template,
        messages,
        mode=mode,
        track_model_generation=False,
    )
    annotated_text, raw_spans = _render_template(
        protocol.generation_ownership_template,
        messages,
        mode=mode,
        track_model_generation=True,
    )
    if canonical_text.encode("utf-8") != annotated_text.encode("utf-8"):
        raise ValueError(
            "Generation-ownership rendering differs from canonical rendered text"
        )

    spans = _validate_model_generated_spans(raw_spans, text=canonical_text)
    return RenderedModelInputWithOwnership(
        text=canonical_text,
        model_generated_spans=spans,
    )


def _load_hash_pinned_template(
    path: Path,
    *,
    expected_hash: str,
    artifact_name: str,
) -> str:
    template_bytes = path.read_bytes()
    observed_hash = f"sha256:{hashlib.sha256(template_bytes).hexdigest()}"
    if observed_hash != expected_hash:
        raise ValueError(
            f"{artifact_name} hash mismatch at {path}: "
            f"{observed_hash!r} != {expected_hash!r}"
        )
    return template_bytes.decode("utf-8")


def _validate_render_request(
    protocol: LoadedModelInputProtocol,
    messages: Sequence[MessageWithoutMetadata],
    *,
    mode: ModelInputSerializationMode,
) -> None:
    if mode not in protocol.record.supported_serialization_modes:
        raise ValueError(f"Unsupported serialization mode: {mode}")
    if not messages:
        raise ValueError("Model input requires at least one message")
    if mode == "generation" and messages[-1].role == "assistant":
        raise ValueError(
            "Generation serialization cannot continue a final assistant message"
        )
    if mode == "completed_transcript" and messages[-1].role != "assistant":
        raise ValueError(
            "Completed-transcript serialization must end with an assistant message"
        )


def _render_template(
    template: str,
    messages: Sequence[MessageWithoutMetadata],
    *,
    mode: ModelInputSerializationMode,
    track_model_generation: bool,
) -> tuple[str, tuple[tuple[int, int], ...]]:
    projected_messages = [
        {"role": message.role, "content": message.content} for message in messages
    ]
    rendered, all_spans = cast(
        tuple[list[str], list[list[tuple[int, int]]]],
        render_jinja_template(
            conversations=[projected_messages],
            tools=None,
            documents=None,
            chat_template=template,
            return_assistant_tokens_mask=track_model_generation,
            continue_final_message=False,
            add_generation_prompt=mode == "generation",
        ),
    )
    if len(rendered) != 1:
        raise ValueError("Expected exactly one rendered conversation")
    if not track_model_generation:
        return rendered[0], ()
    if len(all_spans) != 1:
        raise ValueError("Expected ownership spans for exactly one conversation")
    return rendered[0], tuple(all_spans[0])


def _validate_model_generated_spans(
    raw_spans: tuple[tuple[int, int], ...],
    *,
    text: str,
) -> tuple[ModelGeneratedCharacterSpan, ...]:
    spans: list[ModelGeneratedCharacterSpan] = []
    previous_end = 0
    for start, end in raw_spans:
        if start < previous_end:
            raise ValueError(
                "Model-generated character spans must be ordered and non-overlapping"
            )
        if start < 0 or end <= start or end > len(text):
            raise ValueError("Model-generated character span is outside rendered text")
        spans.append(ModelGeneratedCharacterSpan(start=start, end=end))
        previous_end = end
    return tuple(spans)
