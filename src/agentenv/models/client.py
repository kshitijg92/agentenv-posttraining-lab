from typing import Protocol

from agentenv.models.schema import DecodingConfig, Message, ModelResponse


class ModelClient(Protocol):
    @property
    def model_id(self) -> str: ...

    def generate(
        self,
        messages: list[Message],
        decoding_config: DecodingConfig,
    ) -> ModelResponse: ...
