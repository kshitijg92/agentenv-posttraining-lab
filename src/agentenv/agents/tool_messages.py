import json

from agentenv.models.schema import Message
from agentenv.tools.schema import ToolResult


def render_tool_result_message(
    tool_result: ToolResult,
    tool_call_id: str,
) -> Message:
    if tool_result.status == "ok":
        content = {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "output": (
                tool_result.output.model_dump(mode="json")
                if tool_result.output is not None
                else None
            ),
        }
    else:
        content = {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "stdout": tool_result.stdout,
            "stderr": tool_result.stderr,
            "exit_code": tool_result.exit_code,
            "error_class": tool_result.error_class,
            "error_message": tool_result.error_message,
        }

    return Message(
        role="tool",
        name=tool_result.tool_name,
        tool_call_id=tool_call_id,
        content=json.dumps(content, sort_keys=True),
        metadata={
            "input_hash": tool_result.input_hash,
        },
    )
