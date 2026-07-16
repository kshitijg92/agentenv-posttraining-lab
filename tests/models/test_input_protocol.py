from pathlib import Path
import shutil

import pytest
import yaml
from pydantic import ValidationError

from agentenv.models.input_protocol import (
    load_model_input_protocol,
    render_model_input,
)
from agentenv.models.input_protocol_schema import ModelInputProtocol
from agentenv.models.schema import Message


PROTOCOL_PATH = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)
PINNED_REVISION = "89fe5444e8baf5736e70f528f1edcc79e6616ef6"


def test_load_qwen2_5_protocol_pins_model_tokenizer_and_template() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)
    record = protocol.record

    assert record.protocol_id == "qwen2_5_coder_3b_agentenv_json"
    assert record.model_checkpoint.repository_id == ("Qwen/Qwen2.5-Coder-3B-Instruct")
    assert record.model_checkpoint.revision == PINNED_REVISION
    assert record.tokenizer.source == record.model_checkpoint
    assert {
        upstream_file.repository_path
        for upstream_file in record.tokenizer.upstream_files
    } == {
        "merges.txt",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
    }
    special_tokens = record.tokenizer.required_special_tokens
    assert special_tokens.message_start.token == "<|im_start|>"
    assert special_tokens.message_start.token_id == 151644
    assert special_tokens.end_of_turn.token == "<|im_end|>"
    assert special_tokens.end_of_turn.token_id == 151645
    assert special_tokens.padding.token == "<|endoftext|>"
    assert special_tokens.padding.token_id == 151643
    assert record.chat_template.sha256 == (
        "sha256:cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"
    )
    assert record.chat_template.source_repository_path == "tokenizer_config.json"
    assert record.chat_template.source_field == "chat_template"
    assert record.chat_template.local_snapshot_ref == (
        "templates/qwen2_5_coder_3b_chat_template.jinja"
    )
    assert record.supported_serialization_modes == (
        "generation",
        "completed_transcript",
    )
    assert record.message_fields == ("role", "content")
    assert record.tool_serialization == "agentenv_json_content"
    assert record.native_tool_serialization == "unsupported"


def test_generation_serialization_ends_at_assistant_header() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    rendered = render_model_input(
        protocol,
        [
            _message("0", role="system", content="Follow the JSON protocol."),
            _message("1", role="user", content="What is 6 * 7?"),
        ],
        mode="generation",
    )

    assert rendered == (
        "<|im_start|>system\n"
        "Follow the JSON protocol.<|im_end|>\n"
        "<|im_start|>user\n"
        "What is 6 * 7?<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def test_completed_serialization_includes_assistant_end_of_turn() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    rendered = render_model_input(
        protocol,
        [
            _message("0", role="system", content="Follow the JSON protocol."),
            _message("1", role="user", content="What is 6 * 7?"),
            _message(
                "2",
                role="assistant",
                content='{"action":"final_answer","text":"42"}',
            ),
        ],
        mode="completed_transcript",
    )

    assert rendered == (
        "<|im_start|>system\n"
        "Follow the JSON protocol.<|im_end|>\n"
        "<|im_start|>user\n"
        "What is 6 * 7?<|im_end|>\n"
        "<|im_start|>assistant\n"
        '{"action":"final_answer","text":"42"}<|im_end|>\n'
    )


def test_generation_serialization_uses_agentenv_content_level_tool_protocol() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    rendered = render_model_input(
        protocol,
        [
            _message("0", role="system", content="Use one JSON action."),
            _message("1", role="user", content="Read x.py."),
            _message(
                "2",
                role="assistant",
                content=(
                    '{"action":"tool_call","tool_name":"read_file",'
                    '"arguments":{"path":"x.py"}}'
                ),
            ),
            _message(
                "3",
                role="tool",
                content='{"status":"ok","content":"print(42)"}',
                name="read_file",
                tool_call_id="tool_call_001",
            ),
        ],
        mode="generation",
    )

    assert rendered == (
        "<|im_start|>system\n"
        "Use one JSON action.<|im_end|>\n"
        "<|im_start|>user\n"
        "Read x.py.<|im_end|>\n"
        "<|im_start|>assistant\n"
        '{"action":"tool_call","tool_name":"read_file",'
        '"arguments":{"path":"x.py"}}<|im_end|>\n'
        "<|im_start|>user\n"
        "<tool_response>\n"
        '{"status":"ok","content":"print(42)"}\n'
        "</tool_response><|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    assert "tool_call_001" not in rendered
    assert "read_file" in rendered


def test_generation_serialization_rejects_assistant_prefill() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    with pytest.raises(
        ValueError,
        match="cannot continue a final assistant message",
    ):
        render_model_input(
            protocol,
            [
                _message("0", role="user", content="Finish this JSON."),
                _message("1", role="assistant", content='{"action":'),
            ],
            mode="generation",
        )


def test_completed_serialization_requires_final_assistant_message() -> None:
    protocol = load_model_input_protocol(PROTOCOL_PATH)

    with pytest.raises(
        ValueError,
        match="must end with an assistant message",
    ):
        render_model_input(
            protocol,
            [_message("0", role="user", content="What is 6 * 7?")],
            mode="completed_transcript",
        )


def test_protocol_load_rejects_chat_template_drift(tmp_path: Path) -> None:
    source_dir = PROTOCOL_PATH.parent
    copied_dir = tmp_path / "model_input_protocols"
    shutil.copytree(source_dir, copied_dir)
    copied_template = copied_dir / "templates" / "qwen2_5_coder_3b_chat_template.jinja"
    copied_template.write_text(copied_template.read_text() + "{# drift #}\n")

    with pytest.raises(ValueError, match="Chat-template hash mismatch"):
        load_model_input_protocol(copied_dir / PROTOCOL_PATH.name)


def test_protocol_schema_rejects_native_tool_serialization() -> None:
    payload = yaml.safe_load(PROTOCOL_PATH.read_text())
    payload["native_tool_serialization"] = "provider_owned"

    with pytest.raises(ValidationError, match="native_tool_serialization"):
        ModelInputProtocol.model_validate(payload)


def _message(
    suffix: str,
    *,
    role: str,
    content: str,
    name: str | None = None,
    tool_call_id: str | None = None,
) -> Message:
    return Message.model_validate(
        {
            "message_id": f"message_{suffix.zfill(32)}",
            "role": role,
            "content": content,
            "name": name,
            "tool_call_id": tool_call_id,
            "metadata": {"ignored_by_model_input_protocol": "yes"},
        }
    )
