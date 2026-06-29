import pytest
from pydantic import ValidationError

from agentenv.models.schema import ModelResponse


def test_model_response_accepts_successful_stop() -> None:
    response = ModelResponse(
        model_id="fake-scripted-v0",
        output_text='{"tool_name": "read_file"}',
        finish_reason="stop_criteria_met",
        latency_ms=12,
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        error_class=None,
        raw_response_ref="raw_response.json",
    )

    assert response.model_id == "fake-scripted-v0"
    assert response.finish_reason == "stop_criteria_met"
    assert response.error_class is None
    assert response.total_tokens == 120


def test_model_response_accepts_max_new_tokens_reached_without_error() -> None:
    response = ModelResponse(
        model_id="fake-scripted-v0",
        output_text='{"tool_name": "read_file"',
        finish_reason="max_new_tokens_reached",
        latency_ms=12,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        raw_response_ref="raw_response.json",
    )

    assert response.finish_reason == "max_new_tokens_reached"
    assert response.error_class is None


def test_model_response_accepts_timeout_with_error_class() -> None:
    response = ModelResponse(
        model_id="fake-scripted-v0",
        output_text="",
        finish_reason="timeout",
        latency_ms=30000,
        error_class="ModelTimeout",
        raw_response_ref="raw_response.json",
    )

    assert response.finish_reason == "timeout"
    assert response.error_class == "ModelTimeout"


def test_model_response_accepts_error_with_error_class() -> None:
    response = ModelResponse(
        model_id="fake-scripted-v0",
        output_text="",
        finish_reason="error",
        latency_ms=0,
        error_class="ProviderError",
        error_message="HTTP 429 code=insufficient_quota",
        raw_response_ref="raw_response.json",
    )

    assert response.finish_reason == "error"
    assert response.error_class == "ProviderError"
    assert response.error_message == "HTTP 429 code=insufficient_quota"


def test_model_response_requires_error_class_for_timeout_or_error() -> None:
    with pytest.raises(ValidationError, match="timeout responses require error_class"):
        ModelResponse(
            model_id="fake-scripted-v0",
            output_text="",
            finish_reason="timeout",
            latency_ms=30000,
            raw_response_ref="raw_response.json",
        )

    with pytest.raises(ValidationError, match="error responses require error_class"):
        ModelResponse(
            model_id="fake-scripted-v0",
            output_text="",
            finish_reason="error",
            latency_ms=0,
            raw_response_ref="raw_response.json",
        )


def test_model_response_rejects_error_class_for_successful_finish_reason() -> None:
    with pytest.raises(
        ValidationError,
        match="stop_criteria_met responses cannot include error details",
    ):
        ModelResponse(
            model_id="fake-scripted-v0",
            output_text="{}",
            finish_reason="stop_criteria_met",
            latency_ms=12,
            error_class="Unexpected",
            raw_response_ref="raw_response.json",
        )

    with pytest.raises(
        ValidationError,
        match="max_new_tokens_reached responses cannot include error details",
    ):
        ModelResponse(
            model_id="fake-scripted-v0",
            output_text="{}",
            finish_reason="max_new_tokens_reached",
            latency_ms=12,
            error_class="Unexpected",
            raw_response_ref="raw_response.json",
        )


def test_model_response_requires_consistent_total_tokens() -> None:
    with pytest.raises(
        ValidationError,
        match="total_tokens must equal prompt_tokens \\+ completion_tokens",
    ):
        ModelResponse(
            model_id="fake-scripted-v0",
            output_text="{}",
            finish_reason="stop_criteria_met",
            latency_ms=12,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=119,
            raw_response_ref="raw_response.json",
        )


def test_model_response_requires_total_tokens_when_prompt_and_completion_are_known() -> None:
    with pytest.raises(
        ValidationError,
        match="total_tokens must equal prompt_tokens \\+ completion_tokens",
    ):
        ModelResponse(
            model_id="fake-scripted-v0",
            output_text="{}",
            finish_reason="stop_criteria_met",
            latency_ms=12,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=None,
            raw_response_ref="raw_response.json",
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("model_id", ""),
        ("latency_ms", -1),
        ("prompt_tokens", -1),
        ("completion_tokens", -1),
        ("total_tokens", -1),
        ("error_class", ""),
        ("error_message", ""),
        ("raw_response_ref", ""),
    ],
)
def test_model_response_rejects_invalid_field_values(
    field_name: str,
    value: object,
) -> None:
    payload: dict[str, object] = {
        "model_id": "fake-scripted-v0",
        "output_text": "{}",
        "finish_reason": "stop_criteria_met",
        "latency_ms": 12,
        "raw_response_ref": "raw_response.json",
    }
    payload[field_name] = value
    if field_name == "error_class":
        payload["finish_reason"] = "error"
    if field_name == "error_message":
        payload["finish_reason"] = "error"
        payload["error_class"] = "ProviderError"

    with pytest.raises(ValidationError):
        ModelResponse.model_validate(payload)


def test_model_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ModelResponse.model_validate(
            {
                "model_id": "fake-scripted-v0",
                "output_text": "{}",
                "finish_reason": "stop_criteria_met",
                "latency_ms": 12,
                "raw_response_ref": "raw_response.json",
                "parsed_tool_call": {"tool_name": "read_file"},
            }
        )
