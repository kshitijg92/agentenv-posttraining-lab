from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
import torch
import transformers

from agentenv.hashing import hash_directory
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    load_model_input_protocol,
    render_model_input,
)
from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.models.schema import DecodingConfig, Message
from agentenv.models.transformers_peft import (
    TransformersPeftModelClient,
    TransformersPeftPolicyBinding,
    load_transformers_peft_model_client,
)
import agentenv.models.transformers_peft as transformers_peft


BASE_MODEL = HuggingFaceRevisionPin(
    repository_id="Qwen/Qwen2.5-Coder-3B-Instruct",
    revision="89fe5444e8baf5736e70f528f1edcc79e6616ef6",
)
PROTOCOL_PATH = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
)
END_OF_TURN_ID = 151645


class _FakeTokenizer:
    def __init__(self) -> None:
        self.rendered_prompts: list[str] = []
        self.decoded_token_ids: list[list[int]] = []

    def __call__(
        self,
        text: str,
        *,
        add_special_tokens: bool,
        return_tensors: str,
    ) -> dict[str, object]:
        assert add_special_tokens is False
        assert return_tensors == "pt"
        self.rendered_prompts.append(text)
        return {
            "input_ids": torch.tensor([[11, 12, 13]], dtype=torch.long),
            "attention_mask": torch.tensor([[1, 1, 1]], dtype=torch.long),
        }

    def decode(
        self,
        token_ids: list[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        assert skip_special_tokens is True
        assert clean_up_tokenization_spaces is False
        self.decoded_token_ids.append(token_ids)
        return '{"kind":"final","answer":"done"}'


class _FakeGenerationModelConfig:
    max_position_embeddings = 32


class _FakeGenerationModel:
    def __init__(
        self,
        generated_ids: list[int],
        *,
        trigger_timeout: bool = False,
    ) -> None:
        self.config = _FakeGenerationModelConfig()
        self.generated_ids = generated_ids
        self.trigger_timeout = trigger_timeout
        self.generate_calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> torch.Tensor:
        self.generate_calls.append(kwargs)
        input_ids = kwargs["input_ids"]
        assert isinstance(input_ids, torch.Tensor)
        if self.trigger_timeout:
            stopping_criteria = kwargs["stopping_criteria"]
            assert isinstance(
                stopping_criteria,
                transformers.StoppingCriteriaList,
            )
            criterion = stopping_criteria[0]
            setattr(criterion, "_deadline", 0.0)
            criterion(input_ids, torch.zeros(1))
        suffix = torch.tensor(
            [self.generated_ids],
            dtype=torch.long,
            device=input_ids.device,
        )
        return torch.cat((input_ids, suffix), dim=1)


class _LoadableFakeModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.config = SimpleNamespace(max_position_embeddings=32)

    def generate(self, **kwargs: object) -> torch.Tensor:
        input_ids = kwargs["input_ids"]
        assert isinstance(input_ids, torch.Tensor)
        suffix = torch.tensor(
            [[END_OF_TURN_ID]],
            dtype=torch.long,
            device=input_ids.device,
        )
        return torch.cat((input_ids, suffix), dim=1)

    def get_model_status(self) -> SimpleNamespace:
        return SimpleNamespace(
            enabled=True,
            active_adapters=["policy"],
            available_adapters=["policy"],
            merged_adapters=[],
            trainable_params=0,
        )


def _protocol() -> LoadedModelInputProtocol:
    return load_model_input_protocol(PROTOCOL_PATH)


def _binding(
    *,
    policy_id: str = "qwen2_5_coder_3b_base",
) -> TransformersPeftPolicyBinding:
    return TransformersPeftPolicyBinding(
        policy_id=policy_id,
        base_model=BASE_MODEL,
    )


def _messages() -> list[Message]:
    return [
        Message(
            message_id="message_00000000000000000000000000000000",
            role="user",
            content="Return the final action.",
        )
    ]


def _greedy(*, max_new_tokens: int = 4) -> DecodingConfig:
    return DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=max_new_tokens,
        timeout_seconds=30,
    )


def _client(
    model: _FakeGenerationModel,
    tokenizer: _FakeTokenizer,
    *,
    context_window_tokens: int = 32,
) -> TransformersPeftModelClient:
    return TransformersPeftModelClient(
        binding=_binding(),
        model_input_protocol=_protocol(),
        context_window_tokens=context_window_tokens,
        _model=model,
        _tokenizer=tokenizer,
        _input_device=torch.device("cpu"),
    )


def test_policy_binding_is_immutable_and_requires_a_hash_pinned_adapter(
    tmp_path: Path,
) -> None:
    binding = _binding()

    with pytest.raises(FrozenInstanceError):
        setattr(binding, "policy_id", "changed")
    with pytest.raises(ValidationError, match="Instance is frozen"):
        setattr(binding.base_model, "revision", "1" * 40)

    with pytest.raises(
        ValueError,
        match="adapter_dir and adapter_directory_hash must both be set",
    ):
        TransformersPeftPolicyBinding(
            policy_id="adapted",
            base_model=BASE_MODEL,
            adapter_dir=tmp_path,
        )


def test_generate_uses_pinned_prompt_and_exact_token_accounting() -> None:
    model = _FakeGenerationModel([21, END_OF_TURN_ID])
    tokenizer = _FakeTokenizer()
    client = _client(model, tokenizer)
    messages = _messages()

    response = client.generate(messages, _greedy())

    assert tokenizer.rendered_prompts == [
        render_model_input(_protocol(), messages, mode="generation")
    ]
    assert tokenizer.decoded_token_ids == [[21, END_OF_TURN_ID]]
    assert response.model_id == "qwen2_5_coder_3b_base"
    assert response.output_text == '{"kind":"final","answer":"done"}'
    assert response.finish_reason == "stop_criteria_met"
    assert response.prompt_tokens == 3
    assert response.completion_tokens == 2
    assert response.total_tokens == 5
    assert response.error_class is None

    call = model.generate_calls[0]
    generation_config = call["generation_config"]
    assert isinstance(generation_config, transformers.GenerationConfig)
    assert generation_config.do_sample is False
    assert generation_config.max_new_tokens == 4
    assert generation_config.eos_token_id == END_OF_TURN_ID
    assert generation_config.pad_token_id == 151643
    assert call["use_model_defaults"] is False


def test_generate_attributes_max_new_tokens_without_an_end_token() -> None:
    model = _FakeGenerationModel([21, 22])
    client = _client(model, _FakeTokenizer())

    response = client.generate(_messages(), _greedy(max_new_tokens=2))

    assert response.finish_reason == "max_new_tokens_reached"
    assert response.completion_tokens == 2


def test_generate_fails_closed_on_unsupported_sampling() -> None:
    model = _FakeGenerationModel([END_OF_TURN_ID])
    tokenizer = _FakeTokenizer()
    client = _client(model, tokenizer)
    sampling = DecodingConfig(
        strategy="sampling",
        temperature=0.7,
        top_p=0.9,
        max_new_tokens=4,
        timeout_seconds=30,
    )

    response = client.generate(_messages(), sampling)

    assert response.finish_reason == "error"
    assert response.error_class == "UnsupportedDecodingStrategy"
    assert tokenizer.rendered_prompts == []
    assert model.generate_calls == []


def test_generate_fails_closed_when_requested_budget_exceeds_context() -> None:
    model = _FakeGenerationModel([END_OF_TURN_ID])
    client = _client(model, _FakeTokenizer(), context_window_tokens=4)

    response = client.generate(_messages(), _greedy(max_new_tokens=2))

    assert response.finish_reason == "error"
    assert response.error_class == "LocalModelContextWindowExceeded"
    assert model.generate_calls == []


def test_generate_attributes_deadline_stop_as_timeout() -> None:
    model = _FakeGenerationModel([21], trigger_timeout=True)
    client = _client(model, _FakeTokenizer())

    response = client.generate(_messages(), _greedy())

    assert response.finish_reason == "timeout"
    assert response.error_class == "LocalModelGenerationTimeout"
    assert response.prompt_tokens is None
    assert response.completion_tokens is None


def test_loader_uses_one_path_for_base_and_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = _protocol()
    snapshot_path = tmp_path / BASE_MODEL.revision
    snapshot_path.mkdir()
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": BASE_MODEL.repository_id,
                "revision": BASE_MODEL.revision,
            }
        )
    )
    adapter_hash = hash_directory(adapter_dir)
    tokenizer = _FakeTokenizer()
    base_loads: list[dict[str, object]] = []
    adapter_loads: list[tuple[torch.nn.Module, Path]] = []

    def fake_load_tokenizer(
        protocol_arg: LoadedModelInputProtocol,
        *,
        cache_dir: Path | None,
        local_files_only: bool,
    ) -> _FakeTokenizer:
        assert protocol_arg == protocol
        assert cache_dir is None
        assert local_files_only is True
        return tokenizer

    def fake_load_base(
        path: Path,
        **kwargs: object,
    ) -> _LoadableFakeModel:
        assert path == snapshot_path
        base_loads.append(kwargs)
        return _LoadableFakeModel()

    def fake_load_adapter(
        model: torch.nn.Module,
        model_id: Path,
        **kwargs: object,
    ) -> torch.nn.Module:
        adapter_loads.append((model, model_id))
        assert kwargs == {
            "adapter_name": "policy",
            "is_trainable": False,
            "low_cpu_mem_usage": True,
        }
        return model

    monkeypatch.setattr(transformers_peft, "load_pinned_tokenizer", fake_load_tokenizer)
    monkeypatch.setattr(
        transformers_peft,
        "_resolve_model_snapshot",
        lambda *args, **kwargs: snapshot_path,
    )
    monkeypatch.setattr(
        transformers_peft.transformers.AutoModelForCausalLM,
        "from_pretrained",
        fake_load_base,
    )
    monkeypatch.setattr(
        transformers_peft.PeftModel,
        "from_pretrained",
        fake_load_adapter,
    )

    base_client = load_transformers_peft_model_client(
        _binding(),
        protocol,
        device="cpu",
        weight_dtype="float32",
        attention_implementation="eager",
        local_files_only=True,
    )
    adapted_client = load_transformers_peft_model_client(
        TransformersPeftPolicyBinding(
            policy_id="qwen2_5_coder_3b_week9_smoke",
            base_model=BASE_MODEL,
            adapter_dir=adapter_dir,
            adapter_directory_hash=adapter_hash,
        ),
        protocol,
        device="cpu",
        weight_dtype="float32",
        attention_implementation="eager",
        local_files_only=True,
    )

    assert type(base_client) is type(adapted_client)
    assert base_client.adapter_id is None
    assert adapted_client.adapter_id == adapter_hash
    assert len(base_loads) == 2
    assert base_loads[0] == base_loads[1]
    assert base_loads[0]["dtype"] == torch.float32
    assert base_loads[0]["attn_implementation"] == "eager"
    assert len(adapter_loads) == 1
    assert adapter_loads[0][1] == adapter_dir.resolve()


def test_loader_rejects_adapter_hash_drift_before_loading_model(
    tmp_path: Path,
) -> None:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}")
    binding = TransformersPeftPolicyBinding(
        policy_id="drifted_adapter",
        base_model=BASE_MODEL,
        adapter_dir=adapter_dir,
        adapter_directory_hash="xxh64:0000000000000000",
    )

    with pytest.raises(ValueError, match="adapter directory hash mismatch"):
        load_transformers_peft_model_client(
            binding,
            _protocol(),
            device="cpu",
            weight_dtype="float32",
            attention_implementation="eager",
            local_files_only=True,
        )
