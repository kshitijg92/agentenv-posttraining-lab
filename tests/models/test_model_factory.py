from pathlib import Path

import pytest

from agentenv.models.config import (
    load_model_config,
    load_referenced_model_input_protocol,
)
from agentenv.models.factory import build_model_client
from agentenv.models.ollama_generate import OllamaGenerateModelClient
from agentenv.models.openai_compatible_chat import OpenAICompatibleChatModelClient


def test_build_model_client_builds_openai_compatible_chat_client() -> None:
    config = load_model_config(
        Path("configs/models/openai_compatible_chat_placeholder.yaml")
    )

    model_client = build_model_client(config)

    assert isinstance(model_client, OpenAICompatibleChatModelClient)
    assert model_client.model_id == "placeholder-model"


def test_build_model_client_builds_ollama_generate_client_with_protocol() -> None:
    config_path = Path("configs/models/ollama_qwen2_5_coder_3b.yaml")
    config = load_model_config(config_path)
    protocol = load_referenced_model_input_protocol(config, config_path)

    model_client = build_model_client(
        config,
        model_input_protocol=protocol,
    )

    assert isinstance(model_client, OllamaGenerateModelClient)
    assert model_client.model_id == "qwen2.5-coder:3b"
    assert model_client.model_input_protocol.record.protocol_id == (
        "qwen2_5_coder_3b_agentenv_json"
    )


def test_build_ollama_model_client_requires_protocol() -> None:
    config = load_model_config(Path("configs/models/ollama_qwen2_5_coder_3b.yaml"))

    with pytest.raises(ValueError, match="requires a loaded model input protocol"):
        build_model_client(config)
