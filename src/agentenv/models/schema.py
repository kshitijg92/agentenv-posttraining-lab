from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat
from pydantic import StrictInt, StrictStr, field_validator, model_validator


MessageRole = Literal["system", "user", "assistant", "tool"]
MessageMetadataValue = StrictStr | StrictBool | StrictInt | StrictFloat | None
DecodingStrategy = Literal["greedy", "sampling"]
ModelFinishReason = Literal[
    "stop_criteria_met",
    "max_new_tokens_reached",
    "timeout",
    "error",
]


class MessageWithoutMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str
    name: str | None = Field(default=None, min_length=1)
    tool_call_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_tool_call_fields(self) -> "MessageWithoutMetadata":
        if self.role == "tool":
            if self.name is None:
                raise ValueError("tool messages require name")
            if self.tool_call_id is None:
                raise ValueError("tool messages require tool_call_id")
            return self

        if self.role in {"system", "user"} and self.tool_call_id is not None:
            raise ValueError(f"{self.role} messages cannot include tool_call_id")

        return self


class Message(MessageWithoutMetadata):
    metadata: dict[str, MessageMetadataValue] = Field(default_factory=dict)


class DecodingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: DecodingStrategy
    temperature: float = Field(ge=0.0, le=2.0)
    top_p: float = Field(gt=0.0, le=1.0)
    top_k: int | None = Field(default=None, gt=0)
    max_new_tokens: int = Field(gt=0)
    num_return_sequences: int = Field(default=1, ge=1)
    seed: int | None = Field(default=None, ge=0)
    stop: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(gt=0)

    @field_validator("stop")
    @classmethod
    def validate_stop_sequences(cls, stop: list[str]) -> list[str]:
        if any(sequence == "" for sequence in stop):
            raise ValueError("stop sequences cannot be empty")
        return stop

    @model_validator(mode="after")
    def validate_strategy_settings(self) -> "DecodingConfig":
        if self.strategy == "greedy" and self.temperature != 0.0:
            raise ValueError("greedy decoding requires temperature 0.0")
        if self.num_return_sequences != 1:
            raise ValueError("num_return_sequences must be 1 for v0")
        return self


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1)
    output_text: str
    finish_reason: ModelFinishReason
    latency_ms: int = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    error_class: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)
    raw_response_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_response_consistency(self) -> "ModelResponse":
        if self.prompt_tokens is not None and self.completion_tokens is not None:
            expected_total_tokens = self.prompt_tokens + self.completion_tokens
            if self.total_tokens != expected_total_tokens:
                raise ValueError(
                    "total_tokens must equal prompt_tokens + completion_tokens "
                    "when both token counts are present"
                )

        if self.finish_reason in {"timeout", "error"}:
            if self.error_class is None:
                raise ValueError(f"{self.finish_reason} responses require error_class")
            return self

        if self.error_class is not None or self.error_message is not None:
            raise ValueError(
                f"{self.finish_reason} responses cannot include error details"
            )
        return self
