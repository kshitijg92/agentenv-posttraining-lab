import json

from agentenv.models import ModelClient
from agentenv.ids import new_message_id
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


def _messages() -> list[Message]:
    return [
        Message(
            message_id=new_message_id(),
            role="system",
            content="Return one JSON action.",
        ),
        Message(
            message_id=new_message_id(),
            role="user",
            content="Fix the task.",
        ),
    ]


def _generate_with_client(model_client: ModelClient) -> ModelResponse:
    assert model_client.model_id == "fake-scripted-v0"
    return model_client.generate(_messages(), _decoding_config())


def test_scripted_fake_model_satisfies_model_client_protocol() -> None:
    client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=json.dumps({
                    "action": "final_answer",
                    "text": "done",
                }),
            )
        ],
    )

    response = _generate_with_client(client)

    assert response.model_id == "fake-scripted-v0"
    assert response.output_text == '{"action": "final_answer", "text": "done"}'
