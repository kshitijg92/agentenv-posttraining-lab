from typing import Protocol

from agentenv.models.schema import DecodingConfig, Message, ModelResponse


class ModelClient(Protocol):
    model_id: str

    def generate(
        self,
        messages: list[Message],
        decoding_config: DecodingConfig,
    ) -> ModelResponse: ...
