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
    POSITIVE_SFT_EXPORT_ARTIFACT_REFS,
    POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION,
    TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS,
    TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION,
    TRAJECTORY_EXPORT_ARTIFACT_REFS,
    TRAJECTORY_REVIEW_ARTIFACT_REFS,
    PositiveSFTExportManifest,
    TrainingCandidateExportManifest,
    load_positive_sft_export_manifest,
    load_training_candidate_export_manifest,
)
from agentenv.training.builder import (
    build_training_candidate_records_from_review_validation,
)
from agentenv.training.schema import (
    POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION,
    TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION,
    PositiveSFTExampleRecord,
    TrainingCandidateRecord,
)
from agentenv.trajectories.export import hash_file
from agentenv.trajectories.review import validate_trajectory_review_artifact
from agentenv.trajectories.schema import (
    TRAJECTORY_RECORD_SCHEMA_VERSION,
    TRAJECTORY_REVIEW_SCHEMA_VERSION,
)


@dataclass(frozen=True)
class TrainingCandidateExport:
    out_dir: Path
    manifest: TrainingCandidateExportManifest
    records: tuple[TrainingCandidateRecord, ...]


@dataclass(frozen=True)
class PositiveSFTExport:
    out_dir: Path
    manifest: PositiveSFTExportManifest
    records: tuple[PositiveSFTExampleRecord, ...]


@dataclass(frozen=True)
class TrainingCandidateRecordCounts:
    analysis_allowed_count: int
    positive_sft_allowed_count: int
    negative_example_allowed_count: int
    preference_data_allowed_count: int
    trainable_count: int
    analysis_only_count: int
    not_trainable_count: int

    def as_manifest_fields(self) -> dict[str, int]:
        return {
            "analysis_allowed_count": self.analysis_allowed_count,
            "positive_sft_allowed_count": self.positive_sft_allowed_count,
            "negative_example_allowed_count": self.negative_example_allowed_count,
            "preference_data_allowed_count": self.preference_data_allowed_count,
            "trainable_count": self.trainable_count,
            "analysis_only_count": self.analysis_only_count,
            "not_trainable_count": self.not_trainable_count,
        }


