from collections.abc import Mapping, Sequence
from typing import cast

import pytest

from agentenv.agents.schema import PromptLoopResult, TokenUsage
from agentenv.artifacts.manifests import (
    EvalRunAgentAttemptSummary,
    EvalRunScorerAttemptSummary,
)
from agentenv.reporting.policy_selection import (
    PolicyCellOutcome,
    PolicyTaskCell,
    analyze_policy_cells,
    policy_task_cell_from_agent_attempt,
    render_policy_selection_analysis,
    select_policy,
    summarize_policy_cells,
)


POLICIES = ("base", "raw-sft", "efficiency-filtered-sft")
TASKS = ("task_a", "task_b", "task_c")


def _cells(
    outcomes: Mapping[str, Sequence[str]],
    *,
    total_tokens: Mapping[str, Sequence[int | None]] | None = None,
    action_counts: Mapping[str, Sequence[int | None]] | None = None,
) -> tuple[PolicyTaskCell, ...]:
    records: list[PolicyTaskCell] = []
    for policy_id in POLICIES:
        for index, task_id in enumerate(TASKS):
            outcome = cast(PolicyCellOutcome, outcomes[policy_id][index])
            tokens = total_tokens[policy_id][index] if total_tokens else 100 + index
            actions = action_counts[policy_id][index] if action_counts else 4 + index
            records.append(
                PolicyTaskCell(
                    policy_id=policy_id,
                    task_id=task_id,
                    outcome=outcome,
                    outcome_detail=outcome,
                    prompt_tokens=tokens,
                    completion_tokens=(0 if tokens is not None else None),
                    total_tokens=tokens,
                    action_count=actions,
                )
            )
    return tuple(records)


def test_more_nested_passes_selects_policy_before_efficiency() -> None:
    cells = _cells(
        {
            "base": ("pass", "policy_failure", "policy_failure"),
            "raw-sft": ("pass", "pass", "policy_failure"),
            "efficiency-filtered-sft": ("policy_failure", "policy_failure", "pass"),
        },
        total_tokens={
            "base": (10, 10, 10),
            "raw-sft": (1000, 1000, 1000),
            "efficiency-filtered-sft": (1, 1, 1),
        },
    )

    decision = select_policy(cells, policy_order=POLICIES, task_order=TASKS)

    assert decision.status == "selected"
    assert decision.selected_policy == "raw-sft"
    assert decision.branch == "task_success"


def test_equal_pass_counts_on_different_tasks_abstains() -> None:
    cells = _cells(
        {
            "base": ("pass", "pass", "policy_failure"),
            "raw-sft": ("pass", "policy_failure", "pass"),
            "efficiency-filtered-sft": ("policy_failure", "pass", "pass"),
        }
    )

    decision = select_policy(cells, policy_order=POLICIES, task_order=TASKS)

    assert decision.status == "abstained"
    assert decision.selected_policy is None
    assert decision.branch == "different_success_vectors"


def test_identical_success_vector_uses_tokens_then_actions() -> None:
    outcomes = {
        policy: ("pass", "pass", "policy_failure") for policy in POLICIES
    }
    token_winner = select_policy(
        _cells(
            outcomes,
            total_tokens={
                "base": (100, 100, 20),
                "raw-sft": (90, 90, 20),
                "efficiency-filtered-sft": (95, 95, 20),
            },
        ),
        policy_order=POLICIES,
        task_order=TASKS,
    )
    action_winner = select_policy(
        _cells(
            outcomes,
            total_tokens={policy: (100, 100, 20) for policy in POLICIES},
            action_counts={
                "base": (5, 5, 1),
                "raw-sft": (4, 4, 1),
                "efficiency-filtered-sft": (6, 3, 1),
            },
        ),
        policy_order=POLICIES,
        task_order=TASKS,
    )

    assert token_winner.selected_policy == "raw-sft"
    assert token_winner.branch == "successful_total_tokens"
    assert action_winner.selected_policy == "raw-sft"
    assert action_winner.branch == "successful_action_count"


def test_invalid_cell_or_missing_tiebreak_metric_abstains() -> None:
    invalid = _cells(
        {
            "base": ("pass", "pass", "policy_failure"),
            "raw-sft": ("pass", "invalid", "policy_failure"),
            "efficiency-filtered-sft": ("pass", "pass", "policy_failure"),
        }
    )
    tied_outcomes = {
        policy: ("pass", "pass", "policy_failure") for policy in POLICIES
    }
    missing_tokens = _cells(
        tied_outcomes,
        total_tokens={
            "base": (100, 100, 20),
            "raw-sft": (100, None, 20),
            "efficiency-filtered-sft": (100, 100, 20),
        },
    )

    invalid_decision = select_policy(
        invalid,
        policy_order=POLICIES,
        task_order=TASKS,
    )
    missing_decision = select_policy(
        missing_tokens,
        policy_order=POLICIES,
        task_order=TASKS,
    )

    assert invalid_decision.branch == "invalid_comparison_cells"
    assert missing_decision.branch == "missing_success_token_counts"


