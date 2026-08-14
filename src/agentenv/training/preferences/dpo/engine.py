from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import peft
import torch
import transformers

from agentenv.hashing import hash_json
from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.training.lora.model import (
    audit_lora_adapter_round_trip,
    persist_lora_adapter,
)
from agentenv.training.lora.runtime import (
    build_probe_input_ids,
    configure_model_for_inference,
    configure_model_for_training,
    notify_stage,
    release_accelerator_memory,
    resolve_training_device,
    set_training_determinism,
)
from agentenv.training.lora.state import (
    LoRATrainingState,
    apply_lora_optimizer_step,
    build_parameter_state_audit,
    get_adapter_parameters,
    get_frozen_parameters,
    get_model_logits,
    hash_named_tensors,
    initialize_lora_training_state,
)
from agentenv.training.preferences.dpo.objective import (
    ResponseLogProbability,
    compute_dpo_loss,
    compute_response_log_probability,
)
from agentenv.training.preferences.dpo.schema import (
    DPOInitializationAudit,
    DPOLoRATrainingAudit,
    DPOLoRATrainingConfig,
    DPOLoRATrainingStepRecord,
    SelectedDPOTrainingPair,
)
from agentenv.training.preferences.materialization.schema import (
    CompletedDPOTrainingMaterializationRecord,
    DPOTrainingMaterializationRecord,
)


@dataclass(frozen=True)
class SelectedDPOPair:
    provenance: SelectedDPOTrainingPair
    record: CompletedDPOTrainingMaterializationRecord


@dataclass(frozen=True)
class _ReferencePairLogProbabilities:
    chosen: float
    rejected: float


@dataclass(frozen=True)
class _ReferenceCache:
    adapter_state_hash: str
    frozen_state_hash: str
    pairs: dict[str, _ReferencePairLogProbabilities]


@dataclass(frozen=True)
class DPOLoRATrainingExecution:
    selected_pairs: tuple[SelectedDPOTrainingPair, ...]
    steps: tuple[DPOLoRATrainingStepRecord, ...]
    audit: DPOLoRATrainingAudit


def select_dpo_training_pairs(
    records: Sequence[DPOTrainingMaterializationRecord],
) -> tuple[SelectedDPOPair, ...]:
    completed = [record for record in records if record.status == "completed"]
    if not completed:
        raise ValueError("authorized materializations contain no completed DPO pairs")
    pair_ids = [record.source_preference_pair_id for record in completed]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("selected DPO preference-pair ids must be unique")

    return tuple(
        SelectedDPOPair(
            provenance=SelectedDPOTrainingPair(
                source_preference_pair_id=record.source_preference_pair_id,
                source_materialization_record_hash=hash_json(
                    record.model_dump(mode="json")
                ),
                chosen_sequence_length=record.chosen_sequence_length,
                chosen_response_token_count=record.chosen_response_token_count,
                rejected_sequence_length=record.rejected_sequence_length,
                rejected_response_token_count=record.rejected_response_token_count,
            ),
            record=record,
        )
        for record in completed
    )


