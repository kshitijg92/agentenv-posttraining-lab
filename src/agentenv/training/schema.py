from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.trajectories.schema import ReviewDecision, ReviewStatus


TrainingCandidateRecordSchemaVersion = Literal["training_candidate_record_v0"]

TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION: TrainingCandidateRecordSchemaVersion = (
    "training_candidate_record_v0"
)


class FinalTrainingEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_allowed: bool
    analysis_reason: str = Field(min_length=1)
    positive_sft_allowed: bool
    positive_sft_reason: str = Field(min_length=1)
    negative_example_allowed: bool
    negative_example_reason: str = Field(min_length=1)
    preference_data_allowed: bool
    preference_data_reason: str = Field(min_length=1)

    @property
    def is_trainable(self) -> bool:
        return (
            self.positive_sft_allowed
            or self.negative_example_allowed
            or self.preference_data_allowed
        )

    @property
    def is_analysis_only(self) -> bool:
        return self.analysis_allowed and not self.is_trainable

    @property
    def is_not_trainable(self) -> bool:
        return not self.analysis_allowed and not self.is_trainable


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
    final_eligibility: FinalTrainingEligibility

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

        if self.final_eligibility.is_trainable and (
            self.review_status != "reviewed" or self.review_decision != "accepted"
        ):
            raise ValueError(
                "training-eligible candidates require accepted human review"
            )
        return self
