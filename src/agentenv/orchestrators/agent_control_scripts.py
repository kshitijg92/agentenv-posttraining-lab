import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentenv.agents.schema import PromptLoopStatus
from agentenv.models.fake import FakeModelScriptStep


AGENT_CONTROL_SCRIPT_SCHEMA_VERSION = "agent_control_script_v0"


class AgentControlScriptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[FakeModelScriptStep] = Field(min_length=1)


class ExpectedAgentControlResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_loop_status: PromptLoopStatus


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
