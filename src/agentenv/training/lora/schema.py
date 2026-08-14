from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PositiveInt = Annotated[int, Field(gt=0, strict=True)]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
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
            raise ValueError("CPU training requires float32 weights in this lab")
        return self


class OptimizerIsolationAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trainable_parameter_count: PositiveInt
    trainable_parameter_element_count: PositiveInt
    optimizer_parameter_count: PositiveInt
    optimizer_parameter_element_count: PositiveInt
    trainable_parameter_names_hash: ContentHash
    optimizer_parameter_names_hash: ContentHash
    exact_adapter_only_membership: Literal[True]


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
