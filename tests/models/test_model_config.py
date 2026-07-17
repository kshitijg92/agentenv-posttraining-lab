from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.artifacts.payloads import DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION
from agentenv.artifacts.payloads import MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION
from agentenv.models.config import (
    load_decoding_config,
    load_model_config,
    load_referenced_model_input_protocol,
)
from agentenv.models.config_schema import (
    OllamaGenerateModelConfig,
    OpenAICompatibleChatModelConfig,
)
from agentenv.orchestrators.agent_task_run import (
    decoding_config_provenance_artifact,
    generated_decoding_config_provenance_artifact,
    model_config_provenance_artifact,
)


MODEL_CONFIG = Path("configs/models/openai_compatible_chat_placeholder.yaml")
DECODING_CONFIG = Path("configs/decoding/greedy_1024.yaml")
QWEN2_5_3B_MODEL_CONFIG = Path("configs/models/ollama_qwen2_5_coder_3b.yaml")
QWEN2_5_OPENAI_COMPATIBLE_MODEL_CONFIGS = (
    Path("configs/models/ollama_qwen2_5_coder_7b.yaml"),
    Path("configs/models/ollama_qwen2_5_coder_14b.yaml"),
)


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
    assert config.agent_action_format == "prompt_only"


@pytest.mark.parametrize("config_path", QWEN2_5_OPENAI_COMPATIBLE_MODEL_CONFIGS)
def test_qwen2_5_configs_do_not_inject_qwen3_thinking_switch(
    config_path: Path,
) -> None:
    config = load_model_config(config_path)

    assert isinstance(config, OpenAICompatibleChatModelConfig)
    assert config.prompt_adapter is None


def test_qwen2_5_3b_config_pins_agentenv_owned_input_protocol() -> None:
    config = load_model_config(QWEN2_5_3B_MODEL_CONFIG)

    assert isinstance(config, OllamaGenerateModelConfig)
    assert config.provider == "ollama_generate"
    assert config.base_url_env == "AGENTENV_OLLAMA_BASE_URL"
    assert config.model_manifest_digest == (
        "sha256:f72c60cabf6237b07f6e632b2c48d533"
        "cef25eda2efbd34bed21c5e9c01e6225"
    )
    assert config.model_input_protocol.path == (
        "../model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
    )
    assert config.model_input_protocol.content_hash == ("xxh64:eb0a73b2d5c4174a")
    assert config.capabilities.supports_seed is True
    assert config.capabilities.supports_stop is True
    assert config.capabilities.supports_top_k is True

    protocol = load_referenced_model_input_protocol(
        config,
        QWEN2_5_3B_MODEL_CONFIG,
    )
    assert protocol is not None
    assert protocol.record.protocol_id == "qwen2_5_coder_3b_agentenv_json"


def test_referenced_model_input_protocol_rejects_hash_drift() -> None:
    config = load_model_config(QWEN2_5_3B_MODEL_CONFIG)
    assert isinstance(config, OllamaGenerateModelConfig)
    drifted_ref = config.model_input_protocol.model_copy(
        update={"content_hash": "xxh64:0000000000000000"}
    )
    drifted_config = config.model_copy(update={"model_input_protocol": drifted_ref})

    with pytest.raises(ValueError, match="Model input protocol hash mismatch"):
        load_referenced_model_input_protocol(
            drifted_config,
            QWEN2_5_3B_MODEL_CONFIG,
        )


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
        "agent_action_format": "prompt_only",
        "prompt_adapter": None,
        "provider": "openai_compatible_chat",
        "version": "model_config_v0",
    }
    assert artifact["model_input_protocol"] is None


def test_ollama_model_config_provenance_persists_resolved_input_protocol() -> None:
    config = load_model_config(QWEN2_5_3B_MODEL_CONFIG)
    assert isinstance(config, OllamaGenerateModelConfig)
    protocol = load_referenced_model_input_protocol(
        config,
        QWEN2_5_3B_MODEL_CONFIG,
    )
    assert protocol is not None

    artifact = model_config_provenance_artifact(
        model_config=config,
        model_config_path=QWEN2_5_3B_MODEL_CONFIG,
        model_config_hash="xxh64:modelconfig000",
        model_input_protocol=protocol,
    ).model_dump(mode="json")

    protocol_provenance = artifact["model_input_protocol"]
    assert protocol_provenance is not None
    assert protocol_provenance["source_path"] == str(protocol.source_path)
    assert protocol_provenance["source_hash"] == (
        config.model_input_protocol.content_hash
    )
    assert protocol_provenance["protocol"]["protocol_id"] == (
        "qwen2_5_coder_3b_agentenv_json"
    )


def test_ollama_model_config_provenance_requires_resolved_input_protocol() -> None:
    config = load_model_config(QWEN2_5_3B_MODEL_CONFIG)

    with pytest.raises(
        ValidationError,
        match="ollama_generate provenance requires model_input_protocol",
    ):
        model_config_provenance_artifact(
            model_config=config,
            model_config_path=QWEN2_5_3B_MODEL_CONFIG,
            model_config_hash="xxh64:modelconfig000",
        )


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
