from pathlib import Path

from agentenv.models.client import ModelClient
from agentenv.models.config_schema import (
    ModelConfig,
    OllamaGenerateModelConfig,
    OpenAICompatibleChatModelConfig,
    TransformersPeftModelConfig,
)
from agentenv.models.input_protocol import LoadedModelInputProtocol
from agentenv.models.ollama_generate import OllamaGenerateModelClient
from agentenv.models.openai_compatible_chat import OpenAICompatibleChatModelClient


def build_model_client(
    config: ModelConfig,
    *,
    model_input_protocol: LoadedModelInputProtocol | None = None,
    model_config_path: Path | None = None,
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
    if isinstance(config, TransformersPeftModelConfig):
        if model_input_protocol is None:
            raise ValueError("transformers_peft requires a loaded model input protocol")
        if model_config_path is None:
            raise ValueError("transformers_peft requires the model config path")

        from agentenv.models.config import load_transformers_peft_policy_binding
        from agentenv.models.transformers_peft import (
            load_transformers_peft_model_client,
        )

        binding = load_transformers_peft_policy_binding(
            config,
            model_config_path,
            model_input_protocol=model_input_protocol,
        )
        return load_transformers_peft_model_client(
            binding,
            model_input_protocol,
            device=config.runtime.device,
            weight_dtype=config.runtime.weight_dtype,
            attention_implementation=config.runtime.attention_implementation,
        )
    raise ValueError(f"Unsupported model provider: {config.provider}")
