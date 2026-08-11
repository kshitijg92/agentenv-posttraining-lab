from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, cast

from pydantic import TypeAdapter, ValidationError

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    POSITIVE_SFT_LORA_TRAINING_RUN_ARTIFACT_REFS,
    POSITIVE_SFT_LORA_TRAINING_RUN_ARTIFACT_SCHEMA_VERSION,
    PositiveSFTLoRATrainingRunManifest,
    PositiveSFTTrainingMaterializationManifest,
    load_positive_sft_lora_training_run_manifest,
    load_positive_sft_training_materialization_manifest,
)
from agentenv.hashing import hash_directory, hash_file
from agentenv.ids import new_positive_sft_lora_training_run_id
from agentenv.models.input_protocol import load_model_input_protocol
from agentenv.training.positive_sft.lora.config import (
    load_positive_sft_lora_training_config,
)
from agentenv.training.positive_sft.lora.engine import (
    SelectedTrainingSequence,
    execute_lora_qualification,
    execute_positive_sft_lora_training,
    select_positive_sft_training_sequences,
)
from agentenv.training.positive_sft.lora.model import (
    load_pinned_causal_lm,
    validate_lora_adapter_package,
)
from agentenv.training.positive_sft.lora.runtime import (
    capture_training_runtime_provenance,
    configure_process_determinism,
    require_requested_training_device,
)
from agentenv.training.positive_sft.lora.schema import (
    POSITIVE_SFT_LORA_TRAINING_RESULT_SCHEMA_VERSION,
    POSITIVE_SFT_LORA_TRAINING_STEP_SCHEMA_VERSION,
    CompletedPositiveSFTLoRATrainingResult,
    FailedPositiveSFTLoRATrainingResult,
    PositiveSFTLoRAQualificationResult,
    PositiveSFTLoRATrainingResult,
    PositiveSFTLoRATrainingStepRecord,
    PositiveSFTLoRATrainingConfig,
    SelectedPositiveSFTTrainingExample,
    TrainingFailureStage,
)
from agentenv.training.positive_sft.materialization.export import (
    PositiveSFTTrainingMaterializationExport,
    load_positive_sft_training_materialization_snapshot,
)
from agentenv.training.positive_sft.materialization.schema import (
    CompletedPositiveSFTTrainingMaterializationRecord,
)
from agentenv.training.positive_sft.export import (
    load_pinned_positive_sft_review,
    load_positive_sft_export_artifact,
)
from agentenv.training.positive_sft.review import (
    hash_positive_sft_review_record,
)


_RESULT_ADAPTER = TypeAdapter(PositiveSFTLoRATrainingResult)


@dataclass(frozen=True)
class PositiveSFTLoRATrainingArtifact:
    out_dir: Path
    manifest: PositiveSFTLoRATrainingRunManifest
    result: PositiveSFTLoRATrainingResult
    steps: tuple[PositiveSFTLoRATrainingStepRecord, ...]


