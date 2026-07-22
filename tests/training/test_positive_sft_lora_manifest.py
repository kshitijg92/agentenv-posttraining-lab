from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.artifacts.manifests import PositiveSFTLoRATrainingRunManifest


def _manifest_payload(**updates: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifact_type": "positive_sft_lora_training_run",
        "artifact_schema_version": "positive_sft_lora_training_run_artifact_v0",
        "created_at": "2026-07-22T00:00:00Z",
        "training_run_id": "positive_sft_lora_run_" + "a" * 32,
        "purpose": "operational_smoke",
        "status": "completed",
        "source_positive_sft_training_materialization": {
            "artifact_dir": "/tmp/source",
            "manifest_hash": "xxh64:1111111111111111",
            "materializations_jsonl_hash": "xxh64:2222222222222222",
        },
        "training_config": {
            "path": "/tmp/config.yaml",
            "content_hash": "xxh64:3333333333333333",
            "config_id": "positive_sft_lora_smoke",
        },
        "model_input_protocol_id": "qwen2_5_coder_3b_agentenv_json",
        "model_input_protocol_hash": "xxh64:4444444444444444",
        "base_model": {
            "repository_id": "Qwen/Qwen2.5-Coder-3B-Instruct",
            "revision": "a" * 40,
        },
        "trainer_code_hash": "xxh64:5555555555555555",
        "training_result_schema_version": ("positive_sft_lora_training_result_v0"),
        "training_step_schema_version": "positive_sft_lora_training_step_v0",
        "selected_example_count": 1,
        "requested_step_count": 2,
        "completed_step_count": 2,
        "training_result_hash": "xxh64:6666666666666666",
        "training_steps_hash": "xxh64:7777777777777777",
        "adapter_directory_hash": "xxh64:8888888888888888",
        "artifacts": {
            "training_result": "training_result.json",
            "training_steps": "training_steps.jsonl",
            "adapter": "adapter",
        },
    }
    payload.update(updates)
    return payload


def test_completed_training_manifest_requires_hash_pinned_adapter() -> None:
    payload = _manifest_payload(adapter_directory_hash=None)
    payload["artifacts"].pop("adapter")

    with pytest.raises(ValidationError, match="hash-pinned adapter"):
        PositiveSFTLoRATrainingRunManifest.model_validate(payload)


def test_training_config_is_a_pinned_input_not_an_output_artifact() -> None:
    manifest = PositiveSFTLoRATrainingRunManifest.model_validate(_manifest_payload())

    assert manifest.training_config.path == "/tmp/config.yaml"
    assert manifest.training_config.content_hash == "xxh64:3333333333333333"
    assert "training_config" not in manifest.artifacts


def test_failed_training_manifest_cannot_publish_adapter() -> None:
    payload = _manifest_payload(
        status="failed",
        completed_step_count=1,
    )

    with pytest.raises(ValidationError, match="cannot publish"):
        PositiveSFTLoRATrainingRunManifest.model_validate(payload)


def test_failed_training_manifest_preserves_partial_step_count_without_adapter() -> (
    None
):
    payload = _manifest_payload(
        status="failed",
        completed_step_count=1,
        adapter_directory_hash=None,
    )
    payload["artifacts"].pop("adapter")

    manifest = PositiveSFTLoRATrainingRunManifest.model_validate(payload)

    assert manifest.status == "failed"
    assert manifest.completed_step_count == 1
    assert "adapter" not in manifest.artifacts
