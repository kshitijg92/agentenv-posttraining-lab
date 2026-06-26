import json
from pathlib import Path

from agentenv.agents.loop import run_prompt_loop
from agentenv.agents.schema import AgentTaskView
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig, Message, ModelResponse


def _decoding_config() -> DecodingConfig:
    return DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=512,
        timeout_seconds=30,
    )


def _agent_task_view(
    workspace_path: Path,
    *,
    allowed_tools: list[str] | None = None,
    max_turns: int = 8,
) -> AgentTaskView:
    return AgentTaskView(
        task_id="task_001",
        instruction="Fix the task.",
        workspace_path=workspace_path,
        allowed_tools=allowed_tools or ["read_file", "write_file", "run_tests"],
        public_checks=["true"],
        max_turns=max_turns,
        timeout_seconds=5,
        network="off",
    )


def _fake_model(*steps: FakeModelScriptStep) -> ScriptedFakeModelClient:
    return ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=list(steps),
    )


def _action(payload: object) -> str:
    return json.dumps(payload)


def test_prompt_loop_completes_on_final_answer(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_prompt_loop(
        _agent_task_view(workspace),
        _fake_model(
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
            )
        ),
        _decoding_config(),
    )

    assert result.status == "completed"
    assert result.turns_executed == 1
    assert [message.role for message in result.messages] == [
        "system",
        "user",
        "assistant",
    ]
    assert result.messages[-1].name == "fake-scripted-v0"
    assert result.tool_results == []


def test_prompt_loop_records_assistant_message_before_invalid_output_error(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_prompt_loop(
        _agent_task_view(workspace),
        _fake_model(FakeModelScriptStep(output_text="{not valid json")),
        _decoding_config(),
    )

    assert result.status == "invalid_model_output"
    assert result.error_class == "MalformedModelOutput"
    assert result.turns_executed == 1
    assert result.model_responses[0].output_text == "{not valid json"
    assert result.messages[-1].role == "assistant"
    assert result.messages[-1].content == "{not valid json"
    assert result.messages[-1].name == "fake-scripted-v0"


def test_prompt_loop_treats_max_new_tokens_as_model_error_after_recording_output(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_prompt_loop(
        _agent_task_view(workspace),
        _fake_model(
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
                finish_reason="max_new_tokens_reached",
            )
        ),
        _decoding_config(),
    )

    assert result.status == "model_error"
    assert result.error_class == "MaxNewTokensReached"
    assert result.messages[-1].role == "assistant"
    assert result.messages[-1].content == result.model_responses[0].output_text


def test_prompt_loop_reports_model_id_when_generate_raises(tmp_path: Path) -> None:
    class RaisingModelClient:
        model_id = "raising-model-v0"

        def generate(
            self,
            messages: list[Message],
            decoding_config: DecodingConfig,
        ) -> ModelResponse:
            del messages
            del decoding_config
            raise RuntimeError("provider unavailable")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_prompt_loop(
        _agent_task_view(workspace),
        RaisingModelClient(),
        _decoding_config(),
    )

    assert result.status == "model_error"
    assert result.error_class == "RuntimeError"
    assert result.error_message == (
        "Model raising-model-v0 generate failed: provider unavailable"
    )
    assert result.model_responses == []
    assert [message.role for message in result.messages] == ["system", "user"]
    assert result.token_usage.prompt_tokens is None


def test_prompt_loop_continues_after_recoverable_tool_error(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_prompt_loop(
        _agent_task_view(workspace),
        _fake_model(
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ),
        _decoding_config(),
    )

    assert result.status == "completed"
    assert result.turns_executed == 2
    assert result.tool_results[0].status == "error"
    assert result.tool_results[0].error_class == "InvalidToolInput"
    assert [message.role for message in result.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert result.messages[2].tool_call_id == "tool_call_0001"
    assert result.messages[3].tool_call_id == "tool_call_0001"


def test_prompt_loop_stops_after_terminal_tool_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_prompt_loop(
        _agent_task_view(workspace, allowed_tools=["read_file"]),
        _fake_model(
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "delete_file",
                    "arguments": {"path": "src.py"},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ),
        _decoding_config(),
    )

    assert result.status == "terminal_tool_error"
    assert result.error_class == "ToolNotAllowed"
    assert result.turns_executed == 1
    assert result.tool_results[0].error_class == "ToolNotAllowed"
    assert [message.role for message in result.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]


def test_prompt_loop_reports_max_turns_after_recoverable_tool_error(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_prompt_loop(
        _agent_task_view(workspace, max_turns=1),
        _fake_model(
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {},
                }),
            )
        ),
        _decoding_config(),
    )

    assert result.status == "max_turns_exceeded"
    assert result.error_class == "MaxTurnsExceeded"
    assert result.turns_executed == 1
    assert result.tool_results[0].error_class == "InvalidToolInput"
