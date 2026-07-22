from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence, cast

from pydantic import TypeAdapter, ValidationError

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    DPO_TRAINING_MATERIALIZATION_ARTIFACT_REFS,
    DPO_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION,
    DPOTrainingMaterializationManifest,
    TrainingAuthorizationOverride,
    load_dpo_training_materialization_manifest,
    load_preference_pair_export_manifest,
)
from agentenv.hashing import hash_file
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    load_model_input_protocol,
)
from agentenv.training.preferences.hashing import hash_preference_pair_record
from agentenv.training.preferences.materialization.builder import (
    DPO_TRAINING_MATERIALIZER_VERSION,
    compute_dpo_training_materializer_code_hash,
    materialize_dpo_preference_pair_inputs,
)
from agentenv.training.preferences.materialization.schema import (
    DPO_TRAINING_MATERIALIZATION_RECORD_SCHEMA_VERSION,
    DPOTrainingMaterializationRecord,
)
from agentenv.training.preferences.materialization.source_reconstruction import (
    reconstruct_dpo_preference_pair_inputs,
)
from agentenv.training.preferences.pair_export import (
    PreferencePairExport,
    load_preference_pair_export_artifact,
)
from agentenv.training.tokenization import (
    MaterializationTokenizer,
    load_pinned_tokenizer,
)


_MATERIALIZATION_RECORD_ADAPTER = TypeAdapter(DPOTrainingMaterializationRecord)


@dataclass(frozen=True)
class DPOTrainingMaterializationExport:
    out_dir: Path
    manifest: DPOTrainingMaterializationManifest
    records: tuple[DPOTrainingMaterializationRecord, ...]


