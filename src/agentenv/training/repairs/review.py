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
    TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS,
    TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_SCHEMA_VERSION,
    TrainingCandidateRepairReviewManifest,
    load_training_candidate_repair_review_manifest,
)
from agentenv.hashing import hash_file
from agentenv.training.repairs.redundancy_repair import (
    hash_training_candidate_repair_record,
)
from agentenv.training.repairs.export import (
    TrainingCandidateRepairExport,
    load_training_candidate_repair_export_artifact,
)
from agentenv.training.repairs.schema import (
    TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION,
    TrainingCandidateRepairRecord,
    TrainingCandidateRepairReviewRecord,
)


@dataclass(frozen=True)
class TrainingCandidateRepairReviewArtifact:
    out_dir: Path
    manifest: TrainingCandidateRepairReviewManifest
    reviews: tuple[TrainingCandidateRepairReviewRecord, ...]


@dataclass(frozen=True)
class TrainingCandidateRepairReviewValidation:
    source_export: TrainingCandidateRepairExport
    review_artifact: TrainingCandidateRepairReviewArtifact
    record_count: int
    review_status_counts: dict[str, int]
    review_decision_counts: dict[str, int]


def initialize_training_candidate_repair_review_artifact(
    repair_export_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> TrainingCandidateRepairReviewArtifact:
    source_export = load_training_candidate_repair_export_artifact(repair_export_dir)
    reviews = build_initial_repair_review_records(source_export.records)

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    reviews_path = resolve_relative_artifact_ref(
        out_dir,
        TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS["reviews"],
    )
    review_queue_path = resolve_relative_artifact_ref(
        out_dir,
        TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS["review_queue"],
    )
    write_training_candidate_repair_review_records_jsonl(reviews_path, reviews)
    review_queue_path.write_text(
        render_training_candidate_repair_review_queue(source_export, reviews)
    )

    manifest = build_training_candidate_repair_review_manifest(
        out_dir=out_dir,
        source_export=source_export,
        review_record_count=len(reviews),
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_training_candidate_repair_review_artifact(out_dir)


def validate_training_candidate_repair_review_artifact(
    repair_export_dir: Path,
    review_dir: Path,
) -> TrainingCandidateRepairReviewValidation:
    source_export = load_training_candidate_repair_export_artifact(repair_export_dir)
    review_artifact = load_training_candidate_repair_review_artifact(review_dir)
    validate_repair_review_manifest_matches_source(
        review_artifact.manifest,
        source_export,
    )
    validate_repair_review_records_match_repairs(
        review_artifact.reviews,
        source_export.records,
    )
    return TrainingCandidateRepairReviewValidation(
        source_export=source_export,
        review_artifact=review_artifact,
        record_count=len(review_artifact.reviews),
        review_status_counts=count_repair_review_statuses(review_artifact.reviews),
        review_decision_counts=count_repair_review_decisions(review_artifact.reviews),
    )


def load_training_candidate_repair_review_artifact(
    review_dir: Path,
) -> TrainingCandidateRepairReviewArtifact:
    review_dir = review_dir.resolve()
    manifest = load_training_candidate_repair_review_manifest(
        review_dir / MANIFEST_FILENAME
    )
    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["reviews"],
    )
    review_queue_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["review_queue"],
    )
    if not review_queue_path.is_file():
        raise ValueError(
            f"Missing training candidate repair review queue at {review_queue_path}"
        )
    reviews = load_training_candidate_repair_review_records_jsonl(reviews_path)
    if len(reviews) != manifest.record_count:
        raise ValueError(
            "Training candidate repair review record count mismatch at "
            f"{reviews_path}: {len(reviews)} != {manifest.record_count}"
        )
    return TrainingCandidateRepairReviewArtifact(
        out_dir=review_dir,
        manifest=manifest,
        reviews=reviews,
    )


def validate_repair_review_manifest_matches_source(
    manifest: TrainingCandidateRepairReviewManifest,
    source_export: TrainingCandidateRepairExport,
) -> None:
    source_manifest_path = source_export.out_dir / MANIFEST_FILENAME
    compared_fields = (
        (
            "source artifact directory",
            manifest.source_training_candidate_repair_export.artifact_dir,
            str(source_export.out_dir),
        ),
        (
            "source manifest hash",
            manifest.source_training_candidate_repair_export.manifest_hash,
            hash_file(source_manifest_path),
        ),
        ("record_count", manifest.record_count, len(source_export.records)),
    )
    for field_name, observed, expected in compared_fields:
        if observed != expected:
            raise ValueError(
                f"Training candidate repair review manifest {field_name} mismatch: "
                f"{observed!r} != {expected!r}"
            )


def validate_repair_review_records_match_repairs(
    reviews: tuple[TrainingCandidateRepairReviewRecord, ...],
    repairs: tuple[TrainingCandidateRepairRecord, ...],
) -> None:
    repairs_by_id = _index_repairs(repairs)
    reviews_by_id = _index_repair_reviews(reviews)

    missing_repair_ids = sorted(set(repairs_by_id) - set(reviews_by_id))
    if missing_repair_ids:
        raise ValueError(
            "Training candidate repair review is missing repair_id: "
            + ", ".join(missing_repair_ids)
        )
    unknown_repair_ids = sorted(set(reviews_by_id) - set(repairs_by_id))
    if unknown_repair_ids:
        raise ValueError(
            "Training candidate repair review contains unknown repair_id: "
            + ", ".join(unknown_repair_ids)
        )
    for repair_id, repair in repairs_by_id.items():
        review = reviews_by_id[repair_id]
        observed_hash = hash_training_candidate_repair_record(repair)
        if review.source_training_candidate_repair_record_hash != observed_hash:
            raise ValueError(
                "Training candidate repair review source repair record hash "
                f"mismatch for repair_id {repair_id!r}"
            )


