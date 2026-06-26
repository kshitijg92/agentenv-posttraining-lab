import json
from pathlib import Path

from agentenv.agents.loop import run_prompt_loop
from agentenv.agents.schema import AgentTaskView
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig
from agentenv.tools.schema import RunTestsOutput


PUBLIC_CHECK_COMMAND = "python -m pytest tests/test_calculator.py"
BROKEN_SOURCE = "def add(left, right):\n    return left - right\n"
FIXED_SOURCE = "def add(left, right):\n    return left + right\n"


def _decoding_config() -> DecodingConfig:
    return DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=512,
        timeout_seconds=30,
    )


def _action(payload: object) -> str:
    return json.dumps(payload)


def _prepare_calculator_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    tests_dir = workspace / "tests"
    tests_dir.mkdir(parents=True)
    source_file = workspace / "calculator.py"
    source_file.write_text(BROKEN_SOURCE)
    (tests_dir / "test_calculator.py").write_text(
        "from calculator import add\n\n\n"
        "def test_adds_two_numbers():\n"
        "    assert add(1, 2) == 3\n"
    )
    return workspace, source_file


def _agent_task_view(workspace: Path, *, max_turns: int = 8) -> AgentTaskView:
    return AgentTaskView(
        task_id="fake_agent_e2e_001",
        instruction="Fix calculator.add so the public test passes.",
        workspace_path=workspace,
        allowed_tools=["read_file", "write_file", "run_tests"],
        public_checks=[PUBLIC_CHECK_COMMAND],
        max_turns=max_turns,
        timeout_seconds=10,
        network="off",
    )


def test_fake_agent_reads_writes_runs_tests_and_finishes(
    tmp_path: Path,
) -> None:
    workspace, source_file = _prepare_calculator_workspace(tmp_path)
    model_client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {"path": "calculator.py"},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "calculator.py",
                        "content": FIXED_SOURCE,
                    },
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "run_tests",
                    "arguments": {"command": PUBLIC_CHECK_COMMAND},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ],
    )

    result = run_prompt_loop(
        _agent_task_view(workspace),
        model_client,
        _decoding_config(),
    )

    assert result.status == "completed"
    assert result.turns_executed == 4
    assert source_file.read_text() == FIXED_SOURCE
    assert [tool_result.tool_name for tool_result in result.tool_results] == [
        "read_file",
        "write_file",
        "run_tests",
    ]
    assert isinstance(result.tool_results[2].output, RunTestsOutput)
    assert result.tool_results[2].output.passed is True
    assert result.tool_results[2].exit_code == 0
    assert [message.role for message in result.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert result.messages[2].tool_call_id == "tool_call_0001"
    assert result.messages[3].tool_call_id == "tool_call_0001"
    assert result.messages[4].tool_call_id == "tool_call_0002"
    assert result.messages[5].tool_call_id == "tool_call_0002"
    assert result.messages[6].tool_call_id == "tool_call_0003"
    assert result.messages[7].tool_call_id == "tool_call_0003"
    assert result.messages[8].tool_call_id is None
    assert str(workspace) not in "\n".join(message.content for message in result.messages)


def test_fake_agent_can_recover_from_invalid_tool_input(
    tmp_path: Path,
) -> None:
    workspace, source_file = _prepare_calculator_workspace(tmp_path)
    model_client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {"path": "calculator.py"},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "calculator.py",
                        "content": FIXED_SOURCE,
                    },
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "run_tests",
                    "arguments": {"command": PUBLIC_CHECK_COMMAND},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ],
    )

    result = run_prompt_loop(
        _agent_task_view(workspace),
        model_client,
        _decoding_config(),
    )

    assert result.status == "completed"
    assert result.turns_executed == 5
    assert source_file.read_text() == FIXED_SOURCE
    assert result.tool_results[0].tool_name == "read_file"
    assert result.tool_results[0].status == "error"
    assert result.tool_results[0].error_class == "InvalidToolInput"
    assert result.messages[2].tool_call_id == "tool_call_0001"
    assert result.messages[3].tool_call_id == "tool_call_0001"
    invalid_tool_observation = json.loads(result.messages[3].content)
    assert invalid_tool_observation["status"] == "error"
    assert invalid_tool_observation["error_class"] == "InvalidToolInput"
    assert [tool_result.status for tool_result in result.tool_results] == [
        "error",
        "ok",
        "ok",
        "ok",
    ]
    assert isinstance(result.tool_results[3].output, RunTestsOutput)
    assert result.tool_results[3].output.passed is True
    assert [message.role for message in result.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
