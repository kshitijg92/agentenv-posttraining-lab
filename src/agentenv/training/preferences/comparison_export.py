from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    PREFERENCE_COMPARISON_EXPORT_ARTIFACT_REFS,
    PREFERENCE_COMPARISON_EXPORT_ARTIFACT_SCHEMA_VERSION,
    PreferenceComparisonExportManifest,
    load_preference_comparison_export_manifest,
)
from agentenv.hashing import hash_file
from agentenv.training.candidates.export import (
    TrainingCandidateExport,
    load_training_candidate_export_artifact,
)
from agentenv.training.preferences.builder import (
    PREFERENCE_DISCOVERY_METHOD,
    PREFERENCE_DISCOVERY_VERSION,
    compute_preference_discovery_code_hash,
    discover_preference_comparison_candidates_from_export,
)
from agentenv.training.preferences.schema import (
    PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION,
    PreferenceComparisonCandidateRecord,
)


@dataclass(frozen=True)
class PreferenceComparisonExport:
    out_dir: Path
    manifest: PreferenceComparisonExportManifest
    records: tuple[PreferenceComparisonCandidateRecord, ...]
    source_training_candidate_export: TrainingCandidateExport


def export_preference_comparison_candidates(
    training_candidate_export_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> PreferenceComparisonExport:
    candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    records = discover_preference_comparison_candidates_from_export(candidate_export)
    _validate_unique_comparison_candidate_ids(records)

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    records_path = resolve_relative_artifact_ref(
        out_dir,
        PREFERENCE_COMPARISON_EXPORT_ARTIFACT_REFS["comparison_candidates"],
    )
    write_preference_comparison_candidates_jsonl(records_path, records)
    manifest = build_preference_comparison_export_manifest(
        out_dir=out_dir,
        candidate_export=candidate_export,
        records_path=records_path,
        records=records,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_preference_comparison_export_artifact(out_dir)


def load_preference_comparison_export_artifact(
    export_dir: Path,
) -> PreferenceComparisonExport:
    export_dir = export_dir.resolve()
    manifest = load_preference_comparison_export_manifest(
        export_dir / MANIFEST_FILENAME
    )
    candidate_export = _load_pinned_training_candidate_export(
        export_dir,
        artifact_dir=manifest.source_training_candidate_export.artifact_dir,
        expected_manifest_hash=(
            manifest.source_training_candidate_export.manifest_hash
        ),
    )
    records_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["comparison_candidates"],
    )
    observed_records_hash = hash_file(records_path)
    if observed_records_hash != manifest.comparison_candidates_jsonl_hash:
        raise ValueError(
            "Preference comparison candidate JSONL hash mismatch: "
            f"{observed_records_hash!r} != "
            f"{manifest.comparison_candidates_jsonl_hash!r}"
        )
    records = load_preference_comparison_candidates_jsonl(records_path)
    _validate_unique_comparison_candidate_ids(records)
    _validate_manifest_counts(manifest, records)

    expected_records = discover_preference_comparison_candidates_from_export(
        candidate_export
    )
    if records != expected_records:
        raise ValueError(
            "Persisted preference comparison candidates do not match discovery "
            "recomputed from the pinned training candidate export"
        )
    _validate_manifest_discovery_provenance(manifest, records)
    return PreferenceComparisonExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
        source_training_candidate_export=candidate_export,
    )


