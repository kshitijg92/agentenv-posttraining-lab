from pathlib import Path

import yaml
from pydantic import TypeAdapter

from agentenv.hashing import hash_file
from agentenv.models.config_schema import (
    ModelConfig,
    OllamaGenerateModelConfig,
)
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    load_model_input_protocol,
)
from agentenv.models.schema import DecodingConfig


_MODEL_CONFIG_ADAPTER = TypeAdapter(ModelConfig)


def load_model_config(path: Path) -> ModelConfig:
    raw_config = _load_yaml_mapping(path)
    return _MODEL_CONFIG_ADAPTER.validate_python(raw_config)


def load_referenced_model_input_protocol(
    config: ModelConfig,
    model_config_path: Path,
) -> LoadedModelInputProtocol | None:
    if not isinstance(config, OllamaGenerateModelConfig):
        return None

    protocol_path = (
        model_config_path.parent / config.model_input_protocol.path
    ).resolve()
    if not protocol_path.is_file():
        raise ValueError(f"Model input protocol path is not a file: {protocol_path}")

    observed_hash = hash_file(protocol_path)
    expected_hash = config.model_input_protocol.content_hash
    if observed_hash != expected_hash:
        raise ValueError(
            f"Model input protocol hash mismatch at {protocol_path}: "
            f"{observed_hash!r} != {expected_hash!r}"
        )
    return load_model_input_protocol(protocol_path)


def load_decoding_config(path: Path) -> DecodingConfig:
    raw_config = _load_yaml_mapping(path)
    return DecodingConfig.model_validate(raw_config)


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    raw_config = yaml.safe_load(path.read_text())
    if not isinstance(raw_config, dict):
        raise ValueError(f"Expected YAML mapping at {path}")
    return raw_config
