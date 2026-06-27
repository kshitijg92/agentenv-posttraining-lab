from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentenv.tasks.schema import TaskSplit


ScorerControlName = Literal["oracle", "bad.noop", "bad.public_only"]
AgentControlName = Literal["happy", "malformed", "recoverable"]
ReplayScope = Literal["control_policies"]


class ScorerControlPatchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["scorer_control_patch"]
    control: ScorerControlName


class AgentControlScriptPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["agent_control_script"]
    control: AgentControlName


EvalPolicy = ScorerControlPatchPolicy | AgentControlScriptPolicy


class TraceCaptureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    capture_stdout: bool
    capture_stderr: bool
    capture_diff: bool


class EvalReplayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    scope: ReplayScope
    repeats: int = Field(gt=0)


class EvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    task_pack: str = Field(min_length=1)
    tasks: list[str] = Field(min_length=1)
    split: TaskSplit
    attempts: int = Field(gt=0)
    policies: dict[str, EvalPolicy] = Field(min_length=1)
    replay: EvalReplayConfig
    trace: TraceCaptureConfig
