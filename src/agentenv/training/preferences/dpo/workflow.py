from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    DPO_LORA_TRAINING_RUN_ARTIFACT_REFS,
    DPO_LORA_TRAINING_RUN_ARTIFACT_SCHEMA_VERSION,
    DPOLoRATrainingRunManifest,
    load_dpo_lora_training_run_manifest,
)
from agentenv.hashing import hash_directory, hash_file
from agentenv.ids import new_dpo_lora_training_run_id
from agentenv.training.lora.model import (
    load_pinned_causal_lm,
    validate_lora_adapter_package,
)
from agentenv.training.lora.runtime import (
    capture_training_runtime_provenance,
    configure_process_determinism,
    require_requested_training_device,
)
from agentenv.training.positive_sft.lora.schema import (
    CompletedPositiveSFTLoRATrainingResult,
)
from agentenv.training.positive_sft.lora.workflow import (
    load_positive_sft_lora_training_artifact,
    load_positive_sft_lora_training_task_ids,
)
from agentenv.training.preferences.dpo.config import (
    load_dpo_lora_training_config,
)
from agentenv.training.preferences.dpo.engine import (
    execute_dpo_lora_training,
    select_dpo_training_pairs,
)
from agentenv.training.preferences.dpo.schema import (
    DPO_LORA_TRAINING_RESULT_SCHEMA_VERSION,
    DPO_LORA_TRAINING_STEP_SCHEMA_VERSION,
    CompletedDPOLoRATrainingResult,
    DPOLoRATrainingConfig,
    DPOLoRATrainingStepRecord,
)
from agentenv.training.preferences.materialization.export import (
    DPOTrainingMaterializationExport,
    load_dpo_training_materialization_snapshot,
)


@dataclass(frozen=True)
class DPOLoRATrainingArtifact:
    out_dir: Path
    manifest: DPOLoRATrainingRunManifest
    result: CompletedDPOLoRATrainingResult
    steps: tuple[DPOLoRATrainingStepRecord, ...]


