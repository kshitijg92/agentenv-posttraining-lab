from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.hashing import hash_file
from agentenv.training.candidates.export import TrainingCandidateExport
from agentenv.training.candidates.schema import TrainingCandidateRecord
from agentenv.training.repairs.redundancy_repair import (
    MECHANICAL_REDUNDANCY_REPAIR_METHOD,
    hash_training_candidate_record,
)
from agentenv.training.repairs.schema import (
    TrainingCandidateRepairRecord,
    TrainingCandidateRepairReviewRecord,
)
from agentenv.trajectories.schema import ArtifactRef, TrajectoryRecord

if TYPE_CHECKING:
    from agentenv.training.positive_sft.review import PositiveSFTReviewValidation
    from agentenv.training.repairs.review import (
        TrainingCandidateRepairReviewValidation,
    )


@dataclass(frozen=True)
class SelectedPositiveSFTRepair:
    repair_export_dir: Path
    record: TrainingCandidateRepairRecord
    review: TrainingCandidateRepairReviewRecord


def load_positive_sft_repair_sources(
    training_candidate_export: TrainingCandidateExport,
    *,
    repair_export_dir: Path | None,
    repair_review_dir: Path | None,
    selected_repair_ids: Sequence[str],
) -> TrainingCandidateRepairReviewValidation | None:
    selected_ids = tuple(selected_repair_ids)
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Positive SFT repair selections contain duplicate repair_id")
    if not selected_ids:
        if repair_export_dir is not None or repair_review_dir is not None:
            raise ValueError(
                "Positive SFT repair sources require at least one selected repair_id"
            )
        return None
    if repair_export_dir is None or repair_review_dir is None:
        raise ValueError(
            "Selected positive SFT repairs require repair export and review artifacts"
        )

    from agentenv.training.repairs.review import (
        validate_training_candidate_repair_review_artifact,
    )

    validation = validate_training_candidate_repair_review_artifact(
        repair_export_dir,
        repair_review_dir,
    )
    validate_positive_sft_repair_source_matches_candidate_export(
        training_candidate_export,
        validation,
    )
    return validation


def validate_positive_sft_repair_source_matches_candidate_export(
    training_candidate_export: TrainingCandidateExport,
    repair_validation: TrainingCandidateRepairReviewValidation,
) -> None:
    repair_export = repair_validation.source_export
    source_ref = repair_export.manifest.source_training_candidate_export
    source_dir = Path(source_ref.artifact_dir)
    if not source_dir.is_absolute():
        source_dir = repair_export.out_dir / source_dir
    if source_dir.resolve() != training_candidate_export.out_dir.resolve():
        raise ValueError(
            "Positive SFT repair export references a different training candidate "
            "export"
        )
    candidate_manifest_hash = hash_file(
        training_candidate_export.out_dir / MANIFEST_FILENAME
    )
    if source_ref.manifest_hash != candidate_manifest_hash:
        raise ValueError(
            "Positive SFT repair export source training candidate manifest hash "
            "mismatch"
        )


def validate_positive_sft_review_matches_candidate_export(
    training_candidate_export: TrainingCandidateExport,
    review_validation: PositiveSFTReviewValidation,
) -> None:
    source_export = review_validation.source_candidate_export
    if source_export.out_dir.resolve() != training_candidate_export.out_dir.resolve():
        raise ValueError(
            "Positive-SFT review references a different training candidate export"
        )
    expected_manifest_hash = hash_file(
        training_candidate_export.out_dir / MANIFEST_FILENAME
    )
    review_source_ref = (
        review_validation.review_artifact.manifest.source_training_candidate_export
    )
    if review_source_ref.manifest_hash != expected_manifest_hash:
        raise ValueError(
            "Positive-SFT review source training candidate manifest hash mismatch"
        )


