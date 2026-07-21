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
    PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS,
    PREFERENCE_PAIR_EXPORT_ARTIFACT_REFS,
    PREFERENCE_PAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
    PreferencePairExportManifest,
    load_preference_pair_export_manifest,
)
from agentenv.hashing import hash_file
from agentenv.training.preferences.export import (
    PreferenceComparisonExport,
    load_preference_comparison_export_artifact,
)
from agentenv.training.preferences.hashing import (
    build_preference_pair_id,
    hash_preference_adjudication_record,
    hash_preference_comparison_candidate_record,
)
from agentenv.training.preferences.review import (
    PreferenceAdjudicationReviewValidation,
    validate_preference_adjudication_review_artifact,
)
from agentenv.training.preferences.schema import (
    PREFERENCE_PAIR_RECORD_SCHEMA_VERSION,
    PreferenceAdjudicationRecord,
    PreferenceComparisonCandidateRecord,
    PreferencePairRecord,
    PreferencePairSource,
)


@dataclass(frozen=True)
class PreferencePairExport:
    out_dir: Path
    manifest: PreferencePairExportManifest
    records: tuple[PreferencePairRecord, ...]


def export_preference_pairs(
    comparison_export_dir: Path,
    adjudication_review_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> PreferencePairExport:
    comparison_export = load_preference_comparison_export_artifact(
        comparison_export_dir
    )
    review_validation = validate_preference_adjudication_review_artifact(
        adjudication_review_dir
    )
    validate_preference_review_matches_comparison_export(
        comparison_export,
        review_validation,
    )
    records = build_preference_pair_records(
        comparison_export,
        review_validation,
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    records_path = resolve_relative_artifact_ref(
        out_dir,
        PREFERENCE_PAIR_EXPORT_ARTIFACT_REFS["preference_pairs"],
    )
    write_preference_pair_records_jsonl(records_path, records)
    manifest = build_preference_pair_export_manifest(
        out_dir=out_dir,
        comparison_export=comparison_export,
        review_validation=review_validation,
        records_path=records_path,
        records=records,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_preference_pair_export_artifact(out_dir)


def load_preference_pair_export_artifact(export_dir: Path) -> PreferencePairExport:
    export_dir = export_dir.resolve()
    manifest = load_preference_pair_export_manifest(export_dir / MANIFEST_FILENAME)
    records_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["preference_pairs"],
    )
    observed_records_hash = hash_file(records_path)
    if observed_records_hash != manifest.preference_pairs_jsonl_hash:
        raise ValueError(
            "Preference pair JSONL hash mismatch: "
            f"{observed_records_hash!r} != {manifest.preference_pairs_jsonl_hash!r}"
        )
    records = load_preference_pair_records_jsonl(records_path)
    if len(records) != manifest.record_count:
        raise ValueError(
            "Preference pair record count mismatch: "
            f"{len(records)} != {manifest.record_count}"
        )
    _validate_unique_preference_pair_records(records)

    comparison_export = _load_pinned_comparison_export(export_dir, manifest)
    review_validation = _load_pinned_adjudication_review(export_dir, manifest)
    validate_preference_review_matches_comparison_export(
        comparison_export,
        review_validation,
    )
    expected_records = build_preference_pair_records(
        comparison_export,
        review_validation,
    )
    if records != expected_records:
        raise ValueError(
            "Persisted preference pairs do not match preferred adjudications "
            "rebuilt from their pinned source artifacts"
        )
    validate_preference_pair_manifest_counts(
        manifest,
        comparison_export=comparison_export,
        review_validation=review_validation,
        records=records,
    )
    return PreferencePairExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


def build_preference_pair_records(
    comparison_export: PreferenceComparisonExport,
    review_validation: PreferenceAdjudicationReviewValidation,
) -> tuple[PreferencePairRecord, ...]:
    validate_preference_review_matches_comparison_export(
        comparison_export,
        review_validation,
    )
    adjudications_by_candidate = _index_adjudications(
        review_validation.review_artifact.adjudications
    )
    records = tuple(
        _build_preference_pair_record(
            candidate,
            adjudications_by_candidate[candidate.comparison_candidate_id],
        )
        for candidate in comparison_export.records
        if _is_preferred_adjudication(
            adjudications_by_candidate[candidate.comparison_candidate_id]
        )
    )
    _validate_unique_preference_pair_records(records)
    return records


def _build_preference_pair_record(
    candidate: PreferenceComparisonCandidateRecord,
    adjudication: PreferenceAdjudicationRecord,
) -> PreferencePairRecord:
    candidate_hash = hash_preference_comparison_candidate_record(candidate)
    adjudication_hash = hash_preference_adjudication_record(adjudication)
    source = PreferencePairSource(
        comparison_candidate_id=candidate.comparison_candidate_id,
        source_preference_comparison_candidate_record_hash=candidate_hash,
        source_preference_adjudication_record_hash=adjudication_hash,
    )
    return PreferencePairRecord(
        preference_pair_id=build_preference_pair_id(
            comparison_candidate_id=candidate.comparison_candidate_id,
            source_preference_comparison_candidate_record_hash=candidate_hash,
            source_preference_adjudication_record_hash=adjudication_hash,
        ),
        source=source,
    )


def _is_preferred_adjudication(record: PreferenceAdjudicationRecord) -> bool:
    return record.review_status == "reviewed" and record.review_decision == "preferred"


def validate_preference_review_matches_comparison_export(
    comparison_export: PreferenceComparisonExport,
    review_validation: PreferenceAdjudicationReviewValidation,
) -> None:
    review_source = review_validation.source_comparison_export
    compared = (
        (
            "artifact directory",
            review_source.out_dir,
            comparison_export.out_dir,
        ),
        (
            "manifest hash",
            hash_file(review_source.out_dir / MANIFEST_FILENAME),
            hash_file(comparison_export.out_dir / MANIFEST_FILENAME),
        ),
        (
            "comparison candidate JSONL hash",
            review_source.manifest.comparison_candidates_jsonl_hash,
            comparison_export.manifest.comparison_candidates_jsonl_hash,
        ),
    )
    for field_name, observed, expected in compared:
        if observed != expected:
            raise ValueError(
                "Preference adjudication review source comparison "
                f"{field_name} mismatch: {observed!r} != {expected!r}"
            )


def write_preference_pair_records_jsonl(
    path: Path,
    records: tuple[PreferencePairRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_preference_pair_records_jsonl(
    path: Path,
) -> tuple[PreferencePairRecord, ...]:
    records: list[PreferencePairRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(PreferencePairRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PreferencePairRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_preference_pair_export_manifest(
    *,
    out_dir: Path,
    comparison_export: PreferenceComparisonExport,
    review_validation: PreferenceAdjudicationReviewValidation,
    records_path: Path,
    records: tuple[PreferencePairRecord, ...],
) -> PreferencePairExportManifest:
    expected_records_path = resolve_relative_artifact_ref(
        out_dir,
        PREFERENCE_PAIR_EXPORT_ARTIFACT_REFS["preference_pairs"],
    )
    if records_path.resolve() != expected_records_path:
        raise ValueError(
            "Preference pair JSONL path does not match manifest artifact ref"
        )
    review_artifact = review_validation.review_artifact
    comparison_manifest_path = comparison_export.out_dir / MANIFEST_FILENAME
    review_manifest_path = review_artifact.out_dir / MANIFEST_FILENAME
    adjudications_path = resolve_relative_artifact_ref(
        review_artifact.out_dir,
        PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS["adjudications"],
    )
    counts = _count_adjudication_outcomes(review_artifact.adjudications)
    shared_context_count = _count_exported_shared_contexts(
        comparison_export,
        records,
    )
    return PreferencePairExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.PREFERENCE_PAIR_EXPORT,
            "artifact_schema_version": PREFERENCE_PAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "source_preference_comparison_export": {
                "artifact_dir": str(comparison_export.out_dir),
                "manifest_hash": hash_file(comparison_manifest_path),
                "comparison_candidates_jsonl_hash": (
                    comparison_export.manifest.comparison_candidates_jsonl_hash
                ),
            },
            "source_preference_adjudication_review": {
                "artifact_dir": str(review_artifact.out_dir),
                "manifest_hash": hash_file(review_manifest_path),
                "adjudications_jsonl_hash": hash_file(adjudications_path),
            },
            "training_authorization": "not_authorized",
            "preference_pair_record_schema_version": (
                PREFERENCE_PAIR_RECORD_SCHEMA_VERSION
            ),
            "source_adjudication_record_count": len(review_artifact.adjudications),
            **counts,
            "record_count": len(records),
            "shared_context_count": shared_context_count,
            "preference_pairs_jsonl_hash": hash_file(records_path),
            "artifacts": dict(PREFERENCE_PAIR_EXPORT_ARTIFACT_REFS),
        }
    )


def validate_preference_pair_manifest_counts(
    manifest: PreferencePairExportManifest,
    *,
    comparison_export: PreferenceComparisonExport,
    review_validation: PreferenceAdjudicationReviewValidation,
    records: tuple[PreferencePairRecord, ...],
) -> None:
    adjudications = review_validation.review_artifact.adjudications
    expected_values: dict[str, int] = {
        "source_adjudication_record_count": len(adjudications),
        **_count_adjudication_outcomes(adjudications),
        "record_count": len(records),
        "shared_context_count": _count_exported_shared_contexts(
            comparison_export,
            records,
        ),
    }
    for field_name, expected in expected_values.items():
        observed = getattr(manifest, field_name)
        if observed != expected:
            raise ValueError(
                f"Preference pair manifest {field_name} mismatch: "
                f"{observed!r} != {expected!r}"
            )


def _load_pinned_comparison_export(
    owner_dir: Path,
    manifest: PreferencePairExportManifest,
) -> PreferenceComparisonExport:
    source_ref = manifest.source_preference_comparison_export
    source_dir = _resolve_pinned_artifact_dir(owner_dir, source_ref.artifact_dir)
    source_manifest_path = source_dir / MANIFEST_FILENAME
    if hash_file(source_manifest_path) != source_ref.manifest_hash:
        raise ValueError("Preference pair source comparison manifest hash mismatch")
    source = load_preference_comparison_export_artifact(source_dir)
    if (
        source.manifest.comparison_candidates_jsonl_hash
        != source_ref.comparison_candidates_jsonl_hash
    ):
        raise ValueError(
            "Preference pair source comparison candidate JSONL hash mismatch"
        )
    if hash_file(source_manifest_path) != source_ref.manifest_hash:
        raise ValueError("Preference pair source comparison changed while loading")
    return source


def _load_pinned_adjudication_review(
    owner_dir: Path,
    manifest: PreferencePairExportManifest,
) -> PreferenceAdjudicationReviewValidation:
    source_ref = manifest.source_preference_adjudication_review
    source_dir = _resolve_pinned_artifact_dir(owner_dir, source_ref.artifact_dir)
    source_manifest_path = source_dir / MANIFEST_FILENAME
    adjudications_path = resolve_relative_artifact_ref(
        source_dir,
        PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS["adjudications"],
    )
    if hash_file(source_manifest_path) != source_ref.manifest_hash:
        raise ValueError("Preference pair source adjudication manifest hash mismatch")
    if hash_file(adjudications_path) != source_ref.adjudications_jsonl_hash:
        raise ValueError("Preference pair source adjudication JSONL hash mismatch")
    validation = validate_preference_adjudication_review_artifact(source_dir)
    if (
        hash_file(source_manifest_path),
        hash_file(adjudications_path),
    ) != (source_ref.manifest_hash, source_ref.adjudications_jsonl_hash):
        raise ValueError("Preference pair source adjudication changed while loading")
    return validation


def _count_adjudication_outcomes(
    adjudications: tuple[PreferenceAdjudicationRecord, ...],
) -> dict[str, int]:
    return {
        "source_not_reviewed_count": sum(
            record.review_status == "not_reviewed" for record in adjudications
        ),
        "source_preferred_count": sum(
            record.review_decision == "preferred" for record in adjudications
        ),
        "source_tie_count": sum(
            record.review_decision == "tie" for record in adjudications
        ),
        "source_ambiguous_count": sum(
            record.review_decision == "ambiguous" for record in adjudications
        ),
        "source_invalid_count": sum(
            record.review_decision == "invalid" for record in adjudications
        ),
    }


def _count_exported_shared_contexts(
    comparison_export: PreferenceComparisonExport,
    records: tuple[PreferencePairRecord, ...],
) -> int:
    candidates = _index_comparison_candidates(comparison_export.records)
    return len(
        {
            candidates[
                record.source.comparison_candidate_id
            ].shared_context.shared_context_id
            for record in records
        }
    )


def _index_comparison_candidates(
    records: tuple[PreferenceComparisonCandidateRecord, ...],
) -> dict[str, PreferenceComparisonCandidateRecord]:
    by_id: dict[str, PreferenceComparisonCandidateRecord] = {}
    for record in records:
        candidate_id = record.comparison_candidate_id
        if candidate_id in by_id:
            raise ValueError(
                f"Duplicate preference comparison candidate id: {candidate_id}"
            )
        by_id[candidate_id] = record
    return by_id


def _index_adjudications(
    records: tuple[PreferenceAdjudicationRecord, ...],
) -> dict[str, PreferenceAdjudicationRecord]:
    by_id: dict[str, PreferenceAdjudicationRecord] = {}
    for record in records:
        candidate_id = record.source.comparison_candidate_id
        if candidate_id in by_id:
            raise ValueError(
                "Duplicate preference adjudication for comparison candidate: "
                f"{candidate_id}"
            )
        by_id[candidate_id] = record
    return by_id


def _validate_unique_preference_pair_records(
    records: tuple[PreferencePairRecord, ...],
) -> None:
    pair_ids = [record.preference_pair_id for record in records]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("Preference pair ids must be unique")
    candidate_ids = [record.source.comparison_candidate_id for record in records]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(
            "Preference pair export cannot contain duplicate comparison candidates"
        )


def _resolve_pinned_artifact_dir(owner_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = owner_dir / path
    return path.resolve()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
