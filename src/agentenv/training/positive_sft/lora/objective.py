from dataclasses import dataclass

import torch

from agentenv.training.positive_sft.materialization.schema import (
    TRAINER_IGNORE_INDEX,
)


@dataclass(frozen=True)
class MaskedCausalLoss:
    loss: torch.Tensor
    supervised_prediction_count: int
    ignored_prediction_count: int


def compute_masked_causal_lm_loss(
    logits: torch.Tensor,
    labels: torch.Tensor,
) -> MaskedCausalLoss:
    """Align each position's logits with the next token and mask context targets."""
    if logits.ndim != 3:
        raise ValueError("causal-LM logits must have shape [batch, sequence, vocab]")
    if labels.ndim != 2:
        raise ValueError("causal-LM labels must have shape [batch, sequence]")
    if logits.shape[:2] != labels.shape:
        raise ValueError("logit and label batch/sequence dimensions must match")
    if logits.shape[1] < 2:
        raise ValueError("causal-LM training requires at least two sequence tokens")

    next_token_prediction_logits = logits[:, :-1, :].contiguous()
    next_token_target_labels = labels[:, 1:].contiguous()
    supervised_mask = next_token_target_labels.ne(TRAINER_IGNORE_INDEX)
    supervised_prediction_count = int(supervised_mask.sum().item())
    if supervised_prediction_count == 0:
        raise ValueError("causal-LM batch contains no supervised shifted targets")
    ignored_prediction_count = int((~supervised_mask).sum().item())

    loss = torch.nn.functional.cross_entropy(
        next_token_prediction_logits.float().view(
            -1,
            next_token_prediction_logits.shape[-1],
        ),
        next_token_target_labels.view(-1),
        ignore_index=TRAINER_IGNORE_INDEX,
        reduction="mean",
    )
    if not bool(torch.isfinite(loss).item()):
        raise ValueError("causal-LM loss is not finite")
    return MaskedCausalLoss(
        loss=loss,
        supervised_prediction_count=supervised_prediction_count,
        ignored_prediction_count=ignored_prediction_count,
    )
