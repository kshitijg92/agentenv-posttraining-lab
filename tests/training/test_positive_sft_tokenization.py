from dataclasses import dataclass
import hashlib
from typing import Any

import pytest
from tokenizers import normalizers

from agentenv.training.positive_sft.materialization.tokenization import (
    TokenizerNormalizationChangedRenderedTextError,
    require_tokenizer_preserves_rendered_text,
)


@dataclass
class _BackendTokenizer:
    normalizer: Any


@dataclass
class _Tokenizer:
    backend_tokenizer: _BackendTokenizer


@pytest.mark.parametrize(
    "rendered_text",
    [
        "plain ASCII",
        "precomposed é",
        "Greek Ω",
        "emoji 😀",
    ],
)
def test_normalization_guard_accepts_unchanged_text(rendered_text: str) -> None:
    tokenizer = _Tokenizer(_BackendTokenizer(normalizers.NFC()))

    require_tokenizer_preserves_rendered_text(tokenizer, rendered_text)


def test_normalization_guard_accepts_tokenizer_without_normalizer() -> None:
    tokenizer = _Tokenizer(_BackendTokenizer(None))

    require_tokenizer_preserves_rendered_text(tokenizer, "e\u0301")


def test_normalization_guard_rejects_changed_text_without_exposing_content() -> None:
    tokenizer = _Tokenizer(_BackendTokenizer(normalizers.NFC()))
    rendered_text = "private prefix e\u0301 private suffix"
    normalized_text = "private prefix é private suffix"

    with pytest.raises(
        TokenizerNormalizationChangedRenderedTextError
    ) as exc_info:
        require_tokenizer_preserves_rendered_text(tokenizer, rendered_text)

    error = exc_info.value
    assert error.rendered_length == len(rendered_text)
    assert error.normalized_length == len(normalized_text)
    assert error.first_difference_index == len("private prefix ")
    assert error.rendered_text_sha256 == _sha256(rendered_text)
    assert error.normalized_text_sha256 == _sha256(normalized_text)
    assert rendered_text not in str(error)
    assert normalized_text not in str(error)


def test_normalization_guard_detects_change_after_equal_prefix() -> None:
    tokenizer = _Tokenizer(_BackendTokenizer(normalizers.NFC()))

    with pytest.raises(
        TokenizerNormalizationChangedRenderedTextError
    ) as exc_info:
        require_tokenizer_preserves_rendered_text(tokenizer, "abc e\u0301")

    assert exc_info.value.first_difference_index == 4


def _sha256(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
