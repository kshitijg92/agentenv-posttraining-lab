from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import re
from typing import Any, Literal, cast

import torch
import xxhash

from agentenv.hashing import hash_json
from agentenv.training.positive_sft.lora.schema import (
    AdapterParameterQualificationAudit,
    AdapterQualificationAudit,
    LoRATargetModule,
    OptimizerIsolationAudit,
    ParameterStateAudit,
)


_LORA_PARAMETER_RE = re.compile(
    r"^(?P<logical>.+)\.lora_(?P<factor>[AB])\.[^.]+\.weight$"
)
_PEFT_BASE_PREFIX = "base_model.model."


@dataclass
class _MutableGradientEvidence:
    gradient_observed: bool = False
    nonzero_gradient_observed: bool = False
    all_observed_gradients_finite: bool = True


class AdapterQualificationTracker:
    def __init__(self, adapter_parameters: Mapping[str, torch.nn.Parameter]) -> None:
        self._evidence = {
            name: _MutableGradientEvidence() for name in adapter_parameters
        }

    def observe(self, adapter_parameters: Mapping[str, torch.nn.Parameter]) -> None:
        if set(adapter_parameters) != set(self._evidence):
            raise ValueError("adapter parameter set changed during training")
        for name, parameter in adapter_parameters.items():
            gradient = parameter.grad
            if gradient is None:
                continue
            evidence = self._evidence[name]
            evidence.gradient_observed = True
            finite = bool(torch.isfinite(gradient).all().item())
            evidence.all_observed_gradients_finite &= finite
            if finite and bool(torch.count_nonzero(gradient).item()):
                evidence.nonzero_gradient_observed = True

    def build_audit(
        self,
        *,
        qualification_step_count: int,
        intended_logical_adapters: frozenset[str],
        adapter_parameters: Mapping[str, torch.nn.Parameter],
        initial_adapter_state: Mapping[str, torch.Tensor],
    ) -> AdapterQualificationAudit:
        observed_logical_adapters = frozenset(
            parse_lora_parameter_name(name)[0] for name in adapter_parameters
        )
        if observed_logical_adapters != intended_logical_adapters:
            missing = sorted(intended_logical_adapters - observed_logical_adapters)
            unexpected = sorted(observed_logical_adapters - intended_logical_adapters)
            raise ValueError(
                "PEFT logical adapter set differs from configured target modules; "
                f"missing={missing}, unexpected={unexpected}"
            )

        parameter_audits: list[AdapterParameterQualificationAudit] = []
        for name, parameter in sorted(adapter_parameters.items()):
            logical_name, factor = parse_lora_parameter_name(name)
            evidence = self._evidence[name]
            parameter_audits.append(
                AdapterParameterQualificationAudit(
                    parameter_name=name,
                    logical_adapter_name=logical_name,
                    factor=factor,
                    gradient_observed_during_qualification=(
                        evidence.gradient_observed
                    ),
                    nonzero_gradient_observed_during_qualification=(
                        evidence.nonzero_gradient_observed
                    ),
                    all_qualification_gradients_finite=(
                        evidence.all_observed_gradients_finite
                    ),
                    parameter_changed_during_qualification=not torch.equal(
                        initial_adapter_state[name],
                        parameter.detach().cpu(),
                    ),
                )
            )

        adapter_rows: dict[str, list[AdapterParameterQualificationAudit]] = {}
        for audit in parameter_audits:
            adapter_rows.setdefault(audit.logical_adapter_name, []).append(audit)
        every_adapter_received_finite_gradient = all(
            any(
                row.gradient_observed_during_qualification
                and row.nonzero_gradient_observed_during_qualification
                and row.all_qualification_gradients_finite
                for row in rows
            )
            for rows in adapter_rows.values()
        )
        every_adapter_changed = all(
            any(row.parameter_changed_during_qualification for row in rows)
            for rows in adapter_rows.values()
        )
        if not every_adapter_received_finite_gradient:
            missing = sorted(
                name
                for name, rows in adapter_rows.items()
                if not any(
                    row.gradient_observed_during_qualification
                    and row.nonzero_gradient_observed_during_qualification
                    and row.all_qualification_gradients_finite
                    for row in rows
                )
            )
            raise ValueError(
                "logical LoRA adapters lacked finite nonzero gradient evidence: "
                + ", ".join(missing)
            )
        if not every_adapter_changed:
            unchanged = sorted(
                name
                for name, rows in adapter_rows.items()
                if not any(
                    row.parameter_changed_during_qualification for row in rows
                )
            )
            raise ValueError(
                "logical LoRA adapters did not change during training: "
                + ", ".join(unchanged)
            )

        return AdapterQualificationAudit(
            qualification_step_count=qualification_step_count,
            intended_logical_adapter_count=len(intended_logical_adapters),
            observed_logical_adapter_count=len(observed_logical_adapters),
            adapter_parameter_count=len(parameter_audits),
            every_logical_adapter_received_finite_nonzero_gradient_during_qualification=(
                True
            ),
            every_logical_adapter_changed_during_qualification=True,
            parameters=tuple(parameter_audits),
        )


def enumerate_intended_lora_modules(
    model: torch.nn.Module,
    target_modules: Iterable[LoRATargetModule],
) -> frozenset[str]:
    target_names = frozenset(target_modules)
    intended = frozenset(
        name
        for name, module in model.named_modules()
        if isinstance(module, torch.nn.Linear)
        and name.rsplit(".", maxsplit=1)[-1] in target_names
    )
    if not intended:
        raise ValueError("configured LoRA target modules matched no linear layers")
    matched_suffixes = {name.rsplit(".", maxsplit=1)[-1] for name in intended}
    if matched_suffixes != target_names:
        missing = sorted(target_names - matched_suffixes)
        raise ValueError(
            "LoRA target module suffixes were not found: " + ", ".join(missing)
        )
    return intended


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
