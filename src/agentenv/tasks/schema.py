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


class BaselinePolicySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    practice: str = Field(min_length=1)
    dev: str = Field(min_length=1)
    heldout_private: str = Field(min_length=1)
    public_calibration: str = Field(min_length=1)


class TaskPackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    domain: TaskDomain
    created_at: str = Field(min_length=1)
    description: str = Field(min_length=1)
    scoring_contract: str = Field(min_length=1)
    split_lock: str = Field(min_length=1)
    tasks_dir: str = Field(min_length=1)
    required_task_files: list[str] = Field(min_length=1)
    baseline_policy: BaselinePolicySpec
    provenance_policy: str = Field(min_length=1)


class TaskSplitsLock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    task_pack: str = Field(min_length=1)
    practice: list[str]
    dev: list[str]
    heldout_private: list[str]
    public_calibration: list[str]
    policy: str = Field(min_length=1)
