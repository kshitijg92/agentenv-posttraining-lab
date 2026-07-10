import pytest
from pydantic import ValidationError

from agentenv.models.schema import Message, MessageWithoutMetadata


def test_message_accepts_plain_system_message() -> None:
    message = Message(role="system", content="You are a coding agent.")

    assert message.role == "system"
    assert message.content == "You are a coding agent."
    assert message.name is None
    assert message.tool_call_id is None
    assert message.metadata == {}


def test_message_without_metadata_reuses_message_field_contract() -> None:
    message = MessageWithoutMetadata(
        role="tool",
        content="file contents",
        name="read_file",
        tool_call_id="tool_call_001",
    )

    assert message.role == "tool"
    assert message.name == "read_file"
    assert message.tool_call_id == "tool_call_001"


def test_message_without_metadata_rejects_metadata() -> None:
    with pytest.raises(ValidationError):
        MessageWithoutMetadata.model_validate(
            {
                "role": "assistant",
                "content": "{}",
                "metadata": {"source": "runtime"},
            }
        )


def test_message_accepts_task_user_metadata() -> None:
    message = Message(
        role="user",
        content="Fix the bug.",
        name="task_manifest",
        metadata={
            "task_id": "repair_jsonl_deduper",
            "source": "task_manifest",
            "turn_index": 0,
            "truncated": False,
            "score": 1.0,
            "optional": None,
        },
    )

    assert message.name == "task_manifest"
    assert message.metadata["task_id"] == "repair_jsonl_deduper"
    assert message.metadata["truncated"] is False


def test_tool_message_requires_name_and_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="tool messages require name"):
        Message(role="tool", content="contents", tool_call_id="tool_call_001")

    with pytest.raises(ValidationError, match="tool messages require tool_call_id"):
        Message(role="tool", content="contents", name="read_file")


def test_tool_message_accepts_name_and_tool_call_id() -> None:
    message = Message(
        role="tool",
        content="file contents",
        name="read_file",
        tool_call_id="tool_call_001",
        metadata={
            "tool_name": "read_file",
            "arguments_hash": "xxh64:abc123",
        },
    )

    assert message.name == "read_file"
    assert message.tool_call_id == "tool_call_001"


def test_system_and_user_messages_reject_tool_call_id() -> None:
    with pytest.raises(
        ValidationError,
        match="system messages cannot include tool_call_id",
    ):
        Message(
            role="system",
            content="system prompt",
            tool_call_id="tool_call_001",
        )

    with pytest.raises(
        ValidationError,
        match="user messages cannot include tool_call_id",
    ):
        Message(
            role="user",
            content="task prompt",
            tool_call_id="tool_call_001",
        )


def test_message_rejects_empty_name_and_tool_call_id() -> None:
    with pytest.raises(ValidationError):
        Message(role="assistant", content="{}", name="")

    with pytest.raises(ValidationError):
        Message(role="assistant", content="{}", tool_call_id="")


def test_message_rejects_nested_metadata() -> None:
    with pytest.raises(ValidationError):
        Message.model_validate(
            {
                "role": "user",
                "content": "Fix the bug.",
                "metadata": {"nested": {"hidden": "not allowed"}},
            }
        )

    with pytest.raises(ValidationError):
        Message.model_validate(
            {
                "role": "user",
                "content": "Fix the bug.",
                "metadata": {"list": ["not", "allowed"]},
            }
        )


def test_message_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Message.model_validate(
            {
                "role": "user",
                "content": "Fix the bug.",
                "timestamp_utc": "2026-06-24T00:00:00Z",
            }
        )