def run_positive_sft_lora_training(
    source_materialization_dirs: Sequence[Path],
    training_config_path: Path,
    out_dir: Path,
    *,
    model_cache_dir: Path | None = None,
    local_files_only: bool = False,
    overwrite: bool = False,
) -> PositiveSFTLoRATrainingArtifact:
    config_path = training_config_path.resolve()
    config = load_positive_sft_lora_training_config(config_path)
    configure_process_determinism(config)
    sources = _load_authorized_sources(source_materialization_dirs)
    _validate_config_matches_sources(config, sources)
    selected_records = _select_treatment_records(sources, config=config)
    selected_sequences = select_positive_sft_training_sequences(
        selected_records,
    )
    _validate_training_exposure(selected_sequences, config=config)
    runtime_provenance = capture_training_runtime_provenance(config)
    require_requested_training_device(runtime_provenance)

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    steps_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_LORA_TRAINING_RUN_ARTIFACT_REFS["training_steps"],
    )
    steps_path.write_text("")
    result_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_LORA_TRAINING_RUN_ARTIFACT_REFS["training_result"],
    )
    incomplete_adapter_dir = out_dir / "adapter_incomplete"
    final_adapter_dir = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_LORA_TRAINING_RUN_ARTIFACT_REFS["adapter"],
    )

    run_id = new_positive_sft_lora_training_run_id()
    started_at = _utc_now()
    completed_steps: list[PositiveSFTLoRATrainingStepRecord] = []
    qualification: PositiveSFTLoRAQualificationResult | None = None
    stage: TrainingFailureStage = "qualification_model_loading"

    def record_stage(value: str) -> None:
        nonlocal stage
        stage = cast(TrainingFailureStage, value)

    def persist_step(step: PositiveSFTLoRATrainingStepRecord) -> None:
        completed_steps.append(step)
        with steps_path.open("a") as handle:
            handle.write(
                json.dumps(step.model_dump(mode="json"), sort_keys=True) + "\n"
            )

    try:
        qualification = execute_lora_qualification(
            base_model=load_pinned_causal_lm(
                config,
                cache_dir=model_cache_dir,
                local_files_only=local_files_only,
            ),
            selected_sequences=selected_sequences,
            config=config,
            on_stage=record_stage,
        )
        stage = "training_model_loading"

        def reload_base_model():
            return load_pinned_causal_lm(
                config,
                cache_dir=model_cache_dir,
                local_files_only=True,
            )

        execution = execute_positive_sft_lora_training(
            base_model=load_pinned_causal_lm(
                config,
                cache_dir=model_cache_dir,
                local_files_only=True,
            ),
            reload_base_model=reload_base_model,
            selected_sequences=selected_sequences,
            qualification=qualification,
            config=config,
            adapter_dir=incomplete_adapter_dir,
            on_stage=record_stage,
            on_step=persist_step,
        )
        stage = "artifact_persistence"
        incomplete_adapter_dir.rename(final_adapter_dir)
        result: PositiveSFTLoRATrainingResult = CompletedPositiveSFTLoRATrainingResult(
            training_run_id=run_id,
            started_at=started_at,
            finished_at=_utc_now(),
            selected_examples=execution.selected_examples,
            requested_step_count=config.max_steps,
            completed_step_count=len(execution.steps),
            runtime_provenance=runtime_provenance,
            status="completed",
            qualification=qualification,
            training_initial_adapter_state_matches_qualification=True,
            training_initial_frozen_state_matches_qualification=True,
            optimizer_isolation=execution.optimizer_isolation,
            parameter_state=execution.parameter_state,
            adapter_round_trip=execution.adapter_round_trip,
        )
    except Exception as exc:
        if final_adapter_dir.exists():
            final_adapter_dir.rename(out_dir / "adapter_failed")
        result = FailedPositiveSFTLoRATrainingResult(
            training_run_id=run_id,
            started_at=started_at,
            finished_at=_utc_now(),
            selected_examples=tuple(item.provenance for item in selected_sequences),
            requested_step_count=config.max_steps,
            completed_step_count=len(completed_steps),
            runtime_provenance=runtime_provenance,
            status="failed",
            qualification=qualification,
            failure_stage=stage,
            error_class=type(exc).__name__,
            error_message=str(exc) or type(exc).__name__,
        )

    result_path.write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    manifest = _build_manifest(
        out_dir=out_dir,
        sources=sources,
        config_path=config_path,
        result_path=result_path,
        steps_path=steps_path,
        result=result,
        trainer_code_hash=runtime_provenance.trainer_code_hash,
        adapter_dir=final_adapter_dir,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_positive_sft_lora_training_artifact(out_dir)


def load_positive_sft_lora_training_artifact(
    out_dir: Path,
) -> PositiveSFTLoRATrainingArtifact:
    out_dir = out_dir.resolve()
    manifest = load_positive_sft_lora_training_run_manifest(out_dir / MANIFEST_FILENAME)
    result_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["training_result"],
    )
    steps_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["training_steps"],
    )
    config_path = Path(manifest.training_config.path)
    if not config_path.is_absolute():
        config_path = out_dir / config_path
    config_path = config_path.resolve()
    if hash_file(config_path) != manifest.training_config.content_hash:
        raise ValueError("hash-pinned LoRA training config mismatch")
    if hash_file(result_path) != manifest.training_result_hash:
        raise ValueError("LoRA training result hash mismatch")
    if hash_file(steps_path) != manifest.training_steps_hash:
        raise ValueError("LoRA training steps hash mismatch")

    config = load_positive_sft_lora_training_config(config_path)
    if config.config_id != manifest.training_config.config_id:
        raise ValueError("training config id differs from manifest reference")
    result = _load_result(result_path)
    steps = _load_steps(steps_path)
    if result.training_run_id != manifest.training_run_id:
        raise ValueError("training result run id differs from manifest")
    if result.status != manifest.status:
        raise ValueError("training result status differs from manifest")
    if len(result.selected_examples) != manifest.selected_example_count:
        raise ValueError("selected example count differs from manifest")
    if result.requested_step_count != manifest.requested_step_count:
        raise ValueError("requested step count differs from manifest")
    if result.completed_step_count != manifest.completed_step_count:
        raise ValueError("completed step count differs from manifest")
    if len(steps) != result.completed_step_count:
        raise ValueError("persisted training-step count differs from result")
    if [step.step_index for step in steps] != list(range(len(steps))):
        raise ValueError("persisted training step indexes must be contiguous")
    _validate_executed_order(
        steps,
        selected_examples=result.selected_examples,
        owner="persisted training steps",
    )
    if result.qualification is not None:
        _validate_executed_order(
            result.qualification.steps,
            selected_examples=result.selected_examples,
            owner="persisted qualification steps",
        )
    if result.runtime_provenance.trainer_code_hash != manifest.trainer_code_hash:
        raise ValueError("training result code hash differs from manifest")
    if config.max_steps != manifest.requested_step_count:
        raise ValueError("training config step count differs from manifest")
    if config.base_model != manifest.base_model:
        raise ValueError("training config base model differs from manifest")
    if config.model_input_protocol_id != manifest.model_input_protocol_id:
        raise ValueError("training config input protocol differs from manifest")

    if manifest.status == "completed":
        adapter_dir = resolve_relative_artifact_ref(
            out_dir,
            manifest.artifacts["adapter"],
        )
        adapter_hash = hash_directory(adapter_dir)
        if adapter_hash != manifest.adapter_directory_hash:
            raise ValueError("persisted LoRA adapter directory hash mismatch")
        validate_lora_adapter_package(adapter_dir, base_model=config.base_model)
        if not isinstance(result, CompletedPositiveSFTLoRATrainingResult):
            raise ValueError("completed manifest requires a completed result")
        if (
            result.qualification.adapter_qualification.qualification_step_count
            != config.qualification_step_count
        ):
            raise ValueError("qualification step count differs from training config")
        if adapter_hash != result.adapter_round_trip.persisted_adapter_directory_hash:
            raise ValueError("adapter hash differs from round-trip audit")

    _validate_source_refs(out_dir, manifest)
    return PositiveSFTLoRATrainingArtifact(
        out_dir=out_dir,
        manifest=manifest,
        result=result,
        steps=steps,
    )


