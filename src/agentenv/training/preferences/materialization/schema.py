from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


DPOTrainingMaterializationRecordSchemaVersion = Literal[
    "dpo_training_materialization_record_v0"
]
DPOTrainingMaterializationFailureKind = Literal[
    "sequence_length_exceeded",
    "materialization_error",
]

DPO_TRAINING_MATERIALIZATION_RECORD_SCHEMA_VERSION: DPOTrainingMaterializationRecordSchemaVersion = "dpo_training_materialization_record_v0"
TRAINER_IGNORE_INDEX = -100

PositiveInt = Annotated[int, Field(gt=0, strict=True)]
TokenId = Annotated[int, Field(ge=0, strict=True)]
TrainerLabel = Annotated[int, Field(strict=True)]


class _DPOTrainingMaterializationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: DPOTrainingMaterializationRecordSchemaVersion = (
        DPO_TRAINING_MATERIALIZATION_RECORD_SCHEMA_VERSION
    )
    source_preference_pair_id: str = Field(min_length=1)
    source_preference_pair_record_hash: str = Field(
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
    serialization_mode: Literal["shared_context_next_action"]
    max_sequence_length: PositiveInt
    materializer_version: str = Field(min_length=1)
    materializer_code_hash: str = Field(
        pattern=r"^xxh64:[0-9a-f]{16}$",
        strict=True,
    )


class CompletedDPOTrainingMaterializationRecord(_DPOTrainingMaterializationRecord):
    status: Literal["completed"]
    shared_prompt_token_count: PositiveInt
    chosen_input_ids: list[TokenId] = Field(min_length=1)
    chosen_labels: list[TrainerLabel] = Field(min_length=1)
    chosen_sequence_length: PositiveInt
    chosen_response_token_count: PositiveInt
    rejected_input_ids: list[TokenId] = Field(min_length=1)
    rejected_labels: list[TrainerLabel] = Field(min_length=1)
    rejected_sequence_length: PositiveInt
    rejected_response_token_count: PositiveInt

    @model_validator(mode="after")
    def validate_completed_materialization(
        self,
    ) -> "CompletedDPOTrainingMaterializationRecord":
        self._validate_branch(
            branch="chosen",
            input_ids=self.chosen_input_ids,
            labels=self.chosen_labels,
            sequence_length=self.chosen_sequence_length,
            response_token_count=self.chosen_response_token_count,
        )
        self._validate_branch(
            branch="rejected",
            input_ids=self.rejected_input_ids,
            labels=self.rejected_labels,
            sequence_length=self.rejected_sequence_length,
            response_token_count=self.rejected_response_token_count,
        )

        prompt_end = self.shared_prompt_token_count
        if self.chosen_input_ids[:prompt_end] != self.rejected_input_ids[:prompt_end]:
            raise ValueError(
                "chosen and rejected branches must have identical shared-prompt "
                "token ids"
            )
        if self.chosen_input_ids[prompt_end:] == self.rejected_input_ids[prompt_end:]:
            raise ValueError("chosen and rejected response token ids must differ")
        return self

    def _validate_branch(
        self,
        *,
        branch: str,
        input_ids: list[int],
        labels: list[int],
        sequence_length: int,
        response_token_count: int,
    ) -> None:
        if len(input_ids) != len(labels):
            raise ValueError(f"{branch} input_ids and labels must have the same length")
        if sequence_length != len(input_ids):
            raise ValueError(
                f"{branch}_sequence_length must equal the number of input_ids"
            )
        if sequence_length > self.max_sequence_length:
            raise ValueError(
                f"completed {branch} materialization cannot exceed max_sequence_length"
            )
        if self.shared_prompt_token_count >= sequence_length:
            raise ValueError(
                "shared_prompt_token_count must leave at least one response token "
                f"in the {branch} branch"
            )

        prompt_labels = labels[: self.shared_prompt_token_count]
        if any(label != TRAINER_IGNORE_INDEX for label in prompt_labels):
            raise ValueError(
                f"every {branch} shared-prompt label must use the trainer ignore index"
            )

        response_ids = input_ids[self.shared_prompt_token_count :]
        response_labels = labels[self.shared_prompt_token_count :]
        if any(
            label != token_id
            for token_id, label in zip(response_ids, response_labels, strict=True)
        ):
            raise ValueError(
                f"every {branch} response label must equal its corresponding "
                "input token id"
            )
        if response_token_count != len(response_ids):
            raise ValueError(
                f"{branch}_response_token_count must equal the number of scored "
                "response tokens"
            )


class FailedDPOTrainingMaterializationRecord(_DPOTrainingMaterializationRecord):
    status: Literal["failed"]
    failure_kind: DPOTrainingMaterializationFailureKind
    observed_chosen_sequence_length: PositiveInt | None = None
    observed_rejected_sequence_length: PositiveInt | None = None
    error_class: str = Field(min_length=1)
    error_message: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_failed_materialization(
        self,
    ) -> "FailedDPOTrainingMaterializationRecord":
        observed_lengths = (
            self.observed_chosen_sequence_length,
            self.observed_rejected_sequence_length,
        )
        if self.failure_kind == "sequence_length_exceeded":
            if any(length is None for length in observed_lengths):
                raise ValueError(
                    "sequence-length failures require observed lengths for both "
                    "branches"
                )
            if not any(
                length is not None and length > self.max_sequence_length
                for length in observed_lengths
            ):
                raise ValueError(
                    "sequence-length failures require at least one observed branch "
                    "length greater than max_sequence_length"
                )
        elif any(length is not None for length in observed_lengths):
            raise ValueError(
                "materialization errors cannot claim observed branch lengths"
            )
        return self


DPOTrainingMaterializationRecord: TypeAlias = Annotated[
    CompletedDPOTrainingMaterializationRecord | FailedDPOTrainingMaterializationRecord,
    Field(discriminator="status"),
]
