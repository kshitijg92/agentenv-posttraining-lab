from pathlib import Path

import yaml

from agentenv.models.config_schema import ModelConfig
from agentenv.models.schema import DecodingConfig


def load_model_config(path: Path) -> ModelConfig:
    raw_config = _load_yaml_mapping(path)
    return ModelConfig.model_validate(raw_config)


def load_decoding_config(path: Path) -> DecodingConfig:
    raw_config = _load_yaml_mapping(path)
    return DecodingConfig.model_validate(raw_config)


def _load_yaml_mapping(path: Path) -> dict[str, object]:
    raw_config = yaml.safe_load(path.read_text())
    if not isinstance(raw_config, dict):
        raise ValueError(f"Expected YAML mapping at {path}")
    return raw_config
