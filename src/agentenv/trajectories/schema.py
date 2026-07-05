from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.config import JsonDict

from agentenv.agents.schema import PromptLoopStatus
from agentenv.artifacts.base import validate_relative_artifact_ref
from agentenv.evals.schema import AGENT_EVAL_POLICY_TYPES, EvalPolicy
from agentenv.orchestrators.agent_task_schema import AgentTaskRunStatus
from agentenv.orchestrators.attempt import AttemptStatus, CheckStatus
from agentenv.orchestrators.attempt import validate_attempt_check_statuses
from agentenv.tasks.schema import TaskSplit


TrajectoryRecordSchemaVersion = Literal["trajectory_record_v0"]
RewardComponentsVersion = Literal["reward_components_v0"]
GradeState = Literal["scored_pass", "scored_fail", "cannot_grade"]
ReviewStatus = Literal["not_reviewed", "reviewed"]
ReviewDecision = Literal["accepted", "rejected", "needs_followup"]

TRAJECTORY_RECORD_SCHEMA_VERSION: TrajectoryRecordSchemaVersion = "trajectory_record_v0"
REWARD_COMPONENTS_VERSION: RewardComponentsVersion = "reward_components_v0"
REWARD_COMPONENT_METADATA_SCHEMA_EXTRA_KEY = "reward_component_metadata"
NON_TRAINING_SPLITS = frozenset({"heldout_private", "public_calibration"})


def build_reward_component_metadata_schema_extra() -> JsonDict:
    return {REWARD_COMPONENT_METADATA_SCHEMA_EXTRA_KEY: True}


class TrajectoryIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trajectory_id: str = Field(min_length=1)
    eval_suite_id: str | None = Field(default=None, min_length=1)
    eval_run_id: str = Field(min_length=1)
    eval_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    attempt_index: int = Field(ge=0, strict=True)
    agent_attempt_id: str | None = Field(default=None, min_length=1)
    scorer_attempt_id: str | None = Field(default=None, min_length=1)
    replay_run_id: str | None = Field(default=None, min_length=1)


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
        if self.agent_task_run_status is None:
            if self.prompt_loop_status is not None:
                raise ValueError("prompt_loop_status requires agent_task_run_status")
        elif self.agent_task_run_status == "scored":
            if self.prompt_loop_status != "completed":
                raise ValueError(
                    "scored agent trajectories require completed prompt loop"
                )
        elif self.agent_task_run_status == "agent_loop_failed":
            if self.prompt_loop_status is None:
                raise ValueError("agent loop failures require prompt_loop_status")
            if self.prompt_loop_status == "completed":
                raise ValueError(
                    "agent loop failures cannot have completed prompt loop"
                )

        check_statuses = (self.public_status, self.hidden_status)
        if self.attempt_status is None:
            if any(status is not None for status in check_statuses):
                raise ValueError("public and hidden statuses require attempt_status")
        else:
            if self.public_status is None or self.hidden_status is None:
                raise ValueError("attempt_status requires public and hidden statuses")
            validate_attempt_check_statuses(
                self.attempt_status,
                public_status=self.public_status,
                hidden_status=self.hidden_status,
            )

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

        if self.grade_state == "scored_fail":
            if self.task_success:
                raise ValueError("grade_state=scored_fail requires task_success=false")
            if self.attempt_status is None:
                raise ValueError("grade_state=scored_fail requires attempt_status")

        return self


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    content_hash: str | None = Field(default=None, min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)


class TrajectoryArtifacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_run_path: str = Field(min_length=1)
    eval_suite_json: ArtifactRef | None = None
    manifest_json: ArtifactRef
    agent_task_run_json: ArtifactRef | None = None
    agent_task_view_json: ArtifactRef | None = None
    prompt_loop_result_json: ArtifactRef | None = None
    decoding_config_json: ArtifactRef | None = None
    model_config_json: ArtifactRef | None = None
    agent_control_script_json: ArtifactRef | None = None
    candidate_patch: ArtifactRef | None = None
    attempt_json: ArtifactRef | None = None
    trace_jsonl: ArtifactRef | None = None
    stdout: ArtifactRef | None = None
    stderr: ArtifactRef | None = None
    error_txt: ArtifactRef | None = None
    final_diff: ArtifactRef | None = None


class RewardComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reward_version: RewardComponentsVersion = Field(
        default=REWARD_COMPONENTS_VERSION,
        json_schema_extra=build_reward_component_metadata_schema_extra(),
    )
    reward_config_hash: str = Field(
        min_length=1,
        json_schema_extra=build_reward_component_metadata_schema_extra(),
    )
    reward_code_hash: str = Field(
        min_length=1,
        json_schema_extra=build_reward_component_metadata_schema_extra(),
    )
    public_validator_success: bool | None = None
    hidden_validator_success: bool | None = None
    model_output_format_valid: bool | None = None
    model_tool_usage_valid: bool | None = None
    orchestration_failure: bool
    reward_hack_flag: bool | None = None


def list_reward_component_signal_field_names() -> tuple[str, ...]:
    return tuple(
        field_name
        for field_name, field in RewardComponents.model_fields.items()
        if not is_reward_component_metadata_field(field.json_schema_extra)
    )


def is_reward_component_metadata_field(json_schema_extra: object) -> bool:
    return (
        isinstance(json_schema_extra, dict)
        and json_schema_extra.get(REWARD_COMPONENT_METADATA_SCHEMA_EXTRA_KEY) is True
    )


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
                raise ValueError("not_reviewed records cannot include review details")
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
            self.statuses.agent_task_run_status is not None
            and self.identity.agent_attempt_id is None
        ):
            raise ValueError("agent_task_run_status requires identity.agent_attempt_id")

        if (
            self.statuses.agent_task_run_status == "scored"
            and self.artifacts.candidate_patch is None
        ):
            raise ValueError("scored agent trajectories require candidate_patch")

        if self.identity.agent_attempt_id is None:
            agent_artifact_fields = (
                "agent_task_run_json",
                "agent_task_view_json",
                "prompt_loop_result_json",
                "decoding_config_json",
                "model_config_json",
                "agent_control_script_json",
                "candidate_patch",
            )
            present_agent_artifacts = [
                field_name
                for field_name in agent_artifact_fields
                if getattr(self.artifacts, field_name) is not None
            ]
            if present_agent_artifacts:
                joined_fields = ", ".join(present_agent_artifacts)
                raise ValueError(
                    "agent artifact refs require identity.agent_attempt_id: "
                    f"{joined_fields}"
                )

        if (
            self.statuses.attempt_status is not None
            and self.identity.scorer_attempt_id is None
        ):
            raise ValueError("attempt_status requires identity.scorer_attempt_id")

        if (
            self.statuses.grade_state != "cannot_grade"
            and self.identity.scorer_attempt_id is None
        ):
            raise ValueError(
                "scored trajectory records require identity.scorer_attempt_id"
            )

        if (
            self.training_eligibility.positive_sft_allowed
            and not self.statuses.task_success
        ):
            raise ValueError("positive_sft_allowed=true requires task_success=true")

        is_agent_policy = self.policy.policy_spec.type in AGENT_EVAL_POLICY_TYPES
        has_leakage = (
            self.leakage.canary_leaked
            or self.leakage.hidden_validators_visible_to_model
        )
        statuses_show_orchestration_failure = statuses_have_orchestration_failure(
            self.statuses
        )
        if (
            self.reward_components.orchestration_failure
            != statuses_show_orchestration_failure
        ):
            raise ValueError(
                "reward_components.orchestration_failure must reflect "
                "orchestrator terminal statuses"
            )
        self._validate_reward_component_consistency()
        has_orchestration_failure = (
            self.reward_components.orchestration_failure
            or statuses_show_orchestration_failure
        )

        if self.training_eligibility.positive_sft_allowed and not is_agent_policy:
            raise ValueError("positive_sft_allowed=true requires an agent policy")

        if (
            self.training_eligibility.positive_sft_allowed
            and self.source_provenance.split in NON_TRAINING_SPLITS
        ):
            raise ValueError(
                "positive_sft_allowed=true is forbidden for heldout_private "
                "and public_calibration splits"
            )

        if self.training_eligibility.positive_sft_allowed:
            self._validate_training_agent_evidence()
            if self.statuses.agent_task_run_status != "scored":
                raise ValueError(
                    "positive_sft_allowed=true requires a scored agent trajectory"
                )
            if self.leakage.canary_leaked:
                raise ValueError("positive_sft_allowed=true forbids canary leakage")
            if self.leakage.hidden_validators_visible_to_model:
                raise ValueError(
                    "positive_sft_allowed=true forbids visible hidden validators"
                )
            if has_orchestration_failure:
                raise ValueError(
                    "positive_sft_allowed=true forbids orchestration failure"
                )

        if self.training_eligibility.negative_example_allowed:
            if not is_agent_policy:
                raise ValueError(
                    "negative_example_allowed=true requires an agent policy"
                )
            if self.statuses.task_success:
                raise ValueError(
                    "negative_example_allowed=true requires task_success=false"
                )
            if self.source_provenance.split in NON_TRAINING_SPLITS:
                raise ValueError(
                    "negative_example_allowed=true is forbidden for heldout_private "
                    "and public_calibration splits"
                )
            self._validate_training_agent_evidence()
            if has_leakage:
                raise ValueError("negative_example_allowed=true forbids leakage")
            if has_orchestration_failure:
                raise ValueError(
                    "negative_example_allowed=true forbids orchestration failure"
                )

        if self.training_eligibility.preference_data_allowed:
            if not is_agent_policy:
                raise ValueError(
                    "preference_data_allowed=true requires an agent policy"
                )
            if self.statuses.grade_state == "cannot_grade":
                raise ValueError(
                    "preference_data_allowed=true requires a gradable trajectory"
                )
            if self.source_provenance.split in NON_TRAINING_SPLITS:
                raise ValueError(
                    "preference_data_allowed=true is forbidden for heldout_private "
                    "and public_calibration splits"
                )
            self._validate_training_agent_evidence()
            if self.statuses.agent_task_run_status != "scored":
                raise ValueError(
                    "preference_data_allowed=true requires a scored agent trajectory"
                )
            if has_leakage:
                raise ValueError("preference_data_allowed=true forbids leakage")
            if has_orchestration_failure:
                raise ValueError(
                    "preference_data_allowed=true forbids orchestration failure"
                )

        return self

    def _validate_training_agent_evidence(self) -> None:
        if self.identity.agent_attempt_id is None:
            raise ValueError("training-eligible records require agent_attempt_id")
        if self.statuses.agent_task_run_status is None:
            raise ValueError("training-eligible records require agent_task_run_status")
        if self.artifacts.agent_task_run_json is None:
            raise ValueError("training-eligible records require agent_task_run_json")
        if self.artifacts.agent_task_view_json is None:
            raise ValueError("training-eligible records require agent_task_view_json")
        if self.artifacts.prompt_loop_result_json is None:
            raise ValueError(
                "training-eligible records require prompt_loop_result_json"
            )
        if self.artifacts.decoding_config_json is None:
            raise ValueError("training-eligible records require decoding_config_json")

    def _validate_reward_component_consistency(self) -> None:
        expected_public_success = validator_success(self.statuses.public_status)
        if self.reward_components.public_validator_success != expected_public_success:
            raise ValueError(
                "reward_components.public_validator_success must reflect public_status"
            )
        expected_hidden_success = validator_success(self.statuses.hidden_status)
        if self.reward_components.hidden_validator_success != expected_hidden_success:
            raise ValueError(
                "reward_components.hidden_validator_success must reflect hidden_status"
            )
        expected_output_format = model_output_format_valid(self.statuses)
        if self.reward_components.model_output_format_valid != expected_output_format:
            raise ValueError(
                "reward_components.model_output_format_valid must reflect "
                "prompt_loop_status"
            )
        expected_tool_usage = model_tool_usage_valid(self.statuses)
        if self.reward_components.model_tool_usage_valid != expected_tool_usage:
            raise ValueError(
                "reward_components.model_tool_usage_valid must reflect "
                "prompt_loop_status"
            )
        expected_reward_hack = reward_hack_flag(self.statuses.attempt_status)
        if self.reward_components.reward_hack_flag != expected_reward_hack:
            raise ValueError(
                "reward_components.reward_hack_flag must reflect attempt_status"
            )


def statuses_have_orchestration_failure(statuses: TrajectoryStatuses) -> bool:
    return (
        statuses.agent_task_run_status == "orchestrator_error"
        or statuses.attempt_status == "ORCHESTRATOR_ERROR"
    )


def validator_success(status: CheckStatus | None) -> bool | None:
    if status is None:
        return None
    return status == "PASS"


def model_output_format_valid(statuses: TrajectoryStatuses) -> bool | None:
    if statuses.agent_task_run_status is None or statuses.prompt_loop_status is None:
        return None
    return statuses.prompt_loop_status != "invalid_model_output"


def model_tool_usage_valid(statuses: TrajectoryStatuses) -> bool | None:
    if statuses.agent_task_run_status is None or statuses.prompt_loop_status is None:
        return None
    if statuses.prompt_loop_status == "terminal_tool_error":
        return False
    if statuses.prompt_loop_status in {"completed", "max_turns_exceeded"}:
        return True
    return None


def reward_hack_flag(attempt_status: AttemptStatus | None) -> bool | None:
    if attempt_status is None:
        return None
    return attempt_status in {
        "INVALID_SHORTCUT",
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT",
    }
