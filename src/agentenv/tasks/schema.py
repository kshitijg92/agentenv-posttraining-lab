from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TaskDomain = Literal["repo_patch_python"]
TaskSplit = Literal["practice", "dev", "heldout_private", "public_calibration"]
HiddenValidatorType = Literal["pytest"]
NetworkMode = Literal["off"]


class PublicCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1)


class HiddenValidator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: HiddenValidatorType
    path: str = Field(min_length=1)


class ScoringSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: str = Field(min_length=1)


class LimitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(gt=0)
    max_turns: int = Field(gt=0)
    network: NetworkMode


class BadControlSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noop: str = Field(min_length=1)
    public_only: str = Field(min_length=1)


class ControlSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oracle: str = Field(min_length=1)
    bad: BadControlSpec


class ReplaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture: list[str] = Field(min_length=1)


class TaskManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    domain: TaskDomain
    split: TaskSplit
    instruction: str = Field(min_length=1)
    workspace_seed: str = Field(min_length=1)
    allowed_tools: list[str] = Field(min_length=1)
    public_checks: list[PublicCheck] = Field(min_length=1)
    hidden_validators: list[HiddenValidator] = Field(min_length=1)
    scoring: ScoringSpec
    limits: LimitSpec
    controls: ControlSpec
    replay: ReplaySpec
    leakage_canary: str = Field(min_length=1)
