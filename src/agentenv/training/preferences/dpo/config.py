from pathlib import Path

import yaml

from agentenv.training.preferences.dpo.schema import DPOLoRATrainingConfig


def load_dpo_lora_training_config(path: Path) -> DPOLoRATrainingConfig:
    raw_config = yaml.safe_load(path.read_text())
    if not isinstance(raw_config, dict):
        raise ValueError("DPO LoRA training config must contain a YAML object")
    return DPOLoRATrainingConfig.model_validate(raw_config)
