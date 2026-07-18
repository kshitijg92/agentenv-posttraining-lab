import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence, cast

from huggingface_hub import snapshot_download
from transformers import AutoTokenizer, PreTrainedTokenizerFast

from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    ModelGeneratedCharacterSpan,
)


class ContentSafeMaterializationError(ValueError):
    """An error whose message contains no rendered transcript content."""


class _TokenizerNormalizer(Protocol):
    def normalize_str(self, sequence: str) -> str: ...


class _BackendTokenizer(Protocol):
    @property
    def normalizer(self) -> _TokenizerNormalizer | None: ...


class TokenizerWithBackend(Protocol):
    @property
    def backend_tokenizer(self) -> _BackendTokenizer: ...


class TokenizerNormalizationChangedRenderedTextError(
    ContentSafeMaterializationError
):
    def __init__(
        self,
        *,
        rendered_length: int,
        normalized_length: int,
        first_difference_index: int,
        rendered_text_sha256: str,
        normalized_text_sha256: str,
    ) -> None:
        self.rendered_length = rendered_length
        self.normalized_length = normalized_length
        self.first_difference_index = first_difference_index
        self.rendered_text_sha256 = rendered_text_sha256
        self.normalized_text_sha256 = normalized_text_sha256
        super().__init__(
            "Pinned tokenizer normalization changed canonical rendered text; "
            f"rendered_length={rendered_length}, "
            f"normalized_length={normalized_length}, "
            f"first_difference_index={first_difference_index}, "
            f"rendered_text_sha256={rendered_text_sha256}, "
            f"normalized_text_sha256={normalized_text_sha256}"
        )


class PinnedTokenizerArtifactError(ContentSafeMaterializationError):
    pass


class PinnedTokenizerSpecialTokenError(ContentSafeMaterializationError):
    pass


class TokenizerOutputContractError(ContentSafeMaterializationError):
    pass


class TokenizerDecodeChangedRenderedTextError(ContentSafeMaterializationError):
    def __init__(
        self,
        *,
        rendered_length: int,
        decoded_length: int,
        rendered_text_sha256: str,
        decoded_text_sha256: str,
    ) -> None:
        super().__init__(
            "Pinned tokenizer decode changed canonical rendered text; "
            f"rendered_length={rendered_length}, "
            f"decoded_length={decoded_length}, "
            f"rendered_text_sha256={rendered_text_sha256}, "
            f"decoded_text_sha256={decoded_text_sha256}"
        )


class TokenOwnershipBoundaryCrossingError(ContentSafeMaterializationError):
    def __init__(self, *, token_index: int, start: int, end: int) -> None:
        super().__init__(
            "Token crosses a model/context ownership boundary; "
            f"token_index={token_index}, start={start}, end={end}"
        )


@dataclass(frozen=True)
class TokenizedPositiveSFTInput:
    input_ids: tuple[int, ...]
    labels: tuple[int, ...]


