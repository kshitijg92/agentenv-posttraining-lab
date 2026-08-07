from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Literal, Mapping, Protocol, cast

from huggingface_hub import snapshot_download
from peft import PeftModel
import torch
import transformers

from agentenv.hashing import hash_directory
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    render_model_input,
)
from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.models.schema import DecodingConfig, Message, ModelResponse
from agentenv.security.secrets import redact_secrets
from agentenv.training.positive_sft.lora.model import (
    validate_lora_adapter_package,
)
from agentenv.training.tokenization import load_pinned_tokenizer


WeightDtype = Literal["bfloat16", "float32"]
AttentionImplementation = Literal["sdpa", "eager"]

_CONTENT_HASH_RE = re.compile(r"^xxh64:[0-9a-f]{16}$")
_RAW_RESPONSE_REF = "in_process_transformers/not_persisted"
_NOT_STARTED_RAW_RESPONSE_REF = "in_process_transformers/not_started"


class _InferenceTokenizer(Protocol):
    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        return_tensors: str,
    ) -> Mapping[str, object]: ...

    def decode(
        self,
        token_ids: list[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str: ...


class _GenerationModelConfig(Protocol):
    max_position_embeddings: int


class _GenerationModel(Protocol):
    @property
    def config(self) -> _GenerationModelConfig: ...

    def generate(self, **kwargs: object) -> torch.Tensor: ...


@dataclass(frozen=True)
class TransformersPeftPolicyBinding:
    """The immutable base-plus-optional-adapter identity for one client."""

    policy_id: str
    base_model: HuggingFaceRevisionPin
    adapter_dir: Path | None = None
    adapter_directory_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must not be empty")
        if (self.adapter_dir is None) != (self.adapter_directory_hash is None):
            raise ValueError(
                "adapter_dir and adapter_directory_hash must both be set or both null"
            )
        if (
            self.adapter_directory_hash is not None
            and _CONTENT_HASH_RE.fullmatch(self.adapter_directory_hash) is None
        ):
            raise ValueError(
                "adapter_directory_hash must use the xxh64:<16 lowercase hex> form"
            )
        if self.adapter_dir is not None:
            object.__setattr__(self, "adapter_dir", self.adapter_dir.resolve())

    @property
    def adapter_id(self) -> str | None:
        return self.adapter_directory_hash


@dataclass(frozen=True)
class TransformersPeftModelClient:
    """In-process greedy generation for one immutable policy composition."""

    binding: TransformersPeftPolicyBinding
    model_input_protocol: LoadedModelInputProtocol
    context_window_tokens: int
    _model: _GenerationModel = field(repr=False)
    _tokenizer: _InferenceTokenizer = field(repr=False)
    _input_device: torch.device = field(repr=False)

    def __post_init__(self) -> None:
        if self.context_window_tokens <= 0:
            raise ValueError("context_window_tokens must be greater than zero")
        _require_protocol_matches_base(self.binding, self.model_input_protocol)

    @property
    def model_id(self) -> str:
        return self.binding.policy_id

    @property
    def adapter_id(self) -> str | None:
        return self.binding.adapter_id

    def generate(
        self,
        messages: list[Message],
        decoding_config: DecodingConfig,
    ) -> ModelResponse:
        started = perf_counter()
        unsupported_error = _unsupported_decoding_error(decoding_config)
        if unsupported_error is not None:
            return _error_response(
                self.model_id,
                started,
                unsupported_error,
                raw_response_ref=_NOT_STARTED_RAW_RESPONSE_REF,
            )

        try:
            prompt = render_model_input(
                self.model_input_protocol,
                messages,
                mode="generation",
            )
        except Exception as exc:
            return _exception_response(
                self.model_id,
                started,
                "LocalModelInputRenderingError",
                exc,
                raw_response_ref=_NOT_STARTED_RAW_RESPONSE_REF,
            )

        try:
            encoded = self._tokenizer(
                prompt,
                add_special_tokens=False,
                return_tensors="pt",
            )
            input_ids = _single_batch_tensor(encoded, "input_ids")
            attention_mask = _single_batch_tensor(encoded, "attention_mask")
        except Exception as exc:
            return _exception_response(
                self.model_id,
                started,
                "LocalModelInputTokenizationError",
                exc,
                raw_response_ref=_NOT_STARTED_RAW_RESPONSE_REF,
            )

        prompt_tokens = input_ids.shape[1]
        if prompt_tokens == 0:
            return _error_response(
                self.model_id,
                started,
                "EmptyLocalModelInput",
                raw_response_ref=_NOT_STARTED_RAW_RESPONSE_REF,
            )
        if (
            prompt_tokens + decoding_config.max_new_tokens
            > self.context_window_tokens
        ):
            return _error_response(
                self.model_id,
                started,
                "LocalModelContextWindowExceeded",
                error_message=(
                    f"prompt_tokens={prompt_tokens}, "
                    f"max_new_tokens={decoding_config.max_new_tokens}, "
                    f"context_window_tokens={self.context_window_tokens}"
                ),
                raw_response_ref=_NOT_STARTED_RAW_RESPONSE_REF,
            )

        input_ids = input_ids.to(self._input_device)
        attention_mask = attention_mask.to(self._input_device)
        deadline = _DeadlineStoppingCriteria(
            deadline=perf_counter() + decoding_config.timeout_seconds
        )
        end_of_turn_id = (
            self.model_input_protocol.record.tokenizer.required_special_tokens
            .end_of_turn.token_id
        )
        padding_id = (
            self.model_input_protocol.record.tokenizer.required_special_tokens
            .padding.token_id
        )
        generation_config = transformers.GenerationConfig(
            do_sample=False,
            max_new_tokens=decoding_config.max_new_tokens,
            num_return_sequences=1,
            eos_token_id=end_of_turn_id,
            pad_token_id=padding_id,
            use_cache=True,
            return_dict_in_generate=False,
            output_scores=False,
        )

        try:
            with torch.inference_mode():
                output = self._model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    generation_config=generation_config,
                    use_model_defaults=False,
                    stopping_criteria=transformers.StoppingCriteriaList([deadline]),
                )
        except torch.OutOfMemoryError as exc:
            return _exception_response(
                self.model_id,
                started,
                "LocalModelOutOfMemory",
                exc,
            )
        except Exception as exc:
            return _exception_response(
                self.model_id,
                started,
                "LocalModelGenerationError",
                exc,
            )

        if deadline.triggered:
            return ModelResponse(
                model_id=self.model_id,
                output_text="",
                finish_reason="timeout",
                latency_ms=_latency_ms(started),
                error_class="LocalModelGenerationTimeout",
                raw_response_ref=_RAW_RESPONSE_REF,
            )

        generated_ids = _generated_token_ids(
            output,
            prompt_token_count=prompt_tokens,
        )
        if generated_ids is None or not generated_ids:
            return _error_response(
                self.model_id,
                started,
                "MalformedLocalModelOutput",
            )

        if generated_ids[-1] == end_of_turn_id:
            finish_reason = "stop_criteria_met"
        elif len(generated_ids) == decoding_config.max_new_tokens:
            finish_reason = "max_new_tokens_reached"
        else:
            return _error_response(
                self.model_id,
                started,
                "UnattributedLocalModelStop",
            )

        try:
            output_text = self._tokenizer.decode(
                generated_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        except Exception as exc:
            return _exception_response(
                self.model_id,
                started,
                "LocalModelOutputDecodingError",
                exc,
            )

        completion_tokens = len(generated_ids)
        return ModelResponse(
            model_id=self.model_id,
            output_text=redact_secrets(output_text),
            finish_reason=finish_reason,
            latency_ms=_latency_ms(started),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            raw_response_ref=_RAW_RESPONSE_REF,
        )


def load_transformers_peft_model_client(
    binding: TransformersPeftPolicyBinding,
    model_input_protocol: LoadedModelInputProtocol,
    *,
    device: Literal["cuda", "cpu"],
    weight_dtype: WeightDtype,
    attention_implementation: AttentionImplementation,
    model_cache_dir: Path | None = None,
    tokenizer_cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> TransformersPeftModelClient:
    """Load one base policy or base-plus-LoRA policy without adapter switching."""

    _require_protocol_matches_base(binding, model_input_protocol)
    _validate_adapter_binding(binding)
    input_device = _resolve_device(device, weight_dtype=weight_dtype)

    tokenizer = load_pinned_tokenizer(
        model_input_protocol,
        cache_dir=tokenizer_cache_dir,
        local_files_only=local_files_only,
    )
    snapshot_path = _resolve_model_snapshot(
        binding.base_model,
        cache_dir=model_cache_dir,
        local_files_only=local_files_only,
    )
    dtype = {
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[weight_dtype]
    base_model = transformers.AutoModelForCausalLM.from_pretrained(
        snapshot_path,
        local_files_only=True,
        trust_remote_code=False,
        dtype=dtype,
        attn_implementation=attention_implementation,
        low_cpu_mem_usage=True,
    )
    model: torch.nn.Module = base_model
    if binding.adapter_dir is not None:
        peft_model = PeftModel.from_pretrained(
            base_model,
            binding.adapter_dir,
            adapter_name="policy",
            is_trainable=False,
            low_cpu_mem_usage=True,
        )
        _require_loaded_adapter_active(peft_model)
        model = peft_model

    model = cast(torch.nn.Module, model)
    model.to(device=input_device)
    model.eval()
    context_window_tokens = _context_window_tokens(model)
    return TransformersPeftModelClient(
        binding=binding,
        model_input_protocol=model_input_protocol,
        context_window_tokens=context_window_tokens,
        _model=cast(_GenerationModel, model),
        _tokenizer=cast(_InferenceTokenizer, tokenizer),
        _input_device=input_device,
    )


class _DeadlineStoppingCriteria(transformers.StoppingCriteria):
    def __init__(self, *, deadline: float) -> None:
        self._deadline = deadline
        self.triggered = False

    def __call__(
        self,
        input_ids: torch.LongTensor,
        scores: torch.FloatTensor,
        **kwargs: object,
    ) -> torch.BoolTensor:
        del scores
        del kwargs
        self.triggered = perf_counter() >= self._deadline
        return cast(
            torch.BoolTensor,
            torch.full(
                (input_ids.shape[0],),
                self.triggered,
                dtype=torch.bool,
                device=input_ids.device,
            ),
        )


def _validate_adapter_binding(binding: TransformersPeftPolicyBinding) -> None:
    if binding.adapter_dir is None:
        return
    expected_hash = binding.adapter_directory_hash
    if expected_hash is None:
        raise ValueError("adapter binding is missing adapter_directory_hash")
    observed_hash = hash_directory(binding.adapter_dir)
    if observed_hash != expected_hash:
        raise ValueError(
            "LoRA adapter directory hash mismatch: "
            f"expected {expected_hash}, observed {observed_hash}"
        )
    validate_lora_adapter_package(
        binding.adapter_dir,
        base_model=binding.base_model,
    )


def _require_loaded_adapter_active(model: PeftModel) -> None:
    status = model.get_model_status()
    if status.enabled is not True:
        raise ValueError("loaded LoRA adapter is not uniformly enabled")
    if status.active_adapters != ["policy"]:
        raise ValueError("loaded LoRA adapter is not the sole active adapter")
    if status.available_adapters != ["policy"]:
        raise ValueError("local policy must contain exactly one LoRA adapter")
    if status.merged_adapters != []:
        raise ValueError("local policy LoRA adapter must remain unmerged")
    if status.trainable_params != 0:
        raise ValueError("serving policy unexpectedly has trainable parameters")


def _require_protocol_matches_base(
    binding: TransformersPeftPolicyBinding,
    protocol: LoadedModelInputProtocol,
) -> None:
    if protocol.record.model_checkpoint != binding.base_model:
        raise ValueError(
            "model input protocol checkpoint does not match the policy base model"
        )
    if protocol.record.tokenizer.source != binding.base_model:
        raise ValueError(
            "model input protocol tokenizer does not match the policy base model"
        )


def _resolve_device(
    device: Literal["cuda", "cpu"],
    *,
    weight_dtype: WeightDtype,
) -> torch.device:
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA serving was requested but CUDA is unavailable")
    if device == "cpu" and weight_dtype == "bfloat16":
        raise ValueError("CPU serving requires float32 weights in this lab")
    return torch.device(device)


def _resolve_model_snapshot(
    model_pin: HuggingFaceRevisionPin,
    *,
    cache_dir: Path | None,
    local_files_only: bool,
) -> Path:
    snapshot_path = Path(
        snapshot_download(
            repo_id=model_pin.repository_id,
            revision=model_pin.revision,
            cache_dir=cache_dir,
            local_files_only=local_files_only,
            ignore_patterns=[
                "*.gguf",
                "*.h5",
                "*.msgpack",
                "*.onnx",
                "*.ot",
                "*.tflite",
            ],
        )
    ).resolve()
    if snapshot_path.name != model_pin.revision:
        raise ValueError(
            "Hugging Face model snapshot did not resolve to the pinned revision"
        )
    return snapshot_path


def _context_window_tokens(model: torch.nn.Module) -> int:
    config = getattr(model, "config", None)
    value = getattr(config, "max_position_embeddings", None)
    if type(value) is not int or value <= 0:
        raise ValueError(
            "local causal language model is missing a positive "
            "max_position_embeddings"
        )
    return value


def _single_batch_tensor(
    encoded: Mapping[str, object],
    field_name: str,
) -> torch.Tensor:
    value = encoded.get(field_name)
    if not isinstance(value, torch.Tensor):
        raise ValueError(f"tokenizer output is missing tensor field {field_name}")
    if value.ndim != 2 or value.shape[0] != 1:
        raise ValueError(f"tokenizer field {field_name} must have batch size one")
    if field_name == "attention_mask":
        input_ids = encoded.get("input_ids")
        if not isinstance(input_ids, torch.Tensor):
            raise ValueError("tokenizer output is missing tensor field input_ids")
        if value.shape[1] != input_ids.shape[1]:
            raise ValueError("attention_mask length must match input_ids")
    return value


def _generated_token_ids(
    output: object,
    *,
    prompt_token_count: int,
) -> list[int] | None:
    if not isinstance(output, torch.Tensor):
        return None
    if output.ndim != 2 or output.shape[0] != 1:
        return None
    if output.shape[1] < prompt_token_count:
        return None
    values = output[0, prompt_token_count:].detach().cpu().tolist()
    if not isinstance(values, list) or any(type(value) is not int for value in values):
        return None
    return cast(list[int], values)


def _unsupported_decoding_error(decoding_config: DecodingConfig) -> str | None:
    if decoding_config.strategy != "greedy":
        return "UnsupportedDecodingStrategy"
    if decoding_config.seed is not None:
        return "UnsupportedDecodingSeed"
    if decoding_config.stop:
        return "UnsupportedDecodingStop"
    if decoding_config.top_k is not None:
        return "UnsupportedDecodingTopK"
    if decoding_config.top_p != 1.0:
        return "UnsupportedDecodingTopP"
    return None


def _exception_response(
    model_id: str,
    started: float,
    error_class: str,
    exc: Exception,
    *,
    raw_response_ref: str = _RAW_RESPONSE_REF,
) -> ModelResponse:
    message = " ".join(str(exc).split())
    if message:
        error_message = redact_secrets(
            f"{type(exc).__name__}: {_truncate(message, max_length=1000)}"
        )
    else:
        error_message = type(exc).__name__
    return _error_response(
        model_id,
        started,
        error_class,
        error_message=error_message,
        raw_response_ref=raw_response_ref,
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
        error_message=error_message,
        raw_response_ref=raw_response_ref,
    )


def _truncate(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def _latency_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
