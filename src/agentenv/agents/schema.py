import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat
from pydantic import StrictInt, StrictStr, TypeAdapter


AgentActionValue = StrictStr | StrictBool | StrictInt | StrictFloat | None
AgentNetworkMode = Literal["off"]


class AgentTaskView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    workspace_path: Path
    allowed_tools: list[str] = Field(min_length=1)
    public_checks: list[str] = Field(min_length=1)
    max_turns: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    network: AgentNetworkMode


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
