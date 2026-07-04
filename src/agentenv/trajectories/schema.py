from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.agents.schema import PromptLoopStatus
from agentenv.evals.schema import EvalPolicy
from agentenv.orchestrators.agent_task_run import AgentTaskRunStatus
from agentenv.orchestrators.attempt import AttemptStatus, CheckStatus
from agentenv.tasks.schema import TaskSplit


TrajectoryRecordSchemaVersion = Literal["trajectory_record_v0"]
RewardComponentsVersion = Literal["reward_components_v0"]
GradeState = Literal["scored_pass", "scored_fail", "cannot_grade"]
ReviewStatus = Literal["not_reviewed", "reviewed"]
ReviewDecision = Literal["accepted", "rejected", "needs_followup"]

TRAJECTORY_RECORD_SCHEMA_VERSION: TrajectoryRecordSchemaVersion = (
    "trajectory_record_v0"
)
REWARD_COMPONENTS_VERSION: RewardComponentsVersion = "reward_components_v0"


class TrajectoryIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trajectory_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    attempt_index: int = Field(ge=0)
    attempt_id: str | None = Field(default=None, min_length=1)


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    split: TaskSplit
    scoring_contract: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    task_manifest_hash: str = Field(min_length=1)
    splits_lock_path: str = Field(min_length=1)
    splits_lock_hash: str = Field(min_length=1)
    eval_config_path: str = Field(min_length=1)
    eval_config_hash: str = Field(min_length=1)


class TrajectoryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_name: str = Field(min_length=1)
    policy_spec: EvalPolicy


class TrajectoryStatuses(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_task_run_status: AgentTaskRunStatus | None = None
    prompt_loop_status: PromptLoopStatus | None = None
    attempt_status: AttemptStatus | None = None
    public_status: CheckStatus | None = None
    hidden_status: CheckStatus | None = None
    grade_state: GradeState
    task_success: bool

    @model_validator(mode="after")
    def validate_grade_state(self) -> "TrajectoryStatuses":
        if self.grade_state == "cannot_grade" and self.task_success:
            raise ValueError("grade_state=cannot_grade requires task_success=false")

        if self.task_success and self.grade_state != "scored_pass":
            raise ValueError("task_success=true requires grade_state=scored_pass")

        if self.grade_state == "scored_pass":
            if not self.task_success:
                raise ValueError("grade_state=scored_pass requires task_success=true")
            if (
                self.attempt_status != "PASS"
                or self.public_status != "PASS"
                or self.hidden_status != "PASS"
            ):
                raise ValueError(
                    "grade_state=scored_pass requires PASS attempt, public, and "
                    "hidden statuses"
                )

        return self


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    content_hash: str | None = Field(default=None, min_length=1)


class TrajectoryArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_run_path: str = Field(min_length=1)
    eval_suite_json: ArtifactRef | None = None
    manifest_json: ArtifactRef
    agent_task_run_json: ArtifactRef | None = None
    prompt_loop_result_json: ArtifactRef | None = None
    candidate_patch: ArtifactRef | None = None
    attempt_json: ArtifactRef | None = None
    trace_jsonl: ArtifactRef | None = None
    stdout: ArtifactRef | None = None
    stderr: ArtifactRef | None = None
    error_txt: ArtifactRef | None = None
    final_diff: ArtifactRef | None = None


class RewardComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reward_version: RewardComponentsVersion = REWARD_COMPONENTS_VERSION
    reward_config_hash: str = Field(min_length=1)
    reward_code_hash: str = Field(min_length=1)
    public_validator_success: bool | None = None
    hidden_validator_success: bool | None = None
    model_output_format_valid: bool | None = None
    model_tool_usage_valid: bool | None = None
    orchestration_failure: bool
    reward_hack_flag: bool | None = None


class LeakageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canary_hash: str | None = Field(default=None, min_length=1)
    canary_leaked: bool
    hidden_validators_visible_to_model: bool
    leakage_check_version: str = Field(min_length=1)


class TrainingEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_allowed: bool
    positive_sft_allowed: bool
    negative_example_allowed: bool
    preference_data_allowed: bool
    eligibility_reason: str = Field(min_length=1)


class TrajectoryReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: ReviewStatus
    review_id: str | None = Field(default=None, min_length=1)
    reviewer_id: str | None = Field(default=None, min_length=1)
    review_decision: ReviewDecision | None = None
    review_notes_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> "TrajectoryReview":
        if self.review_status == "not_reviewed":
            if any(
                value is not None
                for value in (
                    self.review_id,
                    self.reviewer_id,
                    self.review_decision,
                    self.review_notes_ref,
                )
            ):
                raise ValueError(
                    "not_reviewed records cannot include review details"
                )
            return self

        if self.review_id is None:
            raise ValueError("reviewed records require review_id")
        if self.reviewer_id is None:
            raise ValueError("reviewed records require reviewer_id")
        if self.review_decision is None:
            raise ValueError("reviewed records require review_decision")
        return self


class TrajectoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TrajectoryRecordSchemaVersion = TRAJECTORY_RECORD_SCHEMA_VERSION
    identity: TrajectoryIdentity
    source_provenance: SourceProvenance
    policy: TrajectoryPolicy
    statuses: TrajectoryStatuses
    artifacts: TrajectoryArtifacts
    reward_components: RewardComponents
    leakage: LeakageEvidence
    training_eligibility: TrainingEligibility
    review: TrajectoryReview

    @model_validator(mode="after")
    def validate_cross_section_invariants(self) -> "TrajectoryRecord":
        if self.identity.task_id != self.source_provenance.task_id:
            raise ValueError("identity.task_id must match source_provenance.task_id")

        if self.identity.policy_id != self.policy.policy_id:
            raise ValueError("identity.policy_id must match policy.policy_id")

        if (
            self.training_eligibility.positive_sft_allowed
            and not self.statuses.task_success
        ):
            raise ValueError("positive_sft_allowed=true requires task_success=true")

        if (
            self.training_eligibility.positive_sft_allowed
            and self.source_provenance.split
            in {"heldout_private", "public_calibration"}
        ):
            raise ValueError(
                "positive_sft_allowed=true is forbidden for heldout_private "
                "and public_calibration splits"
            )

        if self.training_eligibility.positive_sft_allowed:
            if self.leakage.canary_leaked:
                raise ValueError("positive_sft_allowed=true forbids canary leakage")
            if self.leakage.hidden_validators_visible_to_model:
                raise ValueError(
                    "positive_sft_allowed=true forbids visible hidden validators"
                )

        return self
