import json

from agentenv.agents.schema import AgentTaskView
from agentenv.models.schema import Message
from agentenv.tools.schema import TOOL_REGISTRY


def build_initial_messages(agent_task_view: AgentTaskView) -> list[Message]:
    return [
        Message(
            role="system",
            content=_system_prompt(agent_task_view),
            name="agentenv",
            metadata={"source": "agentenv_protocol"},
        ),
        Message(
            role="user",
            content=_user_prompt(agent_task_view),
            name="task_view",
            metadata={
                "source": "agent_task_view",
                "task_id": agent_task_view.task_id,
            },
        ),
    ]


def _system_prompt(agent_task_view: AgentTaskView) -> str:
    sections = [
        "You are a coding agent operating through a restricted tool interface.",
        "Do not output free-form chat, markdown, or multiple actions.",
        "Only interact through tool_call or final_answer actions.",
        "",
        "Allowed tool-call actions:",
        *_tool_action_lines(agent_task_view.allowed_tools),
        "",
        "Valid final-answer action:",
        '{"action":"final_answer","text":"done"}',
        "",
        "Return exactly one JSON object per turn.",
        "Use final_answer only when you are done interacting with the workspace.",
        "Public checks are diagnostic only; final task success is evaluated privately after the loop.",
    ]
    return "\n".join(sections)


def _user_prompt(agent_task_view: AgentTaskView) -> str:
    sections = [
        "Task instruction:",
        agent_task_view.instruction,
        "",
        "Workspace:",
        "Files are available only through tools in the prepared workspace.",
        "Do not use absolute host paths.",
        "",
        "Public checks:",
        *[f"- {command}" for command in agent_task_view.public_checks],
        "",
        "Limits:",
        f"- max_turns: {agent_task_view.max_turns}",
        f"- timeout_seconds: {agent_task_view.timeout_seconds}",
        f"- network: {agent_task_view.network}",
    ]
    return "\n".join(sections)


def _tool_action_lines(allowed_tools: list[str]) -> list[str]:
    lines: list[str] = []
    for tool_name in allowed_tools:
        tool_definition = (
            TOOL_REGISTRY.get(tool_name)
            if tool_name in TOOL_REGISTRY
            else None
        )
        description = (
            tool_definition.description
            if tool_definition is not None
            else "No registered description."
        )
        example_arguments = (
            tool_definition.example_arguments
            if tool_definition is not None
            else {}
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
