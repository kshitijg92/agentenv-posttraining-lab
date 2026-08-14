from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from typing import Any, Literal, cast

import torch
import xxhash

from agentenv.hashing import hash_json
from agentenv.training.lora.schema import (
    OptimizerConfigRecord,
    OptimizerIsolationAudit,
    ParameterStateAudit,
)


_LORA_PARAMETER_RE = re.compile(
    r"^(?P<logical>.+)\.lora_(?P<factor>[AB])\.[^.]+\.weight$"
)
_PEFT_BASE_PREFIX = "base_model.model."


@dataclass
class LoRATrainingState:
    model: Any
    adapters: dict[str, torch.nn.Parameter]
    frozen: dict[str, torch.nn.Parameter]
    optimizer: torch.optim.Optimizer
    optimizer_isolation: OptimizerIsolationAudit
    adapter_state_hash_before: str
    frozen_state_hash_before: str


def initialize_lora_training_state(
    model: Any,
    optimizer_config: OptimizerConfigRecord,
) -> LoRATrainingState:
    adapters = get_adapter_parameters(model)
    frozen = get_frozen_parameters(model)
    optimizer = torch.optim.AdamW(
        list(adapters.values()),
        lr=optimizer_config.learning_rate,
        betas=(optimizer_config.beta1, optimizer_config.beta2),
        eps=optimizer_config.epsilon,
        weight_decay=optimizer_config.weight_decay,
        amsgrad=False,
        foreach=False,
        fused=False,
    )
    return LoRATrainingState(
        model=model,
        adapters=adapters,
        frozen=frozen,
        optimizer=optimizer,
        optimizer_isolation=require_only_adapters_trainable(model, optimizer),
        adapter_state_hash_before=hash_named_tensors(adapters),
        frozen_state_hash_before=hash_named_tensors(frozen),
    )


def apply_lora_optimizer_step(
    training: LoRATrainingState,
    *,
    max_gradient_norm: float,
) -> float:
    gradient_norm = torch.nn.utils.clip_grad_norm_(
        list(training.adapters.values()),
        max_norm=max_gradient_norm,
        error_if_nonfinite=True,
        foreach=False,
    )
    training.optimizer.step()
    return float(gradient_norm.detach().item())


def get_adapter_parameters(
    model: torch.nn.Module,
) -> dict[str, torch.nn.Parameter]:
    parameters = {
        normalize_peft_parameter_name(name): parameter
        for name, parameter in model.named_parameters()
        if _LORA_PARAMETER_RE.fullmatch(normalize_peft_parameter_name(name))
    }
    if not parameters:
        raise ValueError("model contains no ordinary LoRA A/B parameters")
    return parameters


def get_frozen_parameters(
    model: torch.nn.Module,
) -> dict[str, torch.nn.Parameter]:
    adapters = set(get_adapter_parameters(model))
    return {
        normalize_peft_parameter_name(name): parameter
        for name, parameter in model.named_parameters()
        if normalize_peft_parameter_name(name) not in adapters
    }


def require_only_adapters_trainable(
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
) -> OptimizerIsolationAudit:
    adapters = get_adapter_parameters(model)
    trainable = {
        normalize_peft_parameter_name(name): parameter
        for name, parameter in model.named_parameters()
        if parameter.requires_grad
    }
    if set(trainable) != set(adapters):
        raise ValueError("trainable model parameters are not exactly LoRA parameters")

    optimizer_parameters = [
        parameter
        for parameter_group in optimizer.param_groups
        for parameter in parameter_group["params"]
    ]
    if len({id(parameter) for parameter in optimizer_parameters}) != len(
        optimizer_parameters
    ):
        raise ValueError("optimizer contains duplicate parameter references")
    optimizer_names_by_id = {
        id(parameter): name for name, parameter in trainable.items()
    }
    unknown_optimizer_parameters = [
        parameter
        for parameter in optimizer_parameters
        if id(parameter) not in optimizer_names_by_id
    ]
    if unknown_optimizer_parameters:
        raise ValueError("optimizer owns parameters outside the LoRA adapter set")
    optimizer_names = {
        optimizer_names_by_id[id(parameter)] for parameter in optimizer_parameters
    }
    if optimizer_names != set(trainable):
        raise ValueError(
            "optimizer does not own exactly every trainable LoRA parameter"
        )

    return OptimizerIsolationAudit(
        trainable_parameter_count=len(trainable),
        trainable_parameter_element_count=sum(
            parameter.numel() for parameter in trainable.values()
        ),
        optimizer_parameter_count=len(optimizer_parameters),
        optimizer_parameter_element_count=sum(
            parameter.numel() for parameter in optimizer_parameters
        ),
        trainable_parameter_names_hash=hash_json(sorted(trainable)),
        optimizer_parameter_names_hash=hash_json(sorted(optimizer_names)),
        exact_adapter_only_membership=True,
    )


