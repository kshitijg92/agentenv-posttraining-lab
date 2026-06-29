from pathlib import Path

from agentenv.models.config import load_model_config
from agentenv.models.factory import build_model_client
from agentenv.models.openai_compatible_chat import OpenAICompatibleChatModelClient


def test_build_model_client_builds_openai_compatible_chat_client() -> None:
    config = load_model_config(
        Path("configs/models/openai_compatible_chat_placeholder.yaml")
    )

    model_client = build_model_client(config)

    assert isinstance(model_client, OpenAICompatibleChatModelClient)
    assert model_client.model_id == "placeholder-model"
