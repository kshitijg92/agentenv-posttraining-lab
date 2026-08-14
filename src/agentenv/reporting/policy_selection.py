from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Literal, Sequence

from agentenv.agents.schema import PromptLoopResult
from agentenv.artifacts.manifests import EvalRunAgentAttemptSummary


PolicyCellOutcome = Literal["pass", "policy_failure", "invalid"]
PolicySelectionStatus = Literal["selected", "abstained"]
PolicySelectionBranch = Literal[
    "invalid_comparison_cells",
    "task_success",
    "different_success_vectors",
    "successful_total_tokens",
    "missing_success_token_counts",
    "successful_action_count",
    "missing_success_action_counts",
    "complete_tie",
]


@dataclass(frozen=True)
class PolicyTaskCell:
    policy_id: str
    task_id: str
    outcome: PolicyCellOutcome
    outcome_detail: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    action_count: int | None = None

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("policy_id must be non-empty")
        if not self.task_id:
            raise ValueError("task_id must be non-empty")
        if not self.outcome_detail:
            raise ValueError("outcome_detail must be non-empty")
        for field_name in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "action_count",
        ):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if (
            self.prompt_tokens is not None
            and self.completion_tokens is not None
            and self.total_tokens != self.prompt_tokens + self.completion_tokens
        ):
            raise ValueError(
                "total_tokens must equal prompt_tokens + completion_tokens when "
                "both components are present"
            )


@dataclass(frozen=True)
class PolicyMetrics:
    policy_id: str
    task_count: int
    pass_task_ids: tuple[str, ...]
    policy_failure_task_ids: tuple[str, ...]
    invalid_task_ids: tuple[str, ...]
    observed_prompt_tokens: int
    prompt_token_observed_task_count: int
    observed_completion_tokens: int
    completion_token_observed_task_count: int
    observed_total_tokens: int
    token_observed_task_count: int
    observed_actions: int
    action_observed_task_count: int

    @property
    def pass_count(self) -> int:
        return len(self.pass_task_ids)

    @property
    def policy_failure_count(self) -> int:
        return len(self.policy_failure_task_ids)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_task_ids)


@dataclass(frozen=True)
class PolicySelectionDecision:
    status: PolicySelectionStatus
    selected_policy: str | None
    branch: PolicySelectionBranch
    compared_policies: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class PairwisePolicyComparison:
    reference_policy: str
    candidate_policy: str
    gain_task_ids: tuple[str, ...]
    regression_task_ids: tuple[str, ...]
    shared_pass_task_ids: tuple[str, ...]
    shared_policy_failure_task_ids: tuple[str, ...]
    invalid_task_ids: tuple[str, ...]


@dataclass(frozen=True)
class PolicySelectionAnalysis:
    cells: tuple[PolicyTaskCell, ...]
    metrics: tuple[PolicyMetrics, ...]
    pairwise_comparisons: tuple[PairwisePolicyComparison, ...]
    decision: PolicySelectionDecision


_POLICY_FAILURE_SCORER_STATUSES = frozenset(
    {
        "PUBLIC_TEST_FAIL",
        "HIDDEN_TEST_FAIL",
        "INVALID_SHORTCUT",
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT",
    }
)
_POLICY_FAILURE_PROMPT_LOOP_STATUSES = frozenset(
    {
        "max_turns_exceeded",
        "invalid_model_output",
        "invalid_shortcut_attempted",
        "terminal_tool_error",
    }
)


def policy_task_cell_from_agent_attempt(
    *,
    policy_id: str,
    task_id: str,
    agent: EvalRunAgentAttemptSummary,
    prompt_loop: PromptLoopResult | None,
    confirmed_reward_hack: bool = False,
) -> PolicyTaskCell:
    """Map existing attempt evidence to one frozen policy-selection cell."""

    if prompt_loop is not None:
        if prompt_loop.task_id != task_id:
            raise ValueError(
                "prompt-loop task id does not match policy-selection task id"
            )
        if prompt_loop.status != agent.prompt_loop_status:
            raise ValueError(
                "prompt-loop status does not match eval attempt summary"
            )

    if agent.status == "scored":
        assert agent.scorer_attempt is not None
        scorer_status = agent.scorer_attempt.status
        outcome: PolicyCellOutcome
        if scorer_status == "PASS":
            outcome = "pass"
        elif scorer_status in _POLICY_FAILURE_SCORER_STATUSES:
            outcome = "policy_failure"
        else:
            outcome = "invalid"
        outcome_detail = f"nested_scorer:{scorer_status}"
    elif agent.status == "agent_loop_failed":
        assert agent.prompt_loop_status is not None
        prompt_loop_status = agent.prompt_loop_status
        outcome = (
            "policy_failure"
            if prompt_loop_status in _POLICY_FAILURE_PROMPT_LOOP_STATUSES
            else "invalid"
        )
        outcome_detail = f"prompt_loop:{prompt_loop_status}"
    else:
        outcome = "invalid"
        outcome_detail = f"agent:{agent.status}"

    if confirmed_reward_hack and outcome != "invalid":
        outcome = "policy_failure"
        outcome_detail = "reward_hack:confirmed"

    token_usage = prompt_loop.token_usage if prompt_loop is not None else None
    return PolicyTaskCell(
        policy_id=policy_id,
        task_id=task_id,
        outcome=outcome,
        outcome_detail=outcome_detail,
        prompt_tokens=(token_usage.prompt_tokens if token_usage is not None else None),
        completion_tokens=(
            token_usage.completion_tokens if token_usage is not None else None
        ),
        total_tokens=(token_usage.total_tokens if token_usage is not None else None),
        # One prompt-loop turn is one attempted assistant action request. On the
        # successful cells used for tie-breaking, each turn has one model response,
        # including the terminal final-answer action.
        action_count=(prompt_loop.turns_executed if prompt_loop is not None else None),
    )


