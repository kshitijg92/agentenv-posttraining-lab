from pathlib import Path

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import TRAJECTORY_REVIEW_ARTIFACT_REFS
from agentenv.hashing import hash_file
from agentenv.training.candidates.export import (
    TrainingCandidateExport,
    hash_source_trajectories_jsonl,
)
from agentenv.trajectories.export import (
    TrajectoryExport,
    load_trajectory_export_artifact,
)
from agentenv.trajectories.schema import ArtifactRef, TrajectoryRecord


def load_pinned_candidate_trajectory_export(
    training_candidate_export: TrainingCandidateExport,
) -> TrajectoryExport:
    trajectory_export_dir = resolve_source_trajectory_export_dir(
        training_candidate_export
    )
    observed_manifest_hash = hash_file(trajectory_export_dir / MANIFEST_FILENAME)
    expected_manifest_hash = (
        training_candidate_export.manifest.source_trajectory_export_manifest_hash
    )
    if observed_manifest_hash != expected_manifest_hash:
        raise ValueError(
            "Source trajectory export manifest hash mismatch: "
            f"{observed_manifest_hash!r} != {expected_manifest_hash!r}"
        )

    observed_jsonl_hash = hash_source_trajectories_jsonl(trajectory_export_dir)
    expected_jsonl_hash = (
        training_candidate_export.manifest.source_trajectories_jsonl_hash
    )
    if observed_jsonl_hash != expected_jsonl_hash:
        raise ValueError(
            "Source trajectory JSONL hash mismatch: "
            f"{observed_jsonl_hash!r} != {expected_jsonl_hash!r}"
        )

    return load_trajectory_export_artifact(trajectory_export_dir)


def validate_pinned_candidate_source_review(
    training_candidate_export: TrainingCandidateExport,
) -> None:
    review_dir = resolve_source_review_dir(training_candidate_export)
    observed_manifest_hash = hash_file(review_dir / MANIFEST_FILENAME)
    expected_manifest_hash = (
        training_candidate_export.manifest.source_review_manifest_hash
    )
    if observed_manifest_hash != expected_manifest_hash:
        raise ValueError(
            "Source review manifest hash mismatch: "
            f"{observed_manifest_hash!r} != {expected_manifest_hash!r}"
        )

    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        TRAJECTORY_REVIEW_ARTIFACT_REFS["reviews"],
    )
    observed_reviews_hash = hash_file(reviews_path)
    expected_reviews_hash = training_candidate_export.manifest.source_reviews_jsonl_hash
    if observed_reviews_hash != expected_reviews_hash:
        raise ValueError(
            "Source reviews JSONL hash mismatch: "
            f"{observed_reviews_hash!r} != {expected_reviews_hash!r}"
        )


def resolve_source_trajectory_export_dir(
    training_candidate_export: TrainingCandidateExport,
) -> Path:
    source_dir = Path(training_candidate_export.manifest.source_trajectory_export_dir)
    if not source_dir.is_absolute():
        source_dir = training_candidate_export.out_dir / source_dir
    return source_dir.resolve()


def resolve_source_review_dir(
    training_candidate_export: TrainingCandidateExport,
) -> Path:
    source_dir = Path(training_candidate_export.manifest.source_review_dir)
    if not source_dir.is_absolute():
        source_dir = training_candidate_export.out_dir / source_dir
    return source_dir.resolve()


def build_trajectory_record_index(
    records: tuple[TrajectoryRecord, ...],
) -> dict[str, TrajectoryRecord]:
    record_by_id: dict[str, TrajectoryRecord] = {}
    for record in records:
        trajectory_id = record.identity.trajectory_id
        if trajectory_id in record_by_id:
            raise ValueError(
                f"Duplicate trajectory_id in trajectory export: {trajectory_id}"
            )
        record_by_id[trajectory_id] = record
    return record_by_id


def resolve_trajectory_artifact_path(
    trajectory: TrajectoryRecord,
    artifact_ref: ArtifactRef,
) -> Path:
    eval_run_dir = Path(trajectory.artifacts.eval_run_path).resolve()
    raw_path = Path(artifact_ref.path)
    if raw_path.is_absolute():
        raise ValueError(
            f"Trajectory artifact ref must be relative: {artifact_ref.path}"
        )
    resolved = (eval_run_dir / raw_path).resolve()
    if not resolved.is_relative_to(eval_run_dir):
        raise ValueError(
            f"Trajectory artifact ref escapes eval run dir: {artifact_ref.path}"
        )
    return resolved


def validate_artifact_ref_hash(path: Path, artifact_ref: ArtifactRef) -> None:
    if artifact_ref.content_hash is None:
        raise ValueError(
            f"Training artifact ref is missing content_hash: {artifact_ref.path}"
        )
    observed_hash = hash_file(path)
    if observed_hash != artifact_ref.content_hash:
        raise ValueError(
            f"Artifact hash mismatch for {artifact_ref.path}: "
            f"{observed_hash!r} != {artifact_ref.content_hash!r}"
        )
