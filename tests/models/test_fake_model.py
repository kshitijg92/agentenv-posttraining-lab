import json

from agentenv.agents.schema import ToolCallAction, parse_agent_action
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig, Message


def _decoding_config() -> DecodingConfig:
    return DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=512,
        timeout_seconds=30,
    )


def _messages() -> list[Message]:
    return [
        Message(role="system", content="Return one JSON action."),
        Message(role="user", content="Fix the task."),
    ]


def test_scripted_fake_model_returns_scripted_outputs_in_order() -> None:
    client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=json.dumps({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {"path": "src/foo.py"},
                }),
            ),
            FakeModelScriptStep(
                output_text=json.dumps({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ],
    )

    first_response = client.generate(_messages(), _decoding_config())
    second_response = client.generate(_messages(), _decoding_config())

    assert first_response.model_id == "fake-scripted-v0"
    assert first_response.finish_reason == "stop_criteria_met"
    assert first_response.prompt_tokens is None
    assert first_response.completion_tokens is None
    assert first_response.total_tokens is None
    assert parse_agent_action(first_response.output_text) == ToolCallAction(
        action="tool_call",
        tool_name="read_file",
        arguments={"path": "src/foo.py"},
    )
    assert parse_agent_action(second_response.output_text).action == "final_answer"
    assert second_response.total_tokens is None


def test_scripted_fake_model_default_decoding_config_is_deterministic() -> None:
    decoding_config = ScriptedFakeModelClient.default_decoding_config()

    assert decoding_config.strategy == "greedy"
    assert decoding_config.temperature == 0.0
    assert decoding_config.top_p == 1.0
    assert decoding_config.max_new_tokens == 512
    assert decoding_config.timeout_seconds == 30


def test_scripted_fake_model_returns_error_when_script_exhausted() -> None:
    client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=json.dumps({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ],
    )

    first_response = client.generate(_messages(), _decoding_config())
    exhausted_response = client.generate(_messages(), _decoding_config())

    assert first_response.finish_reason == "stop_criteria_met"
    assert exhausted_response.finish_reason == "error"
    assert exhausted_response.error_class == "FakeModelScriptExhausted"
    assert exhausted_response.output_text == ""
    assert exhausted_response.raw_response_ref == "fake_model/raw_response.json"


def test_scripted_fake_model_uses_custom_raw_response_ref() -> None:
    client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=json.dumps({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ],
        raw_response_ref="models/fake/raw_001.json",
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.raw_response_ref == "models/fake/raw_001.json"


def test_scripted_fake_model_can_emit_invalid_text() -> None:
    client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(output_text="{not valid json"),
        ],
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.finish_reason == "stop_criteria_met"
    assert response.output_text == "{not valid json"
