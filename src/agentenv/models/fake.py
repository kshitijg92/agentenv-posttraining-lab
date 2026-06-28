from dataclasses import dataclass, field
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.models.schema import DecodingConfig, Message, ModelFinishReason
from agentenv.models.schema import ModelResponse


class FakeModelScriptStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_text: str
    finish_reason: ModelFinishReason = "stop_criteria_met"
    error_class: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_error_class(self) -> "FakeModelScriptStep":
        if self.finish_reason in {"timeout", "error"}:
            if self.error_class is None:
                raise ValueError(
                    f"{self.finish_reason} script steps require error_class"
                )
            return self

        if self.error_class is not None:
            raise ValueError(
                f"{self.finish_reason} script steps cannot include error_class"
            )
        return self


@dataclass
class ScriptedFakeModelClient:
    model_id: str
    script: list[FakeModelScriptStep]
    raw_response_ref: str = "fake_model/raw_response.json"
    _next_index: int = field(default=0, init=False)

    @staticmethod
    def default_decoding_config() -> DecodingConfig:
        return DecodingConfig(
            strategy="greedy",
            temperature=0.0,
            top_p=1.0,
            max_new_tokens=512,
            timeout_seconds=30,
        )

    def generate(
        self,
        messages: list[Message],
        decoding_config: DecodingConfig,
    ) -> ModelResponse:
        # The scripted fake conforms to the model interface but stays deterministic.
        del messages
        del decoding_config

        started = perf_counter()
        if self._next_index >= len(self.script):
            return ModelResponse(
                model_id=self.model_id,
                output_text="",
                finish_reason="error",
                latency_ms=_latency_ms(started),
                error_class="FakeModelScriptExhausted",
                raw_response_ref=self.raw_response_ref,
            )

        step = self.script[self._next_index]
        self._next_index += 1
        return ModelResponse(
            model_id=self.model_id,
            output_text=step.output_text,
            finish_reason=step.finish_reason,
            latency_ms=_latency_ms(started),
            error_class=step.error_class,
            raw_response_ref=self.raw_response_ref,
        )


def _latency_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
