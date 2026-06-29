import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypedDict

import httpx

from agentenv.models.config_schema import OpenAICompatibleChatModelConfig
from agentenv.models.schema import (
    DecodingConfig,
    Message,
    ModelFinishReason,
    ModelResponse,
)
from agentenv.security.secrets import redact_secrets


_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_RAW_RESPONSE_REF = "provider_response/not_persisted"
_NOT_STARTED_RAW_RESPONSE_REF = "provider_response/not_started"


class TokenUsage(TypedDict):
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


@dataclass
class OpenAICompatibleChatModelClient:
    config: OpenAICompatibleChatModelConfig
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

        try:
            response = self._post_chat_completion(messages, decoding_config)
        except httpx.TimeoutException:
            return _timeout_response(self.model_id, started, "ProviderTimeout")
        except httpx.RequestError:
            return _error_response(self.model_id, started, "ProviderRequestError")

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
            decoding_config,
        )

    def _post_chat_completion(
        self,
        messages: list[Message],
        decoding_config: DecodingConfig,
    ) -> httpx.Response:
        base_url = _base_url(self.config)
        headers = {"Content-Type": "application/json"}
        api_key = _api_key(self.config)
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = _request_payload(self.config, messages, decoding_config)
        if self.http_client is not None:
            return self.http_client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=decoding_config.timeout_seconds,
            )

        with httpx.Client() as http_client:
            return http_client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=decoding_config.timeout_seconds,
            )


def _request_payload(
    config: OpenAICompatibleChatModelConfig,
    messages: list[Message],
    decoding_config: DecodingConfig,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": config.model_id,
        "messages": [_message_payload(message) for message in messages],
        "temperature": decoding_config.temperature,
        "top_p": decoding_config.top_p,
        "max_tokens": decoding_config.max_new_tokens,
    }
    if decoding_config.stop:
        payload["stop"] = decoding_config.stop
    if decoding_config.seed is not None:
        payload["seed"] = decoding_config.seed
    if decoding_config.top_k is not None:
        payload["top_k"] = decoding_config.top_k
    return payload


def _message_payload(message: Message) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": message.role,
        "content": message.content,
    }
    if message.name is not None:
        payload["name"] = message.name
    if message.role == "tool":
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _model_response_from_payload(
    model_id: str,
    started: float,
    payload: object,
    decoding_config: DecodingConfig,
) -> ModelResponse:
    if not isinstance(payload, dict):
        return _error_response(model_id, started, "MalformedProviderResponse")

    choice = _single_choice(payload, decoding_config)
    if choice is None:
        return _error_response(model_id, started, "MalformedProviderResponse")

    output_text = redact_secrets(_choice_output_text(choice))
    provider_finish_reason = choice.get("finish_reason")
    finish_reason = _local_finish_reason(provider_finish_reason)
    if finish_reason is None:
        return _error_response(model_id, started, "UnsupportedProviderFinishReason")

    token_usage = _token_usage(payload)
    if token_usage is None:
        return _error_response(model_id, started, "MalformedProviderResponse")

    return ModelResponse(
        model_id=model_id,
        output_text=output_text,
        finish_reason=finish_reason,
        latency_ms=_latency_ms(started),
        prompt_tokens=token_usage["prompt_tokens"],
        completion_tokens=token_usage["completion_tokens"],
        total_tokens=token_usage["total_tokens"],
        raw_response_ref=_RAW_RESPONSE_REF,
    )


def _single_choice(
    payload: dict[str, object],
    decoding_config: DecodingConfig,
) -> dict[str, Any] | None:
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return None
    if len(choices) != decoding_config.num_return_sequences:
        return None
    if decoding_config.num_return_sequences != 1:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    return choice


def _choice_output_text(choice: dict[str, Any]) -> str:
    message = choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _local_finish_reason(provider_finish_reason: object) -> ModelFinishReason | None:
    if provider_finish_reason == "stop":
        return "stop_criteria_met"
    if provider_finish_reason == "length":
        return "max_new_tokens_reached"
    return None


def _token_usage(
    payload: dict[str, object],
) -> TokenUsage | None:
    usage = payload.get("usage")
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    if not isinstance(usage, dict):
        return None

    try:
        prompt_tokens = _optional_int(usage.get("prompt_tokens"))
        completion_tokens = _optional_int(usage.get("completion_tokens"))
        total_tokens = _optional_int(usage.get("total_tokens"))
    except ValueError:
        return None

    if prompt_tokens is not None and completion_tokens is not None:
        expected_total_tokens = prompt_tokens + completion_tokens
        if total_tokens is None:
            total_tokens = expected_total_tokens
        elif total_tokens != expected_total_tokens:
            return None

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _provider_http_error_message(response: httpx.Response) -> str:
    parts = [f"HTTP {response.status_code}"]
    try:
        payload = response.json()
    except ValueError:
        return " ".join(parts)

    if not isinstance(payload, dict):
        return " ".join(parts)
    error = payload.get("error")
    if not isinstance(error, dict):
        return " ".join(parts)

    for field_name in ("type", "code", "param", "message"):
        field_value = _clean_error_fragment(error.get(field_name))
        if field_value is not None:
            parts.append(f"{field_name}={field_value}")

    return redact_secrets(_truncate_error_message(" ".join(parts)))


def _clean_error_fragment(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = " ".join(text.split())
    if not text:
        return None
    return text


def _truncate_error_message(message: str) -> str:
    max_length = 1000
    if len(message) <= max_length:
        return message
    return f"{message[:max_length - 3]}..."


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError("Expected non-negative integer or null")


def _unsupported_decoding_error(
    config: OpenAICompatibleChatModelConfig,
    decoding_config: DecodingConfig,
) -> str | None:
    if decoding_config.seed is not None and not config.capabilities.supports_seed:
        return "UnsupportedDecodingSeed"
    if decoding_config.stop and not config.capabilities.supports_stop:
        return "UnsupportedDecodingStop"
    if decoding_config.top_k is not None and not config.capabilities.supports_top_k:
        return "UnsupportedDecodingTopK"
    return None


def _missing_env_error(config: OpenAICompatibleChatModelConfig) -> str | None:
    if config.base_url_env is not None and os.getenv(config.base_url_env) is None:
        return "MissingModelBaseUrlEnvVar"
    if config.api_key_env is not None and os.getenv(config.api_key_env) is None:
        return "MissingModelApiKeyEnvVar"
    return None


def _base_url(config: OpenAICompatibleChatModelConfig) -> str:
    if config.base_url_env is None:
        return _DEFAULT_BASE_URL
    value = os.environ[config.base_url_env]
    return value.rstrip("/")


def _api_key(config: OpenAICompatibleChatModelConfig) -> str | None:
    if config.api_key_env is None:
        return None
    return os.environ[config.api_key_env]


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
