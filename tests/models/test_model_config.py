from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.artifacts.payloads import DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION
from agentenv.artifacts.payloads import MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION
from agentenv.models.config import load_decoding_config, load_model_config
from agentenv.models.config_schema import OpenAICompatibleChatModelConfig
from agentenv.orchestrators.agent_task_run import (
    decoding_config_provenance_artifact,
    generated_decoding_config_provenance_artifact,
    model_config_provenance_artifact,
)


MODEL_CONFIG = Path("configs/models/openai_compatible_chat_placeholder.yaml")
DECODING_CONFIG = Path("configs/decoding/greedy_1024.yaml")


def test_load_model_config_reads_openai_compatible_chat_config() -> None:
    config = load_model_config(MODEL_CONFIG)

    assert config.version == "model_config_v0"
    assert config.provider == "openai_compatible_chat"
    assert config.model_id == "placeholder-model"
    assert config.api_key_env == "AGENTENV_MODEL_API_KEY"
    assert config.base_url_env == "AGENTENV_MODEL_BASE_URL"
    assert config.capabilities.token_usage == "native"
    assert config.capabilities.supports_seed is False
    assert config.capabilities.supports_stop is True
    assert config.capabilities.supports_top_k is False
    assert config.prompt_adapter is None


def test_load_decoding_config_reads_generation_config() -> None:
    config = load_decoding_config(DECODING_CONFIG)

    assert config.strategy == "greedy"
    assert config.temperature == 0.0
    assert config.top_p == 1.0
    assert config.top_k is None
    assert config.max_new_tokens == 1024
    assert config.num_return_sequences == 1
    assert config.seed is None
    assert config.stop == []
    assert config.timeout_seconds == 60


def test_model_config_provenance_artifact_records_sanitized_config() -> None:
    config = load_model_config(MODEL_CONFIG)

    artifact = model_config_provenance_artifact(
        model_config=config,
        model_config_path=MODEL_CONFIG,
        model_config_hash="xxh64:testhash",
    ).model_dump(mode="json")

    assert artifact["schema_version"] == MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION
    assert artifact["source_path"] == str(MODEL_CONFIG)
    assert artifact["source_hash"] == "xxh64:testhash"
    assert artifact["config"] == {
        "api_key_env": "AGENTENV_MODEL_API_KEY",
        "base_url_env": "AGENTENV_MODEL_BASE_URL",
        "capabilities": {
            "supports_seed": False,
            "supports_stop": True,
            "supports_top_k": False,
            "token_usage": "native",
        },
        "model_id": "placeholder-model",
        "prompt_adapter": None,
        "provider": "openai_compatible_chat",
        "version": "model_config_v0",
    }


def test_file_backed_decoding_config_provenance_artifact_records_source() -> None:
    config = load_decoding_config(DECODING_CONFIG)

    artifact = decoding_config_provenance_artifact(
        decoding_config=config,
        decoding_config_path=DECODING_CONFIG,
        decoding_config_hash="xxh64:testhash",
    ).model_dump(mode="json")

    assert artifact["schema_version"] == DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION
    assert artifact["source_path"] == str(DECODING_CONFIG)
    assert artifact["source_hash"] == "xxh64:testhash"
    assert artifact["config"]["max_new_tokens"] == 1024
    assert artifact["config"]["timeout_seconds"] == 60


def test_generated_decoding_config_provenance_artifact_records_null_source() -> None:
    config = load_decoding_config(DECODING_CONFIG)

    artifact = generated_decoding_config_provenance_artifact(config).model_dump(
        mode="json"
    )

    assert artifact["schema_version"] == DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION
    assert artifact["source_path"] is None
    assert artifact["source_hash"] is None
    assert artifact["config"]["max_new_tokens"] == 1024
    assert artifact["config"]["timeout_seconds"] == 60


@pytest.mark.parametrize("env_var_name", ["1BAD", "BAD-NAME", "BAD NAME"])
def test_model_config_rejects_invalid_env_var_names(env_var_name: str) -> None:
    with pytest.raises(ValidationError, match="environment variable names"):
        OpenAICompatibleChatModelConfig.model_validate(
            {
                "version": "model_config_v0",
                "provider": "openai_compatible_chat",
                "model_id": "some-model",
                "api_key_env": env_var_name,
                "base_url_env": "AGENTENV_MODEL_BASE_URL",
                "capabilities": {
                    "token_usage": "native",
                    "supports_seed": False,
                    "supports_stop": True,
                    "supports_top_k": False,
                },
            }
        )


def test_model_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleChatModelConfig.model_validate(
            {
                "version": "model_config_v0",
                "provider": "openai_compatible_chat",
                "model_id": "some-model",
                "api_key_env": "AGENTENV_MODEL_API_KEY",
                "base_url_env": "AGENTENV_MODEL_BASE_URL",
                "temperature": 0.0,
                "capabilities": {
                    "token_usage": "native",
                    "supports_seed": False,
                    "supports_stop": True,
                    "supports_top_k": False,
                },
            }
        )
