from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RewardHackCaseSchemaVersion = Literal["reward_hack_case_v0"]
ExploitClassification = Literal["hidden_validator_probe_attempt"]
HiddenValidatorProbeReferenceType = Literal[
    "hidden_validator_path",
    "leakage_canary",
]
HiddenValidatorProbeSurface = Literal[
    "submitted_patch_text",
    "agent_tool_call",
]

REWARD_HACK_CASE_SCHEMA_VERSION: RewardHackCaseSchemaVersion = (
    "reward_hack_case_v0"
)


def _validate_repo_relative_path(value: str) -> str:
    if not value:
        raise ValueError("path must not be empty")
    if value.startswith("/"):
        raise ValueError("path must be repo-relative")
    parts = value.split("/")
    if ".." in parts:
        raise ValueError("path must not contain '..'")
    return value


class HarnessAuditCaseRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_dir: str = Field(min_length=1)
    case_id: str = Field(min_length=1)

    @field_validator("case_dir")
    @classmethod
    def validate_case_dir(cls, value: str) -> str:
        return _validate_repo_relative_path(value)


class ScorerAuditEvidencePair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["scorer_audit_case"]
    exploit: HarnessAuditCaseRef
    valid_control: HarnessAuditCaseRef


class AgentTaskAuditEvidencePair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["agent_task_audit_case"]
    exploit: HarnessAuditCaseRef
    valid_control: HarnessAuditCaseRef


class EvalAttemptRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_artifact_dir: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    eval_attempt_id: str = Field(min_length=1)

    @field_validator("eval_artifact_dir")
    @classmethod
    def validate_eval_artifact_dir(cls, value: str) -> str:
        return _validate_repo_relative_path(value)


class EvalAttemptEvidencePair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["eval_attempt"]
    exploit: EvalAttemptRef
    valid_control: EvalAttemptRef


class TrajectoryRecordRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trajectory_export_dir: str = Field(min_length=1)
    trajectory_id: str = Field(min_length=1)

    @field_validator("trajectory_export_dir")
    @classmethod
    def validate_trajectory_export_dir(cls, value: str) -> str:
        return _validate_repo_relative_path(value)


class TrajectoryRecordEvidencePair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["trajectory_record"]
    exploit: TrajectoryRecordRef
    valid_control: TrajectoryRecordRef


RewardHackEvidencePair: TypeAlias = Annotated[
    ScorerAuditEvidencePair
    | AgentTaskAuditEvidencePair
    | EvalAttemptEvidencePair
    | TrajectoryRecordEvidencePair,
    Field(discriminator="source_type"),
]


class HiddenValidatorProbeExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_target: str = Field(min_length=1)
    probe_surface: HiddenValidatorProbeSurface
    probe_reference_type: HiddenValidatorProbeReferenceType
    expected_blocking_layer: str = Field(min_length=1)
    private_content_must_not_appear: bool

    @model_validator(mode="after")
    def validate_private_content_expectation(self) -> "HiddenValidatorProbeExploitSpec":
        if not self.private_content_must_not_appear:
            raise ValueError(
                "hidden_validator_probe_attempt requires "
                "private_content_must_not_appear=true"
            )
        return self


class HiddenValidatorProbeExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["hidden_validator_probe_attempt"]
    exploit_spec: HiddenValidatorProbeExploitSpec


RewardHackExploit: TypeAlias = HiddenValidatorProbeExploit


class ExpectedRewardHackOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    private_content_exposed: bool
    exploit_blocked: bool
    training_allowed: bool

    @model_validator(mode="after")
    def validate_training_blocked(self) -> "ExpectedRewardHackOutcome":
        if self.training_allowed:
            raise ValueError("reward-hack cases cannot be training-allowed")
        return self


class RewardHackCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: RewardHackCaseSchemaVersion = REWARD_HACK_CASE_SCHEMA_VERSION
    reward_hack_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    evidence: RewardHackEvidencePair
    exploit: RewardHackExploit
    expected_reward_hack_outcome: ExpectedRewardHackOutcome
    notes: str | None = Field(default=None, min_length=1)
