import json

from agentenv.agents.tool_messages import render_tool_result_message
from agentenv.models.schema import Message
from agentenv.tools.schema import ReadFileOutput, ToolResult


def test_render_tool_result_message_for_success() -> None:
    tool_result = ToolResult(
        tool_name="read_file",
        input_hash="xxh64:abc123",
        status="ok",
        output=ReadFileOutput(
            content="file contents",
            bytes_read=13,
            truncated=False,
        ),
        duration_ms=2,
    )

    message = render_tool_result_message(tool_result, "tool_call_0001")

    assert message == Message(
        role="tool",
        name="read_file",
        tool_call_id="tool_call_0001",
        content=message.content,
        metadata={
            "input_hash": "xxh64:abc123",
        },
    )
    content = json.loads(message.content)
    assert content == {
        "tool_name": "read_file",
        "status": "ok",
        "output": {
            "content": "file contents",
            "bytes_read": 13,
            "truncated": False,
        },
    }
    assert "duration_ms" not in content
    assert "error_class" not in content


def test_render_tool_result_message_for_error() -> None:
    tool_result = ToolResult(
        tool_name="read_file",
        input_hash="xxh64:abc123",
        status="error",
        output=None,
        stdout="",
        stderr="Permission denied\n",
        exit_code=None,
        duration_ms=2,
        error_class="ToolExecutionError",
        error_message="Permission denied",
    )

    message = render_tool_result_message(tool_result, "tool_call_0002")

    assert message.role == "tool"
    assert message.name == "read_file"
    assert message.tool_call_id == "tool_call_0002"
    assert message.metadata == {
        "input_hash": "xxh64:abc123",
    }
    content = json.loads(message.content)
    assert content == {
        "tool_name": "read_file",
        "status": "error",
        "stdout": "",
        "stderr": "Permission denied\n",
        "exit_code": None,
        "error_class": "ToolExecutionError",
        "error_message": "Permission denied",
    }
    assert "output" not in content
    assert "duration_ms" not in content
    assert "input_hash" not in content
