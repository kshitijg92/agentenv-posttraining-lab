import json
from pathlib import Path
from typing import cast

from huggingface_hub import snapshot_download
import torch
import transformers

from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.training.positive_sft.lora.schema import (
    PositiveSFTLoRATrainingConfig,
)


_ADAPTER_CONFIG_FILENAME = "adapter_config.json"
_GENERATED_MODEL_CARD_FILENAME = "README.md"


def load_pinned_causal_lm(
    config: PositiveSFTLoRATrainingConfig,
    *,
    cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> transformers.PreTrainedModel:
    model_pin = config.base_model
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
    }[config.runtime.weight_dtype]
    model = transformers.AutoModelForCausalLM.from_pretrained(
        snapshot_path,
        local_files_only=True,
        trust_remote_code=False,
        dtype=dtype,
        attn_implementation=config.runtime.attention_implementation,
        low_cpu_mem_usage=True,
    )
    if not isinstance(model, transformers.PreTrainedModel):
        raise ValueError("pinned checkpoint did not load as a PreTrainedModel")
    return cast(transformers.PreTrainedModel, model)


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
        raise ValueError("canonical LoRA adapter package is missing adapter_config.json")
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
