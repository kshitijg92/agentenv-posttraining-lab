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
    POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_REFS,
    POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION,
    PositiveSFTTrainingMaterializationManifest,
    load_positive_sft_export_manifest,
    load_positive_sft_training_materialization_manifest,
)
from agentenv.hashing import hash_file, hash_json
from agentenv.models.input_protocol import (
    LoadedModelInputProtocol,
    load_model_input_protocol,
)
from agentenv.training.positive_sft.export import (
    PositiveSFTExport,
    load_positive_sft_export_artifact,
)
from agentenv.training.positive_sft.materialization.builder import (
    POSITIVE_SFT_TRAINING_MATERIALIZER_VERSION,
    compute_positive_sft_training_materializer_code_hash,
    materialize_positive_sft_examples,
)
from agentenv.training.positive_sft.materialization.schema import (
    POSITIVE_SFT_TRAINING_MATERIALIZATION_RECORD_SCHEMA_VERSION,
    PositiveSFTTrainingMaterializationRecord,
)
from agentenv.training.positive_sft.materialization.tokenization import (
    MaterializationTokenizer,
    load_pinned_tokenizer,
)


_MATERIALIZATION_RECORD_ADAPTER = TypeAdapter(
    PositiveSFTTrainingMaterializationRecord
)


@dataclass(frozen=True)
class PositiveSFTTrainingMaterializationExport:
    out_dir: Path
    manifest: PositiveSFTTrainingMaterializationManifest
    records: tuple[PositiveSFTTrainingMaterializationRecord, ...]


