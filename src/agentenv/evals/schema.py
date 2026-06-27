from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentenv.tasks.schema import TaskSplit


PolicyType = Literal["scorer_control_patch"]
ControlName = Literal["oracle", "bad.noop", "bad.public_only"]


class ScorerControlPatchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: PolicyType
    control: ControlName


class TraceCaptureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    capture_stdout: bool
    capture_stderr: bool
    capture_diff: bool


class EvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    task_pack: str = Field(min_length=1)
    tasks: list[str] = Field(min_length=1)
    split: TaskSplit
    attempts: int = Field(gt=0)
    policies: dict[str, ScorerControlPatchPolicy] = Field(min_length=1)
    trace: TraceCaptureConfig