def _load_authorized_sources(
    source_dirs: Sequence[Path],
) -> tuple[PositiveSFTTrainingMaterializationExport, ...]:
    resolved_dirs = sorted(path.resolve() for path in source_dirs)
    if not resolved_dirs:
        raise ValueError("LoRA training requires at least one source materialization")
    if len(resolved_dirs) != len(set(resolved_dirs)):
        raise ValueError("LoRA training source materializations must be unique")

    sources: list[PositiveSFTTrainingMaterializationExport] = []
    for source_dir in resolved_dirs:
        source_manifest = load_positive_sft_training_materialization_manifest(
            source_dir / MANIFEST_FILENAME
        )
        if source_manifest.training_authorization != "authorized":
            raise ValueError(
                "LoRA training requires authorized positive-SFT materializations"
            )
        if source_manifest.training_authorization_override is None:
            raise ValueError(
                "authorized positive-SFT materialization is missing override provenance"
            )
        source = load_positive_sft_training_materialization_snapshot(source_dir)
        if source.manifest.training_authorization != "authorized":
            raise ValueError(
                "LoRA training requires authorized positive-SFT materializations"
            )
        if source.manifest.training_authorization_override is None:
            raise ValueError(
                "authorized positive-SFT materialization is missing override provenance"
            )
        sources.append(source)
    return tuple(sources)


def _validate_config_matches_sources(
    config: PositiveSFTLoRATrainingConfig,
    sources: Sequence[PositiveSFTTrainingMaterializationExport],
) -> None:
    protocol_ids = {source.manifest.model_input_protocol_id for source in sources}
    protocol_hashes = {source.manifest.model_input_protocol_hash for source in sources}
    if len(protocol_ids) != 1 or len(protocol_hashes) != 1:
        raise ValueError("LoRA training sources must share one model input protocol")

    for source in sources:
        manifest = source.manifest
        if config.model_input_protocol_id != manifest.model_input_protocol_id:
            raise ValueError("training config and source input protocol ids differ")
        protocol_path = Path(manifest.model_input_protocol_path)
        if not protocol_path.is_absolute():
            protocol_path = source.out_dir / protocol_path
        protocol_path = protocol_path.resolve()
        if hash_file(protocol_path) != manifest.model_input_protocol_hash:
            raise ValueError("source model input protocol hash mismatch")
        protocol = load_model_input_protocol(protocol_path)
        if protocol.record.model_checkpoint != config.base_model:
            raise ValueError(
                "training base model must equal each materialization protocol "
                "checkpoint"
            )


