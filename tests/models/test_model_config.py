import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.artifacts.payloads import DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION
from agentenv.artifacts.payloads import MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION
from agentenv.hashing import hash_file
from agentenv.models.config import (
    load_decoding_config,
    load_model_config,
    load_referenced_model_input_protocol,
    load_transformers_peft_policy_binding,
)
from agentenv.models.config_schema import (
    OllamaGenerateModelConfig,
    OpenAICompatibleChatModelConfig,
    TransformersPeftModelConfig,
)
from agentenv.models.runtime_schema import OllamaProviderRuntimeProvenance
from agentenv.orchestrators.agent_task_run import (
    decoding_config_provenance_artifact,
    generated_decoding_config_provenance_artifact,
    model_config_provenance_artifact,
)


MODEL_CONFIG = Path("configs/models/openai_compatible_chat_placeholder.yaml")
OLLAMA_MODEL_CONFIG = Path("configs/models/ollama_qwen2_5_coder_14b.yaml")
DECODING_CONFIG = Path("configs/decoding/greedy_1024.yaml")
QWEN2_5_3B_MODEL_CONFIG = Path("configs/models/ollama_qwen2_5_coder_3b.yaml")
QWEN2_5_3B_MODEL_INPUT_PROTOCOL = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)
TRANSFORMERS_PEFT_BASE_CONFIG = Path(
    "configs/models/transformers_peft_qwen2_5_coder_3b_base.yaml"
)
TRANSFORMERS_PEFT_ADAPTER_CONFIG = Path(
    "configs/models/"
    "transformers_peft_qwen2_5_coder_3b_operational_smoke_adapter.yaml"
)
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
    assert config.provider_runtime_probe is None


def test_load_ollama_model_config_requires_runtime_probe() -> None:
    config = load_model_config(OLLAMA_MODEL_CONFIG)

    assert isinstance(config, OpenAICompatibleChatModelConfig)
    assert config.model_id == "qwen2.5-coder:14b"
    assert config.provider_runtime_probe == "ollama"


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
    assert config.model_input_protocol.content_hash == ("xxh64:9b9eba719de618f1")
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


def test_load_transformers_peft_base_config_resolves_immutable_base_policy() -> None:
    config = load_model_config(TRANSFORMERS_PEFT_BASE_CONFIG)
    assert isinstance(config, TransformersPeftModelConfig)
    protocol = load_referenced_model_input_protocol(
        config,
        TRANSFORMERS_PEFT_BASE_CONFIG,
    )
    assert protocol is not None

    binding = load_transformers_peft_policy_binding(
        config,
        TRANSFORMERS_PEFT_BASE_CONFIG,
        model_input_protocol=protocol,
    )

    assert config.provider == "transformers_peft"
    assert config.adapter is None
    assert config.runtime.device == "cuda"
    assert config.runtime.weight_dtype == "bfloat16"
    assert binding.policy_id == "qwen2.5-coder-3b-transformers-base"
    assert binding.base_model == config.base_model
    assert binding.adapter_id is None
    assert binding.adapter_dir is None


def test_load_transformers_peft_adapter_config_derives_adapter_from_manifest() -> (
    None
):
    config = load_model_config(TRANSFORMERS_PEFT_ADAPTER_CONFIG)
    assert isinstance(config, TransformersPeftModelConfig)
    protocol = load_referenced_model_input_protocol(
        config,
        TRANSFORMERS_PEFT_ADAPTER_CONFIG,
    )
    assert protocol is not None

    binding = load_transformers_peft_policy_binding(
        config,
        TRANSFORMERS_PEFT_ADAPTER_CONFIG,
        model_input_protocol=protocol,
    )

    assert config.adapter is not None
    assert config.adapter.content_hash == "xxh64:51369f8947cc96f8"
    assert binding.adapter_id == "xxh64:ccd2828a4bc5fbe1"
    assert binding.adapter_dir == Path(
        "experiments/models/"
        "week_09_positive_sft_lora_smoke_qwen2_5_coder_3b/adapter"
    ).resolve()


def test_transformers_peft_adapter_manifest_reference_rejects_hash_drift() -> None:
    config = load_model_config(TRANSFORMERS_PEFT_ADAPTER_CONFIG)
    assert isinstance(config, TransformersPeftModelConfig)
    assert config.adapter is not None
    protocol = load_referenced_model_input_protocol(
        config,
        TRANSFORMERS_PEFT_ADAPTER_CONFIG,
    )
    assert protocol is not None
    drifted_adapter = config.adapter.model_copy(
        update={"content_hash": "xxh64:0000000000000000"}
    )
    drifted_config = config.model_copy(update={"adapter": drifted_adapter})

    with pytest.raises(ValueError, match="LoRA training manifest hash mismatch"):
        load_transformers_peft_policy_binding(
            drifted_config,
            TRANSFORMERS_PEFT_ADAPTER_CONFIG,
            model_input_protocol=protocol,
        )


