import json

import httpx
import pytest
from pydantic import ValidationError

from agentenv.artifacts.payloads import ModelConfigProvenance
from agentenv.models.config_schema import (
    ModelCapabilities,
    OllamaGenerateModelConfig,
    OpenAICompatibleChatModelConfig,
)
from agentenv.models.provider_runtime import (
    ProviderRuntimeProbeError,
    capture_provider_runtime_provenance,
)


RAW_MODEL_DIGEST = "a" * 64
MODEL_DIGEST = "sha256:" + RAW_MODEL_DIGEST


def _ollama_config() -> OpenAICompatibleChatModelConfig:
    return OpenAICompatibleChatModelConfig(
        version="model_config_v0",
        provider="openai_compatible_chat",
        model_id="qwen-test:7b",
        base_url_env="AGENTENV_MODEL_BASE_URL",
        capabilities=ModelCapabilities(
            token_usage="native",
            supports_seed=False,
            supports_stop=True,
            supports_top_k=False,
        ),
        provider_runtime_probe="ollama",
    )


def _ollama_generate_config() -> OllamaGenerateModelConfig:
    return OllamaGenerateModelConfig.model_validate(
        {
            "version": "model_config_v0",
            "provider": "ollama_generate",
            "model_id": "qwen-test:7b",
            "model_manifest_digest": MODEL_DIGEST,
            "base_url_env": "AGENTENV_OLLAMA_BASE_URL",
            "capabilities": {
                "token_usage": "native",
                "supports_seed": True,
                "supports_stop": True,
                "supports_top_k": True,
            },
            "model_input_protocol": {
                "path": "../model_input_protocols/qwen-test.yaml",
                "content_hash": "xxh64:1111111111111111",
            },
            "agent_action_format": "json_schema",
        }
    )


def test_ollama_runtime_probe_pins_model_digest_and_server_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTENV_MODEL_BASE_URL",
        "http://provider.test/ollama/v1/",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ollama/api/version":
            return httpx.Response(200, json={"version": "0.30.11"})
        if request.url.path == "/ollama/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "qwen-test:7b",
                            "model": "qwen-test:7b",
                            "digest": RAW_MODEL_DIGEST,
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected provider probe path {request.url.path}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provenance = capture_provider_runtime_provenance(
            _ollama_config(),
            http_client=client,
        )

    assert provenance is not None
    assert provenance.provider == "ollama"
    assert provenance.model_id == "qwen-test:7b"
    assert provenance.model_digest == MODEL_DIGEST
    assert provenance.server_version == "0.30.11"


def test_ollama_runtime_probe_rejects_missing_exact_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "http://provider.test/v1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.30.11"})
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen-test:7b-latest",
                        "digest": RAW_MODEL_DIGEST,
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderRuntimeProbeError, match="exact model-id match"):
            capture_provider_runtime_provenance(
                _ollama_config(),
                http_client=client,
            )


def test_ollama_generate_runtime_probe_uses_native_root_and_config_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTENV_OLLAMA_BASE_URL",
        "http://provider.test/ollama/",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ollama/api/version":
            return httpx.Response(200, json={"version": "0.30.11"})
        if request.url.path == "/ollama/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "qwen-test:7b",
                            "digest": RAW_MODEL_DIGEST,
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected provider probe path {request.url.path}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provenance = capture_provider_runtime_provenance(
            _ollama_generate_config(),
            http_client=client,
        )

    assert provenance is not None
    assert provenance.model_digest == MODEL_DIGEST


def test_model_config_provenance_requires_configured_runtime_evidence() -> None:
    config = _ollama_config()
    payload = {
        "schema_version": "model_config_provenance_v0",
        "source_path": "configs/models/ollama.yaml",
        "source_hash": "xxh64:model",
        "config": json.loads(config.model_dump_json()),
        "model_input_protocol": None,
        "provider_runtime": None,
    }

    with pytest.raises(
        ValidationError,
        match="configured provider_runtime_probe requires provider_runtime evidence",
    ):
        ModelConfigProvenance.model_validate(payload)


def test_model_config_provenance_requires_matching_runtime_model_id() -> None:
    config = _ollama_config()
    payload = {
        "schema_version": "model_config_provenance_v0",
        "source_path": "configs/models/ollama.yaml",
        "source_hash": "xxh64:model",
        "config": json.loads(config.model_dump_json()),
        "model_input_protocol": None,
        "provider_runtime": {
            "provider": "ollama",
            "model_id": "different-model:7b",
            "model_digest": MODEL_DIGEST,
            "server_version": "0.30.11",
        },
    }

    with pytest.raises(
        ValidationError,
        match="provider_runtime model_id must match",
    ):
        ModelConfigProvenance.model_validate(payload)