def _select_treatment_records(
    sources: Sequence[PositiveSFTTrainingMaterializationExport],
    *,
    config: PositiveSFTLoRATrainingConfig,
) -> tuple[CompletedPositiveSFTTrainingMaterializationRecord, ...]:
    raw_records: list[CompletedPositiveSFTTrainingMaterializationRecord] = []
    filtered_records: list[CompletedPositiveSFTTrainingMaterializationRecord] = []
    raw_task_ids: set[str] = set()
    filtered_task_ids: set[str] = set()
    observed_example_ids: set[str] = set()

    for source in sources:
        export_dir = Path(source.manifest.source_positive_sft_export.artifact_dir)
        if not export_dir.is_absolute():
            export_dir = source.out_dir / export_dir
        positive_sft_export = load_positive_sft_export_artifact(export_dir.resolve())
        examples_by_id = {
            example.example_id: example for example in positive_sft_export.records
        }
        if len(examples_by_id) != len(positive_sft_export.records):
            raise ValueError("positive-SFT export example ids must be unique")

        review_validation = load_pinned_positive_sft_review(
            positive_sft_export.out_dir,
            positive_sft_export.manifest,
        )
        reviews_by_hash = {
            hash_positive_sft_review_record(review): review
            for review in review_validation.review_artifact.reviews
        }
        if len(reviews_by_hash) != len(review_validation.review_artifact.reviews):
            raise ValueError("positive-SFT review record hashes must be unique")

        for record in source.records:
            if not isinstance(
                record,
                CompletedPositiveSFTTrainingMaterializationRecord,
            ):
                continue
            example_id = record.source_positive_sft_example_id
            if example_id in observed_example_ids:
                raise ValueError(
                    "positive-SFT example ids must be unique across materializations"
                )
            observed_example_ids.add(example_id)

            example = examples_by_id.get(example_id)
            if example is None:
                raise ValueError(
                    "materialization references an unknown positive-SFT example: "
                    f"{example_id}"
                )
            review_hash = (
                example.review_provenance.source_positive_sft_review_record_hash
            )
            review = reviews_by_hash.get(review_hash)
            if review is None:
                raise ValueError(
                    "positive-SFT example references an unknown review record: "
                    f"{example_id}"
                )
            if review.review_decision != "accepted":
                raise ValueError(
                    "materialized positive-SFT examples require accepted prefixes"
                )
            efficiency = review.efficiency_judgment
            if efficiency is None:
                raise ValueError(
                    "LoRA treatment selection requires completed efficiency reviews"
                )

            task_id = example.provenance_ids.task_id
            raw_records.append(record)
            raw_task_ids.add(task_id)
            if efficiency.review_decision == "accepted":
                filtered_records.append(record)
                filtered_task_ids.add(task_id)

    if not raw_records:
        raise ValueError("LoRA training sources contain no completed SFT rows")
    if not filtered_records:
        raise ValueError("efficiency filtering removed every completed SFT row")
    if filtered_task_ids != raw_task_ids:
        raise ValueError(
            "raw and efficiency-filtered treatments must cover the same task ids"
        )

    selected = (
        raw_records if config.data.treatment == "raw" else filtered_records
    )
    return tuple(
        sorted(
            selected,
            key=lambda record: (
                -record.supervised_token_count,
                record.source_positive_sft_example_id,
            ),
        )
    )


def _validate_training_exposure(
    selected_sequences: Sequence[SelectedTrainingSequence],
    *,
    config: PositiveSFTLoRATrainingConfig,
) -> None:
    observed_supervised_tokens = sum(
        selected_sequences[step_index % len(selected_sequences)]
        .provenance.stored_supervised_token_count
        for step_index in range(config.max_steps)
    )
    target = config.data.target_supervised_token_count
    tolerance = config.data.supervised_token_tolerance
    if abs(observed_supervised_tokens - target) > tolerance:
        raise ValueError(
            "LoRA training exposure is outside the configured supervised-token "
            f"tolerance: observed={observed_supervised_tokens}, target={target}, "
            f"tolerance={tolerance}"
        )


def _validate_executed_order(
    steps: Sequence[PositiveSFTLoRATrainingStepRecord],
    *,
    selected_examples: Sequence[SelectedPositiveSFTTrainingExample],
    owner: str,
) -> None:
    if steps and not selected_examples:
        raise ValueError(f"{owner} require selected examples")
    for step in steps:
        expected = selected_examples[step.step_index % len(selected_examples)]
        observed_fields = (
            step.source_positive_sft_example_id,
            step.source_materialization_record_hash,
            step.sequence_length,
            step.supervised_prediction_count,
            step.ignored_prediction_count,
        )
        expected_fields = (
            expected.source_positive_sft_example_id,
            expected.source_materialization_record_hash,
            expected.sequence_length,
            expected.effective_shifted_supervised_token_count,
            expected.ignored_prediction_count,
        )
        if observed_fields != expected_fields:
            raise ValueError(f"{owner} differ from deterministic selected order")