def snapshot_parameter_state(
    parameters: Mapping[str, torch.nn.Parameter],
) -> dict[str, torch.Tensor]:
    return {
        name: parameter.detach().cpu().clone()
        for name, parameter in sorted(parameters.items())
    }


def build_parameter_state_audit(
    *,
    frozen: Mapping[str, torch.nn.Parameter],
    frozen_state_hash_before: str,
    adapters: Mapping[str, torch.nn.Parameter],
    adapter_state_hash_before: str,
) -> ParameterStateAudit:
    frozen_state_hash_after = hash_named_tensors(frozen)
    adapter_state_hash_after = hash_named_tensors(adapters)
    if frozen_state_hash_after != frozen_state_hash_before:
        raise ValueError("frozen base parameters changed during LoRA training")
    if adapter_state_hash_after == adapter_state_hash_before:
        raise ValueError("LoRA adapter aggregate state did not change")
    return ParameterStateAudit(
        frozen_parameter_count=len(frozen),
        frozen_parameter_element_count=sum(
            parameter.numel() for parameter in frozen.values()
        ),
        frozen_state_hash_before=frozen_state_hash_before,
        frozen_state_hash_after=frozen_state_hash_after,
        frozen_state_exactly_unchanged=True,
        adapter_parameter_count=len(adapters),
        adapter_parameter_element_count=sum(
            parameter.numel() for parameter in adapters.values()
        ),
        adapter_state_hash_before=adapter_state_hash_before,
        adapter_state_hash_after=adapter_state_hash_after,
        adapter_state_changed=True,
    )


def hash_named_tensors(
    tensors: Mapping[str, torch.Tensor | torch.nn.Parameter],
) -> str:
    digest = xxhash.xxh64()
    for name, tensor in sorted(tensors.items()):
        detached = tensor.detach().contiguous()
        metadata = json.dumps(
            {
                "name": name,
                "dtype": str(detached.dtype),
                "shape": list(detached.shape),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        digest.update(len(metadata).to_bytes(8, byteorder="big"))
        digest.update(metadata)
        byte_view = detached.view(torch.uint8).cpu().numpy()
        digest.update(byte_view.tobytes(order="C"))
    return f"xxh64:{digest.hexdigest()}"


def hash_tensor(tensor: torch.Tensor) -> str:
    return hash_named_tensors({"tensor": tensor})


def normalize_peft_parameter_name(name: str) -> str:
    if name.startswith(_PEFT_BASE_PREFIX):
        return name.removeprefix(_PEFT_BASE_PREFIX)
    return name


def parse_lora_parameter_name(name: str) -> tuple[str, Literal["A", "B"]]:
    match = _LORA_PARAMETER_RE.fullmatch(name)
    if match is None:
        raise ValueError(f"Not an ordinary LoRA parameter name: {name}")
    factor = match.group("factor")
    if factor not in {"A", "B"}:
        raise ValueError(f"Unexpected LoRA factor: {factor}")
    return match.group("logical"), cast(Literal["A", "B"], factor)


def get_model_logits(outputs: Any) -> torch.Tensor:
    logits = getattr(outputs, "logits", None)
    if not isinstance(logits, torch.Tensor):
        raise ValueError("causal-LM model output is missing logits")
    return logits
