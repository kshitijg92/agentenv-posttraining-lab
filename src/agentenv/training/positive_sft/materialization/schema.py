from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


PositiveSFTMaterializationRecordSchemaVersion = Literal[
    "positive_sft_materialization_record_v0"
]
PositiveSFTMaterializationFailureKind = Literal[
    "sequence_length_exceeded",
    "materialization_error",
]

POSITIVE_SFT_MATERIALIZATION_RECORD_SCHEMA_VERSION: (
    PositiveSFTMaterializationRecordSchemaVersion
) = "positive_sft_materialization_record_v0"
TRAINER_IGNORE_INDEX = -100

PositiveInt = Annotated[int, Field(gt=0, strict=True)]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
TokenId = Annotated[int, Field(ge=0, strict=True)]
TrainerLabel = Annotated[int, Field(strict=True)]


class _PositiveSFTMaterializationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: PositiveSFTMaterializationRecordSchemaVersion = (
        POSITIVE_SFT_MATERIALIZATION_RECORD_SCHEMA_VERSION
    )
    source_positive_sft_example_id: str = Field(min_length=1)
    source_positive_sft_example_record_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    model_input_protocol_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9_]+$",
    )
    model_input_protocol_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )
    serialization_mode: Literal["completed_transcript"]
    max_sequence_length: PositiveInt
    materializer_version: str = Field(min_length=1)
    materializer_code_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )


class CompletedPositiveSFTMaterializationRecord(
    _PositiveSFTMaterializationRecord
):
    status: Literal["completed"]
    input_ids: list[TokenId] = Field(min_length=1)
    labels: list[TrainerLabel] = Field(min_length=1)
    sequence_length: PositiveInt
    supervised_token_count: PositiveInt
    ignored_token_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_completed_materialization(
        self,
    ) -> "CompletedPositiveSFTMaterializationRecord":
        if len(self.input_ids) != len(self.labels):
            raise ValueError("input_ids and labels must have the same length")
        if self.sequence_length != len(self.input_ids):
            raise ValueError("sequence_length must equal the number of input_ids")
        if self.sequence_length > self.max_sequence_length:
            raise ValueError(
                "completed materializations cannot exceed max_sequence_length"
            )

        invalid_label_indexes = [
            index
            for index, (token_id, label) in enumerate(zip(self.input_ids, self.labels))
            if label != TRAINER_IGNORE_INDEX and label != token_id
        ]
        if invalid_label_indexes:
            raise ValueError(
                "each label must be either the trainer ignore index or its "
                "corresponding input token id"
            )

        supervised_count = sum(
            label != TRAINER_IGNORE_INDEX for label in self.labels
        )
        ignored_count = self.sequence_length - supervised_count
        if self.supervised_token_count != supervised_count:
            raise ValueError(
                "supervised_token_count must equal the number of non-ignored labels"
            )
        if self.ignored_token_count != ignored_count:
            raise ValueError(
                "ignored_token_count must equal the number of ignored labels"
            )
        return self


class FailedPositiveSFTMaterializationRecord(_PositiveSFTMaterializationRecord):
    status: Literal["failed"]
    failure_kind: PositiveSFTMaterializationFailureKind
    observed_sequence_length: PositiveInt | None = None
    error_class: str = Field(min_length=1)
    error_message: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_failed_materialization(
        self,
    ) -> "FailedPositiveSFTMaterializationRecord":
        if self.failure_kind == "sequence_length_exceeded":
            if self.observed_sequence_length is None:
                raise ValueError(
                    "sequence-length failures require observed_sequence_length"
                )
            if self.observed_sequence_length <= self.max_sequence_length:
                raise ValueError(
                    "sequence-length failures require an observed length greater "
                    "than max_sequence_length"
                )
        return self


PositiveSFTMaterializationRecord: TypeAlias = Annotated[
    CompletedPositiveSFTMaterializationRecord
    | FailedPositiveSFTMaterializationRecord,
    Field(discriminator="status"),
]
