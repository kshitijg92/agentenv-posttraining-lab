from pathlib import Path

import yaml

from agentenv.training.positive_sft.lora.schema import (
    PositiveSFTLoRATrainingConfig,
)


def load_positive_sft_lora_training_config(
    path: Path,
) -> PositiveSFTLoRATrainingConfig:
    raw_config = yaml.safe_load(path.resolve().read_text())
    if not isinstance(raw_config, dict):
        raise ValueError(f"Expected YAML mapping at {path.resolve()}")
    return PositiveSFTLoRATrainingConfig.model_validate(raw_config)
