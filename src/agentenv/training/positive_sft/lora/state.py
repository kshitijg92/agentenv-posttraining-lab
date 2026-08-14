from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import torch

from agentenv.training.lora.schema import LoRATargetModule
from agentenv.training.lora.state import parse_lora_parameter_name
from agentenv.training.positive_sft.lora.schema import (
    AdapterParameterQualificationAudit,
    AdapterQualificationAudit,
)


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
                    gradient_observed_during_qualification=(evidence.gradient_observed),
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
                if not any(row.parameter_changed_during_qualification for row in rows)
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
