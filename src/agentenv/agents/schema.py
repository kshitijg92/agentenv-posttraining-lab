import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat
from pydantic import StrictInt, StrictStr, TypeAdapter, model_validator

from agentenv.models.schema import Message, ModelResponse
from agentenv.tools.schema import ToolResult


AgentActionValue = StrictStr | StrictBool | StrictInt | StrictFloat | None
AgentNetworkMode = Literal["off"]
PromptLoopStatus = Literal[
    "completed",
    "max_turns_exceeded",
    "model_error",
    "invalid_model_output",
    "invalid_shortcut_attempted",
    "terminal_tool_error",
    "orchestrator_error",
]


class AgentTaskPromptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    allowed_tools: list[str] = Field(min_length=1)
    public_checks: list[str] = Field(min_length=1)
    max_turns: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    network: AgentNetworkMode


class AgentTaskView(AgentTaskPromptInput):
    workspace_path: Path


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_total_tokens(self) -> "TokenUsage":
        if self.prompt_tokens is None or self.completion_tokens is None:
            return self

        expected_total_tokens = self.prompt_tokens + self.completion_tokens
        if self.total_tokens != expected_total_tokens:
            raise ValueError(
                "total_tokens must equal prompt_tokens + completion_tokens "
                "when both token counts are present"
            )
        return self


class PromptLoopResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    prompt_builder_version: str = Field(min_length=1)
    prompt_builder_code_hash: str = Field(min_length=1)
    status: PromptLoopStatus
    turns_executed: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    token_usage: TokenUsage
    messages: list[Message]
    model_responses: list[ModelResponse]
    tool_results: list[ToolResult]
    error_class: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "PromptLoopResult":
        message_ids = [message.message_id for message in self.messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("prompt-loop message_ids must be unique")

        if self.status == "completed":
            if self.error_class is not None or self.error_message is not None:
                raise ValueError("completed prompt loops cannot include error fields")
            return self

        if self.error_class is None:
            raise ValueError("non-completed prompt loops require error_class")
        return self


class ToolCallAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["tool_call"]
    tool_name: str = Field(min_length=1)
    arguments: dict[str, AgentActionValue] = Field(default_factory=dict)


class FinalAnswerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["final_answer"]
    text: str = Field(min_length=1)


AgentAction = Annotated[
    ToolCallAction | FinalAnswerAction,
    Field(discriminator="action"),
]

_AGENT_ACTION_ADAPTER = TypeAdapter(AgentAction)


def parse_agent_action(output_text: str) -> AgentAction:
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ValueError("model output is not valid JSON") from exc

    return _AGENT_ACTION_ADAPTER.validate_python(payload)
