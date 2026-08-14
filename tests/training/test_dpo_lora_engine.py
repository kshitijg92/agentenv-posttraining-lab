from collections.abc import Callable
from pathlib import Path

import peft
import pytest
import torch
import transformers

from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.training.lora.model import finalize_lora_adapter_package
from agentenv.training.lora.state import (
    get_adapter_parameters,
    get_frozen_parameters,
    hash_named_tensors,
)
from agentenv.training.preferences.dpo.engine import (
    execute_dpo_lora_training,
    select_dpo_training_pairs,
)
from agentenv.training.preferences.dpo.schema import DPOLoRATrainingConfig
from agentenv.training.preferences.materialization.schema import (
    CompletedDPOTrainingMaterializationRecord,
)


BASE_PIN = HuggingFaceRevisionPin(
    repository_id="example/tiny-qwen",
    revision="a" * 40,
)


def _config(*, max_steps: int = 1) -> DPOLoRATrainingConfig:
    return DPOLoRATrainingConfig.model_validate(
        {
            "schema_version": "dpo_lora_training_config_v0",
            "config_id": "dpo_lora_test",
            "model_input_protocol_id": "qwen2_5_coder_3b_agentenv_json",
            "objective": {
                "loss": "sigmoid",
                "beta": 0.1,
                "response_log_probability_aggregation": "sum",
                "reference_policy": "frozen_parent",
            },
            "optimizer": {
                "optimizer": "adamw",
                "learning_rate": 0.001,
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
                "device": "cpu",
                "weight_dtype": "float32",
                "attention_implementation": "eager",
                "gradient_checkpointing": False,
                "deterministic_algorithms": True,
                "cublas_workspace_config": ":4096:8",
            },
            "seed": 42,
            "max_steps": max_steps,
            "gradient_accumulation_steps": 1,
            "reload_probe_token_count": 4,
        }
    )


def _record(
    *, pair_id: str = "preference_pair_aaaaaaaaaaaaaaaa"
) -> CompletedDPOTrainingMaterializationRecord:
    return CompletedDPOTrainingMaterializationRecord(
        source_preference_pair_id=pair_id,
        source_preference_pair_record_hash="xxh64:1111111111111111",
        model_input_protocol_id="qwen2_5_coder_3b_agentenv_json",
        model_input_protocol_hash="xxh64:2222222222222222",
        serialization_mode="shared_context_next_action",
        max_sequence_length=16,
        materializer_version="dpo_training_materializer_v0",
        materializer_code_hash="xxh64:3333333333333333",
        status="completed",
        shared_prompt_token_count=3,
        chosen_input_ids=[1, 2, 3, 4, 5],
        chosen_labels=[-100, -100, -100, 4, 5],
        chosen_sequence_length=5,
        chosen_response_token_count=2,
        rejected_input_ids=[1, 2, 3, 6, 7],
        rejected_labels=[-100, -100, -100, 6, 7],
        rejected_sequence_length=5,
        rejected_response_token_count=2,
    )


def _tiny_base_factory() -> Callable[[], transformers.PreTrainedModel]:
    torch.manual_seed(17)
    model_config = transformers.Qwen2Config(
        vocab_size=64,
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=128,
        tie_word_embeddings=True,
    )
    reference = transformers.Qwen2ForCausalLM(model_config)
    state = {
        name: tensor.detach().clone() for name, tensor in reference.state_dict().items()
    }

    def load() -> transformers.PreTrainedModel:
        model = transformers.Qwen2ForCausalLM(model_config)
        model.load_state_dict(state, strict=True)
        return model

    return load


def _write_parent_adapter(
    path: Path,
    base_factory: Callable[[], transformers.PreTrainedModel],
) -> tuple[str, str]:
    model = peft.get_peft_model(
        base_factory(),
        peft.LoraConfig(
            task_type=peft.TaskType.CAUSAL_LM,
            inference_mode=False,
            r=2,
            lora_alpha=2,
            lora_dropout=0.0,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            bias="none",
        ),
    )
    model.peft_config["default"].base_model_name_or_path = BASE_PIN.repository_id
    model.peft_config["default"].revision = BASE_PIN.revision
    adapter_hash = hash_named_tensors(get_adapter_parameters(model))
    frozen_hash = hash_named_tensors(get_frozen_parameters(model))
    model.save_pretrained(
        str(path),
        safe_serialization=True,
        save_embedding_layers=False,
    )
    finalize_lora_adapter_package(path, base_model=BASE_PIN)
    return adapter_hash, frozen_hash


def test_dpo_training_starts_from_exact_parent_and_persists_changed_adapter(
    tmp_path: Path,
) -> None:
    config = _config()
    selected = select_dpo_training_pairs([_record()])
    base_factory = _tiny_base_factory()
    parent_dir = tmp_path / "parent"
    parent_hash, frozen_hash = _write_parent_adapter(parent_dir, base_factory)

    execution = execute_dpo_lora_training(
        load_base_model=base_factory,
        parent_adapter_dir=parent_dir,
        base_model_pin=BASE_PIN,
        expected_parent_adapter_state_hash=parent_hash,
        expected_parent_frozen_state_hash=frozen_hash,
        selected_pairs=selected,
        config=config,
        adapter_dir=tmp_path / "trained",
    )

    assert len(execution.steps) == 1
    step = execution.steps[0]
    assert step.loss == pytest.approx(torch.log(torch.tensor(2.0)).item())
    assert step.reward_margin == pytest.approx(0.0)
    assert step.policy_chosen_log_probability == pytest.approx(
        step.reference_chosen_log_probability
    )
    assert step.policy_rejected_log_probability == pytest.approx(
        step.reference_rejected_log_probability
    )
    assert step.chosen_response_prediction_count == 2
    assert step.rejected_response_prediction_count == 2
    assert step.adapter_gradient_norm_before_clipping > 0.0
    assert execution.audit.initialization.policy_and_reference_start_identically
    assert execution.audit.initialization.compared_pair_count == 1
    assert execution.audit.optimizer_isolation.exact_adapter_only_membership
    assert execution.audit.parameter_state.frozen_state_exactly_unchanged
    assert execution.audit.parameter_state.adapter_state_changed
    assert execution.audit.adapter_round_trip.adapter_state_exactly_reloaded
    assert execution.audit.adapter_round_trip.probe_logits_exactly_equal


def test_selection_rejects_duplicate_pair_ids() -> None:
    with pytest.raises(ValueError, match="ids must be unique"):
        select_dpo_training_pairs([_record(), _record()])
