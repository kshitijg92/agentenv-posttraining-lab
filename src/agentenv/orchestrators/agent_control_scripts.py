import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentenv.agents.schema import PromptLoopStatus
from agentenv.models.fake import FakeModelScriptStep
from agentenv.tools.schema import ToolResultStatus


AGENT_CONTROL_SCRIPT_SCHEMA_VERSION = "agent_control_script_v0"


class AgentControlScriptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[FakeModelScriptStep] = Field(min_length=1)


class ExpectedAgentControlToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    status: ToolResultStatus
    error_class: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_error_class(self) -> "ExpectedAgentControlToolResult":
        if self.status == "error":
            if self.error_class is None:
                raise ValueError("error tool result expectations require error_class")
            return self

        if self.error_class is not None:
            raise ValueError("ok tool result expectations cannot include error_class")
        return self


class ExpectedAgentControlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_loop_status: PromptLoopStatus
    tool_results: list[ExpectedAgentControlToolResult] | None = None


class AgentControlScriptCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    script: AgentControlScriptSpec
    expected_result: ExpectedAgentControlResult

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != AGENT_CONTROL_SCRIPT_SCHEMA_VERSION:
            raise ValueError(
                "unsupported agent control script schema_version: "
                f"{value!r}; expected {AGENT_CONTROL_SCRIPT_SCHEMA_VERSION!r}"
            )
        return value


def load_agent_control_script_case(path: Path) -> AgentControlScriptCase:
    raw_case = json.loads(path.read_text())
    return AgentControlScriptCase.model_validate(raw_case)