def execute_dpo_lora_training(
    *,
    load_base_model: Callable[[], transformers.PreTrainedModel],
    parent_adapter_dir: Path,
    base_model_pin: HuggingFaceRevisionPin,
    expected_parent_adapter_state_hash: str,
    expected_parent_frozen_state_hash: str,
    selected_pairs: Sequence[SelectedDPOPair],
    config: DPOLoRATrainingConfig,
    adapter_dir: Path,
    on_stage: Callable[[str], None] | None = None,
    on_step: Callable[[DPOLoRATrainingStepRecord], None] | None = None,
) -> DPOLoRATrainingExecution:
    if not selected_pairs:
        raise ValueError("DPO training requires at least one selected pair")
    device = resolve_training_device(config.runtime)
    set_training_determinism(config.seed)
    scheduled_pairs = tuple(
        selected_pairs[index % len(selected_pairs)] for index in range(config.max_steps)
    )

    notify_stage(on_stage, "reference_model_loading")
    reference_base = load_base_model()
    reference_model: Any = peft.PeftModel.from_pretrained(
        reference_base,
        parent_adapter_dir,
        is_trainable=False,
    )
    _configure_model(reference_model, config=config, trainable=False)
    reference_model.to(device)
    reference_cache = _build_reference_cache(
        reference_model,
        scheduled_pairs=scheduled_pairs,
        expected_parent_adapter_state_hash=expected_parent_adapter_state_hash,
        expected_parent_frozen_state_hash=expected_parent_frozen_state_hash,
        device=device,
    )
    del reference_model, reference_base
    release_accelerator_memory(device)

    notify_stage(on_stage, "policy_model_loading")
    policy_base = load_base_model()
    policy_model: Any = peft.PeftModel.from_pretrained(
        policy_base,
        parent_adapter_dir,
        is_trainable=True,
    )
    _configure_model(policy_model, config=config, trainable=True)
    policy_model.to(device)
    training = initialize_lora_training_state(policy_model, config.optimizer)
    del policy_model
    if training.adapter_state_hash_before != expected_parent_adapter_state_hash:
        raise ValueError("trainable DPO policy adapter does not match parent state")
    if training.frozen_state_hash_before != expected_parent_frozen_state_hash:
        raise ValueError("trainable DPO policy frozen state does not match parent")

    initialization = _build_initialization_audit(
        training.model,
        scheduled_pairs=scheduled_pairs,
        reference_cache=reference_cache,
        expected_parent_adapter_state_hash=expected_parent_adapter_state_hash,
        expected_parent_frozen_state_hash=expected_parent_frozen_state_hash,
        policy_adapter_state_hash=training.adapter_state_hash_before,
        policy_frozen_state_hash=training.frozen_state_hash_before,
        device=device,
    )

    notify_stage(on_stage, "training")
    training.model.train()
    steps: list[DPOLoRATrainingStepRecord] = []
    for step_index, selected in enumerate(scheduled_pairs):
        step = _execute_training_step(
            training=training,
            selected=selected,
            reference=reference_cache.pairs[
                selected.provenance.source_preference_pair_id
            ],
            step_index=step_index,
            config=config,
            device=device,
        )
        steps.append(step)
        if on_step is not None:
            on_step(step)

    notify_stage(on_stage, "verification")
    parameter_state = build_parameter_state_audit(
        frozen=training.frozen,
        frozen_state_hash_before=training.frozen_state_hash_before,
        adapters=training.adapters,
        adapter_state_hash_before=training.adapter_state_hash_before,
    )
    probe_ids = build_probe_input_ids(
        scheduled_pairs[0].record.chosen_input_ids,
        token_count=config.reload_probe_token_count,
        device=device,
    )
    notify_stage(on_stage, "adapter_persistence")
    persisted = persist_lora_adapter(
        model=training.model,
        adapters=training.adapters,
        frozen=training.frozen,
        probe_input_ids=probe_ids,
        adapter_dir=adapter_dir,
        base_model=base_model_pin,
    )
    optimizer_isolation = training.optimizer_isolation
    del training, policy_base
    release_accelerator_memory(device)

    notify_stage(on_stage, "adapter_reload")
    adapter_round_trip = audit_lora_adapter_round_trip(
        persisted=persisted,
        adapter_dir=adapter_dir,
        base_model=base_model_pin,
        load_base_model=load_base_model,
        probe_input_ids=probe_ids,
        device=device,
    )

    return DPOLoRATrainingExecution(
        selected_pairs=tuple(item.provenance for item in selected_pairs),
        steps=tuple(steps),
        audit=DPOLoRATrainingAudit(
            initialization=initialization,
            optimizer_isolation=optimizer_isolation,
            parameter_state=parameter_state,
            adapter_round_trip=adapter_round_trip,
        ),
    )


