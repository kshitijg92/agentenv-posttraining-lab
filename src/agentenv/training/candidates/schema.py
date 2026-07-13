from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentenv.trajectories.schema import ReviewDecision, ReviewStatus
from agentenv.tools.schema import ToolName


TrainingCandidateRecordSchemaVersion = Literal["training_candidate_record_v0"]
MechanicalRedundancyEvaluationStatus = Literal["complete", "incomplete"]

TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION: TrainingCandidateRecordSchemaVersion = (
    "training_candidate_record_v0"
)


class TrainingCandidateEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_eligible: bool
    analysis_reason: str = Field(min_length=1)
    positive_sft_review_eligible: bool
    positive_sft_review_reason: str = Field(min_length=1)
    negative_example_eligible: bool
    negative_example_reason: str = Field(min_length=1)
    preference_pairing_eligible: bool
    preference_pairing_reason: str = Field(min_length=1)

    @property
    def has_training_use_path(self) -> bool:
        return (
            self.positive_sft_review_eligible
            or self.negative_example_eligible
            or self.preference_pairing_eligible
        )

    @property
    def is_analysis_only(self) -> bool:
        return self.analysis_eligible and not self.has_training_use_path

    @property
    def is_fully_ineligible(self) -> bool:
        return not self.analysis_eligible and not self.has_training_use_path


class MechanicallyRedundantToolCallBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: ToolName
    arguments_hash: str = Field(min_length=1)
    baseline_tool_call_id: str = Field(min_length=1)
    redundant_tool_call_ids: list[str] = Field(min_length=1)
    redundant_call_count: int = Field(gt=0, strict=True)
    stable_workspace_hash: str = Field(min_length=1)
    normalized_observation_hash: str = Field(min_length=1)
    public_check_index: int | None = Field(default=None, ge=0, strict=True)

    @field_validator("redundant_tool_call_ids")
    @classmethod
    def validate_redundant_tool_call_ids(cls, value: list[str]) -> list[str]:
        if any(not tool_call_id for tool_call_id in value):
            raise ValueError("redundant tool-call ids must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("redundant tool-call ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_block(self) -> "MechanicallyRedundantToolCallBlock":
        if self.baseline_tool_call_id in self.redundant_tool_call_ids:
            raise ValueError("baseline tool-call id cannot be redundant")
        if self.redundant_call_count != len(self.redundant_tool_call_ids):
            raise ValueError(
                "redundant_call_count must equal redundant_tool_call_ids length"
            )
        if self.tool_name == "run_tests":
            if self.public_check_index is None:
                raise ValueError("run_tests redundancy requires public_check_index")
        elif self.public_check_index is not None:
            raise ValueError("public_check_index is only valid for run_tests")
        return self


class MechanicalRedundancyAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detector_version: str = Field(min_length=1)
    detector_code_hash: str = Field(min_length=1)
    evaluation_status: MechanicalRedundancyEvaluationStatus
    blocks: list[MechanicallyRedundantToolCallBlock]
    error_class: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_assessment(self) -> "MechanicalRedundancyAssessment":
        if self.evaluation_status == "complete":
            if self.error_class is not None or self.error_message is not None:
                raise ValueError(
                    "complete mechanical-redundancy assessments cannot include errors"
                )
        else:
            if self.error_class is None or self.error_message is None:
                raise ValueError(
                    "incomplete mechanical-redundancy assessments require errors"
                )
            if self.blocks:
                raise ValueError(
                    "incomplete mechanical-redundancy assessments cannot include blocks"
                )

        tool_call_ids = [
            tool_call_id
            for block in self.blocks
            for tool_call_id in (
                block.baseline_tool_call_id,
                *block.redundant_tool_call_ids,
            )
        ]
        if len(tool_call_ids) != len(set(tool_call_ids)):
            raise ValueError("mechanical-redundancy blocks cannot share tool-call ids")
        return self


class TrainingCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TrainingCandidateRecordSchemaVersion = (
        TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
    )
    trajectory_id: str = Field(min_length=1)
    eval_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    review_status: ReviewStatus
    review_id: str | None = Field(default=None, min_length=1)
    reviewer_id: str | None = Field(default=None, min_length=1)
    review_decision: ReviewDecision | None = None
    mechanical_redundancy_assessment: MechanicalRedundancyAssessment
    training_eligibility: TrainingCandidateEligibility

    @model_validator(mode="after")
    def validate_review_gate(self) -> "TrainingCandidateRecord":
        if self.review_status == "not_reviewed":
            if any(
                value is not None
                for value in (
                    self.review_id,
                    self.reviewer_id,
                    self.review_decision,
                )
            ):
                raise ValueError(
                    "not_reviewed training candidates cannot include review details"
                )
        else:
            if self.review_id is None:
                raise ValueError("reviewed training candidates require review_id")
            if self.reviewer_id is None:
                raise ValueError("reviewed training candidates require reviewer_id")
            if self.review_decision is None:
                raise ValueError("reviewed training candidates require review_decision")

        if self.training_eligibility.has_training_use_path and (
            self.review_status != "reviewed" or self.review_decision != "accepted"
        ):
            raise ValueError(
                "candidates with a training-use path require accepted human review"
            )
        return self
