from dataclasses import dataclass

from agentenv.agents.schema import PromptLoopStatus
from agentenv.evals.schema import AgentControlName, ScorerControlName
from agentenv.orchestrators.agent_task_schema import AgentTaskRunStatus
from agentenv.orchestrators.attempt import AttemptStatus, CheckStatus


@dataclass(frozen=True)
class ScorerControlExpectation:
    control: ScorerControlName
    attempt_status: AttemptStatus
    public_status: CheckStatus
    hidden_status: CheckStatus


@dataclass(frozen=True)
class AgentControlExpectation:
    control: AgentControlName
    agent_status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus
    nested_scorer_status: AttemptStatus | None


def expected_scorer_control_outcome(
    control: ScorerControlName,
) -> ScorerControlExpectation:
    if control == "oracle":
        return ScorerControlExpectation(
            control=control,
            attempt_status="PASS",
            public_status="PASS",
            hidden_status="PASS",
        )
    if control in {"bad.noop", "bad.public_only"}:
        return ScorerControlExpectation(
            control=control,
            attempt_status="HIDDEN_TEST_FAIL",
            public_status="PASS",
            hidden_status="FAIL",
        )
    raise ValueError(f"Unknown scorer control: {control}")


def expected_agent_control_outcome(
    control: AgentControlName,
) -> AgentControlExpectation:
    if control in {"happy", "recoverable"}:
        return AgentControlExpectation(
            control=control,
            agent_status="scored",
            prompt_loop_status="completed",
            nested_scorer_status="PASS",
        )
    if control == "malformed":
        return AgentControlExpectation(
            control=control,
            agent_status="agent_loop_failed",
            prompt_loop_status="invalid_model_output",
            nested_scorer_status=None,
        )
    raise ValueError(f"Unknown agent control: {control}")
