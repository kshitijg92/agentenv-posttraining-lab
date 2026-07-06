from pathlib import Path

from agentenv.agents.prompts import build_initial_messages
from agentenv.agents.schema import AgentTaskPromptInput, AgentTaskView


def _agent_task_prompt_input() -> AgentTaskPromptInput:
    return AgentTaskPromptInput(
        task_id="repair_jsonl_deduper",
        instruction="Fix the JSONL deduper.",
        allowed_tools=["list_files", "read_file", "write_file", "run_tests"],
        public_checks=["uv run pytest tests/test_public.py"],
        max_turns=8,
        timeout_seconds=30,
        network="off",
    )


def _agent_task_view(tmp_path: Path) -> AgentTaskView:
    return AgentTaskView(
        task_id="repair_jsonl_deduper",
        instruction="Fix the JSONL deduper.",
        workspace_path=tmp_path / "workspace",
        allowed_tools=["list_files", "read_file", "write_file", "run_tests"],
        public_checks=["uv run pytest tests/test_public.py"],
        max_turns=8,
        timeout_seconds=30,
        network="off",
    )


def test_build_initial_messages_returns_system_and_user_messages(
    tmp_path: Path,
) -> None:
    messages = build_initial_messages(_agent_task_view(tmp_path))

    assert [message.role for message in messages] == ["system", "user"]
    assert messages[0].name == "agentenv"
    assert messages[1].name == "task_view"
    assert messages[0].metadata == {"source": "agentenv_protocol"}
    assert messages[1].metadata == {
        "source": "agent_task_view",
        "task_id": "repair_jsonl_deduper",
    }


def test_build_initial_messages_accepts_prompt_input_without_workspace_path() -> None:
    messages = build_initial_messages(_agent_task_prompt_input())

    assert [message.role for message in messages] == ["system", "user"]
    assert "Fix the JSONL deduper." in messages[1].content
    assert "Do not use absolute host paths." in messages[1].content


def test_system_message_defines_strict_json_action_protocol(
    tmp_path: Path,
) -> None:
    system_message = build_initial_messages(_agent_task_view(tmp_path))[0]

    assert "Return exactly one JSON object per turn." in system_message.content
    assert "Do not output free-form chat" in system_message.content
    assert "Only interact through tool_call or final_answer actions." in (
        system_message.content
    )
    assert '"action":"tool_call"' in system_message.content
    assert '"action":"final_answer"' in system_message.content
    assert "- list_files: List files under" in system_message.content
    assert "- read_file: Read a text file" in system_message.content
    assert "- write_file: Replace the entire contents" in system_message.content
    assert "- run_tests: Run a test command" in system_message.content
    assert '"max_depth":4' in system_message.content
    assert '"max_files":200' in system_message.content
    assert '"arguments":{"path":"src/file.py"}' in system_message.content
    assert '"content":"entire replacement file contents..."' in system_message.content
    assert "Public checks are diagnostic only" in system_message.content


def test_system_message_places_one_json_rule_before_final_answer_usage(
    tmp_path: Path,
) -> None:
    system_message = build_initial_messages(_agent_task_view(tmp_path))[0]

    one_json_index = system_message.content.index(
        "Return exactly one JSON object per turn."
    )
    final_answer_usage_index = system_message.content.index(
        "Use final_answer only when you are done interacting with the workspace."
    )

    assert one_json_index < final_answer_usage_index


def test_user_message_includes_visible_task_context(tmp_path: Path) -> None:
    user_message = build_initial_messages(_agent_task_view(tmp_path))[1]

    assert "Fix the JSONL deduper." in user_message.content
    assert "uv run pytest tests/test_public.py" in user_message.content
    assert "- max_turns: 8" in user_message.content
    assert "- timeout_seconds: 30" in user_message.content
    assert "- network: off" in user_message.content
    assert "Allowed tools:" not in user_message.content


def test_user_message_excludes_private_and_host_path_context(tmp_path: Path) -> None:
    agent_task_view = _agent_task_view(tmp_path)
    user_message = build_initial_messages(agent_task_view)[1]

    assert str(agent_task_view.workspace_path) not in user_message.content
    assert agent_task_view.task_id not in user_message.content
    assert "hidden_validators" not in user_message.content
    assert "controls" not in user_message.content
    assert "leakage_canary" not in user_message.content
    assert "task.yaml" not in user_message.content


def test_user_message_handles_unknown_allowed_tool_without_crashing(
    tmp_path: Path,
) -> None:
    agent_task_view = AgentTaskView(
        task_id="task_001",
        instruction="Fix the task.",
        workspace_path=tmp_path / "workspace",
        allowed_tools=["read_file", "unknown_tool"],
        public_checks=["uv run pytest tests/test_public.py"],
        max_turns=8,
        timeout_seconds=30,
        network="off",
    )

    system_message = build_initial_messages(agent_task_view)[0]

    assert "- read_file: Read a text file" in system_message.content
    assert "- unknown_tool: No registered description." in system_message.content
    assert '"tool_name":"unknown_tool"' in system_message.content


def test_system_message_only_lists_allowed_tools(tmp_path: Path) -> None:
    agent_task_view = AgentTaskView(
        task_id="task_001",
        instruction="Fix the task.",
        workspace_path=tmp_path / "workspace",
        allowed_tools=["run_tests"],
        public_checks=["uv run pytest tests/test_public.py"],
        max_turns=8,
        timeout_seconds=30,
        network="off",
    )

    system_message = build_initial_messages(agent_task_view)[0]

    assert "- run_tests: Run a test command" in system_message.content
    assert "- read_file:" not in system_message.content
    assert "- write_file:" not in system_message.content