def export_dpo_training_materializations(
    preference_pair_export_dir: Path,
    model_input_protocol_path: Path,
    out_dir: Path,
    *,
    max_sequence_length: int,
    tokenizer_cache_dir: Path | None = None,
    local_files_only: bool = False,
    authorization_override: TrainingAuthorizationOverride | None = None,
    overwrite: bool = False,
) -> DPOTrainingMaterializationExport:
    source_export = load_preference_pair_export_artifact(preference_pair_export_dir)
    protocol = load_model_input_protocol(model_input_protocol_path)
    tokenizer = load_pinned_tokenizer(
        protocol,
        cache_dir=tokenizer_cache_dir,
        local_files_only=local_files_only,
    )
    materialization_inputs = reconstruct_dpo_preference_pair_inputs(source_export)
    records = materialize_dpo_preference_pair_inputs(
        materialization_inputs,
        protocol=protocol,
        tokenizer=tokenizer,
        max_sequence_length=max_sequence_length,
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    records_path = resolve_relative_artifact_ref(
        out_dir,
        DPO_TRAINING_MATERIALIZATION_ARTIFACT_REFS["materializations"],
    )
    write_dpo_training_materialization_records_jsonl(records_path, records)
    manifest = build_dpo_training_materialization_manifest(
        out_dir=out_dir,
        source_export=source_export,
        protocol=protocol,
        records_path=records_path,
        records=records,
        max_sequence_length=max_sequence_length,
        authorization_override=authorization_override,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return _load_and_validate_dpo_training_materialization_artifact(
        out_dir,
        tokenizer=tokenizer,
    )


def load_dpo_training_materialization_artifact(
    export_dir: Path,
    *,
    tokenizer_cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> DPOTrainingMaterializationExport:
    return _load_and_validate_dpo_training_materialization_artifact(
        export_dir,
        tokenizer=None,
        tokenizer_cache_dir=tokenizer_cache_dir,
        local_files_only=local_files_only,
    )


def _load_and_validate_dpo_training_materialization_artifact(
    export_dir: Path,
    *,
    tokenizer: MaterializationTokenizer | None,
    tokenizer_cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> DPOTrainingMaterializationExport:
    export_dir = export_dir.resolve()
    manifest = load_dpo_training_materialization_manifest(
        export_dir / MANIFEST_FILENAME
    )
    records_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["materializations"],
    )
    observed_records_hash = hash_file(records_path)
    if observed_records_hash != manifest.materializations_jsonl_hash:
        raise ValueError(
            "DPO materializations JSONL hash mismatch: "
            f"{observed_records_hash!r} != "
            f"{manifest.materializations_jsonl_hash!r}"
        )
    records = load_dpo_training_materialization_records_jsonl(records_path)
    _validate_manifest_counts(manifest, records)

    source_export = _load_pinned_preference_pair_export(export_dir, manifest)
    _validate_exact_source_coverage(source_export, records)
    protocol = _load_pinned_model_input_protocol(export_dir, manifest)
    _validate_record_provenance(manifest, records)

    active_tokenizer = tokenizer
    if active_tokenizer is None:
        active_tokenizer = load_pinned_tokenizer(
            protocol,
            cache_dir=tokenizer_cache_dir,
            local_files_only=local_files_only,
        )
    materialization_inputs = reconstruct_dpo_preference_pair_inputs(source_export)
    expected_records = materialize_dpo_preference_pair_inputs(
        materialization_inputs,
        protocol=protocol,
        tokenizer=active_tokenizer,
        max_sequence_length=manifest.max_sequence_length,
    )
    if records != expected_records:
        raise ValueError(
            "Persisted DPO materializations do not match records rebuilt from "
            "their pinned sources"
        )
    return DPOTrainingMaterializationExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


def write_dpo_training_materialization_records_jsonl(
    path: Path,
    records: Sequence[DPOTrainingMaterializationRecord],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_dpo_training_materialization_records_jsonl(
    path: Path,
) -> tuple[DPOTrainingMaterializationRecord, ...]:
    records: list[DPOTrainingMaterializationRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(_MATERIALIZATION_RECORD_ADAPTER.validate_python(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"DPOTrainingMaterializationRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_dpo_training_materialization_manifest(
    *,
    out_dir: Path,
    source_export: PreferencePairExport,
    protocol: LoadedModelInputProtocol,
    records_path: Path,
    records: Sequence[DPOTrainingMaterializationRecord],
    max_sequence_length: int,
    authorization_override: TrainingAuthorizationOverride | None = None,
) -> DPOTrainingMaterializationManifest:
    expected_records_path = resolve_relative_artifact_ref(
        out_dir,
        DPO_TRAINING_MATERIALIZATION_ARTIFACT_REFS["materializations"],
    )
    if expected_records_path != records_path.resolve():
        raise ValueError("DPO materialization JSONL path does not match artifact ref")
    source_manifest_path = source_export.out_dir / MANIFEST_FILENAME
    source_pairs_path = resolve_relative_artifact_ref(
        source_export.out_dir,
        source_export.manifest.artifacts["preference_pairs"],
    )
    completed_count = sum(record.status == "completed" for record in records)
    sequence_length_exceeded_count = sum(
        record.status == "failed" and record.failure_kind == "sequence_length_exceeded"
        for record in records
    )
    materialization_error_count = sum(
        record.status == "failed" and record.failure_kind == "materialization_error"
        for record in records
    )
    failed_count = sequence_length_exceeded_count + materialization_error_count
    return DPOTrainingMaterializationManifest.model_validate(
        {
            "artifact_type": ArtifactType.DPO_TRAINING_MATERIALIZATION,
            "artifact_schema_version": (
                DPO_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "training_authorization": (
                "authorized"
                if authorization_override is not None
                else "not_authorized"
            ),
            "training_authorization_override": (
                None
                if authorization_override is None
                else authorization_override.model_dump(mode="json")
            ),
            "source_preference_pair_export": {
                "artifact_dir": str(source_export.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
                "preference_pairs_jsonl_hash": hash_file(source_pairs_path),
            },
            "model_input_protocol_path": str(protocol.source_path),
            "model_input_protocol_id": protocol.record.protocol_id,
            "model_input_protocol_hash": hash_file(protocol.source_path),
            "serialization_mode": "shared_context_next_action",
            "max_sequence_length": max_sequence_length,
            "materializer_version": DPO_TRAINING_MATERIALIZER_VERSION,
            "materializer_code_hash": compute_dpo_training_materializer_code_hash(),
            "dpo_training_materialization_record_schema_version": (
                DPO_TRAINING_MATERIALIZATION_RECORD_SCHEMA_VERSION
            ),
            "record_count": len(records),
            "completed_count": completed_count,
            "failed_count": failed_count,
            "sequence_length_exceeded_count": sequence_length_exceeded_count,
            "materialization_error_count": materialization_error_count,
            "materializations_jsonl_hash": hash_file(records_path),
            "artifacts": dict(DPO_TRAINING_MATERIALIZATION_ARTIFACT_REFS),
        }
    )


def _load_pinned_preference_pair_export(
    materialization_export_dir: Path,
    manifest: DPOTrainingMaterializationManifest,
) -> PreferencePairExport:
    source_ref = manifest.source_preference_pair_export
    source_dir = Path(source_ref.artifact_dir)
    if not source_dir.is_absolute():
        source_dir = materialization_export_dir / source_dir
    source_dir = source_dir.resolve()
    source_manifest_path = source_dir / MANIFEST_FILENAME
    if hash_file(source_manifest_path) != source_ref.manifest_hash:
        raise ValueError("Source preference-pair export manifest hash mismatch")
    source_manifest = load_preference_pair_export_manifest(source_manifest_path)
    source_pairs_path = resolve_relative_artifact_ref(
        source_dir,
        source_manifest.artifacts["preference_pairs"],
    )
    if hash_file(source_pairs_path) != source_ref.preference_pairs_jsonl_hash:
        raise ValueError("Source preference-pair JSONL hash mismatch")
    source_export = load_preference_pair_export_artifact(source_dir)
    if (
        hash_file(source_manifest_path),
        hash_file(source_pairs_path),
    ) != (source_ref.manifest_hash, source_ref.preference_pairs_jsonl_hash):
        raise ValueError("Source preference-pair export changed while loading")
    return source_export


def _load_pinned_model_input_protocol(
    materialization_export_dir: Path,
    manifest: DPOTrainingMaterializationManifest,
) -> LoadedModelInputProtocol:
    protocol_path = Path(manifest.model_input_protocol_path)
    if not protocol_path.is_absolute():
        protocol_path = materialization_export_dir / protocol_path
    protocol_path = protocol_path.resolve()
    if hash_file(protocol_path) != manifest.model_input_protocol_hash:
        raise ValueError("DPO model input protocol hash mismatch")
    protocol = load_model_input_protocol(protocol_path)
    if protocol.record.protocol_id != manifest.model_input_protocol_id:
        raise ValueError("DPO model input protocol id does not match manifest")
    if hash_file(protocol_path) != manifest.model_input_protocol_hash:
        raise ValueError("DPO model input protocol changed while loading")
    return protocol


def _validate_exact_source_coverage(
    source_export: PreferencePairExport,
    records: Sequence[DPOTrainingMaterializationRecord],
) -> None:
    pair_ids = [pair.preference_pair_id for pair in source_export.records]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("Source preference-pair ids must be unique")
    if len(records) != len(source_export.records):
        raise ValueError(
            "DPO materialization record count does not equal source pair count"
        )
    for record_index, (pair, record) in enumerate(
        zip(source_export.records, records, strict=True)
    ):
        if record.source_preference_pair_id != pair.preference_pair_id:
            raise ValueError(
                "DPO materialization source order/id mismatch; "
                f"record_index={record_index}"
            )
        if record.source_preference_pair_record_hash != (
            hash_preference_pair_record(pair)
        ):
            raise ValueError(
                "DPO materialization source pair hash mismatch; "
                f"record_index={record_index}"
            )


def _validate_record_provenance(
    manifest: DPOTrainingMaterializationManifest,
    records: Sequence[DPOTrainingMaterializationRecord],
) -> None:
    expected = (
        manifest.model_input_protocol_id,
        manifest.model_input_protocol_hash,
        manifest.serialization_mode,
        manifest.max_sequence_length,
        manifest.materializer_version,
        manifest.materializer_code_hash,
        manifest.dpo_training_materialization_record_schema_version,
    )
    for record_index, record in enumerate(records):
        observed = (
            record.model_input_protocol_id,
            record.model_input_protocol_hash,
            record.serialization_mode,
            record.max_sequence_length,
            record.materializer_version,
            record.materializer_code_hash,
            record.schema_version,
        )
        if observed != expected:
            raise ValueError(
                "DPO materialization record provenance differs from manifest; "
                f"record_index={record_index}"
            )


def _validate_manifest_counts(
    manifest: DPOTrainingMaterializationManifest,
    records: Sequence[DPOTrainingMaterializationRecord],
) -> None:
    expected = {
        "record_count": len(records),
        "completed_count": sum(record.status == "completed" for record in records),
        "failed_count": sum(record.status == "failed" for record in records),
        "sequence_length_exceeded_count": sum(
            record.status == "failed"
            and record.failure_kind == "sequence_length_exceeded"
            for record in records
        ),
        "materialization_error_count": sum(
            record.status == "failed" and record.failure_kind == "materialization_error"
            for record in records
        ),
    }
    for field_name, expected_value in expected.items():
        if getattr(manifest, field_name) != expected_value:
            raise ValueError(
                f"DPO materialization manifest {field_name} mismatch: "
                f"{getattr(manifest, field_name)!r} != {expected_value!r}"
            )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
