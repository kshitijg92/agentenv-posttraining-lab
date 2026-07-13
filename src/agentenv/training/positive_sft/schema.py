from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.agents.schema import AgentTaskPromptInput
from agentenv.models.schema import MessageId, MessageWithoutMetadata
from agentenv.training.positive_sft.identity import build_positive_sft_example_id
from agentenv.trajectories.schema import ArtifactRef, ReviewDecision, ReviewStatus


PositiveSFTReviewRecordSchemaVersion = Literal["positive_sft_review_record_v0"]
PositiveSFTExampleRecordSchemaVersion = Literal["positive_sft_example_record_v0"]

POSITIVE_SFT_REVIEW_RECORD_SCHEMA_VERSION: PositiveSFTReviewRecordSchemaVersion = (
    "positive_sft_review_record_v0"
)
POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION: PositiveSFTExampleRecordSchemaVersion = (
    "positive_sft_example_record_v0"
)


class _PositiveSFTReviewSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_artifact_ref: ArtifactRef

    @model_validator(mode="after")
    def validate_source_artifact_is_hash_pinned(self) -> "_PositiveSFTReviewSource":
        if self.source_artifact_ref.content_hash is None:
            raise ValueError("positive-SFT review source artifact must be hash-pinned")
        return self


class OriginalPositiveSFTReviewSource(_PositiveSFTReviewSource):
    source_type: Literal["original"]


class RepairedPositiveSFTReviewSource(_PositiveSFTReviewSource):
    source_type: Literal["repaired"]
    repair_id: str = Field(min_length=1)
    source_training_candidate_repair_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    source_training_candidate_repair_review_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    repair_review_id: str = Field(min_length=1)


PositiveSFTReviewSource: TypeAlias = Annotated[
    OriginalPositiveSFTReviewSource | RepairedPositiveSFTReviewSource,
    Field(discriminator="source_type"),
]


class PositiveSFTReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: PositiveSFTReviewRecordSchemaVersion = (
        POSITIVE_SFT_REVIEW_RECORD_SCHEMA_VERSION
    )
    source_training_candidate_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    source: PositiveSFTReviewSource
    review_status: ReviewStatus
    review_id: str | None = Field(default=None, min_length=1)
    reviewer_id: str | None = Field(default=None, min_length=1)
    review_decision: ReviewDecision | None = None
    review_notes_ref: ArtifactRef | None = None
    last_approved_assistant_message_id: MessageId | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> "PositiveSFTReviewRecord":
        review_details = (
            self.review_id,
            self.reviewer_id,
            self.review_decision,
            self.review_notes_ref,
            self.last_approved_assistant_message_id,
        )
        if self.review_status == "not_reviewed":
            if any(value is not None for value in review_details):
                raise ValueError(
                    "not_reviewed positive-SFT reviews cannot include review details"
                )
            return self

        if self.review_id is None:
            raise ValueError("reviewed positive-SFT reviews require review_id")
        if self.reviewer_id is None:
            raise ValueError("reviewed positive-SFT reviews require reviewer_id")
        if self.review_decision is None:
            raise ValueError("reviewed positive-SFT reviews require review_decision")
        if self.review_decision == "accepted":
            if self.last_approved_assistant_message_id is None:
                raise ValueError(
                    "accepted positive-SFT reviews require an approved assistant "
                    "message boundary"
                )
        elif self.last_approved_assistant_message_id is not None:
            raise ValueError(
                "non-accepted positive-SFT reviews cannot authorize a message boundary"
            )
        return self


class PositiveSFTTaskInput(AgentTaskPromptInput):
    pass


class PositiveSFTMessage(MessageWithoutMetadata):
    pass


class PositiveSFTProvenanceIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trajectory_id: str = Field(min_length=1)
    eval_suite_id: str | None = Field(default=None, min_length=1)
    eval_run_id: str = Field(min_length=1)
    eval_attempt_id: str = Field(min_length=1)
    agent_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)


class PositiveSFTPromptProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_builder_version: str = Field(min_length=1)
    prompt_builder_code_hash: str = Field(min_length=1)


class PositiveSFTReviewProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_positive_sft_review_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    positive_sft_review_id: str = Field(min_length=1)
    last_approved_assistant_message_id: MessageId


class _PositiveSFTSourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_training_candidate_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    source_artifact_ref: ArtifactRef

    @model_validator(mode="after")
    def validate_source_artifact_is_hash_pinned(
        self,
    ) -> "_PositiveSFTSourceProvenance":
        if self.source_artifact_ref.content_hash is None:
            raise ValueError("positive SFT source artifact must be content-hash pinned")
        return self


class OriginalPositiveSFTSourceProvenance(_PositiveSFTSourceProvenance):
    source_type: Literal["original"]
    task_outcome_provenance: Literal["executed_source_trajectory"]


class RepairedPositiveSFTSourceProvenance(_PositiveSFTSourceProvenance):
    source_type: Literal["repaired"]
    repair_id: str = Field(min_length=1)
    source_training_candidate_repair_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    source_training_candidate_repair_review_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    repair_review_id: str = Field(min_length=1)
    task_outcome_provenance: Literal["inherited_from_source_trajectory"]
    task_outcome_inheritance_basis: Literal[
        "mechanical_redundancy_state_and_observation_preserving_deletion"
    ]


PositiveSFTSourceProvenance: TypeAlias = Annotated[
    OriginalPositiveSFTSourceProvenance | RepairedPositiveSFTSourceProvenance,
    Field(discriminator="source_type"),
]


class PositiveSFTExampleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: PositiveSFTExampleRecordSchemaVersion = (
        POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
    )
    example_id: str = Field(min_length=1)
    provenance_ids: PositiveSFTProvenanceIds
    prompt_provenance: PositiveSFTPromptProvenance
    review_provenance: PositiveSFTReviewProvenance
    source_provenance: PositiveSFTSourceProvenance
    task_input: PositiveSFTTaskInput
    messages: list[PositiveSFTMessage] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_positive_sft_contract(self) -> "PositiveSFTExampleRecord":
        source_artifact_hash = self.source_provenance.source_artifact_ref.content_hash
        if source_artifact_hash is None:
            raise ValueError("positive SFT source artifact must be content-hash pinned")
        source_repair_record_hash = (
            self.source_provenance.source_training_candidate_repair_record_hash
            if isinstance(
                self.source_provenance,
                RepairedPositiveSFTSourceProvenance,
            )
            else None
        )
        expected_example_id = build_positive_sft_example_id(
            source_type=self.source_provenance.source_type,
            source_training_candidate_record_hash=(
                self.source_provenance.source_training_candidate_record_hash
            ),
            source_artifact_content_hash=source_artifact_hash,
            source_positive_sft_review_record_hash=(
                self.review_provenance.source_positive_sft_review_record_hash
            ),
            source_training_candidate_repair_record_hash=source_repair_record_hash,
        )
        if self.example_id != expected_example_id:
            raise ValueError(
                "positive SFT example_id must be derived from its selected source"
            )

        if self.provenance_ids.task_id != self.task_input.task_id:
            raise ValueError("positive SFT provenance task_id must match task_input")

        if not any(message.role == "assistant" for message in self.messages):
            raise ValueError("positive SFT examples require an assistant message")

        message_ids = [message.message_id for message in self.messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("positive SFT message_ids must be unique")

        if self.messages[0].role != "system" or self.messages[1].role != "user":
            raise ValueError(
                "positive SFT messages must start with system and user messages"
            )

        if self.messages[-1].role != "assistant" or (
            self.messages[-1].message_id
            != self.review_provenance.last_approved_assistant_message_id
        ):
            raise ValueError(
                "positive SFT examples must end at their approved assistant boundary"
            )

        return self
