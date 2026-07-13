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
    TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS,
    TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION,
    TRAJECTORY_EXPORT_ARTIFACT_REFS,
    TRAJECTORY_REVIEW_ARTIFACT_REFS,
    TrainingCandidateExportManifest,
    load_training_candidate_export_manifest,
)
from agentenv.training.candidates.builder import (
    build_training_candidate_records_from_review_validation,
)
from agentenv.training.candidates.gates import (
    TrainingExportGateValidation,
    validate_training_export_gates,
)
from agentenv.training.candidates.schema import (
    TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION,
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
class TrainingCandidateRecordCounts:
    analysis_eligible_count: int
    positive_sft_review_eligible_count: int
    negative_example_eligible_count: int
    preference_pairing_eligible_count: int
    any_training_use_eligible_count: int
    analysis_only_count: int
    fully_ineligible_count: int

    def as_manifest_fields(self) -> dict[str, int]:
        return {
            "analysis_eligible_count": self.analysis_eligible_count,
            "positive_sft_review_eligible_count": (
                self.positive_sft_review_eligible_count
            ),
            "negative_example_eligible_count": self.negative_example_eligible_count,
            "preference_pairing_eligible_count": (
                self.preference_pairing_eligible_count
            ),
            "any_training_use_eligible_count": (
                self.any_training_use_eligible_count
            ),
            "analysis_only_count": self.analysis_only_count,
            "fully_ineligible_count": self.fully_ineligible_count,
        }


def export_training_candidate_records(
    trajectory_export_dir: Path,
    review_dir: Path,
    out_dir: Path,
    *,
    harness_audit_dir: Path,
    control_calibration_dir: Path,
    overwrite: bool = False,
) -> TrainingCandidateExport:
    validation = validate_trajectory_review_artifact(
        trajectory_export_dir,
        review_dir,
    )
    gate_validation = validate_training_export_gates(
        validation,
        harness_audit_dir=harness_audit_dir,
        control_calibration_dir=control_calibration_dir,
    )
    records = build_training_candidate_records_from_review_validation(
        validation,
        gate_validation=gate_validation,
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    candidates_path = (
        out_dir / TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS["training_candidates"]
    )
    write_training_candidate_records_jsonl(candidates_path, records)

    manifest = build_training_candidate_export_manifest(
        out_dir=out_dir,
        trajectory_export_dir=validation.source_export.out_dir,
        review_dir=validation.review_artifact.out_dir,
        gate_validation=gate_validation,
        candidates_path=candidates_path,
        records=records,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_training_candidate_export_artifact(out_dir)


def load_training_candidate_export_artifact(
    export_dir: Path,
) -> TrainingCandidateExport:
    export_dir = export_dir.resolve()
    manifest = load_training_candidate_export_manifest(export_dir / MANIFEST_FILENAME)
    source_validation = validate_trajectory_review_artifact(
        Path(manifest.source_trajectory_export_dir),
        Path(manifest.source_review_dir),
    )
    observed_gates = validate_training_export_gates(
        source_validation,
        harness_audit_dir=Path(manifest.harness_audit_gate.artifact_dir),
        control_calibration_dir=Path(manifest.control_calibration_gate.artifact_dir),
    )
    if observed_gates.harness_audit_gate != manifest.harness_audit_gate:
        raise ValueError("Training candidate harness-audit gate provenance drifted")
    if observed_gates.control_calibration_gate != manifest.control_calibration_gate:
        raise ValueError(
            "Training candidate control-calibration gate provenance drifted"
        )
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
    expected_records = build_training_candidate_records_from_review_validation(
        source_validation,
        gate_validation=observed_gates,
    )
    if records != expected_records:
        raise ValueError(
            "Persisted training candidate records do not match eligibility "
            "recomputed from their pinned trajectories and reviews"
        )
    validate_training_candidate_counts_match_manifest(manifest, records)
    return TrainingCandidateExport(
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


def build_training_candidate_export_manifest(
    *,
    out_dir: Path,
    trajectory_export_dir: Path,
    review_dir: Path,
    gate_validation: TrainingExportGateValidation,
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
            "harness_audit_gate": gate_validation.harness_audit_gate,
            "control_calibration_gate": gate_validation.control_calibration_gate,
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
        analysis_eligible_count=sum(
            record.training_eligibility.analysis_eligible for record in records
        ),
        positive_sft_review_eligible_count=sum(
            record.training_eligibility.positive_sft_review_eligible
            for record in records
        ),
        negative_example_eligible_count=sum(
            record.training_eligibility.negative_example_eligible
            for record in records
        ),
        preference_pairing_eligible_count=sum(
            record.training_eligibility.preference_pairing_eligible
            for record in records
        ),
        any_training_use_eligible_count=sum(
            record.training_eligibility.has_training_use_path for record in records
        ),
        analysis_only_count=sum(
            record.training_eligibility.is_analysis_only for record in records
        ),
        fully_ineligible_count=sum(
            record.training_eligibility.is_fully_ineligible for record in records
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
