import pytest
from pydantic import ValidationError

from agentenv.models.schema import DecodingConfig


def test_decoding_config_accepts_greedy_config() -> None:
    config = DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=512,
        timeout_seconds=30,
    )

    assert config.strategy == "greedy"
    assert config.temperature == 0.0
    assert config.top_p == 1.0
    assert config.top_k is None
    assert config.max_new_tokens == 512
    assert config.num_return_sequences == 1
    assert config.seed is None
    assert config.stop == []
    assert config.timeout_seconds == 30


def test_decoding_config_accepts_sampling_config() -> None:
    config = DecodingConfig(
        strategy="sampling",
        temperature=0.7,
        top_p=0.95,
        top_k=40,
        max_new_tokens=1024,
        num_return_sequences=1,
        seed=123,
        stop=["</tool_call>"],
        timeout_seconds=60,
    )

    assert config.strategy == "sampling"
    assert config.top_k == 40
    assert config.seed == 123
    assert config.stop == ["</tool_call>"]


def test_decoding_config_rejects_greedy_nonzero_temperature() -> None:
    with pytest.raises(
        ValidationError,
        match="greedy decoding requires temperature 0.0",
    ):
        DecodingConfig(
            strategy="greedy",
            temperature=0.1,
            top_p=1.0,
            max_new_tokens=512,
            timeout_seconds=30,
        )


def test_decoding_config_rejects_multiple_return_sequences_for_v0() -> None:
    with pytest.raises(
        ValidationError,
        match="num_return_sequences must be 1 for v0",
    ):
        DecodingConfig(
            strategy="sampling",
            temperature=0.7,
            top_p=0.95,
            max_new_tokens=512,
            num_return_sequences=2,
            timeout_seconds=30,
        )


def test_decoding_config_rejects_empty_stop_sequence() -> None:
    with pytest.raises(ValidationError, match="stop sequences cannot be empty"):
        DecodingConfig(
            strategy="sampling",
            temperature=0.7,
            top_p=0.95,
            max_new_tokens=512,
            stop=[""],
            timeout_seconds=30,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("temperature", -0.1),
        ("temperature", 2.1),
        ("top_p", 0.0),
        ("top_p", 1.1),
        ("top_k", 0),
        ("max_new_tokens", 0),
        ("seed", -1),
        ("timeout_seconds", 0),
    ],
)
def test_decoding_config_rejects_out_of_range_values(
    field_name: str,
    value: object,
) -> None:
    payload: dict[str, object] = {
        "strategy": "sampling",
        "temperature": 0.7,
        "top_p": 0.95,
        "max_new_tokens": 512,
        "timeout_seconds": 30,
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        DecodingConfig.model_validate(payload)


def test_decoding_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DecodingConfig.model_validate(
            {
                "strategy": "greedy",
                "temperature": 0.0,
                "top_p": 1.0,
                "max_new_tokens": 512,
                "timeout_seconds": 30,
                "max_turns": 8,
            }
        )