def _build_manifest(
    *,
    out_dir: Path,
    sources: Sequence[PositiveSFTTrainingMaterializationExport],
    config_path: Path,
    result_path: Path,
    steps_path: Path,
    result: PositiveSFTLoRATrainingResult,
    trainer_code_hash: str,
    adapter_dir: Path,
) -> PositiveSFTLoRATrainingRunManifest:
    source_refs = []
    for source in sources:
        source_manifest_path = source.out_dir / MANIFEST_FILENAME
        source_materializations_path = resolve_relative_artifact_ref(
            source.out_dir,
            source.manifest.artifacts["materializations"],
        )
        source_refs.append(
            {
                "artifact_dir": str(source.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
                "materializations_jsonl_hash": hash_file(
                    source_materializations_path
                ),
            }
        )
    artifacts = {
        key: value
        for key, value in POSITIVE_SFT_LORA_TRAINING_RUN_ARTIFACT_REFS.items()
        if key != "adapter" or result.status == "completed"
    }
    adapter_hash = hash_directory(adapter_dir) if result.status == "completed" else None
    config = load_positive_sft_lora_training_config(config_path)
    return PositiveSFTLoRATrainingRunManifest.model_validate(
        {
            "artifact_type": ArtifactType.POSITIVE_SFT_LORA_TRAINING_RUN,
            "artifact_schema_version": (
                POSITIVE_SFT_LORA_TRAINING_RUN_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "training_run_id": result.training_run_id,
            "status": result.status,
            "source_positive_sft_training_materializations": source_refs,
            "training_config": {
                "path": str(config_path),
                "content_hash": hash_file(config_path),
                "config_id": config.config_id,
            },
            "model_input_protocol_id": sources[0].manifest.model_input_protocol_id,
            "model_input_protocol_hash": sources[0].manifest.model_input_protocol_hash,
            "base_model": config.base_model.model_dump(mode="json"),
            "trainer_code_hash": trainer_code_hash,
            "training_result_schema_version": (
                POSITIVE_SFT_LORA_TRAINING_RESULT_SCHEMA_VERSION
            ),
            "training_step_schema_version": (
                POSITIVE_SFT_LORA_TRAINING_STEP_SCHEMA_VERSION
            ),
            "selected_example_count": len(result.selected_examples),
            "requested_step_count": result.requested_step_count,
            "completed_step_count": result.completed_step_count,
            "training_result_hash": hash_file(result_path),
            "training_steps_hash": hash_file(steps_path),
            "adapter_directory_hash": adapter_hash,
            "artifacts": artifacts,
        }
    )


def _validate_source_refs(
    out_dir: Path,
    manifest: PositiveSFTLoRATrainingRunManifest,
) -> None:
    for source_ref in manifest.source_positive_sft_training_materializations:
        source_dir = Path(source_ref.artifact_dir)
        if not source_dir.is_absolute():
            source_dir = out_dir / source_dir
        source_dir = source_dir.resolve()
        if hash_file(source_dir / MANIFEST_FILENAME) != source_ref.manifest_hash:
            raise ValueError(
                "source positive-SFT materialization manifest hash mismatch"
            )
        source_manifest = (
            PositiveSFTTrainingMaterializationManifest.model_validate_json(
                (source_dir / MANIFEST_FILENAME).read_text()
            )
        )
        materializations_path = resolve_relative_artifact_ref(
            source_dir,
            source_manifest.artifacts["materializations"],
        )
        if hash_file(materializations_path) != source_ref.materializations_jsonl_hash:
            raise ValueError(
                "source positive-SFT materializations JSONL hash mismatch"
            )


def _load_result(path: Path) -> PositiveSFTLoRATrainingResult:
    try:
        return _RESULT_ADAPTER.validate_json(path.read_text())
    except ValidationError as exc:
        raise ValidationError.from_exception_data(
            f"PositiveSFTLoRATrainingResult at {path}",
            cast(Any, exc.errors()),
        ) from exc


def _load_steps(path: Path) -> tuple[PositiveSFTLoRATrainingStepRecord, ...]:
    steps: list[PositiveSFTLoRATrainingStepRecord] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            steps.append(PositiveSFTLoRATrainingStepRecord.model_validate_json(line))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PositiveSFTLoRATrainingStepRecord at {path}:{line_number}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(steps)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