def write_preference_comparison_candidates_jsonl(
    path: Path,
    records: tuple[PreferenceComparisonCandidateRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_preference_comparison_candidates_jsonl(
    path: Path,
) -> tuple[PreferenceComparisonCandidateRecord, ...]:
    records: list[PreferenceComparisonCandidateRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(PreferenceComparisonCandidateRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PreferenceComparisonCandidateRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_preference_comparison_export_manifest(
    *,
    out_dir: Path,
    candidate_export: TrainingCandidateExport,
    records_path: Path,
    records: tuple[PreferenceComparisonCandidateRecord, ...],
) -> PreferenceComparisonExportManifest:
    expected_records_path = resolve_relative_artifact_ref(
        out_dir,
        PREFERENCE_COMPARISON_EXPORT_ARTIFACT_REFS["comparison_candidates"],
    )
    if records_path.resolve() != expected_records_path:
        raise ValueError(
            "Preference comparison JSONL path does not match manifest artifact ref"
        )
    source_manifest_path = candidate_export.out_dir / MANIFEST_FILENAME
    return PreferenceComparisonExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.PREFERENCE_COMPARISON_EXPORT,
            "artifact_schema_version": (
                PREFERENCE_COMPARISON_EXPORT_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "source_training_candidate_export": {
                "artifact_dir": str(candidate_export.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
            },
            "training_authorization": "not_authorized",
            "preference_comparison_candidate_record_schema_version": (
                PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION
            ),
            "discovery_method": PREFERENCE_DISCOVERY_METHOD,
            "discovery_version": PREFERENCE_DISCOVERY_VERSION,
            "discovery_code_hash": compute_preference_discovery_code_hash(),
            "record_count": len(records),
            "shared_context_count": len(
                {record.shared_context.shared_context_id for record in records}
            ),
            "comparison_candidates_jsonl_hash": hash_file(records_path),
            "artifacts": dict(PREFERENCE_COMPARISON_EXPORT_ARTIFACT_REFS),
        }
    )


def _load_pinned_training_candidate_export(
    owner_dir: Path,
    *,
    artifact_dir: str,
    expected_manifest_hash: str,
) -> TrainingCandidateExport:
    source_dir = _resolve_pinned_artifact_dir(owner_dir, artifact_dir)
    observed_manifest_hash = hash_file(source_dir / MANIFEST_FILENAME)
    if observed_manifest_hash != expected_manifest_hash:
        raise ValueError(
            "Preference comparison source training candidate manifest hash "
            f"mismatch: {observed_manifest_hash!r} != {expected_manifest_hash!r}"
        )
    return load_training_candidate_export_artifact(source_dir)


def _resolve_pinned_artifact_dir(owner_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = owner_dir / path
    return path.resolve()


def _validate_manifest_counts(
    manifest: PreferenceComparisonExportManifest,
    records: tuple[PreferenceComparisonCandidateRecord, ...],
) -> None:
    if len(records) != manifest.record_count:
        raise ValueError(
            "Preference comparison candidate record count mismatch: "
            f"{len(records)} != {manifest.record_count}"
        )
    shared_context_count = len(
        {record.shared_context.shared_context_id for record in records}
    )
    if shared_context_count != manifest.shared_context_count:
        raise ValueError(
            "Preference comparison shared-context count mismatch: "
            f"{shared_context_count} != {manifest.shared_context_count}"
        )


def _validate_manifest_discovery_provenance(
    manifest: PreferenceComparisonExportManifest,
    records: tuple[PreferenceComparisonCandidateRecord, ...],
) -> None:
    expected = (
        PREFERENCE_DISCOVERY_METHOD,
        PREFERENCE_DISCOVERY_VERSION,
        compute_preference_discovery_code_hash(),
    )
    observed = (
        manifest.discovery_method,
        manifest.discovery_version,
        manifest.discovery_code_hash,
    )
    if observed != expected:
        raise ValueError(
            "Preference comparison manifest discovery provenance does not match "
            "the active discovery implementation"
        )
    for record in records:
        record_provenance = record.discovery_provenance
        if (
            record_provenance.discovery_method,
            record_provenance.discovery_version,
            record_provenance.discovery_code_hash,
        ) != observed:
            raise ValueError(
                "Preference comparison record discovery provenance differs from "
                "its export manifest"
            )


def _validate_unique_comparison_candidate_ids(
    records: tuple[PreferenceComparisonCandidateRecord, ...],
) -> None:
    candidate_ids = [record.comparison_candidate_id for record in records]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("Preference comparison candidate ids must be unique")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
