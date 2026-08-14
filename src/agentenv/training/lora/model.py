from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, cast

from huggingface_hub import snapshot_download
import peft
import torch
import transformers

from agentenv.hashing import hash_directory
from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.training.lora.runtime import (
    configure_model_for_inference,
    get_last_token_logits,
    release_accelerator_memory,
)
from agentenv.training.lora.schema import (
    AdapterRoundTripAudit,
    TrainingRuntimeConfig,
)
from agentenv.training.lora.state import (
    get_adapter_parameters,
    get_frozen_parameters,
    hash_named_tensors,
    hash_tensor,
)


_ADAPTER_CONFIG_FILENAME = "adapter_config.json"
_GENERATED_MODEL_CARD_FILENAME = "README.md"


@dataclass(frozen=True)
class PersistedLoRAAdapter:
    directory_hash: str
    trained_frozen_state_hash: str
    trained_adapter_state_hash: str
    trained_probe_logits: torch.Tensor


def load_pinned_causal_lm(
    model_pin: HuggingFaceRevisionPin,
    runtime: TrainingRuntimeConfig,
    *,
    cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> transformers.PreTrainedModel:
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
    dtype = {
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[runtime.weight_dtype]
    model = transformers.AutoModelForCausalLM.from_pretrained(
        snapshot_path,
        local_files_only=True,
        trust_remote_code=False,
        dtype=dtype,
        attn_implementation=runtime.attention_implementation,
        low_cpu_mem_usage=True,
    )
    if not isinstance(model, transformers.PreTrainedModel):
        raise ValueError("pinned checkpoint did not load as a PreTrainedModel")
    return cast(transformers.PreTrainedModel, model)


def persist_lora_adapter(
    *,
    model: Any,
    adapters: Mapping[str, torch.nn.Parameter],
    frozen: Mapping[str, torch.nn.Parameter],
    probe_input_ids: torch.Tensor,
    adapter_dir: Path,
    base_model: HuggingFaceRevisionPin,
) -> PersistedLoRAAdapter:
    trained_probe_logits = get_last_token_logits(model, probe_input_ids)
    trained_adapter_state_hash = hash_named_tensors(adapters)
    trained_frozen_state_hash = hash_named_tensors(frozen)

    if adapter_dir.exists() and any(adapter_dir.iterdir()):
        raise ValueError(f"Adapter output directory is not empty: {adapter_dir}")
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(
        str(adapter_dir),
        safe_serialization=True,
        save_embedding_layers=False,
    )
    finalize_lora_adapter_package(adapter_dir, base_model=base_model)
    return PersistedLoRAAdapter(
        directory_hash=hash_directory(adapter_dir),
        trained_frozen_state_hash=trained_frozen_state_hash,
        trained_adapter_state_hash=trained_adapter_state_hash,
        trained_probe_logits=trained_probe_logits,
    )


def audit_lora_adapter_round_trip(
    *,
    persisted: PersistedLoRAAdapter,
    adapter_dir: Path,
    base_model: HuggingFaceRevisionPin,
    load_base_model: Callable[[], transformers.PreTrainedModel],
    probe_input_ids: torch.Tensor,
    device: torch.device,
) -> AdapterRoundTripAudit:
    validate_lora_adapter_package(adapter_dir, base_model=base_model)
    reloaded_base = load_base_model()
    reloaded_model: Any = peft.PeftModel.from_pretrained(
        reloaded_base,
        adapter_dir,
        is_trainable=False,
    )
    configure_model_for_inference(reloaded_model)
    reloaded_model.to(device)
    reloaded_adapters = get_adapter_parameters(reloaded_model)
    reloaded_frozen = get_frozen_parameters(reloaded_model)
    reloaded_adapter_state_hash = hash_named_tensors(reloaded_adapters)
    reloaded_frozen_state_hash = hash_named_tensors(reloaded_frozen)
    if reloaded_adapter_state_hash != persisted.trained_adapter_state_hash:
        raise ValueError("reloaded LoRA adapter state differs from trained state")
    if reloaded_frozen_state_hash != persisted.trained_frozen_state_hash:
        raise ValueError("reloaded frozen base state differs from trained state")

    reloaded_probe_logits = get_last_token_logits(reloaded_model, probe_input_ids)
    maximum_absolute_logit_difference = float(
        (persisted.trained_probe_logits.float() - reloaded_probe_logits.float())
        .abs()
        .max()
        .item()
    )
    if not torch.equal(persisted.trained_probe_logits, reloaded_probe_logits):
        raise ValueError(
            "reloaded LoRA adapter does not reproduce exact probe logits; "
            f"maximum_absolute_difference={maximum_absolute_logit_difference}"
        )

    audit = AdapterRoundTripAudit(
        persisted_adapter_directory_hash=persisted.directory_hash,
        trained_frozen_state_hash=persisted.trained_frozen_state_hash,
        reloaded_frozen_state_hash=reloaded_frozen_state_hash,
        frozen_base_state_exactly_reloaded=True,
        trained_adapter_state_hash=persisted.trained_adapter_state_hash,
        reloaded_adapter_state_hash=reloaded_adapter_state_hash,
        adapter_state_exactly_reloaded=True,
        probe_token_count=probe_input_ids.shape[1],
        trained_probe_logits_hash=hash_tensor(persisted.trained_probe_logits),
        reloaded_probe_logits_hash=hash_tensor(reloaded_probe_logits),
        maximum_absolute_logit_difference=maximum_absolute_logit_difference,
        probe_logits_exactly_equal=True,
    )
    del reloaded_adapters, reloaded_frozen, reloaded_model, reloaded_base
    release_accelerator_memory(device)
    return audit


def finalize_lora_adapter_package(
    adapter_dir: Path,
    *,
    base_model: HuggingFaceRevisionPin,
) -> None:
    (adapter_dir / _GENERATED_MODEL_CARD_FILENAME).unlink(missing_ok=True)
    validate_lora_adapter_package(adapter_dir, base_model=base_model)


def validate_lora_adapter_package(
    adapter_dir: Path,
    *,
    base_model: HuggingFaceRevisionPin,
) -> None:
    generated_model_card = adapter_dir / _GENERATED_MODEL_CARD_FILENAME
    if generated_model_card.exists():
        raise ValueError("canonical LoRA adapter package contains generated README.md")

    adapter_config_path = adapter_dir / _ADAPTER_CONFIG_FILENAME
    if not adapter_config_path.is_file():
        raise ValueError(
            "canonical LoRA adapter package is missing adapter_config.json"
        )
    raw_config = json.loads(adapter_config_path.read_text())
    if not isinstance(raw_config, dict):
        raise ValueError("LoRA adapter_config.json must contain a JSON object")
    if raw_config.get("base_model_name_or_path") != base_model.repository_id:
        raise ValueError(
            "LoRA adapter config does not name the canonical base-model repository"
        )
    if raw_config.get("revision") != base_model.revision:
        raise ValueError(
            "LoRA adapter config does not pin the canonical base-model revision"
        )
