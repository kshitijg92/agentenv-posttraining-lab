import os
import re
from typing import cast

import httpx

from agentenv.models.config_schema import (
    ModelConfig,
    OllamaGenerateModelConfig,
    OpenAICompatibleChatModelConfig,
)
from agentenv.models.runtime_schema import (
    OllamaProviderRuntimeProvenance,
    ProviderRuntimeProvenance,
)


_PROBE_TIMEOUT_SECONDS = 10


class ProviderRuntimeProbeError(ValueError):
    """The configured provider runtime could not be identified reliably."""


def capture_provider_runtime_provenance(
    config: ModelConfig,
    *,
    http_client: httpx.Client | None = None,
) -> ProviderRuntimeProvenance | None:
    if isinstance(config, OllamaGenerateModelConfig):
        provenance = _capture_ollama_runtime(
            config,
            native_root=_ollama_generate_native_root(config),
            http_client=http_client,
        )
        if provenance.model_digest != config.model_manifest_digest:
            raise ProviderRuntimeProbeError(
                "Ollama runtime model digest does not match the model config pin"
            )
        return provenance
    if isinstance(config, OpenAICompatibleChatModelConfig):
        if config.provider_runtime_probe is None:
            return None
        if config.provider_runtime_probe == "ollama":
            return _capture_ollama_runtime(
                config,
                native_root=_openai_compatible_ollama_native_root(config),
                http_client=http_client,
            )
        raise ProviderRuntimeProbeError(
            f"Unsupported provider runtime probe: {config.provider_runtime_probe}"
        )
    raise ProviderRuntimeProbeError(
        f"Unsupported model provider for runtime probing: {config.provider}"
    )


def _capture_ollama_runtime(
    config: ModelConfig,
    *,
    native_root: str,
    http_client: httpx.Client | None,
) -> OllamaProviderRuntimeProvenance:
    if http_client is None:
        with httpx.Client() as client:
            version_payload = _get_json(client, f"{native_root}/api/version")
            tags_payload = _get_json(client, f"{native_root}/api/tags")
    else:
        version_payload = _get_json(http_client, f"{native_root}/api/version")
        tags_payload = _get_json(http_client, f"{native_root}/api/tags")

    server_version = version_payload.get("version")
    if not isinstance(server_version, str) or not server_version:
        raise ProviderRuntimeProbeError(
            "Ollama runtime probe response is missing a non-empty server version"
        )

    models = tags_payload.get("models")
    if not isinstance(models, list):
        raise ProviderRuntimeProbeError(
            "Ollama runtime probe response is missing the model list"
        )
    matching_models = [
        item
        for item in models
        if isinstance(item, dict)
        and (item.get("name") == config.model_id or item.get("model") == config.model_id)
    ]
    if len(matching_models) != 1:
        raise ProviderRuntimeProbeError(
            "Ollama runtime probe requires exactly one exact model-id match for "
            f"{config.model_id!r}; observed {len(matching_models)}"
        )
    raw_model_digest = matching_models[0].get("digest")
    if not isinstance(raw_model_digest, str):
        raise ProviderRuntimeProbeError(
            f"Ollama model {config.model_id!r} is missing its digest"
        )
    model_digest = _canonical_ollama_digest(raw_model_digest)

    return OllamaProviderRuntimeProvenance(
        provider="ollama",
        model_id=config.model_id,
        model_digest=model_digest,
        server_version=server_version,
    )


def _canonical_ollama_digest(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ProviderRuntimeProbeError(
            "Ollama model digest must contain exactly 64 lowercase hex characters"
        )
    return f"sha256:{value}"


def _configured_base_url(config: ModelConfig) -> str:
    env_name = config.base_url_env
    if env_name is None:
        if isinstance(config, OllamaGenerateModelConfig):
            return "http://localhost:11434"
        raise ProviderRuntimeProbeError(
            "Ollama runtime probing requires base_url_env in the model config"
        )
    value = os.getenv(env_name)
    if value is None:
        raise ProviderRuntimeProbeError(
            f"Ollama runtime probing requires environment variable {env_name}"
        )
    return value.rstrip("/")


def _openai_compatible_ollama_native_root(
    config: OpenAICompatibleChatModelConfig,
) -> str:
    openai_base_url = _configured_base_url(config)
    if not openai_base_url.endswith("/v1"):
        raise ProviderRuntimeProbeError(
            "Ollama runtime probing requires an OpenAI-compatible base URL ending "
            "in /v1"
        )
    return openai_base_url[: -len("/v1")]


def _ollama_generate_native_root(config: OllamaGenerateModelConfig) -> str:
    native_root = _configured_base_url(config)
    if native_root.endswith("/v1"):
        raise ProviderRuntimeProbeError(
            "ollama_generate runtime probing requires the Ollama server root, not /v1"
        )
    return native_root


def _get_json(client: httpx.Client, url: str) -> dict[str, object]:
    try:
        response = client.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise ProviderRuntimeProbeError(
            "Ollama runtime probe request failed: " + type(exc).__name__
        ) from exc
    except ValueError as exc:
        raise ProviderRuntimeProbeError(
            "Ollama runtime probe returned malformed JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderRuntimeProbeError(
            "Ollama runtime probe returned a non-object JSON payload"
        )
    return cast(dict[str, object], payload)