def export_training_candidate_records(
    trajectory_export_dir: Path,
    review_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> TrainingCandidateExport:
    validation = validate_trajectory_review_artifact(
        trajectory_export_dir,
        review_dir,
    )
    records = build_training_candidate_records_from_review_validation(validation)

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    candidates_path = (
        out_dir / TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS["training_candidates"]
    )
    write_training_candidate_records_jsonl(candidates_path, records)

    manifest = build_training_candidate_export_manifest(
        out_dir=out_dir,
        trajectory_export_dir=validation.source_export.out_dir,
        review_dir=validation.review_artifact.out_dir,
        candidates_path=candidates_path,
        records=records,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_training_candidate_export_artifact(out_dir)


def export_positive_sft_examples(
    training_candidate_export_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> PositiveSFTExport:
    from agentenv.training.sft_builder import (
        build_positive_sft_examples_from_training_candidate_export,
    )

    training_candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    records = build_positive_sft_examples_from_training_candidate_export(
        training_candidate_export
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    examples_path = out_dir / POSITIVE_SFT_EXPORT_ARTIFACT_REFS["positive_sft_examples"]
    write_positive_sft_example_records_jsonl(examples_path, records)

    manifest = build_positive_sft_export_manifest(
        out_dir=out_dir,
        training_candidate_export=training_candidate_export,
        examples_path=examples_path,
        records=records,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_positive_sft_export_artifact(out_dir)


def load_training_candidate_export_artifact(
    export_dir: Path,
) -> TrainingCandidateExport:
    export_dir = export_dir.resolve()
    manifest = load_training_candidate_export_manifest(export_dir / MANIFEST_FILENAME)
    candidates_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["training_candidates"],
    )
    observed_hash = hash_file(candidates_path)
    if observed_hash != manifest.training_candidates_jsonl_hash:
        raise ValueError(
            f"Training candidate JSONL hash mismatch at {candidates_path}: "
            f"{observed_hash!r} != {manifest.training_candidates_jsonl_hash!r}"
        )

    records = load_training_candidate_records_jsonl(candidates_path)
    if len(records) != manifest.record_count:
        raise ValueError(
            f"Training candidate record count mismatch at {candidates_path}: "
            f"{len(records)} != {manifest.record_count}"
        )
    validate_training_candidate_counts_match_manifest(manifest, records)
    return TrainingCandidateExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


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
    return PositiveSFTExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


def write_training_candidate_records_jsonl(
    path: Path,
    records: tuple[TrainingCandidateRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_training_candidate_records_jsonl(
    path: Path,
) -> tuple[TrainingCandidateRecord, ...]:
    records: list[TrainingCandidateRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(TrainingCandidateRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"TrainingCandidateRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


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


def build_training_candidate_export_manifest(
    *,
    out_dir: Path,
    trajectory_export_dir: Path,
    review_dir: Path,
    candidates_path: Path,
    records: tuple[TrainingCandidateRecord, ...],
) -> TrainingCandidateExportManifest:
    candidate_ref = TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS["training_candidates"]
    if (
        resolve_relative_artifact_ref(out_dir, candidate_ref)
        != candidates_path.resolve()
    ):
        raise ValueError(
            "Training candidate JSONL path does not match manifest artifact ref"
        )

    trajectory_manifest_path = trajectory_export_dir / MANIFEST_FILENAME
    review_manifest_path = review_dir / MANIFEST_FILENAME
    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        TRAJECTORY_REVIEW_ARTIFACT_REFS["reviews"],
    )
    counts = count_training_candidate_records(records)
    return TrainingCandidateExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.TRAINING_CANDIDATE_EXPORT,
            "artifact_schema_version": (
                TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "source_trajectory_export_dir": str(trajectory_export_dir),
            "source_trajectory_export_manifest_hash": hash_file(
                trajectory_manifest_path
            ),
            "source_trajectories_jsonl_hash": hash_source_trajectories_jsonl(
                trajectory_export_dir
            ),
            "source_review_dir": str(review_dir),
            "source_review_manifest_hash": hash_file(review_manifest_path),
            "source_reviews_jsonl_hash": hash_file(reviews_path),
            "trajectory_record_schema_version": TRAJECTORY_RECORD_SCHEMA_VERSION,
            "trajectory_review_schema_version": TRAJECTORY_REVIEW_SCHEMA_VERSION,
            "training_candidate_record_schema_version": (
                TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
            ),
            "record_count": len(records),
            "training_candidates_jsonl_hash": hash_file(candidates_path),
            **counts.as_manifest_fields(),
            "artifacts": dict(TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS),
        }
    )


def build_positive_sft_export_manifest(
    *,
    out_dir: Path,
    training_candidate_export: TrainingCandidateExport,
    examples_path: Path,
    records: tuple[PositiveSFTExampleRecord, ...],
) -> PositiveSFTExportManifest:
    example_ref = POSITIVE_SFT_EXPORT_ARTIFACT_REFS["positive_sft_examples"]
    if resolve_relative_artifact_ref(out_dir, example_ref) != examples_path.resolve():
        raise ValueError("Positive SFT JSONL path does not match manifest artifact ref")

    source_dir = training_candidate_export.out_dir
    source_manifest_path = source_dir / MANIFEST_FILENAME
    return PositiveSFTExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.POSITIVE_SFT_EXPORT,
            "artifact_schema_version": POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "source_training_candidate_export_dir": str(source_dir),
            "source_training_candidate_export_artifact_schema_version": (
                training_candidate_export.manifest.artifact_schema_version
            ),
            "source_training_candidate_export_manifest_hash": hash_file(
                source_manifest_path
            ),
            "source_training_candidates_jsonl_hash": hash_source_training_candidates_jsonl(
                training_candidate_export
            ),
            "training_candidate_record_schema_version": (
                training_candidate_export.manifest.training_candidate_record_schema_version
            ),
            "positive_sft_example_record_schema_version": (
                POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
            ),
            "record_count": len(records),
            "positive_sft_examples_jsonl_hash": hash_file(examples_path),
            "artifacts": dict(POSITIVE_SFT_EXPORT_ARTIFACT_REFS),
        }
    )


def hash_source_trajectories_jsonl(trajectory_export_dir: Path) -> str:
    trajectories_path = resolve_relative_artifact_ref(
        trajectory_export_dir,
        TRAJECTORY_EXPORT_ARTIFACT_REFS["trajectories"],
    )
    return hash_file(trajectories_path)


def hash_source_training_candidates_jsonl(
    training_candidate_export: TrainingCandidateExport,
) -> str:
    candidates_path = resolve_relative_artifact_ref(
        training_candidate_export.out_dir,
        training_candidate_export.manifest.artifacts["training_candidates"],
    )
    return hash_file(candidates_path)


def count_training_candidate_records(
    records: tuple[TrainingCandidateRecord, ...],
) -> TrainingCandidateRecordCounts:
    return TrainingCandidateRecordCounts(
        analysis_allowed_count=sum(
            record.final_eligibility.analysis_allowed for record in records
        ),
        positive_sft_allowed_count=sum(
            record.final_eligibility.positive_sft_allowed for record in records
        ),
        negative_example_allowed_count=sum(
            record.final_eligibility.negative_example_allowed for record in records
        ),
        preference_data_allowed_count=sum(
            record.final_eligibility.preference_data_allowed for record in records
        ),
        trainable_count=sum(
            record.final_eligibility.is_trainable for record in records
        ),
        analysis_only_count=sum(
            record.final_eligibility.is_analysis_only for record in records
        ),
        not_trainable_count=sum(
            record.final_eligibility.is_not_trainable for record in records
        ),
    )


def validate_training_candidate_counts_match_manifest(
    manifest: TrainingCandidateExportManifest,
    records: tuple[TrainingCandidateRecord, ...],
) -> None:
    expected_counts = count_training_candidate_records(records).as_manifest_fields()
    for field_name, expected_count in expected_counts.items():
        observed_count = getattr(manifest, field_name)
        if observed_count != expected_count:
            raise ValueError(
                f"Training candidate manifest {field_name} mismatch: "
                f"{observed_count!r} != {expected_count!r}"
            )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
