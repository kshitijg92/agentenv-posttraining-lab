from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentenv.tasks.schema import TaskSplit


ScorerControlName = Literal["oracle", "bad.noop", "bad.public_only"]
AgentControlName = Literal["happy", "malformed", "recoverable"]
ScorerControlPatchPolicyType = Literal["scorer_control_patch"]
AgentControlScriptPolicyType = Literal["agent_control_script"]
AgentModelPolicyType = Literal["agent_model"]
PolicyType = (
    ScorerControlPatchPolicyType | AgentControlScriptPolicyType | AgentModelPolicyType
)
ControlPolicyFamily = Literal["control"]
AgentPolicyFamily = Literal["agent"]
PolicyFamily = ControlPolicyFamily | AgentPolicyFamily
ScorerControlLayer = Literal["scorer"]
AgentControlLayer = Literal["agent"]
ControlLayer = ScorerControlLayer | AgentControlLayer

SCORER_CONTROL_PATCH_POLICY_TYPE: ScorerControlPatchPolicyType = "scorer_control_patch"
AGENT_CONTROL_SCRIPT_POLICY_TYPE: AgentControlScriptPolicyType = "agent_control_script"
AGENT_MODEL_POLICY_TYPE: AgentModelPolicyType = "agent_model"
CONTROL_POLICY_FAMILY: ControlPolicyFamily = "control"
AGENT_POLICY_FAMILY: AgentPolicyFamily = "agent"
SCORER_CONTROL_LAYER: ScorerControlLayer = "scorer"
AGENT_CONTROL_LAYER: AgentControlLayer = "agent"
AGENT_EVAL_POLICY_TYPES: frozenset[PolicyType] = frozenset(
    {
        AGENT_CONTROL_SCRIPT_POLICY_TYPE,
        AGENT_MODEL_POLICY_TYPE,
    }
)


class PolicyReplayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repeats: int = Field(ge=0)


class EvalPolicyBase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    attempts: int = Field(gt=0)
    replay: PolicyReplayConfig


class ScorerControlPatchPolicy(EvalPolicyBase):
    type: ScorerControlPatchPolicyType
    control: ScorerControlName


class AgentControlScriptPolicy(EvalPolicyBase):
    type: AgentControlScriptPolicyType
    control: AgentControlName


class AgentModelPolicy(EvalPolicyBase):
    type: AgentModelPolicyType
    model_config_path: str = Field(alias="model_config", min_length=1)
    decoding_config_path: str = Field(alias="decoding_config", min_length=1)
    max_turns_override: int | None = Field(default=None, gt=0)


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
