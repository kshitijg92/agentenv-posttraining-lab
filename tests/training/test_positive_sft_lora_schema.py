from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.training.positive_sft.lora.config import (
    load_positive_sft_lora_training_config,
)
from agentenv.training.positive_sft.lora.schema import (
    AdapterQualificationAudit,
    PositiveSFTLoRATrainingConfig,
    SelectedPositiveSFTTrainingExample,
)


CONFIG_PATH = Path("configs/train/positive_sft_lora_smoke.yaml")


def _config_payload() -> dict[str, Any]:
    return load_positive_sft_lora_training_config(CONFIG_PATH).model_dump(mode="json")


def test_smoke_config_pins_scale_one_ordinary_lora() -> None:
    config = load_positive_sft_lora_training_config(CONFIG_PATH)

    assert config.purpose == "operational_smoke"
    assert config.lora.scale == 1.0
    assert config.lora.alpha == config.lora.rank
    assert config.lora.use_rslora is False
    assert config.lora.use_dora is False
    assert config.qualification_step_count == 2
    assert config.lora.target_modules == (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
    )


def test_lora_target_modules_must_be_unique() -> None:
    payload = _config_payload()
    payload["lora"]["target_modules"] = ["q_proj", "q_proj"]

    with pytest.raises(ValidationError, match="must be unique"):
        PositiveSFTLoRATrainingConfig.model_validate(payload)


def test_cpu_bfloat16_is_rejected_by_initial_runtime_contract() -> None:
    payload = _config_payload()
    payload["runtime"]["device"] = "cpu"

    with pytest.raises(ValidationError, match="requires float32"):
        PositiveSFTLoRATrainingConfig.model_validate(payload)


def test_qualification_requires_at_least_two_steps() -> None:
    payload = _config_payload()
    payload["qualification_step_count"] = 1

    with pytest.raises(ValidationError, match="greater than or equal to 2"):
        PositiveSFTLoRATrainingConfig.model_validate(payload)


def test_qualification_length_is_independent_of_training_length() -> None:
    payload = _config_payload()
    payload["max_steps"] = 1
    payload["qualification_step_count"] = 4

    config = PositiveSFTLoRATrainingConfig.model_validate(payload)

    assert config.max_steps == 1
    assert config.qualification_step_count == 4


def test_selected_example_requires_exact_shifted_target_accounting() -> None:
    with pytest.raises(ValidationError, match="reachable after causal shift"):
        SelectedPositiveSFTTrainingExample(
            source_positive_sft_example_id="positive_sft_example_1",
            source_materialization_record_hash="xxh64:1111111111111111",
            sequence_length=6,
            stored_supervised_token_count=3,
            effective_shifted_supervised_token_count=2,
            ignored_prediction_count=3,
        )


def test_qualification_audit_requires_one_row_count_per_parameter() -> None:
    with pytest.raises(ValidationError, match="parameter audit rows"):
        AdapterQualificationAudit.model_validate(
            {
                "qualification_step_count": 2,
                "intended_logical_adapter_count": 1,
                "observed_logical_adapter_count": 1,
                "adapter_parameter_count": 2,
                "every_logical_adapter_received_finite_nonzero_gradient_during_qualification": True,
                "every_logical_adapter_changed_during_qualification": True,
                "parameters": [
                    {
                        "parameter_name": "layer.lora_A.default.weight",
                        "logical_adapter_name": "layer",
                        "factor": "A",
                        "gradient_observed_during_qualification": True,
                        "nonzero_gradient_observed_during_qualification": False,
                        "all_qualification_gradients_finite": True,
                        "parameter_changed_during_qualification": False,
                    }
                ],
            }
        )
