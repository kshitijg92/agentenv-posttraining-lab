from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as functional

from agentenv.training.preferences.materialization.schema import (
    TRAINER_IGNORE_INDEX,
)


@dataclass(frozen=True)
class ResponseLogProbability:
    value: torch.Tensor
    prediction_count: int


@dataclass(frozen=True)
class DPOLoss:
    loss: torch.Tensor
    policy_log_ratio: torch.Tensor
    reference_log_ratio: torch.Tensor
    chosen_reward: torch.Tensor
    rejected_reward: torch.Tensor
    reward_margin: torch.Tensor


def compute_response_log_probability(
    logits: torch.Tensor,
    input_ids: torch.Tensor,
    labels: torch.Tensor,
) -> ResponseLogProbability:
    """Sum causal log probabilities only where materialized labels own loss."""
    if logits.ndim != 3:
        raise ValueError("causal-LM logits must have shape [batch, sequence, vocab]")
    if input_ids.ndim != 2 or labels.ndim != 2:
        raise ValueError("DPO input ids and labels must have shape [batch, sequence]")
    if input_ids.shape != labels.shape or logits.shape[:2] != input_ids.shape:
        raise ValueError("DPO logits, input ids, and labels must share batch/sequence")
    if input_ids.shape[0] != 1:
        raise ValueError("current DPO path requires micro-batch size exactly one")
    if input_ids.shape[1] < 2:
        raise ValueError("DPO branches require at least two tokens for causal loss")

    shifted_targets = input_ids[:, 1:]
    shifted_labels = labels[:, 1:]
    score_mask = shifted_labels.ne(TRAINER_IGNORE_INDEX)
    prediction_count = int(score_mask.sum().item())
    if prediction_count == 0:
        raise ValueError("DPO branch contains no reachable response labels")
    if not torch.equal(
        shifted_labels[score_mask],
        shifted_targets[score_mask],
    ):
        raise ValueError("DPO response labels must equal their causal target ids")

    scored_logits = logits[:, :-1, :][score_mask].float()
    scored_targets = shifted_targets[score_mask]
    target_log_probabilities = (
        torch.log_softmax(scored_logits, dim=-1)
        .gather(
            dim=-1,
            index=scored_targets.unsqueeze(-1),
        )
        .squeeze(-1)
    )
    return ResponseLogProbability(
        value=target_log_probabilities.sum(),
        prediction_count=prediction_count,
    )


def compute_dpo_loss(
    *,
    policy_chosen_log_probability: torch.Tensor,
    policy_rejected_log_probability: torch.Tensor,
    reference_chosen_log_probability: torch.Tensor,
    reference_rejected_log_probability: torch.Tensor,
    beta: float,
) -> DPOLoss:
    """Compute the canonical sigmoid DPO loss for one preference pair."""
    if beta <= 0.0:
        raise ValueError("DPO beta must be positive")
    values = (
        policy_chosen_log_probability,
        policy_rejected_log_probability,
        reference_chosen_log_probability,
        reference_rejected_log_probability,
    )
    if any(value.numel() != 1 for value in values):
        raise ValueError("DPO branch log probabilities must each be scalar")
    if not all(bool(torch.isfinite(value).item()) for value in values):
        raise ValueError("DPO branch log probabilities must be finite")

    policy_log_ratio = policy_chosen_log_probability - policy_rejected_log_probability
    reference_log_ratio = (
        reference_chosen_log_probability - reference_rejected_log_probability
    )
    preference_logit = beta * (policy_log_ratio - reference_log_ratio)
    loss = -functional.logsigmoid(preference_logit)
    chosen_reward = beta * (
        policy_chosen_log_probability - reference_chosen_log_probability
    )
    rejected_reward = beta * (
        policy_rejected_log_probability - reference_rejected_log_probability
    )
    return DPOLoss(
        loss=loss,
        policy_log_ratio=policy_log_ratio,
        reference_log_ratio=reference_log_ratio,
        chosen_reward=chosen_reward,
        rejected_reward=rejected_reward,
        reward_margin=chosen_reward - rejected_reward,
    )
