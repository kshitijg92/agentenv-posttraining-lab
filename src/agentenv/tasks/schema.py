from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

from agentenv.tools.schema import ToolName


TaskDomain = Literal["repo_patch_python"]
TaskSplit = Literal["practice", "dev", "heldout_private", "public_calibration"]
HiddenValidatorType = Literal["pytest"]
NetworkMode = Literal["off"]
AGENT_PRIVATE_FIELD_SCHEMA_EXTRA_KEY = "agent_private"


def _agent_private_schema_extra() -> JsonDict:
    return {AGENT_PRIVATE_FIELD_SCHEMA_EXTRA_KEY: True}


class PublicCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1)
    are_tests_idempotent: bool


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


class BadScorerControlPatchSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noop: str = Field(min_length=1)
    public_only: str = Field(min_length=1)


class ScorerControlPatchSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oracle: str = Field(min_length=1)
    bad: BadScorerControlPatchSpec


class AgentControlScriptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    happy: str = Field(min_length=1)
    malformed: str = Field(min_length=1)
    recoverable: str = Field(min_length=1)


class ControlSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer_control_patches: ScorerControlPatchSpec
    agent_control_scripts: AgentControlScriptSpec


class ReplaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture: list[str] = Field(min_length=1)


class TaskManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    domain: TaskDomain
    split: TaskSplit = Field(json_schema_extra=_agent_private_schema_extra())
    instruction: str = Field(min_length=1)
    seed_workspace: str = Field(min_length=1)
    allowed_tools: list[ToolName] = Field(min_length=1)
    public_checks: list[PublicCheck] = Field(min_length=1)
    hidden_validators: list[HiddenValidator] = Field(
        min_length=1,
        json_schema_extra=_agent_private_schema_extra(),
    )
    scoring: ScoringSpec = Field(json_schema_extra=_agent_private_schema_extra())
    limits: LimitSpec
    controls: ControlSpec = Field(json_schema_extra=_agent_private_schema_extra())
    replay: ReplaySpec = Field(json_schema_extra=_agent_private_schema_extra())
    leakage_canary: str = Field(
        min_length=1,
        json_schema_extra=_agent_private_schema_extra(),
    )


def agent_private_task_manifest_field_names() -> tuple[str, ...]:
    return tuple(
        field_name
        for field_name, field in TaskManifest.model_fields.items()
        if _is_agent_private_field(field.json_schema_extra)
    )


def _is_agent_private_field(json_schema_extra: object) -> bool:
    return (
        isinstance(json_schema_extra, Mapping)
        and json_schema_extra.get(AGENT_PRIVATE_FIELD_SCHEMA_EXTRA_KEY) is True
    )


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
