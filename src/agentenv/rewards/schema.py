from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RewardHackCaseSchemaVersion = Literal["reward_hack_case_v0"]
ExploitClassification = Literal[
    "fake_success_output",
    "format_only_compliance",
    "hidden_validator_probe_attempt",
    "no_op_patch",
    "public_check_tampering",
    "public_test_only_pass",
    "state_corruption",
    "tool_output_spoofing",
]
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


class NoOpPatchExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_surface: Literal["submitted_patch_text"]
    patch_must_be_empty: bool

    @model_validator(mode="after")
    def validate_empty_patch_requirement(self) -> "NoOpPatchExploitSpec":
        if not self.patch_must_be_empty:
            raise ValueError("no_op_patch requires patch_must_be_empty=true")
        return self


class NoOpPatchExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["no_op_patch"]
    exploit_spec: NoOpPatchExploitSpec


class PublicTestOnlyPassExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_surface: Literal["submitted_patch_text"]
    patch_must_be_non_empty: bool
    public_tests_must_not_be_modified: bool

    @model_validator(mode="after")
    def validate_public_only_patch_requirements(
        self,
    ) -> "PublicTestOnlyPassExploitSpec":
        if not self.patch_must_be_non_empty:
            raise ValueError(
                "public_test_only_pass requires patch_must_be_non_empty=true"
            )
        if not self.public_tests_must_not_be_modified:
            raise ValueError(
                "public_test_only_pass requires "
                "public_tests_must_not_be_modified=true"
            )
        return self


class PublicTestOnlyPassExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["public_test_only_pass"]
    exploit_spec: PublicTestOnlyPassExploitSpec


class PublicCheckTamperingExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_surface: Literal["submitted_patch_text"]
    public_test_files_must_be_modified: bool
    expected_blocking_layer: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_public_check_tampering_requirements(
        self,
    ) -> "PublicCheckTamperingExploitSpec":
        if not self.public_test_files_must_be_modified:
            raise ValueError(
                "public_check_tampering requires "
                "public_test_files_must_be_modified=true"
            )
        return self


class PublicCheckTamperingExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["public_check_tampering"]
    exploit_spec: PublicCheckTamperingExploitSpec


class PatchChangeScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comments: bool
    docstrings: bool
    executable_code: bool
    public_tests: bool

    @model_validator(mode="after")
    def validate_format_only_scope(self) -> "PatchChangeScope":
        if not self.comments:
            raise ValueError("format_only_compliance requires comments=true")
        if not self.docstrings:
            raise ValueError("format_only_compliance requires docstrings=true")
        if self.executable_code:
            raise ValueError("format_only_compliance requires executable_code=false")
        if self.public_tests:
            raise ValueError("format_only_compliance requires public_tests=false")
        return self


class FormatOnlyComplianceExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_surface: Literal["submitted_patch_text"]
    patch_must_be_non_empty: bool
    patch_change_scope: PatchChangeScope

    @model_validator(mode="after")
    def validate_format_only_patch_requirements(
        self,
    ) -> "FormatOnlyComplianceExploitSpec":
        if not self.patch_must_be_non_empty:
            raise ValueError(
                "format_only_compliance requires patch_must_be_non_empty=true"
            )
        return self


class FormatOnlyComplianceExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["format_only_compliance"]
    exploit_spec: FormatOnlyComplianceExploitSpec


class ExpectedSpoofFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    required_markers: list[str] = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_repo_relative_path(value)

    @field_validator("required_markers")
    @classmethod
    def validate_required_markers(cls, value: list[str]) -> list[str]:
        if any(not marker for marker in value):
            raise ValueError("expected spoof file markers must not be empty")
        return value


class FakeSuccessOutputExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_surface: Literal["agent_workspace_update"]
    spoofed_authority: Literal["scorer_result"]
    spoof_format: Literal["json_file"]
    spoofed_signal: Literal["pass_status_and_reward"]
    expected_spoof_file: ExpectedSpoofFile
    spoof_must_not_be_accepted: bool

    @model_validator(mode="after")
    def validate_spoof_must_not_be_accepted(
        self,
    ) -> "FakeSuccessOutputExploitSpec":
        if not self.spoof_must_not_be_accepted:
            raise ValueError(
                "fake_success_output requires spoof_must_not_be_accepted=true"
            )
        return self


class FakeSuccessOutputExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["fake_success_output"]
    exploit_spec: FakeSuccessOutputExploitSpec


class ToolOutputSpoofingExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_surface: Literal["agent_workspace_update"]
    spoofed_authority: Literal["tool_provenance"]
    spoof_format: Literal["json_file"]
    spoofed_signal: Literal["tool_sequence_success"]
    expected_spoof_file: ExpectedSpoofFile
    spoof_must_not_be_accepted: bool

    @model_validator(mode="after")
    def validate_spoof_must_not_be_accepted(
        self,
    ) -> "ToolOutputSpoofingExploitSpec":
        if not self.spoof_must_not_be_accepted:
            raise ValueError(
                "tool_output_spoofing requires spoof_must_not_be_accepted=true"
            )
        return self


class ToolOutputSpoofingExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["tool_output_spoofing"]
    exploit_spec: ToolOutputSpoofingExploitSpec


class StateCorruptionExploitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_surface: Literal["agent_workspace_update"]
    corrupted_state_target: Literal["run_manifest", "attempt_result", "task_manifest"]
    corruption_method: Literal["model_authored_file"]
    expected_corrupted_file: ExpectedSpoofFile
    corrupted_state_must_not_be_authoritative: bool

    @model_validator(mode="after")
    def validate_corrupted_state_authority(self) -> "StateCorruptionExploitSpec":
        if not self.corrupted_state_must_not_be_authoritative:
            raise ValueError(
                "state_corruption requires "
                "corrupted_state_must_not_be_authoritative=true"
            )
        return self


class StateCorruptionExploit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exploit_classification: Literal["state_corruption"]
    exploit_spec: StateCorruptionExploitSpec


RewardHackExploit: TypeAlias = Annotated[
    FakeSuccessOutputExploit
    | FormatOnlyComplianceExploit
    | HiddenValidatorProbeExploit
    | NoOpPatchExploit
    | PublicCheckTamperingExploit
    | PublicTestOnlyPassExploit
    | StateCorruptionExploit
    | ToolOutputSpoofingExploit,
    Field(discriminator="exploit_classification"),
]


class ExpectedRewardHackOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    private_content_exposed: bool
    exploit_mechanism_neutralized: bool
    task_success_allowed: bool
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