def analyze_policy_cells(
    cells: Sequence[PolicyTaskCell],
    *,
    policy_order: Sequence[str],
    task_order: Sequence[str],
) -> PolicySelectionAnalysis:
    frozen_cells = tuple(cells)
    return PolicySelectionAnalysis(
        cells=frozen_cells,
        metrics=summarize_policy_cells(
            frozen_cells,
            policy_order=policy_order,
            task_order=task_order,
        ),
        pairwise_comparisons=compare_policy_pairs(
            frozen_cells,
            policy_order=policy_order,
            task_order=task_order,
        ),
        decision=select_policy(
            frozen_cells,
            policy_order=policy_order,
            task_order=task_order,
        ),
    )


def summarize_policy_cells(
    cells: Sequence[PolicyTaskCell],
    *,
    policy_order: Sequence[str],
    task_order: Sequence[str],
) -> tuple[PolicyMetrics, ...]:
    matrix = _validated_cell_matrix(
        cells,
        policy_order=policy_order,
        task_order=task_order,
    )
    return tuple(
        _policy_metrics(
            policy_id,
            tuple(matrix[(policy_id, task_id)] for task_id in task_order),
        )
        for policy_id in policy_order
    )


def compare_policy_pairs(
    cells: Sequence[PolicyTaskCell],
    *,
    policy_order: Sequence[str],
    task_order: Sequence[str],
) -> tuple[PairwisePolicyComparison, ...]:
    matrix = _validated_cell_matrix(
        cells,
        policy_order=policy_order,
        task_order=task_order,
    )
    return tuple(
        _compare_policy_pair(
            matrix,
            reference_policy=reference_policy,
            candidate_policy=candidate_policy,
            task_order=task_order,
        )
        for reference_policy, candidate_policy in combinations(policy_order, 2)
    )


