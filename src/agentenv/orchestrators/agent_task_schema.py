from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.agents.schema import PromptLoopStatus
from agentenv.orchestrators.attempt import AttemptResult


AgentTaskRunStatus = Literal["scored", "agent_loop_failed", "orchestrator_error"]


class AgentTaskRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus | None
    candidate_patch_path: str | None
    candidate_patch_hash: str | None
    attempt_result: AttemptResult | None
    error_class: str | None
    error_message: str | None
    started_at: str = Field(min_length=1)
    ended_at: str = Field(min_length=1)
    duration_ms: int = Field(ge=0, strict=True)
    orchestrator_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "AgentTaskRunResult":
        if self.status == "scored":
            if self.prompt_loop_status != "completed":
                raise ValueError("scored agent task runs require completed prompt loop")
            if self.attempt_result is None:
                raise ValueError("scored agent task runs require attempt_result")
            if self.candidate_patch_path is None or self.candidate_patch_hash is None:
                raise ValueError("scored agent task runs require candidate patch")
            if self.error_class is not None or self.error_message is not None:
                raise ValueError("scored agent task runs cannot include error fields")
            return self

        if self.attempt_result is not None:
            raise ValueError("unscored agent task runs cannot include attempt_result")
        if self.error_class is None:
            raise ValueError("unscored agent task runs require error_class")
        if self.status == "agent_loop_failed":
            if self.prompt_loop_status is None:
                raise ValueError("agent loop failures require prompt_loop_status")
            if self.prompt_loop_status == "completed":
                raise ValueError(
                    "agent loop failures cannot have completed prompt loop"
                )
        return self