def test_complete_tie_abstains_and_summary_reports_all_task_metrics() -> None:
    outcomes = {
        policy: ("pass", "policy_failure", "pass") for policy in POLICIES
    }
    cells = _cells(outcomes)

    decision = select_policy(cells, policy_order=POLICIES, task_order=TASKS)
    summaries = summarize_policy_cells(
        cells,
        policy_order=POLICIES,
        task_order=TASKS,
    )

    assert decision.status == "abstained"
    assert decision.branch == "complete_tie"
    assert summaries[0].pass_task_ids == ("task_a", "task_c")
    assert summaries[0].policy_failure_task_ids == ("task_b",)
    assert summaries[0].observed_total_tokens == 303
    assert summaries[0].token_observed_task_count == 3
    assert summaries[0].observed_actions == 15
    assert summaries[0].action_observed_task_count == 3


def test_policy_selection_requires_exact_frozen_matrix() -> None:
    cells = _cells({policy: ("pass", "pass", "pass") for policy in POLICIES})

    with pytest.raises(ValueError, match="policy-task matrix"):
        select_policy(
            cells[:-1],
            policy_order=POLICIES,
            task_order=TASKS,
        )


def test_attempt_evidence_maps_status_tokens_and_actions_mechanically() -> None:
    scorer = EvalRunScorerAttemptSummary(
        scorer_attempt_id="scorer_attempt_test",
        status="PASS",
        public_status="PASS",
        hidden_status="PASS",
        error_class=None,
        final_diff_hash="xxh64:aaaaaaaaaaaaaaaa",
        duration_ms=10,
    )
    agent = EvalRunAgentAttemptSummary(
        agent_attempt_id="agent_attempt_test",
        status="scored",
        prompt_loop_status="completed",
        error_class=None,
        candidate_patch_hash="xxh64:bbbbbbbbbbbbbbbb",
        duration_ms=20,
        scorer_attempt=scorer,
    )
    prompt_loop = PromptLoopResult(
        task_id="task_a",
        prompt_builder_version="test",
        prompt_builder_code_hash="xxh64:cccccccccccccccc",
        status="completed",
        turns_executed=4,
        duration_ms=15,
        token_usage=TokenUsage(
            prompt_tokens=90,
            completion_tokens=10,
            total_tokens=100,
        ),
        messages=[],
        model_responses=[],
        tool_results=[],
    )

    cell = policy_task_cell_from_agent_attempt(
        policy_id="base",
        task_id="task_a",
        agent=agent,
        prompt_loop=prompt_loop,
    )
    disqualified = policy_task_cell_from_agent_attempt(
        policy_id="base",
        task_id="task_a",
        agent=agent,
        prompt_loop=prompt_loop,
        confirmed_reward_hack=True,
    )

    assert cell.outcome == "pass"
    assert cell.outcome_detail == "nested_scorer:PASS"
    assert cell.prompt_tokens == 90
    assert cell.completion_tokens == 10
    assert cell.total_tokens == 100
    assert cell.action_count == 4
    assert disqualified.outcome == "policy_failure"
    assert disqualified.outcome_detail == "reward_hack:confirmed"


def test_analysis_reports_all_pairs_and_renders_decision() -> None:
    cells = _cells(
        {
            "base": ("pass", "policy_failure", "pass"),
            "raw-sft": ("pass", "pass", "policy_failure"),
            "efficiency-filtered-sft": ("pass", "policy_failure", "pass"),
        }
    )

    analysis = analyze_policy_cells(
        cells,
        policy_order=POLICIES,
        task_order=TASKS,
    )
    report = render_policy_selection_analysis(analysis)

    base_to_raw = analysis.pairwise_comparisons[0]
    assert base_to_raw.reference_policy == "base"
    assert base_to_raw.candidate_policy == "raw-sft"
    assert base_to_raw.gain_task_ids == ("task_b",)
    assert base_to_raw.regression_task_ids == ("task_c",)
    assert len(analysis.pairwise_comparisons) == 3
    assert analysis.decision.branch == "different_success_vectors"
    assert "## Policy Selection" in report
    assert "| base | raw-sft | task_b | task_c | task_a | none | none |" in report
    assert "- Status: abstained" in report
