import torch

from agentenv.training.positive_sft.lora.objective import (
    compute_masked_causal_lm_loss,
)


def test_ignored_targets_have_zero_direct_logit_gradient() -> None:
    logits = torch.tensor(
        [
            [
                [1.0, 0.0, -1.0],
                [0.0, 1.0, -1.0],
                [-1.0, 0.0, 1.0],
                [0.5, -0.5, 0.0],
            ]
        ],
        requires_grad=True,
    )
    labels = torch.tensor([[-100, -100, 2, -100]])

    result = compute_masked_causal_lm_loss(logits, labels)
    result.loss.backward()

    assert result.supervised_prediction_count == 1
    assert result.ignored_prediction_count == 2
    assert logits.grad is not None
    assert torch.count_nonzero(logits.grad[0, 0]).item() == 0
    assert torch.count_nonzero(logits.grad[0, 1]).item() > 0
    assert torch.count_nonzero(logits.grad[0, 2]).item() == 0
    assert torch.count_nonzero(logits.grad[0, 3]).item() == 0


def test_masked_loss_is_mean_over_only_supervised_shifted_targets() -> None:
    logits = torch.tensor(
        [
            [
                [0.0, 0.0],
                [0.0, 0.0],
                [0.0, 0.0],
                [0.0, 0.0],
            ]
        ]
    )
    labels = torch.tensor([[-100, 0, -100, 1]])

    result = compute_masked_causal_lm_loss(logits, labels)

    assert result.supervised_prediction_count == 2
    assert result.ignored_prediction_count == 1
    assert torch.allclose(result.loss, torch.log(torch.tensor(2.0)))
