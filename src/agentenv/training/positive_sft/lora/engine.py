from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import gc
from pathlib import Path
from typing import Any

import peft
import torch
import transformers

from agentenv.hashing import hash_directory, hash_json
from agentenv.training.positive_sft.lora.model import finalize_lora_adapter_package
from agentenv.training.positive_sft.lora.objective import (
    MaskedCausalLoss,
    compute_masked_causal_lm_loss,
)
from agentenv.training.positive_sft.lora.schema import (
    AdapterRoundTripAudit,
    OptimizerIsolationAudit,
    ParameterStateAudit,
    PositiveSFTLoRAQualificationResult,
    PositiveSFTLoRATrainingConfig,
    PositiveSFTLoRATrainingStepRecord,
    SelectedPositiveSFTTrainingExample,
)
from agentenv.training.positive_sft.lora.state import (
    AdapterQualificationTracker,
    build_parameter_state_audit,
    enumerate_intended_lora_modules,
    get_adapter_parameters,
    get_frozen_parameters,
    get_model_logits,
    hash_named_tensors,
    hash_tensor,
    require_only_adapters_trainable,
    snapshot_parameter_state,
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


@dataclass
class _InitializedLoRATraining:
    model: Any
    adapters: dict[str, torch.nn.Parameter]
    frozen: dict[str, torch.nn.Parameter]
    optimizer: torch.optim.Optimizer
    optimizer_isolation: OptimizerIsolationAudit
    intended_logical_adapters: frozenset[str]
    adapter_state_hash_before: str
    frozen_state_hash_before: str


def select_positive_sft_training_sequences(
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
    *,
    max_examples: int,
) -> tuple[SelectedTrainingSequence, ...]:
    completed_records = [record for record in records if record.status == "completed"]
    selected_records = completed_records[:max_examples]
    if not selected_records:
        raise ValueError("authorized materialization contains no completed SFT rows")

    example_ids = [record.source_positive_sft_example_id for record in selected_records]
    if len(example_ids) != len(set(example_ids)):
        raise ValueError("selected positive-SFT example ids must be unique")

    selected: list[SelectedTrainingSequence] = []
    for record in selected_records:
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
    device = _resolve_device(config)
    _notify_stage(on_stage, "qualification")
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
        intended_logical_adapters=initialized.intended_logical_adapters,
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
    _release_accelerator_memory(device)
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
    device = _resolve_device(config)

    _notify_stage(on_stage, "adapter_initialization")
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
    _notify_stage(on_stage, "training")
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

    _notify_stage(on_stage, "verification")
    parameter_state = build_parameter_state_audit(
        frozen=initialized.frozen,
        frozen_state_hash_before=initialized.frozen_state_hash_before,
        adapters=initialized.adapters,
        adapter_state_hash_before=initialized.adapter_state_hash_before,
    )

    probe_ids = _build_probe_input_ids(
        selected_sequences[0].record,
        token_count=config.reload_probe_token_count,
        device=device,
    )
    trained_probe_logits = _get_last_token_logits(initialized.model, probe_ids)
    trained_adapter_state_hash = hash_named_tensors(initialized.adapters)
    trained_frozen_state_hash = hash_named_tensors(initialized.frozen)

    _notify_stage(on_stage, "adapter_persistence")
    if adapter_dir.exists() and any(adapter_dir.iterdir()):
        raise ValueError(f"Adapter output directory is not empty: {adapter_dir}")
    adapter_dir.mkdir(parents=True, exist_ok=True)
    initialized.model.save_pretrained(
        str(adapter_dir),
        safe_serialization=True,
        save_embedding_layers=False,
    )
    finalize_lora_adapter_package(adapter_dir, base_model=config.base_model)
    persisted_adapter_directory_hash = hash_directory(adapter_dir)

    optimizer_isolation = initialized.optimizer_isolation
    del initialized, base_model
    _release_accelerator_memory(device)

    _notify_stage(on_stage, "adapter_reload")
    reloaded_base = reload_base_model()
    reloaded_model: Any = peft.PeftModel.from_pretrained(
        reloaded_base,
        adapter_dir,
        is_trainable=False,
    )
    _configure_model_for_inference(reloaded_model)
    reloaded_model.to(device)
    reloaded_adapters = get_adapter_parameters(reloaded_model)
    reloaded_frozen = get_frozen_parameters(reloaded_model)
    reloaded_adapter_state_hash = hash_named_tensors(reloaded_adapters)
    reloaded_frozen_state_hash = hash_named_tensors(reloaded_frozen)
    if reloaded_adapter_state_hash != trained_adapter_state_hash:
        raise ValueError("reloaded LoRA adapter state differs from trained state")
    if reloaded_frozen_state_hash != trained_frozen_state_hash:
        raise ValueError("reloaded frozen base state differs from trained base state")

    reloaded_probe_logits = _get_last_token_logits(reloaded_model, probe_ids)
    maximum_absolute_logit_difference = float(
        (trained_probe_logits.float() - reloaded_probe_logits.float())
        .abs()
        .max()
        .item()
    )
    probe_logits_equal = torch.equal(trained_probe_logits, reloaded_probe_logits)
    if not probe_logits_equal:
        raise ValueError(
            "reloaded adapter does not reproduce exact fixed-input probe logits; "
            f"maximum_absolute_difference={maximum_absolute_logit_difference}"
        )

    adapter_round_trip = AdapterRoundTripAudit(
        persisted_adapter_directory_hash=persisted_adapter_directory_hash,
        trained_frozen_state_hash=trained_frozen_state_hash,
        reloaded_frozen_state_hash=reloaded_frozen_state_hash,
        frozen_base_state_exactly_reloaded=True,
        trained_adapter_state_hash=trained_adapter_state_hash,
        reloaded_adapter_state_hash=reloaded_adapter_state_hash,
        adapter_state_exactly_reloaded=True,
        probe_token_count=probe_ids.shape[1],
        trained_probe_logits_hash=hash_tensor(trained_probe_logits),
        reloaded_probe_logits_hash=hash_tensor(reloaded_probe_logits),
        maximum_absolute_logit_difference=maximum_absolute_logit_difference,
        probe_logits_exactly_equal=True,
    )
    del reloaded_adapters, reloaded_frozen, reloaded_model, reloaded_base
    _release_accelerator_memory(device)

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
) -> _InitializedLoRATraining:
    _set_training_determinism(config.seed)
    intended_logical_adapters = enumerate_intended_lora_modules(
        base_model,
        config.lora.target_modules,
    )
    model: Any = peft.get_peft_model(base_model, _build_peft_lora_config(config))
    _set_peft_adapter_model_pin(model, config=config)
    _configure_model_for_training(model, config=config)
    model.to(device)

    adapters = get_adapter_parameters(model)
    frozen = get_frozen_parameters(model)
    adapter_state_hash_before = hash_named_tensors(adapters)
    frozen_state_hash_before = hash_named_tensors(frozen)
    optimizer = torch.optim.AdamW(
        list(adapters.values()),
        lr=config.optimizer.learning_rate,
        betas=(config.optimizer.beta1, config.optimizer.beta2),
        eps=config.optimizer.epsilon,
        weight_decay=config.optimizer.weight_decay,
        amsgrad=False,
        foreach=False,
        fused=False,
    )
    optimizer_isolation = require_only_adapters_trainable(model, optimizer)
    return _InitializedLoRATraining(
        model=model,
        adapters=adapters,
        frozen=frozen,
        optimizer=optimizer,
        optimizer_isolation=optimizer_isolation,
        intended_logical_adapters=intended_logical_adapters,
        adapter_state_hash_before=adapter_state_hash_before,
        frozen_state_hash_before=frozen_state_hash_before,
    )