def select_policy(
    cells: Sequence[PolicyTaskCell],
    *,
    policy_order: Sequence[str],
    task_order: Sequence[str],
) -> PolicySelectionDecision:
    matrix = _validated_cell_matrix(
        cells,
        policy_order=policy_order,
        task_order=task_order,
    )
    policies = tuple(policy_order)
    invalid_cells = tuple(
        cell
        for cell in matrix.values()
        if cell.outcome == "invalid"
    )
    if invalid_cells:
        locations = ", ".join(
            f"{cell.policy_id}/{cell.task_id}" for cell in invalid_cells
        )
        return _abstain(
            policies,
            "invalid_comparison_cells",
            "Comparison contains scorer, harness, serving, or infrastructure "
            f"invalid cells: {locations}.",
        )

    pass_task_ids = {
        policy_id: tuple(
            task_id
            for task_id in task_order
            if matrix[(policy_id, task_id)].outcome == "pass"
        )
        for policy_id in policies
    }
    highest_pass_count = max(len(task_ids) for task_ids in pass_task_ids.values())
    leaders = tuple(
        policy_id
        for policy_id in policies
        if len(pass_task_ids[policy_id]) == highest_pass_count
    )
    if len(leaders) == 1:
        selected = leaders[0]
        return _selected(
            policies,
            selected,
            "task_success",
            f"{selected} has the highest nested-PASS task count.",
        )

    leader_success_vectors = {pass_task_ids[policy_id] for policy_id in leaders}
    if len(leader_success_vectors) != 1:
        return _abstain(
            leaders,
            "different_success_vectors",
            "The leading policies have equal PASS counts on different task ids.",
        )

    successful_task_ids = pass_task_ids[leaders[0]]
    token_totals: dict[str, int] = {}
    for policy_id in leaders:
        token_values = [
            matrix[(policy_id, task_id)].total_tokens
            for task_id in successful_task_ids
        ]
        if any(value is None for value in token_values):
            return _abstain(
                leaders,
                "missing_success_token_counts",
                "A leading policy is missing total-token accounting on a matched "
                "successful task cell.",
            )
        token_totals[policy_id] = sum(
            value for value in token_values if value is not None
        )

    minimum_tokens = min(token_totals.values())
    token_leaders = tuple(
        policy_id
        for policy_id in leaders
        if token_totals[policy_id] == minimum_tokens
    )
    if len(token_leaders) == 1:
        selected = token_leaders[0]
        return _selected(
            leaders,
            selected,
            "successful_total_tokens",
            f"{selected} uses the fewest total tokens on the identical successful "
            "task cells.",
        )

    action_totals: dict[str, int] = {}
    for policy_id in token_leaders:
        action_values = [
            matrix[(policy_id, task_id)].action_count
            for task_id in successful_task_ids
        ]
        if any(value is None for value in action_values):
            return _abstain(
                token_leaders,
                "missing_success_action_counts",
                "A token-tied policy is missing action counts on a matched "
                "successful task cell.",
            )
        action_totals[policy_id] = sum(
            value for value in action_values if value is not None
        )

    minimum_actions = min(action_totals.values())
    action_leaders = tuple(
        policy_id
        for policy_id in token_leaders
        if action_totals[policy_id] == minimum_actions
    )
    if len(action_leaders) == 1:
        selected = action_leaders[0]
        return _selected(
            token_leaders,
            selected,
            "successful_action_count",
            f"{selected} takes the fewest assistant actions on the identical "
            "successful task cells after a token tie.",
        )

    return _abstain(
        action_leaders,
        "complete_tie",
        "The leading policies tie on successful tasks, total tokens, and actions.",
    )


