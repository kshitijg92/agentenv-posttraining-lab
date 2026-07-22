import json
from pathlib import Path

import pytest

from agentenv.models.input_protocol_schema import HuggingFaceRevisionPin
from agentenv.training.positive_sft.lora.model import (
    finalize_lora_adapter_package,
    validate_lora_adapter_package,
)


BASE_MODEL = HuggingFaceRevisionPin(
    repository_id="Qwen/Qwen2.5-Coder-3B-Instruct",
    revision="89fe5444e8baf5736e70f528f1edcc79e6616ef6",
)


def _write_adapter_config(adapter_dir: Path, *, base_model: str) -> None:
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "base_model_name_or_path": base_model,
                "revision": BASE_MODEL.revision,
            }
        )
    )


def test_finalize_removes_peft_generated_model_card(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "adapter"
    _write_adapter_config(adapter_dir, base_model=BASE_MODEL.repository_id)
    (adapter_dir / "README.md").write_text("generated template")

    finalize_lora_adapter_package(adapter_dir, base_model=BASE_MODEL)

    assert not (adapter_dir / "README.md").exists()


def test_validation_rejects_machine_local_base_model_path(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "adapter"
    _write_adapter_config(
        adapter_dir,
        base_model=(
            "/home/user/.cache/huggingface/hub/"
            "models--Qwen--Qwen2.5-Coder-3B-Instruct/snapshots/revision"
        ),
    )

    with pytest.raises(ValueError, match="canonical base-model repository"):
        validate_lora_adapter_package(adapter_dir, base_model=BASE_MODEL)