def run_dpo_lora_training(
    source_materialization_dirs: Sequence[Path],
    parent_sft_training_run_dir: Path,
    config_path: Path,
    out_dir: Path,
    *,
    model_cache_dir: Path | None = None,
    local_files_only: bool = False,
    overwrite: bool = False,
) -> DPOLoRATrainingArtifact:
    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    config_path = config_path.resolve()
    config = load_dpo_lora_training_config(config_path)
    configure_process_determinism(config.runtime)
    runtime_provenance = capture_training_runtime_provenance(
        config.runtime,
        objective_code_dir=Path(__file__).resolve().parent,
    )
    require_requested_training_device(runtime_provenance)

    sources = _load_authorized_sources(
        source_materialization_dirs,
    )
    parent = load_positive_sft_lora_training_artifact(
        parent_sft_training_run_dir.resolve()
    )
    if not isinstance(parent.result, CompletedPositiveSFTLoRATrainingResult):
        raise ValueError("DPO parent must be a completed positive-SFT LoRA run")
    _validate_policy_and_data_contract(
        sources,
        parent=parent,
        config_protocol_id=config.model_input_protocol_id,
    )

    records = tuple(record for source in sources for record in source.records)
    selected_pairs = select_dpo_training_pairs(records)
    parent_adapter_dir = resolve_relative_artifact_ref(
        parent.out_dir,
        parent.manifest.artifacts["adapter"],
    )
    started_at = _utc_now()

    def load_base_model():
        return load_pinned_causal_lm(
            parent.manifest.base_model,
            config.runtime,
            cache_dir=model_cache_dir,
            local_files_only=local_files_only,
        )

    execution = execute_dpo_lora_training(
        load_base_model=load_base_model,
        parent_adapter_dir=parent_adapter_dir,
        base_model_pin=parent.manifest.base_model,
        expected_parent_adapter_state_hash=(
            parent.result.adapter_round_trip.trained_adapter_state_hash
        ),
        expected_parent_frozen_state_hash=(
            parent.result.adapter_round_trip.trained_frozen_state_hash
        ),
        selected_pairs=selected_pairs,
        config=config,
        adapter_dir=out_dir / DPO_LORA_TRAINING_RUN_ARTIFACT_REFS["adapter"],
    )
    training_run_id = new_dpo_lora_training_run_id()
    result = CompletedDPOLoRATrainingResult(
        training_run_id=training_run_id,
        status="completed",
        started_at=started_at,
        finished_at=_utc_now(),
        selected_pairs=execution.selected_pairs,
        requested_step_count=config.max_steps,
        completed_step_count=len(execution.steps),
        runtime_provenance=runtime_provenance,
        audit=execution.audit,
    )
    result_path = out_dir / DPO_LORA_TRAINING_RUN_ARTIFACT_REFS["training_result"]
    steps_path = out_dir / DPO_LORA_TRAINING_RUN_ARTIFACT_REFS["training_steps"]
    result_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    steps_path.write_text(
        "".join(
            json.dumps(step.model_dump(mode="json"), sort_keys=True) + "\n"
            for step in execution.steps
        )
    )
    manifest = _build_manifest(
        out_dir=out_dir,
        sources=sources,
        parent=parent,
        config=config,
        config_path=config_path,
        result=result,
        result_path=result_path,
        steps_path=steps_path,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_dpo_lora_training_artifact(out_dir)


def load_dpo_lora_training_artifact(out_dir: Path) -> DPOLoRATrainingArtifact:
    out_dir = out_dir.resolve()
    manifest = load_dpo_lora_training_run_manifest(out_dir / MANIFEST_FILENAME)
    config_path = Path(manifest.training_config.path).resolve()
    if hash_file(config_path) != manifest.training_config.content_hash:
        raise ValueError("hash-pinned DPO training config mismatch")
    config = load_dpo_lora_training_config(config_path)
    if config.config_id != manifest.training_config.config_id:
        raise ValueError("DPO training config id mismatch")

    _validate_parent_ref(out_dir, manifest)
    _validate_source_refs(out_dir, manifest)
    result_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["training_result"],
    )
    steps_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["training_steps"],
    )
    adapter_dir = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["adapter"],
    )
    if hash_file(result_path) != manifest.training_result_hash:
        raise ValueError("DPO training result hash mismatch")
    if hash_file(steps_path) != manifest.training_steps_hash:
        raise ValueError("DPO training steps hash mismatch")
    if hash_directory(adapter_dir) != manifest.adapter_directory_hash:
        raise ValueError("DPO adapter directory hash mismatch")
    validate_lora_adapter_package(adapter_dir, base_model=manifest.base_model)

    result = CompletedDPOLoRATrainingResult.model_validate_json(result_path.read_text())
    steps = _load_steps(steps_path)
    if result.training_run_id != manifest.training_run_id:
        raise ValueError("DPO result training-run id mismatch")
    if result.requested_step_count != manifest.requested_step_count:
        raise ValueError("DPO result requested-step count mismatch")
    if result.completed_step_count != manifest.completed_step_count:
        raise ValueError("DPO result completed-step count mismatch")
    if len(result.selected_pairs) != manifest.selected_pair_count:
        raise ValueError("DPO selected-pair count mismatch")
    if len(steps) != manifest.completed_step_count:
        raise ValueError("DPO persisted step count mismatch")
    if [step.step_index for step in steps] != list(range(len(steps))):
        raise ValueError("DPO step indexes must begin at zero and be contiguous")
    if (
        result.audit.adapter_round_trip.persisted_adapter_directory_hash
        != manifest.adapter_directory_hash
    ):
        raise ValueError("DPO result and manifest adapter hashes differ")
    return DPOLoRATrainingArtifact(
        out_dir=out_dir,
        manifest=manifest,
        result=result,
        steps=steps,
    )


def load_dpo_lora_training_task_ids(out_dir: Path) -> frozenset[str]:
    artifact = load_dpo_lora_training_artifact(out_dir)
    parent_dir = Path(artifact.manifest.parent_sft_policy.artifact_dir)
    if not parent_dir.is_absolute():
        parent_dir = artifact.out_dir / parent_dir
    return load_positive_sft_lora_training_task_ids(parent_dir.resolve())


def _load_authorized_sources(
    source_dirs: Sequence[Path],
) -> tuple[DPOTrainingMaterializationExport, ...]:
    resolved = tuple(sorted(path.resolve() for path in source_dirs))
    if not resolved:
        raise ValueError("DPO training requires at least one source materialization")
    if len(resolved) != len(set(resolved)):
        raise ValueError("DPO training source materializations must be unique")
    sources = tuple(
        load_dpo_training_materialization_snapshot(path) for path in resolved
    )
    for source in sources:
        if (
            source.manifest.training_authorization != "authorized"
            or source.manifest.training_authorization_override is None
        ):
            raise ValueError(
                "DPO training requires explicitly authorized materializations"
            )
    return sources


def _validate_policy_and_data_contract(
    sources: Sequence[DPOTrainingMaterializationExport],
    *,
    parent: Any,
    config_protocol_id: str,
) -> None:
    protocol_ids = {source.manifest.model_input_protocol_id for source in sources}
    protocol_hashes = {source.manifest.model_input_protocol_hash for source in sources}
    if len(protocol_ids) != 1 or len(protocol_hashes) != 1:
        raise ValueError("DPO sources must share one model-input protocol")
    if protocol_ids != {config_protocol_id}:
        raise ValueError("DPO config model-input protocol differs from sources")
    if parent.manifest.model_input_protocol_id != config_protocol_id:
        raise ValueError("DPO parent model-input protocol differs from training data")
    if protocol_hashes != {parent.manifest.model_input_protocol_hash}:
        raise ValueError("DPO parent and materializations pin different protocols")


