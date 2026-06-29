from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentenv.tasks.schema import TaskSplit


ScorerControlName = Literal["oracle", "bad.noop", "bad.public_only"]
AgentControlName = Literal["happy", "malformed", "recoverable"]


class PolicyReplayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeats: int = Field(ge=0)


class EvalPolicyBase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    attempts: int = Field(gt=0)
    replay: PolicyReplayConfig


class ScorerControlPatchPolicy(EvalPolicyBase):
    type: Literal["scorer_control_patch"]
    control: ScorerControlName


class AgentControlScriptPolicy(EvalPolicyBase):
    type: Literal["agent_control_script"]
    control: AgentControlName


class AgentModelPolicy(EvalPolicyBase):
    type: Literal["agent_model"]
    model_config_path: str = Field(alias="model_config", min_length=1)
    decoding_config_path: str = Field(alias="decoding_config", min_length=1)


EvalPolicy = ScorerControlPatchPolicy | AgentControlScriptPolicy | AgentModelPolicy


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
    policies: dict[str, EvalPolicy] = Field(min_length=1)
    trace: TraceCaptureConfig
