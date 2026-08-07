from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import TypeAdapter

from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.hashing import hash_directory, hash_file
from agentenv.models.config_schema import (
    ModelConfig,
    OllamaGenerateModelConfig,
    TransformersPeftModelConfig,
)
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    load_model_input_protocol,
)
from agentenv.models.schema import DecodingConfig


if TYPE_CHECKING:
    from agentenv.models.transformers_peft import TransformersPeftPolicyBinding


_MODEL_CONFIG_ADAPTER = TypeAdapter(ModelConfig)


def load_model_config(path: Path) -> ModelConfig:
    raw_config = _load_yaml_mapping(path)
    return _MODEL_CONFIG_ADAPTER.validate_python(raw_config)


def load_referenced_model_input_protocol(
    config: ModelConfig,
    model_config_path: Path,
) -> LoadedModelInputProtocol | None:
    if not isinstance(
        config,
        (OllamaGenerateModelConfig, TransformersPeftModelConfig),
    ):
        return None

    protocol_path = _resolve_hash_pinned_config_file(
        model_config_path,
        reference_path=config.model_input_protocol.path,
        expected_hash=config.model_input_protocol.content_hash,
        artifact_name="Model input protocol",
    )
    protocol = load_model_input_protocol(protocol_path)
    if isinstance(config, TransformersPeftModelConfig):
        if protocol.record.model_checkpoint != config.base_model:
            raise ValueError(
                "model input protocol checkpoint does not match the configured "
                "Transformers base model"
            )
        if protocol.record.tokenizer.source != config.base_model:
            raise ValueError(
                "model input protocol tokenizer does not match the configured "
                "Transformers base model"
            )
    return protocol


def load_transformers_peft_policy_binding(
    config: TransformersPeftModelConfig,
    model_config_path: Path,
    *,
    model_input_protocol: LoadedModelInputProtocol,
) -> TransformersPeftPolicyBinding:
    """Resolve one immutable base or base-plus-adapter policy composition."""

    from agentenv.artifacts.manifests import (
        load_positive_sft_lora_training_run_manifest,
    )
    from agentenv.models.transformers_peft import TransformersPeftPolicyBinding
    from agentenv.training.positive_sft.lora.model import (
        validate_lora_adapter_package,
    )

    expected_protocol_path = _resolve_hash_pinned_config_file(
        model_config_path,
        reference_path=config.model_input_protocol.path,
        expected_hash=config.model_input_protocol.content_hash,
        artifact_name="Model input protocol",
    )
    if model_input_protocol.source_path != expected_protocol_path:
        raise ValueError(
            "loaded model input protocol does not match the model config reference"
        )
    if model_input_protocol.record.model_checkpoint != config.base_model:
        raise ValueError(
            "loaded model input protocol checkpoint does not match the configured "
            "Transformers base model"
        )
    if model_input_protocol.record.tokenizer.source != config.base_model:
        raise ValueError(
            "loaded model input protocol tokenizer does not match the configured "
            "Transformers base model"
        )

    if config.adapter is None:
        return TransformersPeftPolicyBinding(
            policy_id=config.model_id,
            base_model=config.base_model,
        )

    manifest_path = _resolve_hash_pinned_config_file(
        model_config_path,
        reference_path=config.adapter.path,
        expected_hash=config.adapter.content_hash,
        artifact_name="LoRA training manifest",
    )
    manifest = load_positive_sft_lora_training_run_manifest(manifest_path)
    if manifest.status != "completed":
        raise ValueError("adapted model policies require a completed LoRA training run")
    if manifest.base_model != config.base_model:
        raise ValueError(
            "LoRA training manifest base model does not match the model config"
        )
    if manifest.model_input_protocol_hash != config.model_input_protocol.content_hash:
        raise ValueError(
            "LoRA training manifest model input protocol hash does not match the "
            "model config"
        )
    if (
        manifest.model_input_protocol_id
        != model_input_protocol.record.protocol_id
    ):
        raise ValueError(
            "LoRA training manifest model input protocol id does not match the "
            "loaded protocol"
        )

    adapter_ref = manifest.artifacts.get("adapter")
    adapter_hash = manifest.adapter_directory_hash
    if adapter_ref is None or adapter_hash is None:
        raise ValueError("completed LoRA training manifest is missing its adapter")
    adapter_dir = resolve_relative_artifact_ref(manifest_path.parent, adapter_ref)
    observed_adapter_hash = hash_directory(adapter_dir)
    if observed_adapter_hash != adapter_hash:
        raise ValueError(
            "LoRA adapter directory hash mismatch: "
            f"expected {adapter_hash}, observed {observed_adapter_hash}"
        )
    validate_lora_adapter_package(adapter_dir, base_model=config.base_model)
    return TransformersPeftPolicyBinding(
        policy_id=config.model_id,
        base_model=config.base_model,
        adapter_dir=adapter_dir,
        adapter_directory_hash=adapter_hash,
    )


def load_decoding_config(path: Path) -> DecodingConfig:
    raw_config = _load_yaml_mapping(path)
    return DecodingConfig.model_validate(raw_config)


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    raw_config = yaml.safe_load(path.read_text())
    if not isinstance(raw_config, dict):
        raise ValueError(f"Expected YAML mapping at {path}")
    return raw_config


def _resolve_hash_pinned_config_file(
    config_path: Path,
    *,
    reference_path: str,
    expected_hash: str,
    artifact_name: str,
) -> Path:
    path = (config_path.parent / reference_path).resolve()
    if not path.is_file():
        raise ValueError(f"{artifact_name} path is not a file: {path}")
    observed_hash = hash_file(path)
    if observed_hash != expected_hash:
        raise ValueError(
            f"{artifact_name} hash mismatch at {path}: "
            f"{observed_hash!r} != {expected_hash!r}"
        )
    return path