def _build_reference_cache(
    model: Any,
    *,
    scheduled_pairs: Sequence[SelectedDPOPair],
    expected_parent_adapter_state_hash: str,
    expected_parent_frozen_state_hash: str,
    device: torch.device,
) -> _ReferenceCache:
    adapters = get_adapter_parameters(model)
    frozen = get_frozen_parameters(model)
    adapter_hash_before = hash_named_tensors(adapters)
    frozen_hash_before = hash_named_tensors(frozen)
    if adapter_hash_before != expected_parent_adapter_state_hash:
        raise ValueError("frozen DPO reference adapter does not match parent state")
    if frozen_hash_before != expected_parent_frozen_state_hash:
        raise ValueError("frozen DPO reference base does not match parent state")
    if any(parameter.requires_grad for parameter in model.parameters()):
        raise ValueError("DPO reference model must be completely frozen")

    by_id: dict[str, _ReferencePairLogProbabilities] = {}
    model.eval()
    with torch.inference_mode():
        for selected in scheduled_pairs:
            pair_id = selected.provenance.source_preference_pair_id
            if pair_id in by_id:
                continue
            chosen = _compute_branch_log_probability(
                model,
                input_ids=selected.record.chosen_input_ids,
                labels=selected.record.chosen_labels,
                expected_prediction_count=(selected.record.chosen_response_token_count),
                device=device,
            )
            rejected = _compute_branch_log_probability(
                model,
                input_ids=selected.record.rejected_input_ids,
                labels=selected.record.rejected_labels,
                expected_prediction_count=(
                    selected.record.rejected_response_token_count
                ),
                device=device,
            )
            by_id[pair_id] = _ReferencePairLogProbabilities(
                chosen=float(chosen.value.item()),
                rejected=float(rejected.value.item()),
            )
    if hash_named_tensors(adapters) != adapter_hash_before:
        raise ValueError("frozen DPO reference adapter changed during precomputation")
    if hash_named_tensors(frozen) != frozen_hash_before:
        raise ValueError("frozen DPO reference base changed during precomputation")
    return _ReferenceCache(
        adapter_state_hash=adapter_hash_before,
        frozen_state_hash=frozen_hash_before,
        pairs=by_id,
    )


def _build_initialization_audit(
    model: Any,
    *,
    scheduled_pairs: Sequence[SelectedDPOPair],
    reference_cache: _ReferenceCache,
    expected_parent_adapter_state_hash: str,
    expected_parent_frozen_state_hash: str,
    policy_adapter_state_hash: str,
    policy_frozen_state_hash: str,
    device: torch.device,
) -> DPOInitializationAudit:
    differences: list[float] = []
    model.eval()
    with torch.inference_mode():
        for selected in scheduled_pairs:
            reference = reference_cache.pairs[
                selected.provenance.source_preference_pair_id
            ]
            chosen = _compute_branch_log_probability(
                model,
                input_ids=selected.record.chosen_input_ids,
                labels=selected.record.chosen_labels,
                expected_prediction_count=(selected.record.chosen_response_token_count),
                device=device,
            )
            rejected = _compute_branch_log_probability(
                model,
                input_ids=selected.record.rejected_input_ids,
                labels=selected.record.rejected_labels,
                expected_prediction_count=(
                    selected.record.rejected_response_token_count
                ),
                device=device,
            )
            differences.extend(
                (
                    abs(float(chosen.value.item()) - reference.chosen),
                    abs(float(rejected.value.item()) - reference.rejected),
                )
            )
    maximum_difference = max(differences)
    if maximum_difference != 0.0:
        raise ValueError(
            "DPO policy and reference differ at step zero; "
            f"maximum_absolute_log_probability_difference={maximum_difference}"
        )
    return DPOInitializationAudit(
        expected_parent_adapter_state_hash=expected_parent_adapter_state_hash,
        reference_adapter_state_hash=reference_cache.adapter_state_hash,
        policy_adapter_state_hash_before=policy_adapter_state_hash,
        expected_parent_frozen_state_hash=expected_parent_frozen_state_hash,
        reference_frozen_state_hash=reference_cache.frozen_state_hash,
        policy_frozen_state_hash_before=policy_frozen_state_hash,
        compared_pair_count=len(reference_cache.pairs),
        maximum_absolute_log_probability_difference=maximum_difference,
        policy_and_reference_start_identically=True,
        reference_log_probabilities_precomputed_before_optimization=True,
    )