def _build_manifest(
    *,
    out_dir: Path,
    sources: Sequence[DPOTrainingMaterializationExport],
    parent: Any,
    config: DPOLoRATrainingConfig,
    config_path: Path,
    result: CompletedDPOLoRATrainingResult,
    result_path: Path,
    steps_path: Path,
) -> DPOLoRATrainingRunManifest:
    source_refs = tuple(
        {
            "artifact_dir": str(source.out_dir),
            "manifest_hash": hash_file(source.out_dir / MANIFEST_FILENAME),
            "materializations_jsonl_hash": source.manifest.materializations_jsonl_hash,
        }
        for source in sources
    )
    parent_manifest_path = parent.out_dir / MANIFEST_FILENAME
    adapter_dir = out_dir / DPO_LORA_TRAINING_RUN_ARTIFACT_REFS["adapter"]
    return DPOLoRATrainingRunManifest.model_validate(
        {
            "artifact_type": ArtifactType.DPO_LORA_TRAINING_RUN,
            "artifact_schema_version": (DPO_LORA_TRAINING_RUN_ARTIFACT_SCHEMA_VERSION),
            "created_at": _utc_now(),
            "training_run_id": result.training_run_id,
            "status": "completed",
            "source_dpo_training_materializations": source_refs,
            "parent_sft_policy": {
                "artifact_dir": str(parent.out_dir),
                "manifest_hash": hash_file(parent_manifest_path),
                "training_run_id": parent.manifest.training_run_id,
                "adapter_directory_hash": parent.manifest.adapter_directory_hash,
            },
            "training_config": {
                "path": str(config_path),
                "content_hash": hash_file(config_path),
                "config_id": config.config_id,
            },
            "model_input_protocol_id": parent.manifest.model_input_protocol_id,
            "model_input_protocol_hash": parent.manifest.model_input_protocol_hash,
            "base_model": parent.manifest.base_model.model_dump(mode="json"),
            "trainer_code_hash": result.runtime_provenance.trainer_code_hash,
            "training_result_schema_version": (DPO_LORA_TRAINING_RESULT_SCHEMA_VERSION),
            "training_step_schema_version": DPO_LORA_TRAINING_STEP_SCHEMA_VERSION,
            "selected_pair_count": len(result.selected_pairs),
            "requested_step_count": result.requested_step_count,
            "completed_step_count": result.completed_step_count,
            "training_result_hash": hash_file(result_path),
            "training_steps_hash": hash_file(steps_path),
            "adapter_directory_hash": hash_directory(adapter_dir),
            "artifacts": dict(DPO_LORA_TRAINING_RUN_ARTIFACT_REFS),
        }
    )


def _validate_parent_ref(out_dir: Path, manifest: DPOLoRATrainingRunManifest) -> None:
    parent_dir = Path(manifest.parent_sft_policy.artifact_dir)
    if not parent_dir.is_absolute():
        parent_dir = out_dir / parent_dir
    parent = load_positive_sft_lora_training_artifact(parent_dir.resolve())
    if hash_file(parent.out_dir / MANIFEST_FILENAME) != (
        manifest.parent_sft_policy.manifest_hash
    ):
        raise ValueError("DPO parent SFT manifest hash mismatch")
    if parent.manifest.training_run_id != manifest.parent_sft_policy.training_run_id:
        raise ValueError("DPO parent SFT training-run id mismatch")
    if parent.manifest.adapter_directory_hash != (
        manifest.parent_sft_policy.adapter_directory_hash
    ):
        raise ValueError("DPO parent SFT adapter hash mismatch")


def _validate_source_refs(out_dir: Path, manifest: DPOLoRATrainingRunManifest) -> None:
    for source_ref in manifest.source_dpo_training_materializations:
        source_dir = Path(source_ref.artifact_dir)
        if not source_dir.is_absolute():
            source_dir = out_dir / source_dir
        source_dir = source_dir.resolve()
        if hash_file(source_dir / MANIFEST_FILENAME) != source_ref.manifest_hash:
            raise ValueError("source DPO materialization manifest hash mismatch")
        source_manifest = json.loads((source_dir / MANIFEST_FILENAME).read_text())
        materializations_path = resolve_relative_artifact_ref(
            source_dir,
            source_manifest["artifacts"]["materializations"],
        )
        if hash_file(materializations_path) != source_ref.materializations_jsonl_hash:
            raise ValueError("source DPO materializations JSONL hash mismatch")


def _load_steps(path: Path) -> tuple[DPOLoRATrainingStepRecord, ...]:
    return tuple(
        DPOLoRATrainingStepRecord.model_validate(payload)
        for payload in load_jsonl_objects(path)
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
