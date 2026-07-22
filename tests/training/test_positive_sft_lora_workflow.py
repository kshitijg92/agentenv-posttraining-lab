from collections.abc import Callable
import json
from pathlib import Path

import pytest
import torch
import transformers

from agentenv.artifacts.manifests import (
    POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION,
    PositiveSFTTrainingMaterializationManifest,
    TrainingAuthorizationOverride,
)
from agentenv.hashing import hash_file
from agentenv.training.positive_sft.lora import workflow as lora_workflow
from agentenv.training.positive_sft.lora.config import (
    load_positive_sft_lora_training_config,
)
from agentenv.training.positive_sft.materialization.export import (
    PositiveSFTTrainingMaterializationExport,
)
from agentenv.training.positive_sft.materialization.schema import (
    CompletedPositiveSFTTrainingMaterializationRecord,
)


CONFIG_PATH = Path("configs/train/positive_sft_lora_smoke.yaml")
PROTOCOL_PATH = Path(
    "configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml"
).resolve()


def _tiny_config(tmp_path: Path) -> Path:
    payload = load_positive_sft_lora_training_config(CONFIG_PATH).model_dump(
        mode="json"
    )
    payload["lora"]["rank"] = 2
    payload["runtime"] = {
        "device": "cpu",
        "weight_dtype": "float32",
        "attention_implementation": "eager",
        "gradient_checkpointing": False,
        "deterministic_algorithms": True,
        "cublas_workspace_config": ":4096:8",
    }
    payload["max_steps"] = 2
    payload["reload_probe_token_count"] = 4
    config_path = tmp_path / "tiny_config.yaml"
    import yaml

    config_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return config_path


def _materialization_record() -> CompletedPositiveSFTTrainingMaterializationRecord:
    return CompletedPositiveSFTTrainingMaterializationRecord(
        source_positive_sft_example_id="positive_sft_example_aaaaaaaaaaaaaaaa",
        source_positive_sft_example_record_hash="xxh64:1111111111111111",
        model_input_protocol_id="qwen2_5_coder_3b_agentenv_json",
        model_input_protocol_hash=hash_file(PROTOCOL_PATH),
        serialization_mode="completed_transcript",
        max_sequence_length=16,
        materializer_version="positive_sft_training_materializer_v0",
        materializer_code_hash="xxh64:3333333333333333",
        status="completed",
        input_ids=[1, 2, 3, 4, 5, 6],
        labels=[-100, -100, -100, 4, 5, 6],
        sequence_length=6,
        supervised_token_count=3,
        ignored_token_count=3,
    )


