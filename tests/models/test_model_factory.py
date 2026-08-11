from pathlib import Path

import pytest

from agentenv.models.config import (
    load_model_config,
    load_referenced_model_input_protocol,
)
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.models.factory import build_model_client
from agentenv.models.ollama_generate import OllamaGenerateModelClient
from agentenv.models.openai_compatible_chat import OpenAICompatibleChatModelClient
from agentenv.models.transformers_peft import TransformersPeftPolicyBinding


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


def test_build_model_client_builds_transformers_peft_client_from_config_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = Path("configs/models/transformers_peft_qwen2_5_coder_3b_base.yaml")
    config = load_model_config(config_path)
    protocol = load_referenced_model_input_protocol(config, config_path)
    fake_client = ScriptedFakeModelClient(
        model_id="local-transformers-test",
        script=[FakeModelScriptStep(output_text='{"kind":"final","answer":"done"}')],
    )
    calls: list[tuple[TransformersPeftPolicyBinding, dict[str, object]]] = []

    def fake_load_transformers_peft_model_client(
        binding: TransformersPeftPolicyBinding,
        loaded_protocol: object,
        **kwargs: object,
    ) -> ScriptedFakeModelClient:
        assert loaded_protocol is protocol
        calls.append((binding, kwargs))
        return fake_client

    monkeypatch.setattr(
        "agentenv.models.transformers_peft.load_transformers_peft_model_client",
        fake_load_transformers_peft_model_client,
    )

    model_client = build_model_client(
        config,
        model_input_protocol=protocol,
        model_config_path=config_path,
    )

    assert model_client is fake_client
    assert len(calls) == 1
    binding, runtime = calls[0]
    assert binding.policy_id == "qwen2.5-coder-3b-transformers-base"
    assert binding.adapter_dir is None
    assert runtime == {
        "device": "cuda",
        "weight_dtype": "bfloat16",
        "attention_implementation": "sdpa",
    }


def test_build_transformers_peft_model_client_requires_config_path() -> None:
    config_path = Path("configs/models/transformers_peft_qwen2_5_coder_3b_base.yaml")
    config = load_model_config(config_path)
    protocol = load_referenced_model_input_protocol(config, config_path)

    with pytest.raises(ValueError, match="requires the model config path"):
        build_model_client(config, model_input_protocol=protocol)