def _execute_training_step(
    *,
    training: LoRATrainingState,
    selected: SelectedDPOPair,
    reference: _ReferencePairLogProbabilities,
    step_index: int,
    config: DPOLoRATrainingConfig,
    device: torch.device,
) -> DPOLoRATrainingStepRecord:
    training.optimizer.zero_grad(set_to_none=True)
    training.model.train()
    with torch.no_grad():
        policy_chosen = _compute_branch_log_probability(
            training.model,
            input_ids=selected.record.chosen_input_ids,
            labels=selected.record.chosen_labels,
            expected_prediction_count=selected.record.chosen_response_token_count,
            device=device,
        )
        policy_rejected = _compute_branch_log_probability(
            training.model,
            input_ids=selected.record.rejected_input_ids,
            labels=selected.record.rejected_labels,
            expected_prediction_count=selected.record.rejected_response_token_count,
            device=device,
        )
    detached_chosen = policy_chosen.value.detach().clone().requires_grad_(True)
    detached_rejected = policy_rejected.value.detach().clone().requires_grad_(True)
    dpo_loss = compute_dpo_loss(
        policy_chosen_log_probability=detached_chosen,
        policy_rejected_log_probability=detached_rejected,
        reference_chosen_log_probability=torch.tensor(
            reference.chosen,
            dtype=torch.float32,
            device=device,
        ),
        reference_rejected_log_probability=torch.tensor(
            reference.rejected,
            dtype=torch.float32,
            device=device,
        ),
        beta=config.objective.beta,
    )
    chosen_scale, rejected_scale = torch.autograd.grad(
        dpo_loss.loss,
        (detached_chosen, detached_rejected),
    )
    _backward_branch(
        training.model,
        input_ids=selected.record.chosen_input_ids,
        labels=selected.record.chosen_labels,
        expected_prediction_count=selected.record.chosen_response_token_count,
        expected_log_probability=float(policy_chosen.value.item()),
        gradient_scale=chosen_scale,
        device=device,
    )
    _backward_branch(
        training.model,
        input_ids=selected.record.rejected_input_ids,
        labels=selected.record.rejected_labels,
        expected_prediction_count=selected.record.rejected_response_token_count,
        expected_log_probability=float(policy_rejected.value.item()),
        gradient_scale=rejected_scale,
        device=device,
    )
    gradient_norm = apply_lora_optimizer_step(
        training,
        max_gradient_norm=config.optimizer.max_gradient_norm,
    )
    return DPOLoRATrainingStepRecord(
        step_index=step_index,
        source_preference_pair_id=selected.provenance.source_preference_pair_id,
        source_materialization_record_hash=(
            selected.provenance.source_materialization_record_hash
        ),
        chosen_response_prediction_count=policy_chosen.prediction_count,
        rejected_response_prediction_count=policy_rejected.prediction_count,
        policy_chosen_log_probability=float(policy_chosen.value.item()),
        policy_rejected_log_probability=float(policy_rejected.value.item()),
        reference_chosen_log_probability=reference.chosen,
        reference_rejected_log_probability=reference.rejected,
        loss=float(dpo_loss.loss.detach().item()),
        chosen_reward=float(dpo_loss.chosen_reward.detach().item()),
        rejected_reward=float(dpo_loss.rejected_reward.detach().item()),
        reward_margin=float(dpo_loss.reward_margin.detach().item()),
        adapter_gradient_norm_before_clipping=gradient_norm,
    )


def _backward_branch(
    model: Any,
    *,
    input_ids: list[int],
    labels: list[int],
    expected_prediction_count: int,
    expected_log_probability: float,
    gradient_scale: torch.Tensor,
    device: torch.device,
) -> None:
    observed = _compute_branch_log_probability(
        model,
        input_ids=input_ids,
        labels=labels,
        expected_prediction_count=expected_prediction_count,
        device=device,
    )
    observed_value = float(observed.value.detach().item())
    if observed_value != expected_log_probability:
        raise ValueError(
            "DPO branch changed between coefficient and gradient forwards; "
            f"observed={observed_value}, expected={expected_log_probability}"
        )
    (observed.value * gradient_scale.detach()).backward()


def _compute_branch_log_probability(
    model: Any,
    *,
    input_ids: list[int],
    labels: list[int],
    expected_prediction_count: int,
    device: torch.device,
) -> ResponseLogProbability:
    batched_input_ids = torch.tensor([input_ids], dtype=torch.long, device=device)
    batched_labels = torch.tensor([labels], dtype=torch.long, device=device)
    outputs = model(
        input_ids=batched_input_ids,
        attention_mask=torch.ones_like(batched_input_ids),
        use_cache=False,
    )
    result = compute_response_log_probability(
        get_model_logits(outputs),
        batched_input_ids,
        batched_labels,
    )
    if result.prediction_count != expected_prediction_count:
        raise ValueError(
            "runtime DPO response prediction count differs from materialization"
        )
    return result


def _configure_model(
    model: Any,
    *,
    config: DPOLoRATrainingConfig,
    trainable: bool,
) -> None:
    for module in model.modules():
        if isinstance(module, torch.nn.Dropout):
            module.p = 0.0
    if trainable:
        configure_model_for_training(model, config.runtime)
        model.train()
    else:
        configure_model_for_inference(model)
