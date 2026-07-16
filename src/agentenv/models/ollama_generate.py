import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import TypedDict

import httpx

from agentenv.models.agent_action_schema import agent_action_json_schema
from agentenv.models.config_schema import OllamaGenerateModelConfig
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    render_model_input,
)
from agentenv.models.schema import (
    DecodingConfig,
    Message,
    ModelFinishReason,
    ModelResponse,
)
from agentenv.security.secrets import redact_secrets


_DEFAULT_BASE_URL = "http://localhost:11434"
_RAW_RESPONSE_REF = "provider_response/not_persisted"
_NOT_STARTED_RAW_RESPONSE_REF = "provider_response/not_started"


class TokenUsage(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class OllamaGenerateModelClient:
    config: OllamaGenerateModelConfig
    model_input_protocol: LoadedModelInputProtocol
    http_client: httpx.Client | None = None

    @property
    def model_id(self) -> str:
        return self.config.model_id

    def generate(
        self,
        messages: list[Message],
        decoding_config: DecodingConfig,
    ) -> ModelResponse:
        started = perf_counter()
        unsupported_error = _unsupported_decoding_error(self.config, decoding_config)
        if unsupported_error is not None:
            return _error_response(
                self.model_id,
                started,
                unsupported_error,
                raw_response_ref=_NOT_STARTED_RAW_RESPONSE_REF,
            )

        env_error = _missing_env_error(self.config)
        if env_error is not None:
            return _error_response(
                self.model_id,
                started,
                env_error,
                raw_response_ref=_NOT_STARTED_RAW_RESPONSE_REF,
            )

        prompt = render_model_input(
            self.model_input_protocol,
            messages,
            mode="generation",
        )
        try:
            response = self._post_generate(prompt, decoding_config)
        except httpx.TimeoutException:
            return _timeout_response(self.model_id, started, "ProviderTimeout")
        except httpx.RequestError as exc:
            return _error_response(
                self.model_id,
                started,
                "ProviderRequestError",
                error_message=_provider_request_error_message(exc),
            )

        if response.status_code >= 400:
            return _error_response(
                self.model_id,
                started,
                "ProviderHTTPError",
                error_message=_provider_http_error_message(response),
            )

        try:
            payload = response.json()
        except json.JSONDecodeError:
            return _error_response(self.model_id, started, "MalformedProviderResponse")

        return _model_response_from_payload(
            self.model_id,
            started,
            payload,
        )

    def _post_generate(
        self,
        prompt: str,
        decoding_config: DecodingConfig,
    ) -> httpx.Response:
        payload = _request_payload(self.config, prompt, decoding_config)
        request_url = f"{_base_url(self.config)}/api/generate"
        headers = {"Content-Type": "application/json"}
        if self.http_client is not None:
            return self.http_client.post(
                request_url,
                headers=headers,
                json=payload,
                timeout=decoding_config.timeout_seconds,
            )

        with httpx.Client() as http_client:
            return http_client.post(
                request_url,
                headers=headers,
                json=payload,
                timeout=decoding_config.timeout_seconds,
            )


def _request_payload(
    config: OllamaGenerateModelConfig,
    prompt: str,
    decoding_config: DecodingConfig,
) -> dict[str, object]:
    options: dict[str, object] = {
        "temperature": decoding_config.temperature,
        "top_p": decoding_config.top_p,
        "num_predict": decoding_config.max_new_tokens,
    }
    if decoding_config.stop:
        options["stop"] = decoding_config.stop
    if decoding_config.seed is not None:
        options["seed"] = decoding_config.seed
    if decoding_config.top_k is not None:
        options["top_k"] = decoding_config.top_k

    payload: dict[str, object] = {
        "model": config.model_id,
        "prompt": prompt,
        "raw": True,
        "stream": False,
        "options": options,
    }
    if config.agent_action_format == "json_schema":
        payload["format"] = agent_action_json_schema()
    return payload


def _model_response_from_payload(
    model_id: str,
    started: float,
    payload: object,
) -> ModelResponse:
    if not isinstance(payload, dict):
        return _error_response(model_id, started, "MalformedProviderResponse")
    if payload.get("done") is not True:
        return _error_response(model_id, started, "MalformedProviderResponse")

    output_text = payload.get("response")
    if not isinstance(output_text, str):
        return _error_response(model_id, started, "MalformedProviderResponse")

    finish_reason = _local_finish_reason(payload.get("done_reason"))
    if finish_reason is None:
        return _error_response(
            model_id,
            started,
            "UnsupportedProviderFinishReason",
        )

    token_usage = _token_usage(payload)
    if token_usage is None:
        return _error_response(model_id, started, "MalformedProviderResponse")

    return ModelResponse(
        model_id=model_id,
        output_text=redact_secrets(output_text),
        finish_reason=finish_reason,
        latency_ms=_latency_ms(started),
        prompt_tokens=token_usage["prompt_tokens"],
        completion_tokens=token_usage["completion_tokens"],
        total_tokens=token_usage["total_tokens"],
        raw_response_ref=_RAW_RESPONSE_REF,
    )


def _local_finish_reason(done_reason: object) -> ModelFinishReason | None:
    if done_reason == "stop":
        return "stop_criteria_met"
    if done_reason == "length":
        return "max_new_tokens_reached"
    return None


def _token_usage(payload: dict[str, object]) -> TokenUsage | None:
    try:
        prompt_tokens = _non_negative_int(payload.get("prompt_eval_count"))
        completion_tokens = _non_negative_int(payload.get("eval_count"))
    except ValueError:
        return None
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _non_negative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    raise ValueError("Expected non-negative integer")


def _provider_http_error_message(response: httpx.Response) -> str:
    message = f"HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return message
    if isinstance(payload, dict):
        error = _clean_error_fragment(payload.get("error"))
        if error is not None:
            message = f"{message} error={error}"
    return redact_secrets(_truncate_error_message(message))


def _provider_request_error_message(exc: httpx.RequestError) -> str:
    message = _clean_error_fragment(str(exc))
    if message is None:
        message = "<empty>"
    return redact_secrets(
        _truncate_error_message(f"{exc.__class__.__name__}: {message}")
    )


def _clean_error_fragment(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _truncate_error_message(message: str) -> str:
    max_length = 1000
    if len(message) <= max_length:
        return message
    return f"{message[: max_length - 3]}..."


def _unsupported_decoding_error(
    config: OllamaGenerateModelConfig,
    decoding_config: DecodingConfig,
) -> str | None:
    if decoding_config.seed is not None and not config.capabilities.supports_seed:
        return "UnsupportedDecodingSeed"
    if decoding_config.stop and not config.capabilities.supports_stop:
        return "UnsupportedDecodingStop"
    if decoding_config.top_k is not None and not config.capabilities.supports_top_k:
        return "UnsupportedDecodingTopK"
    return None


def _missing_env_error(config: OllamaGenerateModelConfig) -> str | None:
    if config.base_url_env is not None and os.getenv(config.base_url_env) is None:
        return "MissingModelBaseUrlEnvVar"
    return None


def _base_url(config: OllamaGenerateModelConfig) -> str:
    if config.base_url_env is None:
        return _DEFAULT_BASE_URL
    value = os.environ[config.base_url_env].rstrip("/")
    if value.endswith("/v1"):
        raise ValueError(
            "ollama_generate base URL must be the Ollama server root, not /v1"
        )
    return value


def _timeout_response(
    model_id: str,
    started: float,
    error_class: str,
) -> ModelResponse:
    return ModelResponse(
        model_id=model_id,
        output_text="",
        finish_reason="timeout",
        latency_ms=_latency_ms(started),
        error_class=error_class,
        raw_response_ref=_RAW_RESPONSE_REF,
    )


def _error_response(
    model_id: str,
    started: float,
    error_class: str,
    *,
    error_message: str | None = None,
    raw_response_ref: str = _RAW_RESPONSE_REF,
) -> ModelResponse:
    return ModelResponse(
        model_id=model_id,
        output_text="",
        finish_reason="error",
        latency_ms=_latency_ms(started),
        error_class=error_class,
        error_message=(
            redact_secrets(error_message) if error_message is not None else None
        ),
        raw_response_ref=raw_response_ref,
    )


def _latency_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
