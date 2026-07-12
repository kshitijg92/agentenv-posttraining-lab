from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from agentenv.models.schema import Message
from agentenv.training.schema import MechanicalRedundancyAssessment
from agentenv.trajectories.schema import ArtifactRef, ReviewDecision, ReviewStatus


TrainingCandidateRepairRecordSchemaVersion = Literal[
    "training_candidate_repair_record_v0"
]
TrainingCandidateRepairReviewRecordSchemaVersion = Literal[
    "training_candidate_repair_review_record_v0"
]
RepairStatus = Literal["completed", "cannot_complete", "repair_error"]
RepairArtifactType = Literal["transcript"]
MechanicalRedundancyRepairMethod = Literal["mechanical_redundancy_deletion"]

TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION: TrainingCandidateRepairRecordSchemaVersion = "training_candidate_repair_record_v0"
TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION: TrainingCandidateRepairReviewRecordSchemaVersion = "training_candidate_repair_review_record_v0"


class RepairedTranscriptArtifact(RootModel[list[Message]]):
    @model_validator(mode="after")
    def validate_non_empty_transcript(self) -> "RepairedTranscriptArtifact":
        if not self.root:
            raise ValueError("repaired transcript artifacts must not be empty")
        return self


class MechanicalRedundancyRepairDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repair_method: MechanicalRedundancyRepairMethod
    original_mechanical_redundancy_assessment: MechanicalRedundancyAssessment
    after_repair_mechanical_redundancy_assessment: (
        MechanicalRedundancyAssessment | None
    ) = None
    cannot_complete_reason: str | None = Field(default=None, min_length=1)


class TrainingCandidateRepairRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TrainingCandidateRepairRecordSchemaVersion = (
        TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION
    )
    repair_id: str = Field(min_length=1)
    trajectory_id: str = Field(min_length=1)
    eval_attempt_id: str = Field(min_length=1)
    source_training_candidate_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    repair_artifact_type: RepairArtifactType
    repair_status: RepairStatus
    original_artifact_ref: ArtifactRef
    repaired_artifact_ref: ArtifactRef | None = None
    repairer_version: str = Field(min_length=1)
    repairer_code_hash: str = Field(min_length=1)
    repair: MechanicalRedundancyRepairDetails
    error_class: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_repair_contract(self) -> "TrainingCandidateRepairRecord":
        self._validate_hash_pinned_ref(
            self.original_artifact_ref,
            field_name="original_artifact_ref",
        )

        original_assessment = self.repair.original_mechanical_redundancy_assessment
        if original_assessment.evaluation_status != "complete":
            raise ValueError(
                "repair records require a complete original mechanical-"
                "redundancy assessment"
            )
        if not original_assessment.blocks:
            raise ValueError(
                "repair records require detected mechanical-redundancy blocks"
            )

        if self.repair_status == "completed":
            self._validate_completed_repair(original_assessment)
        elif self.repair_status == "cannot_complete":
            self._validate_cannot_complete_repair()
        else:
            self._validate_repair_error()
        return self

    def _validate_completed_repair(
        self,
        original_assessment: MechanicalRedundancyAssessment,
    ) -> None:
        repaired_ref = self.repaired_artifact_ref
        if repaired_ref is None:
            raise ValueError("completed repairs require repaired_artifact_ref")
        self._validate_hash_pinned_ref(
            repaired_ref,
            field_name="repaired_artifact_ref",
        )
        if repaired_ref.content_hash == self.original_artifact_ref.content_hash:
            raise ValueError(
                "completed repair content must differ from the original artifact"
            )

        after_assessment = self.repair.after_repair_mechanical_redundancy_assessment
        if after_assessment is None:
            raise ValueError(
                "completed repairs require an after-repair mechanical-redundancy "
                "assessment"
            )
        if after_assessment.evaluation_status != "complete":
            raise ValueError(
                "completed repairs require a complete after-repair assessment"
            )
        if after_assessment.blocks:
            raise ValueError(
                "completed repairs require zero after-repair redundancy blocks"
            )
        if (
            after_assessment.detector_version != original_assessment.detector_version
            or after_assessment.detector_code_hash
            != original_assessment.detector_code_hash
        ):
            raise ValueError(
                "before- and after-repair assessments must use the same detector"
            )
        if self.repair.cannot_complete_reason is not None:
            raise ValueError("completed repairs cannot include cannot_complete_reason")
        self._require_no_error_details(status="completed")

    def _validate_cannot_complete_repair(self) -> None:
        if self.repaired_artifact_ref is not None:
            raise ValueError(
                "cannot_complete repairs cannot include repaired_artifact_ref"
            )
        if self.repair.after_repair_mechanical_redundancy_assessment is not None:
            raise ValueError(
                "cannot_complete repairs cannot include an after-repair assessment"
            )
        if self.repair.cannot_complete_reason is None:
            raise ValueError("cannot_complete repairs require cannot_complete_reason")
        self._require_no_error_details(status="cannot_complete")

    def _validate_repair_error(self) -> None:
        if self.repaired_artifact_ref is not None:
            raise ValueError(
                "repair_error records cannot include repaired_artifact_ref"
            )
        if self.repair.after_repair_mechanical_redundancy_assessment is not None:
            raise ValueError(
                "repair_error records cannot include an after-repair assessment"
            )
        if self.repair.cannot_complete_reason is not None:
            raise ValueError(
                "repair_error records cannot include cannot_complete_reason"
            )
        if self.error_class is None or self.error_message is None:
            raise ValueError(
                "repair_error records require error_class and error_message"
            )

    def _require_no_error_details(self, *, status: str) -> None:
        if self.error_class is not None or self.error_message is not None:
            raise ValueError(f"{status} repairs cannot include error details")

    @staticmethod
    def _validate_hash_pinned_ref(
        artifact_ref: ArtifactRef,
        *,
        field_name: str,
    ) -> None:
        if artifact_ref.content_hash is None:
            raise ValueError(f"{field_name} must be content-hash pinned")


class TrainingCandidateRepairReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TrainingCandidateRepairReviewRecordSchemaVersion = (
        TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION
    )
    repair_id: str = Field(min_length=1)
    source_training_candidate_repair_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    review_status: ReviewStatus
    review_id: str | None = Field(default=None, min_length=1)
    reviewer_id: str | None = Field(default=None, min_length=1)
    review_decision: ReviewDecision | None = None
    review_notes_ref: ArtifactRef | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> "TrainingCandidateRepairReviewRecord":
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
                    "not_reviewed repair reviews cannot include review details"
                )
            return self

        if self.review_id is None:
            raise ValueError("reviewed repair reviews require review_id")
        if self.reviewer_id is None:
            raise ValueError("reviewed repair reviews require reviewer_id")
        if self.review_decision is None:
            raise ValueError("reviewed repair reviews require review_decision")
        return self
