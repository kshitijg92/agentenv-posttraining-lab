import pytest
from pydantic import ValidationError

from agentenv.artifacts.manifests import DPOLoRATrainingRunManifest
from agentenv.training.preferences.dpo.schema import (
    DPOInitializationAudit,
    DPOLoRATrainingConfig,
)


def _config_payload() -> dict:
    return {
        "schema_version": "dpo_lora_training_config_v0",
        "config_id": "dpo_lora_exploratory",
        "model_input_protocol_id": "qwen2_5_coder_3b_agentenv_json",
        "objective": {
            "loss": "sigmoid",
            "beta": 0.1,
            "response_log_probability_aggregation": "sum",
            "reference_policy": "frozen_parent",
        },
        "optimizer": {
            "optimizer": "adamw",
            "learning_rate": 0.0002,
            "beta1": 0.9,
            "beta2": 0.999,
            "epsilon": 1.0e-8,
            "weight_decay": 0.0,
            "max_gradient_norm": 1.0,
            "schedule": "constant",
        },
        "data": {
            "pair_order": "source_then_record",
            "shuffle": False,
            "micro_batch_size": 1,
        },
        "runtime": {
            "device": "cuda",
            "weight_dtype": "bfloat16",
            "attention_implementation": "sdpa",
            "gradient_checkpointing": True,
            "deterministic_algorithms": True,
            "cublas_workspace_config": ":4096:8",
        },
        "seed": 42,
        "max_steps": 1,
        "gradient_accumulation_steps": 1,
        "reload_probe_token_count": 64,
    }


def _manifest_payload() -> dict:
    return {
        "artifact_type": "dpo_lora_training_run",
        "artifact_schema_version": "dpo_lora_training_run_artifact_v0",
        "created_at": "2026-08-13T00:00:00Z",
        "training_run_id": f"dpo_lora_run_{'a' * 32}",
        "status": "completed",
        "source_dpo_training_materializations": [
            {
                "artifact_dir": "/tmp/dpo-materialization",
                "manifest_hash": "xxh64:1111111111111111",
                "materializations_jsonl_hash": "xxh64:2222222222222222",
            }
        ],
        "parent_sft_policy": {
            "artifact_dir": "/tmp/sft-parent",
            "manifest_hash": "xxh64:3333333333333333",
            "training_run_id": f"positive_sft_lora_run_{'b' * 32}",
            "adapter_directory_hash": "xxh64:4444444444444444",
        },
        "training_config": {
            "path": "/tmp/dpo.yaml",
            "content_hash": "xxh64:5555555555555555",
            "config_id": "dpo_lora_exploratory",
        },
        "model_input_protocol_id": "qwen2_5_coder_3b_agentenv_json",
        "model_input_protocol_hash": "xxh64:6666666666666666",
        "base_model": {
            "repository_id": "Qwen/Qwen2.5-Coder-3B-Instruct",
            "revision": "c" * 40,
        },
        "trainer_code_hash": "xxh64:7777777777777777",
        "training_result_schema_version": "dpo_lora_training_result_v0",
        "training_step_schema_version": "dpo_lora_training_step_v0",
        "selected_pair_count": 29,
        "requested_step_count": 1,
        "completed_step_count": 1,
        "training_result_hash": "xxh64:8888888888888888",
        "training_steps_hash": "xxh64:9999999999999999",
        "adapter_directory_hash": "xxh64:aaaaaaaaaaaaaaaa",
        "artifacts": {
            "training_result": "training_result.json",
            "training_steps": "training_steps.jsonl",
            "adapter": "adapter",
        },
    }


def test_exploratory_config_pins_canonical_dpo_objective() -> None:
    config = DPOLoRATrainingConfig.model_validate(_config_payload())

    assert config.objective.loss == "sigmoid"
    assert config.objective.response_log_probability_aggregation == "sum"
    assert config.objective.reference_policy == "frozen_parent"


def test_initialization_audit_requires_exact_parent_policy_reference_identity() -> None:
    with pytest.raises(ValidationError, match="adapter states must match"):
        DPOInitializationAudit.model_validate(
            {
                "expected_parent_adapter_state_hash": "xxh64:1111111111111111",
                "reference_adapter_state_hash": "xxh64:1111111111111111",
                "policy_adapter_state_hash_before": "xxh64:2222222222222222",
                "expected_parent_frozen_state_hash": "xxh64:3333333333333333",
                "reference_frozen_state_hash": "xxh64:3333333333333333",
                "policy_frozen_state_hash_before": "xxh64:3333333333333333",
                "compared_pair_count": 1,
                "maximum_absolute_log_probability_difference": 0.0,
                "policy_and_reference_start_identically": True,
                "reference_log_probabilities_precomputed_before_optimization": True,
            }
        )


def test_dpo_manifest_pins_parent_sources_config_and_adapter() -> None:
    manifest = DPOLoRATrainingRunManifest.model_validate(_manifest_payload())

    assert manifest.selected_pair_count == 29
    assert manifest.parent_sft_policy.adapter_directory_hash == (
        "xxh64:4444444444444444"
    )


def test_dpo_manifest_rejects_partial_completed_run() -> None:
    payload = _manifest_payload()
    payload["requested_step_count"] = 2

    with pytest.raises(ValidationError, match="every requested step"):
        DPOLoRATrainingRunManifest.model_validate(payload)
