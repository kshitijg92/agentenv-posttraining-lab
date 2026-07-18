from agentenv.models.client import ModelClient
from agentenv.models.config_schema import (
    ModelConfig,
    OllamaGenerateModelConfig,
    OpenAICompatibleChatModelConfig,
)
from agentenv.models.input_protocol import LoadedModelInputProtocol
from agentenv.models.ollama_generate import OllamaGenerateModelClient
from agentenv.models.openai_compatible_chat import OpenAICompatibleChatModelClient


def build_model_client(
    config: ModelConfig,
    *,
    model_input_protocol: LoadedModelInputProtocol | None = None,
) -> ModelClient:
    if isinstance(config, OpenAICompatibleChatModelConfig):
        if model_input_protocol is not None:
            raise ValueError(
                "openai_compatible_chat cannot consume a model input protocol"
            )
        return OpenAICompatibleChatModelClient(config=config)
    if isinstance(config, OllamaGenerateModelConfig):
        if model_input_protocol is None:
            raise ValueError("ollama_generate requires a loaded model input protocol")
        return OllamaGenerateModelClient(
            config=config,
            model_input_protocol=model_input_protocol,
        )
    raise ValueError(f"Unsupported model provider: {config.provider}")