def _compute_loss_and_backward(
    *,
    initialized: _InitializedLoRATraining,
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
    initialized: _InitializedLoRATraining,
    selected: SelectedTrainingSequence,
    masked_loss: MaskedCausalLoss,
    step_index: int,
    config: PositiveSFTLoRATrainingConfig,
) -> PositiveSFTLoRATrainingStepRecord:
    gradient_norm_before_clipping = torch.nn.utils.clip_grad_norm_(
        list(initialized.adapters.values()),
        max_norm=config.optimizer.max_gradient_norm,
        error_if_nonfinite=True,
        foreach=False,
    )
    initialized.optimizer.step()
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
        adapter_gradient_norm_before_clipping=float(
            gradient_norm_before_clipping.detach().item()
        ),
    )


def _release_accelerator_memory(device: torch.device) -> None:
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()


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


def _configure_model_for_training(
    model: Any,
    *,
    config: PositiveSFTLoRATrainingConfig,
) -> None:
    model.config.use_cache = False
    if config.runtime.gradient_checkpointing:
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
        model.enable_input_require_grads()


def _configure_model_for_inference(model: Any) -> None:
    model.config.use_cache = False
    model.eval()


def _resolve_device(config: PositiveSFTLoRATrainingConfig) -> torch.device:
    if config.runtime.device == "cuda" and not torch.cuda.is_available():
        raise ValueError("training config requires CUDA, but CUDA is unavailable")
    return torch.device(config.runtime.device)


def _set_training_determinism(seed: int) -> None:
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)


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


def _build_probe_input_ids(
    record: CompletedPositiveSFTTrainingMaterializationRecord,
    *,
    token_count: int,
    device: torch.device,
) -> torch.Tensor:
    selected_count = min(token_count, record.sequence_length)
    return torch.tensor(
        [record.input_ids[:selected_count]],
        dtype=torch.long,
        device=device,
    )


def _get_last_token_logits(model: Any, input_ids: torch.Tensor) -> torch.Tensor:
    model.eval()
    with torch.inference_mode():
        outputs = model(
            input_ids=input_ids,
            attention_mask=torch.ones_like(input_ids),
            use_cache=False,
        )
    return get_model_logits(outputs)[:, -1, :].detach().cpu().clone()


def _notify_stage(on_stage: Callable[[str], None] | None, stage: str) -> None:
    if on_stage is not None:
        on_stage(stage)
