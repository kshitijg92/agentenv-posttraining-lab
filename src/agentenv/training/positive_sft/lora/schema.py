from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.training.lora.schema import (
    AdapterRoundTripAudit,
    ContentHash,
    LoRAConfigRecord,
    NonNegativeInt,
    OptimizerConfigRecord,
    OptimizerIsolationAudit,
    ParameterStateAudit,
    PositiveInt,
    TrainingRuntimeConfig,
    TrainingRuntimeProvenance,
)


POSITIVE_SFT_LORA_TRAINING_CONFIG_SCHEMA_VERSION = (
    "positive_sft_lora_training_config_v0"
)
POSITIVE_SFT_LORA_TRAINING_RESULT_SCHEMA_VERSION = (
    "positive_sft_lora_training_result_v0"
)
POSITIVE_SFT_LORA_TRAINING_STEP_SCHEMA_VERSION = "positive_sft_lora_training_step_v0"

AtLeastTwoInt = Annotated[int, Field(ge=2, strict=True)]
TrainingFailureStage = Literal[
    "source_validation",
    "runtime_validation",
    "qualification_model_loading",
    "adapter_initialization",
    "qualification",
    "training_model_loading",
    "training",
    "verification",
    "adapter_persistence",
    "adapter_reload",
    "artifact_persistence",
]
TrainingTreatment = Literal["raw", "efficiency_filtered"]


class TrainingDataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    treatment: TrainingTreatment
    target_supervised_token_count: PositiveInt
    supervised_token_tolerance: NonNegativeInt
    shuffle: Literal[False]
    micro_batch_size: Literal[1]


class PositiveSFTLoRATrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["positive_sft_lora_training_config_v0"]
    config_id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    model_input_protocol_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9_]+$",
    )
    base_model: HuggingFaceRevisionPin
    lora: LoRAConfigRecord
    optimizer: OptimizerConfigRecord
    data: TrainingDataConfig
    runtime: TrainingRuntimeConfig
    seed: NonNegativeInt
    max_steps: PositiveInt
    qualification_step_count: AtLeastTwoInt
    gradient_accumulation_steps: Literal[1]
    reload_probe_token_count: PositiveInt


class SelectedPositiveSFTTrainingExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_positive_sft_example_id: str = Field(min_length=1)
    source_materialization_record_hash: ContentHash
    sequence_length: PositiveInt
    stored_supervised_token_count: PositiveInt
    effective_shifted_supervised_token_count: PositiveInt
    ignored_prediction_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_prediction_accounting(self) -> "SelectedPositiveSFTTrainingExample":
        if (
            self.effective_shifted_supervised_token_count
            + self.ignored_prediction_count
            != self.sequence_length - 1
        ):
            raise ValueError(
                "effective supervised and ignored predictions must cover exactly "
                "the shifted causal targets"
            )
        if (
            self.stored_supervised_token_count
            != self.effective_shifted_supervised_token_count
        ):
            raise ValueError(
                "every stored supervised label must be reachable after causal shift"
            )
        return self


class PositiveSFTLoRATrainingStepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["positive_sft_lora_training_step_v0"] = (
        POSITIVE_SFT_LORA_TRAINING_STEP_SCHEMA_VERSION
    )
    step_index: NonNegativeInt
    source_positive_sft_example_id: str = Field(min_length=1)
    source_materialization_record_hash: ContentHash
    sequence_length: PositiveInt
    supervised_prediction_count: PositiveInt
    ignored_prediction_count: NonNegativeInt
    loss: float = Field(allow_inf_nan=False)
    adapter_gradient_norm_before_clipping: float = Field(
        ge=0.0,
        allow_inf_nan=False,
    )


class AdapterParameterQualificationAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter_name: str = Field(min_length=1)
    logical_adapter_name: str = Field(min_length=1)
    factor: Literal["A", "B"]
    gradient_observed_during_qualification: bool
    nonzero_gradient_observed_during_qualification: bool
    all_qualification_gradients_finite: bool
    parameter_changed_during_qualification: bool


class AdapterQualificationAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qualification_step_count: AtLeastTwoInt
    intended_logical_adapter_count: PositiveInt
    observed_logical_adapter_count: PositiveInt
    adapter_parameter_count: PositiveInt
    every_logical_adapter_received_finite_nonzero_gradient_during_qualification: (
        Literal[True]
    )
    every_logical_adapter_changed_during_qualification: Literal[True]
    parameters: tuple[AdapterParameterQualificationAudit, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_qualification_audit(self) -> "AdapterQualificationAudit":
        if self.observed_logical_adapter_count != self.intended_logical_adapter_count:
            raise ValueError("observed logical adapter count must equal intended count")
        if self.adapter_parameter_count != len(self.parameters):
            raise ValueError("adapter_parameter_count must equal parameter audit rows")
        logical_names = {record.logical_adapter_name for record in self.parameters}
        if len(logical_names) != self.observed_logical_adapter_count:
            raise ValueError(
                "observed_logical_adapter_count must equal unique logical adapters"
            )
        return self


class PositiveSFTLoRAQualificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: tuple[PositiveSFTLoRATrainingStepRecord, ...] = Field(min_length=2)
    optimizer_isolation: OptimizerIsolationAudit
    adapter_qualification: AdapterQualificationAudit
    parameter_state: ParameterStateAudit

    @model_validator(mode="after")
    def validate_qualification_steps(self) -> "PositiveSFTLoRAQualificationResult":
        expected_step_count = self.adapter_qualification.qualification_step_count
        if len(self.steps) != expected_step_count:
            raise ValueError(
                "qualification step records must match qualification_step_count"
            )
        if [step.step_index for step in self.steps] != list(range(expected_step_count)):
            raise ValueError("qualification step indexes must begin at zero")
        return self


class _PositiveSFTLoRATrainingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["positive_sft_lora_training_result_v0"] = (
        POSITIVE_SFT_LORA_TRAINING_RESULT_SCHEMA_VERSION
    )
    training_run_id: str = Field(
        min_length=1,
        pattern=r"^positive_sft_lora_run_[0-9a-f]{32}$",
    )
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    selected_examples: tuple[SelectedPositiveSFTTrainingExample, ...]
    requested_step_count: PositiveInt
    completed_step_count: NonNegativeInt
    runtime_provenance: TrainingRuntimeProvenance


class CompletedPositiveSFTLoRATrainingResult(_PositiveSFTLoRATrainingResult):
    status: Literal["completed"]
    completed_step_count: PositiveInt
    qualification: PositiveSFTLoRAQualificationResult
    training_initial_adapter_state_matches_qualification: Literal[True]
    training_initial_frozen_state_matches_qualification: Literal[True]
    optimizer_isolation: OptimizerIsolationAudit
    parameter_state: ParameterStateAudit
    adapter_round_trip: AdapterRoundTripAudit

    @model_validator(mode="after")
    def validate_completed_steps(self) -> "CompletedPositiveSFTLoRATrainingResult":
        if not self.selected_examples:
            raise ValueError("completed training requires selected examples")
        if self.completed_step_count != self.requested_step_count:
            raise ValueError(
                "completed training requires every requested optimization step"
            )
        if self.optimizer_isolation != self.qualification.optimizer_isolation:
            raise ValueError(
                "qualification and training optimizer isolation must match"
            )
        if (
            self.parameter_state.adapter_state_hash_before
            != self.qualification.parameter_state.adapter_state_hash_before
        ):
            raise ValueError("training adapter initialization must match qualification")
        if (
            self.parameter_state.frozen_state_hash_before
            != self.qualification.parameter_state.frozen_state_hash_before
        ):
            raise ValueError("training frozen initialization must match qualification")
        return self


class FailedPositiveSFTLoRATrainingResult(_PositiveSFTLoRATrainingResult):
    status: Literal["failed"]
    qualification: PositiveSFTLoRAQualificationResult | None = None
    failure_stage: TrainingFailureStage
    error_class: str = Field(min_length=1)
    error_message: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_failed_steps(self) -> "FailedPositiveSFTLoRATrainingResult":
        if self.completed_step_count > self.requested_step_count:
            raise ValueError("completed_step_count cannot exceed requested_step_count")
        return self


PositiveSFTLoRATrainingResult = Annotated[
    CompletedPositiveSFTLoRATrainingResult | FailedPositiveSFTLoRATrainingResult,
    Field(discriminator="status"),
]
