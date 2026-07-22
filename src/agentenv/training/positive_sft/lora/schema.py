from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin


POSITIVE_SFT_LORA_TRAINING_CONFIG_SCHEMA_VERSION = (
    "positive_sft_lora_training_config_v0"
)
POSITIVE_SFT_LORA_TRAINING_RESULT_SCHEMA_VERSION = (
    "positive_sft_lora_training_result_v0"
)
POSITIVE_SFT_LORA_TRAINING_STEP_SCHEMA_VERSION = "positive_sft_lora_training_step_v0"

PositiveInt = Annotated[int, Field(gt=0, strict=True)]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
AtLeastTwoInt = Annotated[int, Field(ge=2, strict=True)]
ContentHash = Annotated[str, Field(pattern=r"^xxh64:[0-9a-f]{16}$", strict=True)]
LoRATargetModule = Literal[
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]
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


class LoRAConfigRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: PositiveInt
    scale: float = Field(allow_inf_nan=False)
    dropout: float = Field(ge=0.0, lt=1.0, allow_inf_nan=False)
    target_modules: tuple[LoRATargetModule, ...] = Field(min_length=1)
    bias: Literal["none"]
    use_rslora: Literal[False]
    use_dora: Literal[False]
    init_lora_weights: Literal[True]

    @field_validator("scale")
    @classmethod
    def validate_scale_one(cls, value: float) -> float:
        if value != 1.0:
            raise ValueError("ordinary LoRA experiments require scale exactly 1.0")
        return value

    @field_validator("target_modules")
    @classmethod
    def validate_unique_target_modules(
        cls,
        value: tuple[LoRATargetModule, ...],
    ) -> tuple[LoRATargetModule, ...]:
        if len(value) != len(set(value)):
            raise ValueError("LoRA target_modules must be unique")
        return value

    @property
    def alpha(self) -> int:
        return self.rank


class OptimizerConfigRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optimizer: Literal["adamw"]
    learning_rate: float = Field(gt=0.0, allow_inf_nan=False)
    beta1: float = Field(ge=0.0, lt=1.0, allow_inf_nan=False)
    beta2: float = Field(ge=0.0, lt=1.0, allow_inf_nan=False)
    epsilon: float = Field(gt=0.0, allow_inf_nan=False)
    weight_decay: float = Field(ge=0.0, allow_inf_nan=False)
    max_gradient_norm: float = Field(gt=0.0, allow_inf_nan=False)
    schedule: Literal["constant"]


class TrainingDataSelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_policy: Literal["completed_manifest_order_prefix"]
    max_examples: PositiveInt
    shuffle: Literal[False]
    micro_batch_size: Literal[1]


class TrainingRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: Literal["cuda", "cpu"]
    weight_dtype: Literal["bfloat16", "float32"]
    attention_implementation: Literal["sdpa", "eager"]
    gradient_checkpointing: bool
    deterministic_algorithms: Literal[True]
    cublas_workspace_config: Literal[":4096:8"]

    @model_validator(mode="after")
    def validate_device_dtype(self) -> "TrainingRuntimeConfig":
        if self.device == "cpu" and self.weight_dtype == "bfloat16":
            raise ValueError("CPU smoke training requires float32 weights in this lab")
        return self


class PositiveSFTLoRATrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["positive_sft_lora_training_config_v0"]
    config_id: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    purpose: Literal["operational_smoke"]
    model_input_protocol_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9_]+$",
    )
    base_model: HuggingFaceRevisionPin
    lora: LoRAConfigRecord
    optimizer: OptimizerConfigRecord
    data: TrainingDataSelectionConfig
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


class OptimizerIsolationAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trainable_parameter_count: PositiveInt
    trainable_parameter_element_count: PositiveInt
    optimizer_parameter_count: PositiveInt
    optimizer_parameter_element_count: PositiveInt
    trainable_parameter_names_hash: ContentHash
    optimizer_parameter_names_hash: ContentHash
    exact_adapter_only_membership: Literal[True]


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


class ParameterStateAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frozen_parameter_count: PositiveInt
    frozen_parameter_element_count: PositiveInt
    frozen_state_hash_before: ContentHash
    frozen_state_hash_after: ContentHash
    frozen_state_exactly_unchanged: Literal[True]
    adapter_parameter_count: PositiveInt
    adapter_parameter_element_count: PositiveInt
    adapter_state_hash_before: ContentHash
    adapter_state_hash_after: ContentHash
    adapter_state_changed: Literal[True]


class AdapterRoundTripAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persisted_adapter_directory_hash: ContentHash
    trained_frozen_state_hash: ContentHash
    reloaded_frozen_state_hash: ContentHash
    frozen_base_state_exactly_reloaded: Literal[True]
    trained_adapter_state_hash: ContentHash
    reloaded_adapter_state_hash: ContentHash
    adapter_state_exactly_reloaded: Literal[True]
    probe_token_count: PositiveInt
    trained_probe_logits_hash: ContentHash
    reloaded_probe_logits_hash: ContentHash
    maximum_absolute_logit_difference: float = Field(
        ge=0.0,
        allow_inf_nan=False,
    )
    probe_logits_exactly_equal: Literal[True]


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
        if [step.step_index for step in self.steps] != list(
            range(expected_step_count)
        ):
            raise ValueError("qualification step indexes must begin at zero")
        return self


class TrainingRuntimeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    torch_version: str = Field(min_length=1)
    transformers_version: str = Field(min_length=1)
    peft_version: str = Field(min_length=1)
    accelerate_version: str = Field(min_length=1)
    requested_device: Literal["cuda", "cpu"]
    observed_device: str = Field(min_length=1)
    accelerator_name: str | None
    accelerator_total_memory_bytes: PositiveInt | None
    torch_cuda_version: str | None
    cublas_workspace_config: Literal[":4096:8"]
    git_sha_or_unknown: str = Field(min_length=1)
    git_worktree_dirty: bool
    git_diff_hash: ContentHash
    trainer_code_hash: ContentHash


class _PositiveSFTLoRATrainingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["positive_sft_lora_training_result_v0"] = (
        POSITIVE_SFT_LORA_TRAINING_RESULT_SCHEMA_VERSION
    )
    training_run_id: str = Field(
        min_length=1,
        pattern=r"^positive_sft_lora_run_[0-9a-f]{32}$",
    )
    purpose: Literal["operational_smoke"]
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
            raise ValueError(
                "training adapter initialization must match qualification"
            )
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
