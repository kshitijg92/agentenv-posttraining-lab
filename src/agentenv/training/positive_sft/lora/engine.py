from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import peft
import torch
import transformers

from agentenv.hashing import hash_json
from agentenv.training.lora.model import (
    audit_lora_adapter_round_trip,
    persist_lora_adapter,
)
from agentenv.training.lora.runtime import (
    build_probe_input_ids,
    configure_model_for_training,
    notify_stage,
    release_accelerator_memory,
    resolve_training_device,
    set_training_determinism,
)
from agentenv.training.lora.schema import (
    AdapterRoundTripAudit,
    OptimizerIsolationAudit,
    ParameterStateAudit,
)
from agentenv.training.lora.state import (
    LoRATrainingState,
    apply_lora_optimizer_step,
    build_parameter_state_audit,
    get_model_logits,
    initialize_lora_training_state,
    snapshot_parameter_state,
)
from agentenv.training.positive_sft.lora.objective import (
    MaskedCausalLoss,
    compute_masked_causal_lm_loss,
)
from agentenv.training.positive_sft.lora.schema import (
    PositiveSFTLoRAQualificationResult,
    PositiveSFTLoRATrainingConfig,
    PositiveSFTLoRATrainingStepRecord,
    SelectedPositiveSFTTrainingExample,
)
from agentenv.training.positive_sft.lora.state import (
    AdapterQualificationTracker,
    enumerate_intended_lora_modules,
)
from agentenv.training.positive_sft.materialization.schema import (
    TRAINER_IGNORE_INDEX,
    CompletedPositiveSFTTrainingMaterializationRecord,
    PositiveSFTTrainingMaterializationRecord,
)


@dataclass(frozen=True)
class SelectedTrainingSequence:
    provenance: SelectedPositiveSFTTrainingExample
    record: CompletedPositiveSFTTrainingMaterializationRecord


@dataclass(frozen=True)
class PositiveSFTLoRATrainingExecution:
    selected_examples: tuple[SelectedPositiveSFTTrainingExample, ...]
    steps: tuple[PositiveSFTLoRATrainingStepRecord, ...]
    optimizer_isolation: OptimizerIsolationAudit
    parameter_state: ParameterStateAudit
    adapter_round_trip: AdapterRoundTripAudit


def select_positive_sft_training_sequences(
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
) -> tuple[SelectedTrainingSequence, ...]:
    completed_records = [record for record in records if record.status == "completed"]
    if not completed_records:
        raise ValueError("authorized materialization contains no completed SFT rows")

    example_ids = [
        record.source_positive_sft_example_id for record in completed_records
    ]
    if len(example_ids) != len(set(example_ids)):
        raise ValueError("selected positive-SFT example ids must be unique")

    selected: list[SelectedTrainingSequence] = []
    for record in completed_records:
        if record.labels[0] != TRAINER_IGNORE_INDEX:
            raise ValueError(
                "the first sequence label is unreachable by shifted causal loss and "
                "must be ignored"
            )
        effective_supervised_count = sum(
            label != TRAINER_IGNORE_INDEX for label in record.labels[1:]
        )
        ignored_prediction_count = (
            record.sequence_length - 1 - effective_supervised_count
        )
        provenance = SelectedPositiveSFTTrainingExample(
            source_positive_sft_example_id=record.source_positive_sft_example_id,
            source_materialization_record_hash=hash_json(
                record.model_dump(mode="json")
            ),
            sequence_length=record.sequence_length,
            stored_supervised_token_count=record.supervised_token_count,
            effective_shifted_supervised_token_count=effective_supervised_count,
            ignored_prediction_count=ignored_prediction_count,
        )
        selected.append(SelectedTrainingSequence(provenance=provenance, record=record))
    return tuple(selected)