def test_transformers_peft_adapter_reference_rejects_failed_training_run(
    tmp_path: Path,
) -> None:
    config = load_model_config(TRANSFORMERS_PEFT_ADAPTER_CONFIG)
    assert isinstance(config, TransformersPeftModelConfig)
    assert config.adapter is not None

    failed_manifest = json.loads(
        Path(
            "experiments/models/"
            "week_09_positive_sft_lora_smoke_qwen2_5_coder_3b/manifest.json"
        ).read_text()
    )
    failed_manifest["status"] = "failed"
    failed_manifest["adapter_directory_hash"] = None
    failed_manifest["artifacts"].pop("adapter")
    manifest_path = tmp_path / "run" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(failed_manifest))

    protocol_relative_path = Path(
        os.path.relpath(QWEN2_5_3B_MODEL_INPUT_PROTOCOL.resolve(), tmp_path.resolve())
    ).as_posix()
    protocol_ref = config.model_input_protocol.model_copy(
        update={"path": protocol_relative_path}
    )
    adapter_ref = config.adapter.model_copy(
        update={
            "path": "run/manifest.json",
            "content_hash": hash_file(manifest_path),
        }
    )
    failed_config = config.model_copy(
        update={
            "model_input_protocol": protocol_ref,
            "adapter": adapter_ref,
        }
    )
    synthetic_config_path = tmp_path / "model.yaml"
    protocol = load_referenced_model_input_protocol(
        failed_config,
        synthetic_config_path,
    )
    assert protocol is not None

    with pytest.raises(ValueError, match="require a completed LoRA training run"):
        load_transformers_peft_policy_binding(
            failed_config,
            synthetic_config_path,
            model_input_protocol=protocol,
        )


def test_transformers_peft_config_rejects_unsupported_capability_claims() -> None:
    config = load_model_config(TRANSFORMERS_PEFT_BASE_CONFIG)
    assert isinstance(config, TransformersPeftModelConfig)
    overstated_capabilities = config.capabilities.model_copy(
        update={"supports_stop": True}
    )

    with pytest.raises(
        ValidationError,
        match="capabilities must match the implemented greedy local client",
    ):
        TransformersPeftModelConfig.model_validate(
            {
                **config.model_dump(mode="json"),
                "capabilities": overstated_capabilities.model_dump(mode="json"),
            }
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
        "provider_runtime_probe": None,
        "version": "model_config_v0",
    }
    assert artifact["provider_runtime"] is None
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
        provider_runtime_provenance=_ollama_runtime(config),
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
    assert artifact["provider_runtime"] == {
        "provider": "ollama",
        "model_id": config.model_id,
        "model_digest": config.model_manifest_digest,
        "server_version": "0.30.11",
    }


def test_transformers_peft_provenance_captures_adapter_manifest_reference() -> None:
    config = load_model_config(TRANSFORMERS_PEFT_ADAPTER_CONFIG)
    assert isinstance(config, TransformersPeftModelConfig)
    protocol = load_referenced_model_input_protocol(
        config,
        TRANSFORMERS_PEFT_ADAPTER_CONFIG,
    )
    assert protocol is not None

    artifact = model_config_provenance_artifact(
        model_config=config,
        model_config_path=TRANSFORMERS_PEFT_ADAPTER_CONFIG,
        model_config_hash="xxh64:modelconfig000",
        model_input_protocol=protocol,
    ).model_dump(mode="json")

    assert artifact["config"]["adapter"] == {
        "path": (
            "../../experiments/models/"
            "week_09_positive_sft_lora_smoke_qwen2_5_coder_3b/manifest.json"
        ),
        "content_hash": "xxh64:51369f8947cc96f8",
    }
    assert artifact["config"]["base_model"] == {
        "repository_id": "Qwen/Qwen2.5-Coder-3B-Instruct",
        "revision": "89fe5444e8baf5736e70f528f1edcc79e6616ef6",
    }
    assert artifact["provider_runtime"] is None
    assert artifact["model_input_protocol"]["source_hash"] == (
        config.model_input_protocol.content_hash
    )


def test_transformers_peft_provenance_requires_resolved_input_protocol() -> None:
    config = load_model_config(TRANSFORMERS_PEFT_BASE_CONFIG)
    assert isinstance(config, TransformersPeftModelConfig)

    with pytest.raises(
        ValidationError,
        match="transformers_peft provenance requires model_input_protocol",
    ):
        model_config_provenance_artifact(
            model_config=config,
            model_config_path=TRANSFORMERS_PEFT_BASE_CONFIG,
            model_config_hash="xxh64:modelconfig000",
        )


def test_ollama_model_config_provenance_requires_resolved_input_protocol() -> None:
    config = load_model_config(QWEN2_5_3B_MODEL_CONFIG)
    assert isinstance(config, OllamaGenerateModelConfig)

    with pytest.raises(
        ValidationError,
        match="ollama_generate provenance requires model_input_protocol",
    ):
        model_config_provenance_artifact(
            model_config=config,
            model_config_path=QWEN2_5_3B_MODEL_CONFIG,
            model_config_hash="xxh64:modelconfig000",
            provider_runtime_provenance=_ollama_runtime(config),
        )


def test_ollama_model_config_provenance_requires_provider_runtime() -> None:
    config = load_model_config(QWEN2_5_3B_MODEL_CONFIG)
    assert isinstance(config, OllamaGenerateModelConfig)
    protocol = load_referenced_model_input_protocol(
        config,
        QWEN2_5_3B_MODEL_CONFIG,
    )

    with pytest.raises(
        ValidationError,
        match="ollama_generate provenance requires provider_runtime",
    ):
        model_config_provenance_artifact(
            model_config=config,
            model_config_path=QWEN2_5_3B_MODEL_CONFIG,
            model_config_hash="xxh64:modelconfig000",
            model_input_protocol=protocol,
        )


def _ollama_runtime(
    config: OllamaGenerateModelConfig,
) -> OllamaProviderRuntimeProvenance:
    return OllamaProviderRuntimeProvenance(
        provider="ollama",
        model_id=config.model_id,
        model_digest=config.model_manifest_digest,
        server_version="0.30.11",
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
