import json
from pathlib import Path

import xxhash

from agentenv.agents.schema import AgentTaskPromptInput
from agentenv.models.schema import Message
from agentenv.tools.schema import TOOL_REGISTRY


AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION = "agent_task_initial_prompt_builder_v0"


def compute_agent_task_initial_prompt_builder_code_hash() -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(Path(__file__).read_bytes())}"


def build_initial_messages(prompt_input: AgentTaskPromptInput) -> list[Message]:
    return [
        Message(
            role="system",
            content=_system_prompt(prompt_input),
            name="agentenv",
            metadata={"source": "agentenv_protocol"},
        ),
        Message(
            role="user",
            content=_user_prompt(prompt_input),
            name="task_view",
            metadata={
                "source": "agent_task_view",
                "task_id": prompt_input.task_id,
            },
        ),
    ]


def _system_prompt(prompt_input: AgentTaskPromptInput) -> str:
    sections = [
        "You are a coding agent operating through a restricted tool interface.",
        "Do not output free-form chat, markdown, or multiple actions.",
        "Only interact through tool_call or final_answer actions.",
        "",
        "Allowed tool-call actions:",
        *_tool_action_lines(prompt_input.allowed_tools),
        "",
        "Valid final-answer action:",
        '{"action":"final_answer","text":"done"}',
        "",
        "Return exactly one JSON object per turn.",
        "Use final_answer only when you are done interacting with the workspace.",
        "Public checks are diagnostic only; final task success is evaluated privately after the loop.",
    ]
    return "\n".join(sections)


def _user_prompt(prompt_input: AgentTaskPromptInput) -> str:
    sections = [
        "Task instruction:",
        prompt_input.instruction,
        "",
        "Workspace:",
        "Files are available only through tools in the prepared workspace.",
        "Do not use absolute host paths.",
        "",
        "Public checks:",
        *[f"- {command}" for command in prompt_input.public_checks],
        "",
        "Limits:",
        f"- max_turns: {prompt_input.max_turns}",
        f"- timeout_seconds: {prompt_input.timeout_seconds}",
        f"- network: {prompt_input.network}",
    ]
    return "\n".join(sections)


def _tool_action_lines(allowed_tools: list[str]) -> list[str]:
    lines: list[str] = []
    for tool_name in allowed_tools:
        tool_definition = (
            TOOL_REGISTRY.get(tool_name) if tool_name in TOOL_REGISTRY else None
        )
        description = (
            tool_definition.description
            if tool_definition is not None
            else "No registered description."
        )
        example_arguments = (
            tool_definition.example_arguments if tool_definition is not None else {}
        )
        lines.append(f"- {tool_name}: {description}")
        example = _tool_action_example(tool_name, example_arguments)
        lines.append(f"  Example: {example}")
    return lines


def _tool_action_example(
    tool_name: str,
    example_arguments: object,
) -> str:
    return json.dumps(
        {
            "action": "tool_call",
            "tool_name": tool_name,
            "arguments": example_arguments,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
