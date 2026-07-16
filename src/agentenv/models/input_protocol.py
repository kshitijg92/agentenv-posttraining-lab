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
    template_bytes = template_path.read_bytes()
    observed_hash = f"sha256:{hashlib.sha256(template_bytes).hexdigest()}"
    if observed_hash != record.chat_template.sha256:
        raise ValueError(
            f"Chat-template hash mismatch at {template_path}: "
            f"{observed_hash!r} != {record.chat_template.sha256!r}"
        )

    return LoadedModelInputProtocol(
        source_path=source_path,
        record=record,
        chat_template=template_bytes.decode("utf-8"),
    )


def render_model_input(
    protocol: LoadedModelInputProtocol,
    messages: Sequence[MessageWithoutMetadata],
    *,
    mode: ModelInputSerializationMode,
) -> str:
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

    projected_messages = [
        {"role": message.role, "content": message.content} for message in messages
    ]
    rendered, _ = cast(
        tuple[list[str], list[list[tuple[int, int]]]],
        render_jinja_template(
            conversations=[projected_messages],
            tools=None,
            documents=None,
            chat_template=protocol.chat_template,
            return_assistant_tokens_mask=False,
            continue_final_message=False,
            add_generation_prompt=mode == "generation",
        ),
    )
    if len(rendered) != 1:
        raise ValueError("Expected exactly one rendered conversation")
    return rendered[0]