def execute_lora_qualification(
    *,
    base_model: transformers.PreTrainedModel,
    selected_sequences: Sequence[SelectedTrainingSequence],
    config: PositiveSFTLoRATrainingConfig,
    on_stage: Callable[[str], None] | None = None,
) -> PositiveSFTLoRAQualificationResult:
    if not selected_sequences:
        raise ValueError("LoRA qualification requires selected sequences")
    device = resolve_training_device(config.runtime)
    intended_logical_adapters = enumerate_intended_lora_modules(
        base_model,
        config.lora.target_modules,
    )
    notify_stage(on_stage, "qualification")
    initialized = _initialize_lora_training(
        base_model=base_model,
        config=config,
        device=device,
    )
    initial_adapter_state = snapshot_parameter_state(initialized.adapters)
    qualification_tracker = AdapterQualificationTracker(initialized.adapters)

    steps: list[PositiveSFTLoRATrainingStepRecord] = []
    initialized.model.train()
    for step_index in range(config.qualification_step_count):
        selected = selected_sequences[step_index % len(selected_sequences)]
        masked_loss = _compute_loss_and_backward(
            initialized=initialized,
            selected=selected,
            device=device,
        )
        qualification_tracker.observe(initialized.adapters)
        steps.append(
            _apply_optimizer_step(
                initialized=initialized,
                selected=selected,
                masked_loss=masked_loss,
                step_index=step_index,
                config=config,
            )
        )

    adapter_qualification = qualification_tracker.build_audit(
        qualification_step_count=config.qualification_step_count,
        intended_logical_adapters=intended_logical_adapters,
        adapter_parameters=initialized.adapters,
        initial_adapter_state=initial_adapter_state,
    )
    parameter_state = build_parameter_state_audit(
        frozen=initialized.frozen,
        frozen_state_hash_before=initialized.frozen_state_hash_before,
        adapters=initialized.adapters,
        adapter_state_hash_before=initialized.adapter_state_hash_before,
    )
    result = PositiveSFTLoRAQualificationResult(
        steps=tuple(steps),
        optimizer_isolation=initialized.optimizer_isolation,
        adapter_qualification=adapter_qualification,
        parameter_state=parameter_state,
    )
    del qualification_tracker, initial_adapter_state, initialized, base_model
    release_accelerator_memory(device)
    return result


def execute_positive_sft_lora_training(
    *,
    base_model: transformers.PreTrainedModel,
    reload_base_model: Callable[[], transformers.PreTrainedModel],
    selected_sequences: Sequence[SelectedTrainingSequence],
    qualification: PositiveSFTLoRAQualificationResult,
    config: PositiveSFTLoRATrainingConfig,
    adapter_dir: Path,
    on_stage: Callable[[str], None] | None = None,
    on_step: Callable[[PositiveSFTLoRATrainingStepRecord], None] | None = None,
) -> PositiveSFTLoRATrainingExecution:
    if not selected_sequences:
        raise ValueError("LoRA training requires at least one selected sequence")
    if (
        qualification.adapter_qualification.qualification_step_count
        != config.qualification_step_count
    ):
        raise ValueError("qualification step count differs from training config")
    device = resolve_training_device(config.runtime)

    notify_stage(on_stage, "adapter_initialization")
    initialized = _initialize_lora_training(
        base_model=base_model,
        config=config,
        device=device,
    )
    if (
        initialized.adapter_state_hash_before
        != qualification.parameter_state.adapter_state_hash_before
    ):
        raise ValueError(
            "fresh training adapter initialization differs from qualification"
        )
    if (
        initialized.frozen_state_hash_before
        != qualification.parameter_state.frozen_state_hash_before
    ):
        raise ValueError("fresh training base state differs from qualification")
    if initialized.optimizer_isolation != qualification.optimizer_isolation:
        raise ValueError("fresh training optimizer differs from qualification")

    steps: list[PositiveSFTLoRATrainingStepRecord] = []
    notify_stage(on_stage, "training")
    initialized.model.train()
    for step_index in range(config.max_steps):
        selected = selected_sequences[step_index % len(selected_sequences)]
        masked_loss = _compute_loss_and_backward(
            initialized=initialized,
            selected=selected,
            device=device,
        )
        step_record = _apply_optimizer_step(
            initialized=initialized,
            selected=selected,
            masked_loss=masked_loss,
            step_index=step_index,
            config=config,
        )
        steps.append(step_record)
        if on_step is not None:
            on_step(step_record)

    notify_stage(on_stage, "verification")
    parameter_state = build_parameter_state_audit(
        frozen=initialized.frozen,
        frozen_state_hash_before=initialized.frozen_state_hash_before,
        adapters=initialized.adapters,
        adapter_state_hash_before=initialized.adapter_state_hash_before,
    )

    probe_ids = build_probe_input_ids(
        selected_sequences[0].record.input_ids,
        token_count=config.reload_probe_token_count,
        device=device,
    )
    notify_stage(on_stage, "adapter_persistence")
    persisted = persist_lora_adapter(
        model=initialized.model,
        adapters=initialized.adapters,
        frozen=initialized.frozen,
        probe_input_ids=probe_ids,
        adapter_dir=adapter_dir,
        base_model=config.base_model,
    )

    optimizer_isolation = initialized.optimizer_isolation
    del initialized, base_model
    release_accelerator_memory(device)

    notify_stage(on_stage, "adapter_reload")
    adapter_round_trip = audit_lora_adapter_round_trip(
        persisted=persisted,
        adapter_dir=adapter_dir,
        base_model=config.base_model,
        load_base_model=reload_base_model,
        probe_input_ids=probe_ids,
        device=device,
    )

    return PositiveSFTLoRATrainingExecution(
        selected_examples=tuple(item.provenance for item in selected_sequences),
        steps=tuple(steps),
        optimizer_isolation=optimizer_isolation,
        parameter_state=parameter_state,
        adapter_round_trip=adapter_round_trip,
    )


