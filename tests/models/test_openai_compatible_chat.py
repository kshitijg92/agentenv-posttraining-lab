import json

import httpx
import pytest

from agentenv.models.config_schema import (
    ModelCapabilities,
    OpenAICompatibleChatModelConfig,
)
from agentenv.models.openai_compatible_chat import OpenAICompatibleChatModelClient
from agentenv.models.schema import DecodingConfig, Message


def _model_config(
    *,
    supports_seed: bool = False,
    supports_stop: bool = True,
    supports_top_k: bool = False,
    api_key_env: str | None = "AGENTENV_MODEL_API_KEY",
    base_url_env: str | None = "AGENTENV_MODEL_BASE_URL",
) -> OpenAICompatibleChatModelConfig:
    return OpenAICompatibleChatModelConfig(
        version="model_config_v0",
        provider="openai_compatible_chat",
        model_id="test-chat-model",
        api_key_env=api_key_env,
        base_url_env=base_url_env,
        capabilities=ModelCapabilities(
            token_usage="native",
            supports_seed=supports_seed,
            supports_stop=supports_stop,
            supports_top_k=supports_top_k,
        ),
    )


def _decoding_config(**overrides: object) -> DecodingConfig:
    payload = {
        "strategy": "greedy",
        "temperature": 0.0,
        "top_p": 1.0,
        "max_new_tokens": 256,
        "timeout_seconds": 30,
    }
    payload.update(overrides)
    return DecodingConfig.model_validate(payload)


def _messages() -> list[Message]:
    return [
        Message(role="system", content="Return one JSON action."),
        Message(role="user", content="Fix the task."),
        Message(
            role="tool",
            name="read_file",
            tool_call_id="tool_001",
            content='{"status":"ok","stdout":"content"}',
        ),
    ]


def test_openai_compatible_chat_sends_chat_completion_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1/")
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", "secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://provider.test/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret-token"
        payload = json.loads(request.content)
        assert payload == {
            "model": "test-chat-model",
            "messages": [
                {"role": "system", "content": "Return one JSON action."},
                {"role": "user", "content": "Fix the task."},
                {
                    "role": "tool",
                    "content": '{"status":"ok","stdout":"content"}',
                    "name": "read_file",
                    "tool_call_id": "tool_001",
                },
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 256,
            "stop": ["</json>"],
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"action":"final_answer"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            },
        )

    client = OpenAICompatibleChatModelClient(
        config=_model_config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(
        _messages(),
        _decoding_config(stop=["</json>"]),
    )

    assert response.model_id == "test-chat-model"
    assert response.output_text == '{"action":"final_answer"}'
    assert response.finish_reason == "stop_criteria_met"
    assert response.prompt_tokens == 11
    assert response.completion_tokens == 7
    assert response.total_tokens == 18
    assert response.error_class is None
    assert response.raw_response_ref == "provider_response/not_persisted"


def test_openai_compatible_chat_maps_length_finish_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", "secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "partial"},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    client = OpenAICompatibleChatModelClient(
        config=_model_config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.output_text == "partial"
    assert response.finish_reason == "max_new_tokens_reached"
    assert response.error_class is None
    assert response.prompt_tokens is None
    assert response.completion_tokens is None
    assert response.total_tokens is None


def test_openai_compatible_chat_rejects_unexpected_choice_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", "secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "one"},
                        "finish_reason": "stop",
                    },
                    {
                        "message": {"content": "two"},
                        "finish_reason": "stop",
                    },
                ]
            },
        )

    client = OpenAICompatibleChatModelClient(
        config=_model_config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.finish_reason == "error"
    assert response.error_class == "MalformedProviderResponse"


def test_openai_compatible_chat_reports_missing_api_key_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.delenv("AGENTENV_MODEL_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request should not be sent")

    client = OpenAICompatibleChatModelClient(
        config=_model_config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.finish_reason == "error"
    assert response.error_class == "MissingModelApiKeyEnvVar"
    assert response.raw_response_ref == "provider_response/not_started"


def test_openai_compatible_chat_reports_unsupported_decoding_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", "secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request should not be sent")

    client = OpenAICompatibleChatModelClient(
        config=_model_config(supports_top_k=False),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config(top_k=40))

    assert response.finish_reason == "error"
    assert response.error_class == "UnsupportedDecodingTopK"
    assert response.raw_response_ref == "provider_response/not_started"


def test_openai_compatible_chat_maps_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", "secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    client = OpenAICompatibleChatModelClient(
        config=_model_config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.finish_reason == "error"
    assert response.error_class == "ProviderHTTPError"
    assert response.error_message == "HTTP 500 message=boom"


def test_openai_compatible_chat_maps_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", "secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = OpenAICompatibleChatModelClient(
        config=_model_config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.finish_reason == "timeout"
    assert response.error_class == "ProviderTimeout"


def test_openai_compatible_chat_rejects_malformed_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", "secret-token")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "done"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 999,
                },
            },
        )

    client = OpenAICompatibleChatModelClient(
        config=_model_config(),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.finish_reason == "error"
    assert response.error_class == "MalformedProviderResponse"
