import json
from pathlib import Path

import httpx
import pytest

from agentenv.ids import new_message_id
from agentenv.models.config_schema import (
    ModelCapabilities,
    OllamaGenerateModelConfig,
    PinnedModelInputProtocolRef,
)
from agentenv.models.input_protocol import load_model_input_protocol
from agentenv.models.ollama_generate import OllamaGenerateModelClient
from agentenv.models.schema import DecodingConfig, Message


PROTOCOL_PATH = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)


def _model_config(
    *,
    supports_seed: bool = True,
    supports_stop: bool = True,
    supports_top_k: bool = True,
) -> OllamaGenerateModelConfig:
    return OllamaGenerateModelConfig(
        version="model_config_v0",
        provider="ollama_generate",
        model_id="qwen2.5-coder:3b",
        base_url_env="AGENTENV_OLLAMA_BASE_URL",
        capabilities=ModelCapabilities(
            token_usage="native",
            supports_seed=supports_seed,
            supports_stop=supports_stop,
            supports_top_k=supports_top_k,
        ),
        model_input_protocol=PinnedModelInputProtocolRef(
            path="../model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml",
            content_hash="xxh64:eb0a73b2d5c4174a",
        ),
        agent_action_format="json_schema",
    )


def _decoding_config(**overrides: object) -> DecodingConfig:
    payload = {
        "strategy": "sampling",
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 40,
        "max_new_tokens": 256,
        "seed": 7,
        "stop": ["<stop>"],
        "timeout_seconds": 30,
    }
    payload.update(overrides)
    return DecodingConfig.model_validate(payload)


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
            content="What is 6 * 7?",
        ),
    ]


def _client(handler: httpx.MockTransport) -> OllamaGenerateModelClient:
    return OllamaGenerateModelClient(
        config=_model_config(),
        model_input_protocol=load_model_input_protocol(PROTOCOL_PATH),
        http_client=httpx.Client(transport=handler),
    )


def test_ollama_generate_renders_protocol_and_sends_mandatory_raw_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_OLLAMA_BASE_URL", "http://ollama.test/")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://ollama.test/api/generate"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen2.5-coder:3b"
        assert payload["prompt"] == (
            "<|im_start|>system\n"
            "Return one JSON action.<|im_end|>\n"
            "<|im_start|>user\n"
            "What is 6 * 7?<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        assert payload["raw"] is True
        assert payload["stream"] is False
        assert payload["options"] == {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 256,
            "stop": ["<stop>"],
            "seed": 7,
            "top_k": 40,
        }
        assert payload["format"]["oneOf"][0]["properties"]["action"] == {
            "type": "string",
            "const": "tool_call",
        }
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5-coder:3b",
                "response": '{"action":"final_answer","text":"42"}',
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 31,
                "eval_count": 9,
            },
        )

    response = _client(httpx.MockTransport(handler)).generate(
        _messages(),
        _decoding_config(),
    )

    assert response.output_text == '{"action":"final_answer","text":"42"}'
    assert response.finish_reason == "stop_criteria_met"
    assert response.prompt_tokens == 31
    assert response.completion_tokens == 9
    assert response.total_tokens == 40
    assert response.error_class is None


def test_ollama_generate_maps_length_done_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_OLLAMA_BASE_URL", "http://ollama.test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "partial",
                "done": True,
                "done_reason": "length",
                "prompt_eval_count": 12,
                "eval_count": 256,
            },
        )

    response = _client(httpx.MockTransport(handler)).generate(
        _messages(),
        _decoding_config(),
    )

    assert response.output_text == "partial"
    assert response.finish_reason == "max_new_tokens_reached"
    assert response.total_tokens == 268


def test_ollama_generate_requires_declared_base_url_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTENV_OLLAMA_BASE_URL", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request should not be sent")

    response = _client(httpx.MockTransport(handler)).generate(
        _messages(),
        _decoding_config(),
    )

    assert response.finish_reason == "error"
    assert response.error_class == "MissingModelBaseUrlEnvVar"
    assert response.raw_response_ref == "provider_response/not_started"


def test_ollama_generate_rejects_openai_v1_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_OLLAMA_BASE_URL", "http://ollama.test/v1")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request should not be sent")

    with pytest.raises(ValueError, match="server root, not /v1"):
        _client(httpx.MockTransport(handler)).generate(
            _messages(),
            _decoding_config(),
        )


def test_ollama_generate_rejects_missing_native_token_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_OLLAMA_BASE_URL", "http://ollama.test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "done",
                "done": True,
                "done_reason": "stop",
            },
        )

    response = _client(httpx.MockTransport(handler)).generate(
        _messages(),
        _decoding_config(),
    )

    assert response.finish_reason == "error"
    assert response.error_class == "MalformedProviderResponse"


def test_ollama_generate_maps_native_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_OLLAMA_BASE_URL", "http://ollama.test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "model failed to load"})

    response = _client(httpx.MockTransport(handler)).generate(
        _messages(),
        _decoding_config(),
    )

    assert response.finish_reason == "error"
    assert response.error_class == "ProviderHTTPError"
    assert response.error_message == "HTTP 500 error=model failed to load"


def test_ollama_generate_rejects_unsupported_decoding_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_OLLAMA_BASE_URL", "http://ollama.test")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request should not be sent")

    client = OllamaGenerateModelClient(
        config=_model_config(supports_top_k=False),
        model_input_protocol=load_model_input_protocol(PROTOCOL_PATH),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.generate(_messages(), _decoding_config())

    assert response.finish_reason == "error"
    assert response.error_class == "UnsupportedDecodingTopK"
    assert response.raw_response_ref == "provider_response/not_started"