def _source_artifact(tmp_path: Path) -> PositiveSFTTrainingMaterializationExport:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    records_path = source_dir / "materializations.jsonl"
    record = _materialization_record()
    records_path.write_text(json.dumps(record.model_dump(mode="json")) + "\n")
    manifest = PositiveSFTTrainingMaterializationManifest.model_validate(
        {
            "artifact_type": "positive_sft_training_materialization",
            "artifact_schema_version": (
                POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": "2026-07-22T00:00:00Z",
            "training_authorization": "authorized",
            "training_authorization_override": {
                "mode": "explicit_user_override",
                "authorized_by": "test",
                "reason": "Tiny local trainer contract test.",
            },
            "source_positive_sft_export": {
                "artifact_dir": "/tmp/not-read-by-this-test",
                "manifest_hash": "xxh64:1111111111111111",
                "positive_sft_examples_jsonl_hash": "xxh64:2222222222222222",
            },
            "model_input_protocol_path": str(PROTOCOL_PATH),
            "model_input_protocol_id": "qwen2_5_coder_3b_agentenv_json",
            "model_input_protocol_hash": hash_file(PROTOCOL_PATH),
            "serialization_mode": "completed_transcript",
            "max_sequence_length": 16,
            "materializer_version": "positive_sft_training_materializer_v0",
            "materializer_code_hash": "xxh64:3333333333333333",
            "positive_sft_training_materialization_record_schema_version": (
                "positive_sft_training_materialization_record_v0"
            ),
            "record_count": 1,
            "completed_count": 1,
            "failed_count": 0,
            "sequence_length_exceeded_count": 0,
            "materialization_error_count": 0,
            "materializations_jsonl_hash": hash_file(records_path),
            "artifacts": {"materializations": "materializations.jsonl"},
        }
    )
    (source_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return PositiveSFTTrainingMaterializationExport(
        out_dir=source_dir,
        manifest=manifest,
        records=(record,),
    )


def _tiny_base_factory() -> Callable[[], transformers.PreTrainedModel]:
    torch.manual_seed(11)
    config = transformers.Qwen2Config(
        vocab_size=64,
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=128,
        tie_word_embeddings=True,
    )
    reference = transformers.Qwen2ForCausalLM(config)
    state = {
        name: tensor.detach().clone() for name, tensor in reference.state_dict().items()
    }

    def load() -> transformers.PreTrainedModel:
        model = transformers.Qwen2ForCausalLM(config)
        model.load_state_dict(state, strict=True)
        return model

    return load


def test_training_artifact_persists_verified_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_artifact(tmp_path)
    config_path = _tiny_config(tmp_path)
    base_factory = _tiny_base_factory()
    monkeypatch.setattr(
        lora_workflow,
        "_load_authorized_source",
        lambda *args, **kwargs: source,
    )
    monkeypatch.setattr(
        lora_workflow,
        "load_pinned_causal_lm",
        lambda *args, **kwargs: base_factory(),
    )

    artifact = lora_workflow.run_positive_sft_lora_training(
        source.out_dir,
        config_path,
        tmp_path / "run",
    )

    assert artifact.manifest.status == "completed"
    assert artifact.result.status == "completed"
    assert artifact.manifest.completed_step_count == 2
    assert len(artifact.steps) == 2
    assert [step.step_index for step in artifact.steps] == [0, 1]
    assert len(artifact.result.qualification.steps) == 2
    assert artifact.result.training_initial_adapter_state_matches_qualification
    assert artifact.result.training_initial_frozen_state_matches_qualification
    assert (
        artifact.result.parameter_state.adapter_state_hash_before
        == artifact.result.qualification.parameter_state.adapter_state_hash_before
    )
    assert (
        artifact.result.parameter_state.frozen_state_hash_before
        == artifact.result.qualification.parameter_state.frozen_state_hash_before
    )
    adapter_dir = artifact.out_dir / "adapter"
    assert (adapter_dir / "adapter_model.safetensors").is_file()
    assert not (adapter_dir / "README.md").exists()
    adapter_config = json.loads((adapter_dir / "adapter_config.json").read_text())
    assert (
        adapter_config["base_model_name_or_path"]
        == "Qwen/Qwen2.5-Coder-3B-Instruct"
    )
    assert adapter_config["revision"] == "89fe5444e8baf5736e70f528f1edcc79e6616ef6"
    assert not (artifact.out_dir / "adapter_incomplete").exists()
    assert artifact.manifest.adapter_directory_hash is not None
    assert artifact.manifest.training_config.path == str(config_path.resolve())
    assert artifact.manifest.training_config.content_hash == hash_file(config_path)
    assert "training_config" not in artifact.manifest.artifacts
    assert not (artifact.out_dir / "training_config.yaml").exists()

    config_path.write_text(config_path.read_text() + "\n")
    with pytest.raises(ValueError, match="hash-pinned LoRA training config"):
        lora_workflow.load_positive_sft_lora_training_artifact(artifact.out_dir)


def test_model_loading_failure_never_publishes_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_artifact(tmp_path)
    config_path = _tiny_config(tmp_path)
    monkeypatch.setattr(
        lora_workflow,
        "_load_authorized_source",
        lambda *args, **kwargs: source,
    )

    def fail_to_load(*args, **kwargs):
        raise RuntimeError("synthetic model load failure")

    monkeypatch.setattr(lora_workflow, "load_pinned_causal_lm", fail_to_load)

    artifact = lora_workflow.run_positive_sft_lora_training(
        source.out_dir,
        config_path,
        tmp_path / "failed_run",
    )

    assert artifact.manifest.status == "failed"
    assert artifact.result.status == "failed"
    assert artifact.result.failure_stage == "qualification_model_loading"
    assert artifact.result.qualification is None
    assert artifact.manifest.adapter_directory_hash is None
    assert "adapter" not in artifact.manifest.artifacts
    assert not (artifact.out_dir / "adapter").exists()


def test_training_model_loading_failure_preserves_completed_qualification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_artifact(tmp_path)
    config_path = _tiny_config(tmp_path)
    base_factory = _tiny_base_factory()
    load_count = 0
    monkeypatch.setattr(
        lora_workflow,
        "_load_authorized_source",
        lambda *args, **kwargs: source,
    )

    def load_then_fail(*args, **kwargs):
        nonlocal load_count
        load_count += 1
        if load_count == 1:
            return base_factory()
        raise RuntimeError("synthetic training model load failure")

    monkeypatch.setattr(lora_workflow, "load_pinned_causal_lm", load_then_fail)

    artifact = lora_workflow.run_positive_sft_lora_training(
        source.out_dir,
        config_path,
        tmp_path / "training_load_failed_run",
    )

    assert artifact.manifest.status == "failed"
    assert artifact.result.status == "failed"
    assert artifact.result.failure_stage == "training_model_loading"
    assert artifact.result.qualification is not None
    assert len(artifact.result.qualification.steps) == 2
    assert artifact.result.completed_step_count == 0
    assert artifact.steps == ()
    assert artifact.manifest.adapter_directory_hash is None
    assert "adapter" not in artifact.manifest.artifacts


def test_authorization_override_is_required_before_source_loading(
    tmp_path: Path,
) -> None:
    source = _source_artifact(tmp_path)
    payload = source.manifest.model_dump(mode="json")
    payload["training_authorization"] = "not_authorized"
    payload["training_authorization_override"] = None
    manifest = PositiveSFTTrainingMaterializationManifest.model_validate(payload)
    (source.out_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )

    with pytest.raises(ValueError, match="requires an authorized"):
        lora_workflow._load_authorized_source(
            source.out_dir,
            tokenizer_cache_dir=None,
            local_files_only=True,
        )


def test_training_authorization_override_shape_remains_explicit() -> None:
    override = TrainingAuthorizationOverride(
        mode="explicit_user_override",
        authorized_by="kshitij",
        reason="Learning-lab smoke run.",
    )

    assert override.mode == "explicit_user_override"
