import math

import pytest
import torch

from agentenv.training.preferences.dpo.objective import (
    compute_dpo_loss,
    compute_response_log_probability,
)


def test_response_log_probability_scores_only_materialized_response_labels() -> None:
    logits = torch.tensor(
        [
            [
                [0.0, 0.0, 0.0, 0.0],
                [0.0, 2.0, 0.0, 0.0],
                [0.0, 0.0, 2.0, 0.0],
                [0.0, 0.0, 0.0, 2.0],
            ]
        ]
    )
    input_ids = torch.tensor([[0, 1, 2, 3]])
    labels = torch.tensor([[-100, -100, 2, 3]])

    result = compute_response_log_probability(logits, input_ids, labels)

    expected = torch.log_softmax(logits[:, :-1, :], dim=-1)
    assert result.prediction_count == 2
    assert result.value.item() == pytest.approx(
        expected[0, 1, 2].item() + expected[0, 2, 3].item()
    )


def test_response_log_probability_rejects_non_target_labels() -> None:
    with pytest.raises(ValueError, match="labels must equal"):
        compute_response_log_probability(
            torch.zeros((1, 3, 4)),
            torch.tensor([[0, 1, 2]]),
            torch.tensor([[-100, -100, 3]]),
        )


def test_identical_policy_and_reference_start_at_log_two_with_zero_margin() -> None:
    chosen = torch.tensor(-8.0, requires_grad=True)
    rejected = torch.tensor(-10.0, requires_grad=True)

    result = compute_dpo_loss(
        policy_chosen_log_probability=chosen,
        policy_rejected_log_probability=rejected,
        reference_chosen_log_probability=torch.tensor(-8.0),
        reference_rejected_log_probability=torch.tensor(-10.0),
        beta=0.1,
    )
    result.loss.backward()

    assert result.loss.item() == pytest.approx(math.log(2.0))
    assert result.reward_margin.item() == pytest.approx(0.0)
    assert chosen.grad is not None and chosen.grad.item() < 0.0
    assert rejected.grad is not None and rejected.grad.item() > 0.0


def test_dpo_loss_rewards_a_larger_policy_preference_margin() -> None:
    result = compute_dpo_loss(
        policy_chosen_log_probability=torch.tensor(-7.0),
        policy_rejected_log_probability=torch.tensor(-11.0),
        reference_chosen_log_probability=torch.tensor(-8.0),
        reference_rejected_log_probability=torch.tensor(-10.0),
        beta=0.1,
    )

    assert result.loss.item() < math.log(2.0)
    assert result.reward_margin.item() > 0.0