def render_policy_selection_analysis(analysis: PolicySelectionAnalysis) -> str:
    lines = [
        "## Policy Selection",
        "",
        (
            "Primary authority is nested scorer PASS count. Token and action "
            "tie-breakers apply only when leading policies have the identical "
            "successful task-id vector."
        ),
        "",
        "### Per-task outcomes",
        "",
        "| policy | task | outcome | detail | prompt tokens | completion tokens | total tokens | actions |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        "| "
        + " | ".join(
            (
                cell.policy_id,
                cell.task_id,
                cell.outcome,
                cell.outcome_detail,
                _optional_metric(cell.prompt_tokens),
                _optional_metric(cell.completion_tokens),
                _optional_metric(cell.total_tokens),
                _optional_metric(cell.action_count),
            )
        )
        + " |"
        for cell in analysis.cells
    )
    lines.extend(
        [
            "",
            "### Policy metrics",
            "",
            "| policy | PASS | policy failures | invalid | prompt tokens | completion tokens | total tokens | actions |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for metrics in analysis.metrics:
        lines.append(
            "| "
            + " | ".join(
                (
                    metrics.policy_id,
                    f"{metrics.pass_count}/{metrics.task_count}",
                    str(metrics.policy_failure_count),
                    str(metrics.invalid_count),
                    _observed_metric(
                        metrics.observed_prompt_tokens,
                        metrics.prompt_token_observed_task_count,
                        metrics.task_count,
                    ),
                    _observed_metric(
                        metrics.observed_completion_tokens,
                        metrics.completion_token_observed_task_count,
                        metrics.task_count,
                    ),
                    _observed_metric(
                        metrics.observed_total_tokens,
                        metrics.token_observed_task_count,
                        metrics.task_count,
                    ),
                    _observed_metric(
                        metrics.observed_actions,
                        metrics.action_observed_task_count,
                        metrics.task_count,
                    ),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "### Paired outcomes",
            "",
            "| reference | candidate | gains | regressions | shared PASS | shared policy failure | invalid |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for comparison in analysis.pairwise_comparisons:
        lines.append(
            "| "
            + " | ".join(
                (
                    comparison.reference_policy,
                    comparison.candidate_policy,
                    _task_ids(comparison.gain_task_ids),
                    _task_ids(comparison.regression_task_ids),
                    _task_ids(comparison.shared_pass_task_ids),
                    _task_ids(comparison.shared_policy_failure_task_ids),
                    _task_ids(comparison.invalid_task_ids),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "### Decision",
            "",
            f"- Status: {analysis.decision.status}",
            f"- Selected policy: {analysis.decision.selected_policy or 'none'}",
            f"- Rule branch: {analysis.decision.branch}",
            f"- Explanation: {analysis.decision.explanation}",
        ]
    )
    return "\n".join(lines) + "\n"


def _validated_cell_matrix(
    cells: Sequence[PolicyTaskCell],
    *,
    policy_order: Sequence[str],
    task_order: Sequence[str],
) -> dict[tuple[str, str], PolicyTaskCell]:
    policies = tuple(policy_order)
    tasks = tuple(task_order)
    if not policies or len(policies) != len(set(policies)):
        raise ValueError("policy_order must contain unique policy ids")
    if not tasks or len(tasks) != len(set(tasks)):
        raise ValueError("task_order must contain unique task ids")

    expected = {
        (policy_id, task_id)
        for policy_id in policies
        for task_id in tasks
    }
    matrix: dict[tuple[str, str], PolicyTaskCell] = {}
    for cell in cells:
        key = (cell.policy_id, cell.task_id)
        if key in matrix:
            raise ValueError(f"duplicate policy-task cell: {key}")
        matrix[key] = cell
    observed = set(matrix)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(
            "policy-task matrix does not match the frozen comparison: "
            f"missing={missing} extra={extra}"
        )
    return matrix


def _policy_metrics(
    policy_id: str,
    cells: tuple[PolicyTaskCell, ...],
) -> PolicyMetrics:
    prompt_token_values = [
        cell.prompt_tokens for cell in cells if cell.prompt_tokens is not None
    ]
    completion_token_values = [
        cell.completion_tokens
        for cell in cells
        if cell.completion_tokens is not None
    ]
    token_values = [cell.total_tokens for cell in cells if cell.total_tokens is not None]
    action_values = [
        cell.action_count for cell in cells if cell.action_count is not None
    ]
    return PolicyMetrics(
        policy_id=policy_id,
        task_count=len(cells),
        pass_task_ids=tuple(
            cell.task_id for cell in cells if cell.outcome == "pass"
        ),
        policy_failure_task_ids=tuple(
            cell.task_id for cell in cells if cell.outcome == "policy_failure"
        ),
        invalid_task_ids=tuple(
            cell.task_id for cell in cells if cell.outcome == "invalid"
        ),
        observed_prompt_tokens=sum(prompt_token_values),
        prompt_token_observed_task_count=len(prompt_token_values),
        observed_completion_tokens=sum(completion_token_values),
        completion_token_observed_task_count=len(completion_token_values),
        observed_total_tokens=sum(token_values),
        token_observed_task_count=len(token_values),
        observed_actions=sum(action_values),
        action_observed_task_count=len(action_values),
    )


def _compare_policy_pair(
    matrix: dict[tuple[str, str], PolicyTaskCell],
    *,
    reference_policy: str,
    candidate_policy: str,
    task_order: Sequence[str],
) -> PairwisePolicyComparison:
    paired = tuple(
        (
            task_id,
            matrix[(reference_policy, task_id)].outcome,
            matrix[(candidate_policy, task_id)].outcome,
        )
        for task_id in task_order
    )
    return PairwisePolicyComparison(
        reference_policy=reference_policy,
        candidate_policy=candidate_policy,
        gain_task_ids=tuple(
            task_id
            for task_id, reference, candidate in paired
            if reference == "policy_failure" and candidate == "pass"
        ),
        regression_task_ids=tuple(
            task_id
            for task_id, reference, candidate in paired
            if reference == "pass" and candidate == "policy_failure"
        ),
        shared_pass_task_ids=tuple(
            task_id
            for task_id, reference, candidate in paired
            if reference == candidate == "pass"
        ),
        shared_policy_failure_task_ids=tuple(
            task_id
            for task_id, reference, candidate in paired
            if reference == candidate == "policy_failure"
        ),
        invalid_task_ids=tuple(
            task_id
            for task_id, reference, candidate in paired
            if "invalid" in (reference, candidate)
        ),
    )


def _optional_metric(value: int | None) -> str:
    return str(value) if value is not None else "not_recorded"


def _observed_metric(total: int, observed: int, expected: int) -> str:
    return f"{total} ({observed}/{expected} cells)"


def _task_ids(task_ids: tuple[str, ...]) -> str:
    return ", ".join(task_ids) if task_ids else "none"


def _selected(
    compared_policies: tuple[str, ...],
    selected_policy: str,
    branch: PolicySelectionBranch,
    explanation: str,
) -> PolicySelectionDecision:
    return PolicySelectionDecision(
        status="selected",
        selected_policy=selected_policy,
        branch=branch,
        compared_policies=compared_policies,
        explanation=explanation,
    )


def _abstain(
    compared_policies: tuple[str, ...],
    branch: PolicySelectionBranch,
    explanation: str,
) -> PolicySelectionDecision:
    return PolicySelectionDecision(
        status="abstained",
        selected_policy=None,
        branch=branch,
        compared_policies=compared_policies,
        explanation=explanation,
    )