def build_initial_repair_review_records(
    records: tuple[TrainingCandidateRepairRecord, ...],
) -> tuple[TrainingCandidateRepairReviewRecord, ...]:
    return tuple(
        TrainingCandidateRepairReviewRecord(
            repair_id=record.repair_id,
            source_training_candidate_repair_record_hash=(
                hash_training_candidate_repair_record(record)
            ),
            review_status="not_reviewed",
        )
        for record in records
    )


def write_training_candidate_repair_review_records_jsonl(
    path: Path,
    records: tuple[TrainingCandidateRepairReviewRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_training_candidate_repair_review_records_jsonl(
    path: Path,
) -> tuple[TrainingCandidateRepairReviewRecord, ...]:
    records: list[TrainingCandidateRepairReviewRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(TrainingCandidateRepairReviewRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"TrainingCandidateRepairReviewRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_training_candidate_repair_review_manifest(
    *,
    out_dir: Path,
    source_export: TrainingCandidateRepairExport,
    review_record_count: int,
) -> TrainingCandidateRepairReviewManifest:
    for artifact_ref in TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS.values():
        resolve_relative_artifact_ref(out_dir, artifact_ref)
    source_manifest_path = source_export.out_dir / MANIFEST_FILENAME
    return TrainingCandidateRepairReviewManifest.model_validate(
        {
            "artifact_type": ArtifactType.TRAINING_CANDIDATE_REPAIR_REVIEW,
            "artifact_schema_version": (
                TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "source_training_candidate_repair_export": {
                "artifact_dir": str(source_export.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
            },
            "training_candidate_repair_review_record_schema_version": (
                TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION
            ),
            "record_count": review_record_count,
            "artifacts": dict(TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS),
        }
    )


def render_training_candidate_repair_review_queue(
    source_export: TrainingCandidateRepairExport,
    reviews: tuple[TrainingCandidateRepairReviewRecord, ...],
) -> str:
    reviews_by_id = _index_repair_reviews(reviews)
    lines = [
        "# Training Candidate Repair Review Queue",
        "",
        f"Source repair export: `{source_export.out_dir}`",
        f"Repair record count: `{len(source_export.records)}`",
        "",
        "Edit `reviews.jsonl` to record human decisions. Keep one row per repair.",
        "",
        (
            "For non-completed repairs, `accepted` means the failure outcome is "
            "accurately represented; it never authorizes training use."
        ),
        "",
    ]
    for index, repair in enumerate(source_export.records, start=1):
        review = reviews_by_id[repair.repair_id]
        lines.extend(
            [
                f"## {index}. `{repair.repair_id}`",
                "",
                f"- repair_status: `{repair.repair_status}`",
                f"- trajectory_id: `{repair.trajectory_id}`",
                f"- eval_attempt_id: `{repair.eval_attempt_id}`",
                f"- repair_method: `{repair.repair.repair_method}`",
                (
                    "- repaired_artifact_ref: `"
                    + (
                        json.dumps(
                            repair.repaired_artifact_ref.model_dump(mode="json"),
                            sort_keys=True,
                        )
                        if repair.repaired_artifact_ref is not None
                        else "null"
                    )
                    + "`"
                ),
                (
                    "- cannot_complete_reason: `"
                    + json.dumps(repair.repair.cannot_complete_reason)
                    + "`"
                ),
                f"- error_class: `{json.dumps(repair.error_class)}`",
                "",
                "Review row:",
                "",
                "```json",
                json.dumps(review.model_dump(mode="json"), sort_keys=True),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def count_repair_review_statuses(
    reviews: tuple[TrainingCandidateRepairReviewRecord, ...],
) -> dict[str, int]:
    counts = {"not_reviewed": 0, "reviewed": 0}
    for review in reviews:
        counts[review.review_status] += 1
    return counts


def count_repair_review_decisions(
    reviews: tuple[TrainingCandidateRepairReviewRecord, ...],
) -> dict[str, int]:
    counts = {"accepted": 0, "rejected": 0, "needs_followup": 0}
    for review in reviews:
        if review.review_decision is not None:
            counts[review.review_decision] += 1
    return counts


def _index_repairs(
    records: tuple[TrainingCandidateRepairRecord, ...],
) -> dict[str, TrainingCandidateRepairRecord]:
    indexed: dict[str, TrainingCandidateRepairRecord] = {}
    for record in records:
        if record.repair_id in indexed:
            raise ValueError(
                "Training candidate repair export contains duplicate repair_id: "
                f"{record.repair_id}"
            )
        indexed[record.repair_id] = record
    return indexed


def _index_repair_reviews(
    reviews: tuple[TrainingCandidateRepairReviewRecord, ...],
) -> dict[str, TrainingCandidateRepairReviewRecord]:
    indexed: dict[str, TrainingCandidateRepairReviewRecord] = {}
    for review in reviews:
        if review.repair_id in indexed:
            raise ValueError(
                "Training candidate repair review contains duplicate repair_id: "
                f"{review.repair_id}"
            )
        indexed[review.repair_id] = review
    return indexed


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
