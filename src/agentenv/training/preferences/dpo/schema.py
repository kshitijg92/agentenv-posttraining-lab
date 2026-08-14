from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.training.lora.schema import (
    AdapterRoundTripAudit,
    NonNegativeInt,
    OptimizerConfigRecord,
    OptimizerIsolationAudit,
    ParameterStateAudit,
    PositiveInt,
    TrainingRuntimeProvenance,
    TrainingRuntimeConfig,
)


DPO_LORA_TRAINING_CONFIG_SCHEMA_VERSION = "dpo_lora_training_config_v0"
DPO_LORA_TRAINING_RESULT_SCHEMA_VERSION = "dpo_lora_training_result_v0"
DPO_LORA_TRAINING_STEP_SCHEMA_VERSION = "dpo_lora_training_step_v0"


class DPOObjectiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loss: Literal["sigmoid"]
    beta: float = Field(gt=0.0, allow_inf_nan=False)
    response_log_probability_aggregation: Literal["sum"]
    reference_policy: Literal["frozen_parent"]


class DPOTrainingDataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_order: Literal["source_then_record"]
    shuffle: Literal[False]
    micro_batch_size: Literal[1]


class DPOLoRATrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["dpo_lora_training_config_v0"]
    config_id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    model_input_protocol_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9_]+$",
    )
    objective: DPOObjectiveConfig
    optimizer: OptimizerConfigRecord
    data: DPOTrainingDataConfig
    runtime: TrainingRuntimeConfig
    seed: NonNegativeInt
    max_steps: PositiveInt
    gradient_accumulation_steps: Literal[1]
    reload_probe_token_count: PositiveInt


class SelectedDPOTrainingPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_preference_pair_id: str = Field(min_length=1)
    source_materialization_record_hash: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    chosen_sequence_length: PositiveInt
    chosen_response_token_count: PositiveInt
    rejected_sequence_length: PositiveInt
    rejected_response_token_count: PositiveInt


class DPOInitializationAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_parent_adapter_state_hash: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    reference_adapter_state_hash: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    policy_adapter_state_hash_before: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    expected_parent_frozen_state_hash: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    reference_frozen_state_hash: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    policy_frozen_state_hash_before: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    compared_pair_count: PositiveInt
    maximum_absolute_log_probability_difference: float = Field(
        ge=0.0,
        allow_inf_nan=False,
    )
    policy_and_reference_start_identically: Literal[True]
    reference_log_probabilities_precomputed_before_optimization: Literal[True]

    @model_validator(mode="after")
    def validate_exact_parent_identity(self) -> "DPOInitializationAudit":
        adapter_hashes = {
            self.expected_parent_adapter_state_hash,
            self.reference_adapter_state_hash,
            self.policy_adapter_state_hash_before,
        }
        frozen_hashes = {
            self.expected_parent_frozen_state_hash,
            self.reference_frozen_state_hash,
            self.policy_frozen_state_hash_before,
        }
        if len(adapter_hashes) != 1:
            raise ValueError(
                "DPO policy/reference adapter states must match the parent"
            )
        if len(frozen_hashes) != 1:
            raise ValueError("DPO policy/reference frozen states must match the parent")
        if self.maximum_absolute_log_probability_difference != 0.0:
            raise ValueError("DPO policy/reference must have exact step-zero log probs")
        return self


class DPOLoRATrainingStepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["dpo_lora_training_step_v0"] = (
        DPO_LORA_TRAINING_STEP_SCHEMA_VERSION
    )
    step_index: NonNegativeInt
    source_preference_pair_id: str = Field(min_length=1)
    source_materialization_record_hash: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$")
    chosen_response_prediction_count: PositiveInt
    rejected_response_prediction_count: PositiveInt
    policy_chosen_log_probability: float = Field(allow_inf_nan=False)
    policy_rejected_log_probability: float = Field(allow_inf_nan=False)
    reference_chosen_log_probability: float = Field(allow_inf_nan=False)
    reference_rejected_log_probability: float = Field(allow_inf_nan=False)
    loss: float = Field(ge=0.0, allow_inf_nan=False)
    chosen_reward: float = Field(allow_inf_nan=False)
    rejected_reward: float = Field(allow_inf_nan=False)
    reward_margin: float = Field(allow_inf_nan=False)
    adapter_gradient_norm_before_clipping: float = Field(
        ge=0.0,
        allow_inf_nan=False,
    )


class DPOLoRATrainingAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initialization: DPOInitializationAudit
    optimizer_isolation: OptimizerIsolationAudit
    parameter_state: ParameterStateAudit
    adapter_round_trip: AdapterRoundTripAudit


class CompletedDPOLoRATrainingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["dpo_lora_training_result_v0"] = (
        DPO_LORA_TRAINING_RESULT_SCHEMA_VERSION
    )
    training_run_id: str = Field(
        min_length=1,
        pattern=r"^dpo_lora_run_[0-9a-f]{32}$",
    )
    status: Literal["completed"]
    started_at: str = Field(min_length=1)
    finished_at: str = Field(min_length=1)
    selected_pairs: tuple[SelectedDPOTrainingPair, ...] = Field(min_length=1)
    requested_step_count: PositiveInt
    completed_step_count: PositiveInt
    runtime_provenance: TrainingRuntimeProvenance
    audit: DPOLoRATrainingAudit

    @model_validator(mode="after")
    def validate_completed_steps(self) -> "CompletedDPOLoRATrainingResult":
        if self.completed_step_count != self.requested_step_count:
            raise ValueError("completed DPO training requires every requested step")
        return self