def export_positive_sft_training_materializations(
    positive_sft_export_dir: Path,
    model_input_protocol_path: Path,
    out_dir: Path,
    *,
    max_sequence_length: int,
    tokenizer_cache_dir: Path | None = None,
    local_files_only: bool = False,
    overwrite: bool = False,
) -> PositiveSFTTrainingMaterializationExport:
    source_export = load_positive_sft_export_artifact(positive_sft_export_dir)
    protocol = load_model_input_protocol(model_input_protocol_path)
    tokenizer = load_pinned_tokenizer(
        protocol,
        cache_dir=tokenizer_cache_dir,
        local_files_only=local_files_only,
    )
    records = materialize_positive_sft_examples(
        source_export.records,
        protocol=protocol,
        tokenizer=tokenizer,
        max_sequence_length=max_sequence_length,
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    records_path = (
        out_dir
        / POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_REFS["materializations"]
    )
    write_positive_sft_training_materialization_records_jsonl(
        records_path,
        records,
    )
    manifest = build_positive_sft_training_materialization_manifest(
        out_dir=out_dir,
        source_export=source_export,
        protocol=protocol,
        records_path=records_path,
        records=records,
        max_sequence_length=max_sequence_length,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return _load_and_validate_positive_sft_training_materialization_artifact(
        out_dir,
        tokenizer=tokenizer,
    )


def load_positive_sft_training_materialization_artifact(
    export_dir: Path,
    *,
    tokenizer_cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> PositiveSFTTrainingMaterializationExport:
    return _load_and_validate_positive_sft_training_materialization_artifact(
        export_dir,
        tokenizer=None,
        tokenizer_cache_dir=tokenizer_cache_dir,
        local_files_only=local_files_only,
    )


def _load_and_validate_positive_sft_training_materialization_artifact(
    export_dir: Path,
    *,
    tokenizer: MaterializationTokenizer | None,
    tokenizer_cache_dir: Path | None = None,
    local_files_only: bool = False,
) -> PositiveSFTTrainingMaterializationExport:
    export_dir = export_dir.resolve()
    manifest = load_positive_sft_training_materialization_manifest(
        export_dir / MANIFEST_FILENAME
    )
    records_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["materializations"],
    )
    observed_records_hash = hash_file(records_path)
    if observed_records_hash != manifest.materializations_jsonl_hash:
        raise ValueError(
            "Positive-SFT materializations JSONL hash mismatch: "
            f"{observed_records_hash!r} != "
            f"{manifest.materializations_jsonl_hash!r}"
        )
    records = load_positive_sft_training_materialization_records_jsonl(records_path)
    _validate_manifest_counts(manifest, records)

    source_export = _load_pinned_positive_sft_export(export_dir, manifest)
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
    expected_records = materialize_positive_sft_examples(
        source_export.records,
        protocol=protocol,
        tokenizer=active_tokenizer,
        max_sequence_length=manifest.max_sequence_length,
    )
    if records != expected_records:
        raise ValueError(
            "Persisted positive-SFT materializations do not match records rebuilt "
            "from their pinned sources"
        )
    return PositiveSFTTrainingMaterializationExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


def write_positive_sft_training_materialization_records_jsonl(
    path: Path,
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_positive_sft_training_materialization_records_jsonl(
    path: Path,
) -> tuple[PositiveSFTTrainingMaterializationRecord, ...]:
    records: list[PositiveSFTTrainingMaterializationRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(_MATERIALIZATION_RECORD_ADAPTER.validate_python(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PositiveSFTTrainingMaterializationRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_positive_sft_training_materialization_manifest(
    *,
    out_dir: Path,
    source_export: PositiveSFTExport,
    protocol: LoadedModelInputProtocol,
    records_path: Path,
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
    max_sequence_length: int,
) -> PositiveSFTTrainingMaterializationManifest:
    expected_records_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_REFS["materializations"],
    )
    if expected_records_path != records_path.resolve():
        raise ValueError(
            "Positive-SFT materialization JSONL path does not match artifact ref"
        )
    source_manifest_path = source_export.out_dir / MANIFEST_FILENAME
    source_examples_path = resolve_relative_artifact_ref(
        source_export.out_dir,
        source_export.manifest.artifacts["positive_sft_examples"],
    )
    completed_count = sum(record.status == "completed" for record in records)
    sequence_length_exceeded_count = sum(
        record.status == "failed"
        and record.failure_kind == "sequence_length_exceeded"
        for record in records
    )
    materialization_error_count = sum(
        record.status == "failed" and record.failure_kind == "materialization_error"
        for record in records
    )
    failed_count = sequence_length_exceeded_count + materialization_error_count
    return PositiveSFTTrainingMaterializationManifest.model_validate(
        {
            "artifact_type": ArtifactType.POSITIVE_SFT_TRAINING_MATERIALIZATION,
            "artifact_schema_version": (
                POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "training_authorization": "not_authorized",
            "source_positive_sft_export": {
                "artifact_dir": str(source_export.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
                "positive_sft_examples_jsonl_hash": hash_file(source_examples_path),
            },
            "model_input_protocol_path": str(protocol.source_path),
            "model_input_protocol_id": protocol.record.protocol_id,
            "model_input_protocol_hash": hash_file(protocol.source_path),
            "serialization_mode": "completed_transcript",
            "max_sequence_length": max_sequence_length,
            "materializer_version": POSITIVE_SFT_TRAINING_MATERIALIZER_VERSION,
            "materializer_code_hash": (
                compute_positive_sft_training_materializer_code_hash()
            ),
            "positive_sft_training_materialization_record_schema_version": (
                POSITIVE_SFT_TRAINING_MATERIALIZATION_RECORD_SCHEMA_VERSION
            ),
            "record_count": len(records),
            "completed_count": completed_count,
            "failed_count": failed_count,
            "sequence_length_exceeded_count": sequence_length_exceeded_count,
            "materialization_error_count": materialization_error_count,
            "materializations_jsonl_hash": hash_file(records_path),
            "artifacts": dict(
                POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_REFS
            ),
        }
    )


def _load_pinned_positive_sft_export(
    materialization_export_dir: Path,
    manifest: PositiveSFTTrainingMaterializationManifest,
) -> PositiveSFTExport:
    source_ref = manifest.source_positive_sft_export
    source_dir = Path(source_ref.artifact_dir)
    if not source_dir.is_absolute():
        source_dir = materialization_export_dir / source_dir
    source_dir = source_dir.resolve()
    source_manifest_path = source_dir / MANIFEST_FILENAME
    observed_manifest_hash = hash_file(source_manifest_path)
    if observed_manifest_hash != source_ref.manifest_hash:
        raise ValueError(
            "Source positive-SFT export manifest hash mismatch: "
            f"{observed_manifest_hash!r} != {source_ref.manifest_hash!r}"
        )
    source_manifest = load_positive_sft_export_manifest(source_manifest_path)
    source_examples_path = resolve_relative_artifact_ref(
        source_dir,
        source_manifest.artifacts["positive_sft_examples"],
    )
    observed_examples_hash = hash_file(source_examples_path)
    if observed_examples_hash != source_ref.positive_sft_examples_jsonl_hash:
        raise ValueError(
            "Source positive-SFT examples JSONL hash mismatch: "
            f"{observed_examples_hash!r} != "
            f"{source_ref.positive_sft_examples_jsonl_hash!r}"
        )
    source_export = load_positive_sft_export_artifact(source_dir)
    if (
        hash_file(source_manifest_path),
        hash_file(source_examples_path),
    ) != (
        source_ref.manifest_hash,
        source_ref.positive_sft_examples_jsonl_hash,
    ):
        raise ValueError("Source positive-SFT export changed while loading")
    return source_export


def _load_pinned_model_input_protocol(
    materialization_export_dir: Path,
    manifest: PositiveSFTTrainingMaterializationManifest,
) -> LoadedModelInputProtocol:
    protocol_path = Path(manifest.model_input_protocol_path)
    if not protocol_path.is_absolute():
        protocol_path = materialization_export_dir / protocol_path
    protocol_path = protocol_path.resolve()
    observed_hash = hash_file(protocol_path)
    if observed_hash != manifest.model_input_protocol_hash:
        raise ValueError(
            "Model input protocol hash mismatch: "
            f"{observed_hash!r} != {manifest.model_input_protocol_hash!r}"
        )
    protocol = load_model_input_protocol(protocol_path)
    if protocol.record.protocol_id != manifest.model_input_protocol_id:
        raise ValueError("Model input protocol id does not match manifest")
    if hash_file(protocol_path) != manifest.model_input_protocol_hash:
        raise ValueError("Model input protocol changed while loading")
    return protocol


def _validate_exact_source_coverage(
    source_export: PositiveSFTExport,
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
) -> None:
    source_ids = [example.example_id for example in source_export.records]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Source positive-SFT example ids must be unique")
    if len(records) != len(source_export.records):
        raise ValueError(
            "Positive-SFT materialization record count does not equal source "
            "example count"
        )
    for record_index, (example, record) in enumerate(
        zip(source_export.records, records, strict=True)
    ):
        if record.source_positive_sft_example_id != example.example_id:
            raise ValueError(
                "Positive-SFT materialization source order/id mismatch; "
                f"record_index={record_index}"
            )
        expected_source_hash = hash_json(example.model_dump(mode="json"))
        if record.source_positive_sft_example_record_hash != expected_source_hash:
            raise ValueError(
                "Positive-SFT materialization source record hash mismatch; "
                f"record_index={record_index}"
            )


def _validate_record_provenance(
    manifest: PositiveSFTTrainingMaterializationManifest,
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
) -> None:
    for record_index, record in enumerate(records):
        observed = (
            record.model_input_protocol_id,
            record.model_input_protocol_hash,
            record.serialization_mode,
            record.max_sequence_length,
            record.materializer_version,
            record.materializer_code_hash,
        )
        expected = (
            manifest.model_input_protocol_id,
            manifest.model_input_protocol_hash,
            manifest.serialization_mode,
            manifest.max_sequence_length,
            manifest.materializer_version,
            manifest.materializer_code_hash,
        )
        if observed != expected:
            raise ValueError(
                "Positive-SFT materialization record provenance does not match "
                f"manifest; record_index={record_index}"
            )


def _validate_manifest_counts(
    manifest: PositiveSFTTrainingMaterializationManifest,
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
) -> None:
    observed_counts = {
        "record_count": len(records),
        "completed_count": sum(record.status == "completed" for record in records),
        "failed_count": sum(record.status == "failed" for record in records),
        "sequence_length_exceeded_count": sum(
            record.status == "failed"
            and record.failure_kind == "sequence_length_exceeded"
            for record in records
        ),
        "materialization_error_count": sum(
            record.status == "failed"
            and record.failure_kind == "materialization_error"
            for record in records
        ),
    }
    for field_name, observed_count in observed_counts.items():
        expected_count = getattr(manifest, field_name)
        if observed_count != expected_count:
            raise ValueError(
                f"Positive-SFT materialization {field_name} mismatch: "
                f"{observed_count} != {expected_count}"
            )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
