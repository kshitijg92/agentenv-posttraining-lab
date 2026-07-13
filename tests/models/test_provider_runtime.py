import json

import httpx
import pytest
from pydantic import ValidationError

from agentenv.artifacts.payloads import ModelConfigProvenance
from agentenv.models.config_schema import (
    ModelCapabilities,
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


def test_model_config_provenance_requires_configured_runtime_evidence() -> None:
    config = _ollama_config()
    payload = {
        "schema_version": "model_config_provenance_v0",
        "source_path": "configs/models/ollama.yaml",
        "source_hash": "xxh64:model",
        "config": json.loads(config.model_dump_json()),
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