def _initialize_lora_training(
    *,
    base_model: transformers.PreTrainedModel,
    config: PositiveSFTLoRATrainingConfig,
    device: torch.device,
) -> LoRATrainingState:
    set_training_determinism(config.seed)
    model: Any = peft.get_peft_model(base_model, _build_peft_lora_config(config))
    _set_peft_adapter_model_pin(model, config=config)
    configure_model_for_training(model, config.runtime)
    model.to(device)
    return initialize_lora_training_state(model, config.optimizer)


def _compute_loss_and_backward(
    *,
    initialized: LoRATrainingState,
    selected: SelectedTrainingSequence,
    device: torch.device,
) -> MaskedCausalLoss:
    input_ids, labels, attention_mask = _build_sequence_tensors(
        selected.record,
        device=device,
    )
    initialized.optimizer.zero_grad(set_to_none=True)
    outputs = initialized.model(
        input_ids=input_ids,
        attention_mask=attention_mask,
        use_cache=False,
    )
    masked_loss = compute_masked_causal_lm_loss(
        get_model_logits(outputs),
        labels,
    )
    if (
        masked_loss.supervised_prediction_count
        != selected.provenance.effective_shifted_supervised_token_count
    ):
        raise ValueError(
            "runtime supervised prediction count differs from source accounting"
        )
    if (
        masked_loss.ignored_prediction_count
        != selected.provenance.ignored_prediction_count
    ):
        raise ValueError(
            "runtime ignored prediction count differs from source accounting"
        )
    masked_loss.loss.backward()
    return masked_loss


def _apply_optimizer_step(
    *,
    initialized: LoRATrainingState,
    selected: SelectedTrainingSequence,
    masked_loss: MaskedCausalLoss,
    step_index: int,
    config: PositiveSFTLoRATrainingConfig,
) -> PositiveSFTLoRATrainingStepRecord:
    gradient_norm_before_clipping = apply_lora_optimizer_step(
        initialized,
        max_gradient_norm=config.optimizer.max_gradient_norm,
    )
    return PositiveSFTLoRATrainingStepRecord(
        step_index=step_index,
        source_positive_sft_example_id=(
            selected.provenance.source_positive_sft_example_id
        ),
        source_materialization_record_hash=(
            selected.provenance.source_materialization_record_hash
        ),
        sequence_length=selected.provenance.sequence_length,
        supervised_prediction_count=masked_loss.supervised_prediction_count,
        ignored_prediction_count=masked_loss.ignored_prediction_count,
        loss=float(masked_loss.loss.detach().item()),
        adapter_gradient_norm_before_clipping=gradient_norm_before_clipping,
    )


def _build_peft_lora_config(
    config: PositiveSFTLoRATrainingConfig,
) -> peft.LoraConfig:
    return peft.LoraConfig(
        task_type=peft.TaskType.CAUSAL_LM,
        inference_mode=False,
        r=config.lora.rank,
        lora_alpha=config.lora.alpha,
        lora_dropout=config.lora.dropout,
        target_modules=list(config.lora.target_modules),
        bias=config.lora.bias,
        use_rslora=config.lora.use_rslora,
        use_dora=config.lora.use_dora,
        init_lora_weights=config.lora.init_lora_weights,
    )


def _set_peft_adapter_model_pin(
    model: Any,
    *,
    config: PositiveSFTLoRATrainingConfig,
) -> None:
    if set(model.peft_config) != {"default"}:
        raise ValueError("ordinary LoRA training requires exactly the default adapter")
    adapter_config = model.peft_config["default"]
    adapter_config.base_model_name_or_path = config.base_model.repository_id
    adapter_config.revision = config.base_model.revision


def _build_sequence_tensors(
    record: CompletedPositiveSFTTrainingMaterializationRecord,
    *,
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Batch and move one materialized sequence without causal shifting."""
    input_ids = torch.tensor([record.input_ids], dtype=torch.long, device=device)
    labels = torch.tensor([record.labels], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(input_ids)
    return input_ids, labels, attention_mask
