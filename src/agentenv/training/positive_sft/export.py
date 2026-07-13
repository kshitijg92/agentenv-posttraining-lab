from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    POSITIVE_SFT_EXPORT_ARTIFACT_REFS,
    POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION,
    POSITIVE_SFT_REVIEW_ARTIFACT_REFS,
    PositiveSFTExportManifest,
    load_positive_sft_export_manifest,
)
from agentenv.hashing import hash_file
from agentenv.training.candidates.export import (
    load_training_candidate_export_artifact,
)
from agentenv.training.positive_sft.schema import (
    POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION,
    POSITIVE_SFT_REVIEW_RECORD_SCHEMA_VERSION,
    PositiveSFTExampleRecord,
)

if TYPE_CHECKING:
    from agentenv.training.positive_sft.review import PositiveSFTReviewValidation


@dataclass(frozen=True)
class PositiveSFTExport:
    out_dir: Path
    manifest: PositiveSFTExportManifest
    records: tuple[PositiveSFTExampleRecord, ...]


def export_positive_sft_examples(
    training_candidate_export_dir: Path,
    positive_sft_review_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> PositiveSFTExport:
    from agentenv.training.positive_sft.builder import (
        build_positive_sft_examples_from_training_candidate_export,
    )
    from agentenv.training.positive_sft.review import (
        validate_positive_sft_review_artifact,
    )
    from agentenv.training.positive_sft.source_selection import (
        validate_positive_sft_review_matches_candidate_export,
    )

    training_candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    review_validation = validate_positive_sft_review_artifact(positive_sft_review_dir)
    validate_positive_sft_review_matches_candidate_export(
        training_candidate_export,
        review_validation,
    )
    records = build_positive_sft_examples_from_training_candidate_export(
        training_candidate_export,
        positive_sft_review_validation=review_validation,
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    examples_path = out_dir / POSITIVE_SFT_EXPORT_ARTIFACT_REFS["positive_sft_examples"]
    write_positive_sft_example_records_jsonl(examples_path, records)

    manifest = build_positive_sft_export_manifest(
        out_dir=out_dir,
        review_validation=review_validation,
        examples_path=examples_path,
        records=records,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_positive_sft_export_artifact(out_dir)


def load_positive_sft_export_artifact(export_dir: Path) -> PositiveSFTExport:
    export_dir = export_dir.resolve()
    manifest = load_positive_sft_export_manifest(export_dir / MANIFEST_FILENAME)
    examples_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["positive_sft_examples"],
    )
    observed_hash = hash_file(examples_path)
    if observed_hash != manifest.positive_sft_examples_jsonl_hash:
        raise ValueError(
            f"Positive SFT examples JSONL hash mismatch at {examples_path}: "
            f"{observed_hash!r} != {manifest.positive_sft_examples_jsonl_hash!r}"
        )

    records = load_positive_sft_example_records_jsonl(examples_path)
    if len(records) != manifest.record_count:
        raise ValueError(
            f"Positive SFT example record count mismatch at {examples_path}: "
            f"{len(records)} != {manifest.record_count}"
        )
    original_count = sum(
        record.source_provenance.source_type == "original" for record in records
    )
    repaired_count = sum(
        record.source_provenance.source_type == "repaired" for record in records
    )
    if original_count != manifest.original_record_count:
        raise ValueError(
            "Positive SFT original record count mismatch: "
            f"{original_count} != {manifest.original_record_count}"
        )
    if repaired_count != manifest.repaired_record_count:
        raise ValueError(
            "Positive SFT repaired record count mismatch: "
            f"{repaired_count} != {manifest.repaired_record_count}"
        )

    review_validation = load_pinned_positive_sft_review(
        export_dir,
        manifest,
    )
    from agentenv.training.positive_sft.builder import (
        build_positive_sft_examples_from_training_candidate_export,
    )

    expected_records = build_positive_sft_examples_from_training_candidate_export(
        review_validation.source_candidate_export,
        positive_sft_review_validation=review_validation,
    )
    if records != expected_records:
        raise ValueError(
            "Persisted positive SFT records do not match records rebuilt from "
            "their pinned sources"
        )
    return PositiveSFTExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


def load_pinned_positive_sft_review(
    positive_sft_export_dir: Path,
    manifest: PositiveSFTExportManifest,
) -> PositiveSFTReviewValidation:
    source_ref = manifest.source_positive_sft_review
    source_dir = Path(source_ref.artifact_dir)
    if not source_dir.is_absolute():
        source_dir = positive_sft_export_dir / source_dir
    source_dir = source_dir.resolve()
    source_manifest_path = source_dir / MANIFEST_FILENAME
    reviews_path = resolve_relative_artifact_ref(
        source_dir,
        POSITIVE_SFT_REVIEW_ARTIFACT_REFS["reviews"],
    )
    observed_manifest_hash = hash_file(source_manifest_path)
    if observed_manifest_hash != source_ref.manifest_hash:
        raise ValueError(
            "Positive SFT source review manifest hash mismatch: "
            f"{observed_manifest_hash!r} != {source_ref.manifest_hash!r}"
        )
    observed_reviews_hash = hash_file(reviews_path)
    if observed_reviews_hash != source_ref.reviews_jsonl_hash:
        raise ValueError(
            "Positive SFT source reviews JSONL hash mismatch: "
            f"{observed_reviews_hash!r} != {source_ref.reviews_jsonl_hash!r}"
        )
    from agentenv.training.positive_sft.review import (
        validate_positive_sft_review_artifact,
    )

    validation = validate_positive_sft_review_artifact(source_dir)
    if (
        hash_file(source_manifest_path),
        hash_file(reviews_path),
    ) != (source_ref.manifest_hash, source_ref.reviews_jsonl_hash):
        raise ValueError("Positive SFT review source changed while loading")
    return validation


def write_positive_sft_example_records_jsonl(
    path: Path,
    records: tuple[PositiveSFTExampleRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_positive_sft_example_records_jsonl(
    path: Path,
) -> tuple[PositiveSFTExampleRecord, ...]:
    records: list[PositiveSFTExampleRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(PositiveSFTExampleRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PositiveSFTExampleRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_positive_sft_export_manifest(
    *,
    out_dir: Path,
    review_validation: PositiveSFTReviewValidation,
    examples_path: Path,
    records: tuple[PositiveSFTExampleRecord, ...],
) -> PositiveSFTExportManifest:
    example_ref = POSITIVE_SFT_EXPORT_ARTIFACT_REFS["positive_sft_examples"]
    if resolve_relative_artifact_ref(out_dir, example_ref) != examples_path.resolve():
        raise ValueError("Positive SFT JSONL path does not match manifest artifact ref")

    review_artifact = review_validation.review_artifact
    source_manifest_path = review_artifact.out_dir / MANIFEST_FILENAME
    source_reviews_path = resolve_relative_artifact_ref(
        review_artifact.out_dir,
        review_artifact.manifest.artifacts["reviews"],
    )
    original_record_count = sum(
        record.source_provenance.source_type == "original" for record in records
    )
    repaired_record_count = sum(
        record.source_provenance.source_type == "repaired" for record in records
    )
    return PositiveSFTExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.POSITIVE_SFT_EXPORT,
            "artifact_schema_version": POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "source_positive_sft_review": {
                "artifact_dir": str(review_artifact.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
                "reviews_jsonl_hash": hash_file(source_reviews_path),
            },
            "positive_sft_review_record_schema_version": (
                POSITIVE_SFT_REVIEW_RECORD_SCHEMA_VERSION
            ),
            "positive_sft_example_record_schema_version": (
                POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
            ),
            "record_count": len(records),
            "original_record_count": original_record_count,
            "repaired_record_count": repaired_record_count,
            "positive_sft_examples_jsonl_hash": hash_file(examples_path),
            "artifacts": dict(POSITIVE_SFT_EXPORT_ARTIFACT_REFS),
        }
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
