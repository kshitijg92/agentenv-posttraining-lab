from agentenv.models.client import ModelClient
from agentenv.models.config_schema import ModelConfig
from agentenv.models.openai_compatible_chat import OpenAICompatibleChatModelClient


def build_model_client(config: ModelConfig) -> ModelClient:
    if config.provider == "openai_compatible_chat":
        return OpenAICompatibleChatModelClient(config=config)
    raise ValueError(f"Unsupported model provider: {config.provider}")
