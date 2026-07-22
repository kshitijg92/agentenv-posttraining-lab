from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import torch
import transformers

from agentenv.training.positive_sft.lora import engine as lora_engine
from agentenv.training.positive_sft.lora.config import (
    load_positive_sft_lora_training_config,
)
from agentenv.training.positive_sft.lora.engine import (
    execute_lora_qualification,
    execute_positive_sft_lora_training,
    select_positive_sft_training_sequences,
)
from agentenv.training.positive_sft.lora.schema import (
    PositiveSFTLoRATrainingConfig,
)
from agentenv.training.positive_sft.materialization.schema import (
    CompletedPositiveSFTTrainingMaterializationRecord,
)


CONFIG_PATH = Path("configs/train/positive_sft_lora_smoke.yaml")


def _tiny_training_config(
    *,
    max_steps: int = 2,
    qualification_step_count: int = 2,
) -> PositiveSFTLoRATrainingConfig:
    payload = load_positive_sft_lora_training_config(CONFIG_PATH).model_dump(
        mode="json"
    )
    payload["base_model"] = {
        "repository_id": "tests/TinyQwen",
        "revision": "a" * 40,
    }
    payload["lora"]["rank"] = 2
    payload["runtime"] = {
        "device": "cpu",
        "weight_dtype": "float32",
        "attention_implementation": "eager",
        "gradient_checkpointing": False,
        "deterministic_algorithms": True,
        "cublas_workspace_config": ":4096:8",
    }
    payload["max_steps"] = max_steps
    payload["qualification_step_count"] = qualification_step_count
    payload["reload_probe_token_count"] = 4
    return PositiveSFTLoRATrainingConfig.model_validate(payload)


def _materialization_record() -> CompletedPositiveSFTTrainingMaterializationRecord:
    return CompletedPositiveSFTTrainingMaterializationRecord(
        source_positive_sft_example_id="positive_sft_example_aaaaaaaaaaaaaaaa",
        source_positive_sft_example_record_hash="xxh64:1111111111111111",
        model_input_protocol_id="qwen2_5_coder_3b_agentenv_json",
        model_input_protocol_hash="xxh64:2222222222222222",
        serialization_mode="completed_transcript",
        max_sequence_length=16,
        materializer_version="positive_sft_training_materializer_v0",
        materializer_code_hash="xxh64:3333333333333333",
        status="completed",
        input_ids=[1, 2, 3, 4, 5, 6],
        labels=[-100, -100, -100, 4, 5, 6],
        sequence_length=6,
        supervised_token_count=3,
        ignored_token_count=3,
    )


def _tiny_base_factory() -> Callable[[], transformers.PreTrainedModel]:
    torch.manual_seed(7)
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
    reference_model = transformers.Qwen2ForCausalLM(model_config)
    reference_state = {
        name: tensor.detach().clone()
        for name, tensor in reference_model.state_dict().items()
    }

    def load_base() -> transformers.PreTrainedModel:
        model = transformers.Qwen2ForCausalLM(model_config)
        model.load_state_dict(reference_state, strict=True)
        return model

    return load_base


def test_tiny_qwen_lora_run_proves_training_invariants(tmp_path: Path) -> None:
    config = _tiny_training_config()
    record = _materialization_record()
    selected = select_positive_sft_training_sequences(
        [record],
        max_examples=config.data.max_examples,
    )
    base_factory = _tiny_base_factory()
    qualification = execute_lora_qualification(
        base_model=base_factory(),
        selected_sequences=selected,
        config=config,
    )

    execution = execute_positive_sft_lora_training(
        base_model=base_factory(),
        reload_base_model=base_factory,
        selected_sequences=selected,
        qualification=qualification,
        config=config,
        adapter_dir=tmp_path / "adapter",
    )

    assert len(execution.steps) == 2
    assert all(step.supervised_prediction_count == 3 for step in execution.steps)
    assert all(step.ignored_prediction_count == 2 for step in execution.steps)
    assert execution.optimizer_isolation.exact_adapter_only_membership is True
    assert execution.parameter_state.frozen_state_exactly_unchanged is True
    assert execution.parameter_state.adapter_state_changed is True
    assert qualification.adapter_qualification.qualification_step_count == 2
    assert qualification.adapter_qualification.intended_logical_adapter_count == 8
    assert all(
        row.parameter_changed_during_qualification
        for row in qualification.adapter_qualification.parameters
        if row.factor == "B"
    )
    assert (
        execution.parameter_state.adapter_state_hash_before
        == qualification.parameter_state.adapter_state_hash_before
    )
    assert (
        execution.parameter_state.frozen_state_hash_before
        == qualification.parameter_state.frozen_state_hash_before
    )
    assert execution.adapter_round_trip.adapter_state_exactly_reloaded is True
    assert execution.adapter_round_trip.frozen_base_state_exactly_reloaded is True
    assert execution.adapter_round_trip.probe_logits_exactly_equal is True
    assert execution.adapter_round_trip.maximum_absolute_logit_difference == 0.0


def test_training_restarts_at_step_zero_without_detailed_gradient_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _tiny_training_config(max_steps=1, qualification_step_count=2)
    selected = select_positive_sft_training_sequences(
        [_materialization_record()],
        max_examples=config.data.max_examples,
    )
    base_factory = _tiny_base_factory()
    observed_step_count = 0
    original_observe = lora_engine.AdapterQualificationTracker.observe

    def count_observation(*args: Any, **kwargs: Any) -> None:
        nonlocal observed_step_count
        observed_step_count += 1
        original_observe(*args, **kwargs)

    monkeypatch.setattr(
        lora_engine.AdapterQualificationTracker,
        "observe",
        count_observation,
    )

    qualification = execute_lora_qualification(
        base_model=base_factory(),
        selected_sequences=selected,
        config=config,
    )
    execution = execute_positive_sft_lora_training(
        base_model=base_factory(),
        reload_base_model=base_factory,
        selected_sequences=selected,
        qualification=qualification,
        config=config,
        adapter_dir=tmp_path / "adapter",
    )

    assert len(execution.steps) == 1
    assert [step.step_index for step in execution.steps] == [0]
    assert qualification.adapter_qualification.qualification_step_count == 2
    assert observed_step_count == 2


def test_selection_rejects_unreachable_supervised_first_label() -> None:
    payload: dict[str, Any] = _materialization_record().model_dump(mode="json")
    payload["labels"][0] = payload["input_ids"][0]
    payload["supervised_token_count"] = 4
    payload["ignored_token_count"] = 2
    record = CompletedPositiveSFTTrainingMaterializationRecord.model_validate(payload)

    try:
        select_positive_sft_training_sequences([record], max_examples=1)
    except ValueError as exc:
        assert "first sequence label is unreachable" in str(exc)
    else:
        raise AssertionError("unreachable first label was accepted")