class MaterializationTokenizer(TokenizerWithBackend, Protocol):
    @property
    def is_fast(self) -> bool: ...

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        return_offsets_mapping: bool,
    ) -> Mapping[str, object]: ...

    def decode(
        self,
        token_ids: Sequence[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str: ...


def load_pinned_tokenizer(
    protocol: LoadedModelInputProtocol,
    *,
    cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> PreTrainedTokenizerFast:
    tokenizer_pin = protocol.record.tokenizer
    snapshot_path = Path(
        snapshot_download(
            repo_id=tokenizer_pin.source.repository_id,
            revision=tokenizer_pin.source.revision,
            cache_dir=cache_dir,
            local_files_only=local_files_only,
            allow_patterns=[
                upstream_file.repository_path
                for upstream_file in tokenizer_pin.upstream_files
            ],
        )
    ).resolve()
    _verify_pinned_tokenizer_artifacts(protocol, snapshot_path)

    tokenizer = AutoTokenizer.from_pretrained(
        snapshot_path,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    if not isinstance(tokenizer, PreTrainedTokenizerFast):
        raise PinnedTokenizerArtifactError(
            "Pinned tokenizer did not load as a fast tokenizer"
        )
    _verify_pinned_special_tokens(protocol, tokenizer)
    return tokenizer


def tokenize_positive_sft_input(
    tokenizer: MaterializationTokenizer,
    *,
    rendered_text: str,
    model_generated_spans: Sequence[ModelGeneratedCharacterSpan],
    trainer_ignore_index: int,
) -> TokenizedPositiveSFTInput:
    if not tokenizer.is_fast:
        raise TokenizerOutputContractError(
            "Positive-SFT materialization requires a fast tokenizer"
        )
    require_tokenizer_preserves_rendered_text(tokenizer, rendered_text)

    encoded = tokenizer(
        rendered_text,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    input_ids = _parse_input_ids(encoded.get("input_ids"))
    offsets = _parse_offsets(encoded.get("offset_mapping"), len(input_ids))
    if not input_ids:
        raise TokenizerOutputContractError(
            "Pinned tokenizer produced an empty token sequence"
        )

    decoded_text = tokenizer.decode(
        input_ids,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )
    if decoded_text != rendered_text:
        raise TokenizerDecodeChangedRenderedTextError(
            rendered_length=len(rendered_text),
            decoded_length=len(decoded_text),
            rendered_text_sha256=_sha256_text(rendered_text),
            decoded_text_sha256=_sha256_text(decoded_text),
        )

    labels = _build_ownership_labels(
        text_length=len(rendered_text),
        input_ids=input_ids,
        offsets=offsets,
        model_generated_spans=model_generated_spans,
        trainer_ignore_index=trainer_ignore_index,
    )
    return TokenizedPositiveSFTInput(
        input_ids=tuple(input_ids),
        labels=tuple(labels),
    )


def require_tokenizer_preserves_rendered_text(
    tokenizer: TokenizerWithBackend,
    rendered_text: str,
) -> None:
    normalizer = tokenizer.backend_tokenizer.normalizer
    if normalizer is None:
        return

    normalized_text = normalizer.normalize_str(rendered_text)
    if normalized_text == rendered_text:
        return

    raise TokenizerNormalizationChangedRenderedTextError(
        rendered_length=len(rendered_text),
        normalized_length=len(normalized_text),
        first_difference_index=_first_difference_index(
            rendered_text,
            normalized_text,
        ),
        rendered_text_sha256=_sha256_text(rendered_text),
        normalized_text_sha256=_sha256_text(normalized_text),
    )


def _verify_pinned_tokenizer_artifacts(
    protocol: LoadedModelInputProtocol,
    snapshot_path: Path,
) -> None:
    for upstream_file in protocol.record.tokenizer.upstream_files:
        artifact_path = snapshot_path / upstream_file.repository_path
        if not artifact_path.is_file():
            raise PinnedTokenizerArtifactError(
                "Pinned tokenizer artifact is missing; "
                f"repository_path={upstream_file.repository_path}"
            )
        observed_hash = _sha256_bytes(artifact_path.read_bytes())
        if observed_hash != upstream_file.sha256:
            raise PinnedTokenizerArtifactError(
                "Pinned tokenizer artifact hash mismatch; "
                f"repository_path={upstream_file.repository_path}, "
                f"observed_hash={observed_hash}, "
                f"expected_hash={upstream_file.sha256}"
            )


def _verify_pinned_special_tokens(
    protocol: LoadedModelInputProtocol,
    tokenizer: PreTrainedTokenizerFast,
) -> None:
    pins = protocol.record.tokenizer.required_special_tokens
    for name, pin in (
        ("message_start", pins.message_start),
        ("end_of_turn", pins.end_of_turn),
        ("padding", pins.padding),
    ):
        observed_token_id = tokenizer.convert_tokens_to_ids(pin.token)
        if observed_token_id != pin.token_id:
            raise PinnedTokenizerSpecialTokenError(
                "Pinned tokenizer special-token id mismatch; "
                f"special_token={name}, observed_id={observed_token_id}, "
                f"expected_id={pin.token_id}"
            )


def _parse_input_ids(raw_input_ids: object) -> list[int]:
    if not isinstance(raw_input_ids, list) or any(
        type(token_id) is not int or token_id < 0 for token_id in raw_input_ids
    ):
        raise TokenizerOutputContractError(
            "Pinned tokenizer returned invalid input_ids"
        )
    return cast(list[int], raw_input_ids)


def _parse_offsets(
    raw_offsets: object,
    token_count: int,
) -> list[tuple[int, int]]:
    if not isinstance(raw_offsets, list) or len(raw_offsets) != token_count:
        raise TokenizerOutputContractError(
            "Pinned tokenizer returned invalid offset_mapping length"
        )

    offsets: list[tuple[int, int]] = []
    for token_index, raw_offset in enumerate(raw_offsets):
        if not isinstance(raw_offset, (list, tuple)) or len(raw_offset) != 2:
            raise TokenizerOutputContractError(
                "Pinned tokenizer returned an invalid token offset; "
                f"token_index={token_index}"
            )
        start, end = raw_offset
        if type(start) is not int or type(end) is not int:
            raise TokenizerOutputContractError(
                "Pinned tokenizer returned a non-integer token offset; "
                f"token_index={token_index}"
            )
        offsets.append((start, end))
    return offsets


def _build_ownership_labels(
    *,
    text_length: int,
    input_ids: Sequence[int],
    offsets: Sequence[tuple[int, int]],
    model_generated_spans: Sequence[ModelGeneratedCharacterSpan],
    trainer_ignore_index: int,
) -> list[int]:
    model_owned = bytearray(text_length)
    for span in model_generated_spans:
        if span.start < 0 or span.end <= span.start or span.end > text_length:
            raise TokenizerOutputContractError(
                "Model-generated span is outside canonical rendered text"
            )
        model_owned[span.start : span.end] = b"\x01" * (span.end - span.start)

    covered = bytearray(text_length)
    labels: list[int] = []
    previous_start = 0
    for token_index, (token_id, (start, end)) in enumerate(
        zip(input_ids, offsets, strict=True)
    ):
        if start < previous_start:
            raise TokenizerOutputContractError(
                "Pinned tokenizer offsets are not ordered; "
                f"token_index={token_index}, start={start}"
            )
        if start < 0 or end <= start or end > text_length:
            raise TokenizerOutputContractError(
                "Pinned tokenizer returned an out-of-range or empty token offset; "
                f"token_index={token_index}, start={start}, end={end}, "
                f"rendered_length={text_length}"
            )
        previous_start = start
        covered[start:end] = b"\x01" * (end - start)
        owned_slice = model_owned[start:end]
        has_model_owned = any(owned_slice)
        has_context_owned = any(value == 0 for value in owned_slice)
        if has_model_owned and has_context_owned:
            raise TokenOwnershipBoundaryCrossingError(
                token_index=token_index,
                start=start,
                end=end,
            )
        labels.append(token_id if has_model_owned else trainer_ignore_index)

    try:
        first_uncovered_index = covered.index(0)
    except ValueError:
        first_uncovered_index = None
    if first_uncovered_index is not None:
        raise TokenizerOutputContractError(
            "Pinned tokenizer offsets do not cover canonical rendered text; "
            f"first_uncovered_index={first_uncovered_index}, "
            f"rendered_length={text_length}"
        )
    if all(label == trainer_ignore_index for label in labels):
        raise TokenizerOutputContractError(
            "Canonical materialization produced no model-owned tokens"
        )
    return labels


def _first_difference_index(left: str, right: str) -> int:
    for index, (left_character, right_character) in enumerate(zip(left, right)):
        if left_character != right_character:
            return index
    return min(len(left), len(right))


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