def build_selected_positive_sft_repair_index(
    training_candidate_export: TrainingCandidateExport,
    *,
    repair_validation: TrainingCandidateRepairReviewValidation | None,
    selected_repair_ids: Sequence[str],
) -> dict[str, SelectedPositiveSFTRepair]:
    selected_ids = tuple(selected_repair_ids)
    if not selected_ids:
        if repair_validation is not None:
            raise ValueError(
                "Positive SFT repair validation is unused without selected repair ids"
            )
        return {}
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Positive SFT repair selections contain duplicate repair_id")
    if repair_validation is None:
        raise ValueError("Positive SFT repair selections require validated artifacts")

    repairs_by_id = {
        record.repair_id: record for record in repair_validation.source_export.records
    }
    reviews_by_id = {
        review.repair_id: review for review in repair_validation.review_artifact.reviews
    }
    candidates_by_hash = {
        hash_training_candidate_record(candidate): candidate
        for candidate in training_candidate_export.records
    }
    selected_by_candidate_hash: dict[str, SelectedPositiveSFTRepair] = {}
    for repair_id in selected_ids:
        repair = repairs_by_id.get(repair_id)
        if repair is None:
            raise ValueError(f"Positive SFT selected unknown repair_id: {repair_id}")
        review = reviews_by_id[repair_id]
        if repair.repair_status != "completed":
            raise ValueError(
                "Positive SFT selected repair is not completed: "
                f"{repair_id} ({repair.repair_status})"
            )
        if review.review_status != "reviewed" or review.review_decision != "accepted":
            raise ValueError(
                "Positive SFT selected repair does not have an accepted review: "
                f"{repair_id}"
            )
        if repair.repair.repair_method != MECHANICAL_REDUNDANCY_REPAIR_METHOD:
            raise ValueError(
                "Positive SFT cannot inherit task outcome for unsupported repair "
                f"method: {repair.repair.repair_method}"
            )

        candidate_hash = repair.source_training_candidate_record_hash
        candidate = candidates_by_hash.get(candidate_hash)
        if candidate is None:
            raise ValueError(
                "Positive SFT selected repair references an unknown training "
                f"candidate: {repair_id}"
            )
        if not candidate.training_eligibility.positive_sft_review_eligible:
            raise ValueError(
                "Positive SFT selected repair belongs to an ineligible candidate: "
                f"{repair_id}"
            )
        assessment = candidate.mechanical_redundancy_assessment
        if assessment.evaluation_status != "complete" or not assessment.blocks:
            raise ValueError(
                "Positive SFT selected repair requires a complete source assessment "
                f"with redundancy blocks: {repair_id}"
            )
        if candidate_hash in selected_by_candidate_hash:
            raise ValueError(
                "Positive SFT selected multiple repairs for one training candidate: "
                f"{candidate.trajectory_id} / {candidate.eval_attempt_id}"
            )
        selected_by_candidate_hash[candidate_hash] = SelectedPositiveSFTRepair(
            repair_export_dir=repair_validation.source_export.out_dir,
            record=repair,
            review=review,
        )
    return selected_by_candidate_hash


def load_selected_repaired_messages(
    selected_repair: SelectedPositiveSFTRepair,
) -> list:
    from agentenv.training.repairs.export import load_repaired_transcript_artifact

    repaired_ref = selected_repair.record.repaired_artifact_ref
    if repaired_ref is None:
        raise ValueError("Positive SFT selected repair is missing repaired artifact")
    expected_hash = require_content_hash(
        repaired_ref,
        field_name="repaired transcript",
    )
    repaired_path = resolve_relative_artifact_ref(
        selected_repair.repair_export_dir,
        repaired_ref.path,
    )
    observed_hash = hash_file(repaired_path)
    if observed_hash != expected_hash:
        raise ValueError(
            "Positive SFT repaired transcript hash mismatch: "
            f"{observed_hash!r} != {expected_hash!r}"
        )
    transcript = load_repaired_transcript_artifact(repaired_path)
    if hash_file(repaired_path) != expected_hash:
        raise ValueError("Positive SFT repaired transcript changed while loading")
    return transcript.root


def require_content_hash(artifact_ref: ArtifactRef, *, field_name: str) -> str:
    if artifact_ref.content_hash is None:
        raise ValueError(f"{field_name} must be content-hash pinned")
    return artifact_ref.content_hash


def validate_positive_sft_candidate_matches_trajectory(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
) -> None:
    compared_fields = (
        ("trajectory_id", candidate.trajectory_id, trajectory.identity.trajectory_id),
        (
            "eval_attempt_id",
            candidate.eval_attempt_id,
            trajectory.identity.eval_attempt_id,
        ),
        ("task_id", candidate.task_id, trajectory.identity.task_id),
        ("policy_id", candidate.policy_id, trajectory.identity.policy_id),
    )
    for field_name, candidate_value, trajectory_value in compared_fields:
        if candidate_value != trajectory_value:
            raise ValueError(
                f"Training candidate {field_name} does not match trajectory: "
                f"{candidate_value!r} != {trajectory_value!r}"
            )


def require_artifact_ref(
    artifact_ref: ArtifactRef | None,
    field_name: str,
    trajectory: TrajectoryRecord,
) -> ArtifactRef:
    if artifact_ref is None:
        raise ValueError(
            f"Positive SFT trajectory missing {field_name}: "
            f"{trajectory.identity.trajectory_id}"
        )
    return artifact_ref
