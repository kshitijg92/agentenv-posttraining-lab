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
    TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION,
    TRAJECTORY_REVIEW_ARTIFACT_REFS,
    TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION,
    TrajectoryReviewManifest,
    load_trajectory_review_manifest,
)
from agentenv.trajectories.export import (
    TrajectoryExport,
    hash_file,
    load_trajectory_export_artifact,
)
from agentenv.trajectories.schema import (
    TRAJECTORY_RECORD_SCHEMA_VERSION,
    TRAJECTORY_REVIEW_SCHEMA_VERSION,
    TrajectoryRecord,
    TrajectoryReviewRecord,
)


@dataclass(frozen=True)
class TrajectoryReviewArtifact:
    out_dir: Path
    manifest: TrajectoryReviewManifest
    reviews: tuple[TrajectoryReviewRecord, ...]


@dataclass(frozen=True)
class TrajectoryReviewValidation:
    source_export: TrajectoryExport
    review_artifact: TrajectoryReviewArtifact
    record_count: int
    review_status_counts: dict[str, int]
    review_decision_counts: dict[str, int]


def initialize_trajectory_review_artifact(
    trajectory_export_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> TrajectoryReviewArtifact:
    trajectory_export_dir = trajectory_export_dir.resolve()
    source_export = load_trajectory_export_artifact(trajectory_export_dir)
    reviews = build_initial_review_records(source_export.records)

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    reviews_path = out_dir / TRAJECTORY_REVIEW_ARTIFACT_REFS["reviews"]
    review_queue_path = out_dir / TRAJECTORY_REVIEW_ARTIFACT_REFS["review_queue"]
    write_trajectory_review_records_jsonl(reviews_path, reviews)
    review_queue_path.write_text(render_review_queue_markdown(source_export, reviews))

    manifest = build_trajectory_review_manifest(
        out_dir=out_dir,
        source_export=source_export,
        review_record_count=len(reviews),
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_trajectory_review_artifact(out_dir)


def validate_trajectory_review_artifact(
    trajectory_export_dir: Path,
    review_dir: Path,
) -> TrajectoryReviewValidation:
    source_export = load_trajectory_export_artifact(trajectory_export_dir)
    review_artifact = load_trajectory_review_artifact(review_dir)
    validate_review_manifest_matches_source_export(
        review_artifact.manifest,
        source_export,
    )
    validate_review_records_match_trajectories(
        review_artifact.reviews,
        source_export.records,
    )
    return TrajectoryReviewValidation(
        source_export=source_export,
        review_artifact=review_artifact,
        record_count=len(review_artifact.reviews),
        review_status_counts=count_review_statuses(review_artifact.reviews),
        review_decision_counts=count_review_decisions(review_artifact.reviews),
    )


def load_trajectory_review_artifact(review_dir: Path) -> TrajectoryReviewArtifact:
    review_dir = review_dir.resolve()
    manifest = load_trajectory_review_manifest(review_dir / MANIFEST_FILENAME)
    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["reviews"],
    )
    review_queue_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["review_queue"],
    )
    if not review_queue_path.is_file():
        raise ValueError(f"Missing trajectory review queue at {review_queue_path}")

    reviews = load_trajectory_review_records_jsonl(reviews_path)
    if len(reviews) != manifest.record_count:
        raise ValueError(
            f"Trajectory review record count mismatch at {reviews_path}: "
            f"{len(reviews)} != {manifest.record_count}"
        )
    return TrajectoryReviewArtifact(
        out_dir=review_dir,
        manifest=manifest,
        reviews=reviews,
    )


def validate_review_manifest_matches_source_export(
    manifest: TrajectoryReviewManifest,
    source_export: TrajectoryExport,
) -> None:
    source_manifest_path = source_export.out_dir / MANIFEST_FILENAME
    compared_fields = (
        (
            "source_artifact_dir",
            manifest.source_artifact_dir,
            str(source_export.out_dir),
        ),
        (
            "source_manifest_path",
            manifest.source_manifest_path,
            str(source_manifest_path),
        ),
        (
            "source_manifest_hash",
            manifest.source_manifest_hash,
            hash_file(source_manifest_path),
        ),
        (
            "source_eval_run_id",
            manifest.source_eval_run_id,
            source_export.manifest.source_eval_run_id,
        ),
        (
            "source_eval_suite_id",
            manifest.source_eval_suite_id,
            source_export.manifest.source_eval_suite_id,
        ),
        (
            "source_trajectories_jsonl_hash",
            manifest.source_trajectories_jsonl_hash,
            source_export.manifest.trajectories_jsonl_hash,
        ),
        (
            "trajectory_record_schema_version",
            manifest.trajectory_record_schema_version,
            source_export.manifest.trajectory_record_schema_version,
        ),
        ("record_count", manifest.record_count, len(source_export.records)),
    )
    for field_name, observed, expected in compared_fields:
        if observed != expected:
            raise ValueError(
                f"Trajectory review manifest {field_name} mismatch: "
                f"{observed!r} != {expected!r}"
            )


def validate_review_records_match_trajectories(
    reviews: tuple[TrajectoryReviewRecord, ...],
    trajectories: tuple[TrajectoryRecord, ...],
) -> None:
    trajectory_by_id = build_trajectory_record_index(trajectories)
    review_by_id = build_review_record_index(reviews)

    missing_trajectory_ids = sorted(set(trajectory_by_id) - set(review_by_id))
    if missing_trajectory_ids:
        raise ValueError(
            "Trajectory review is missing review rows for trajectory_id: "
            f"{', '.join(missing_trajectory_ids)}"
        )

    unknown_trajectory_ids = sorted(set(review_by_id) - set(trajectory_by_id))
    if unknown_trajectory_ids:
        raise ValueError(
            "Trajectory review contains unknown trajectory_id: "
            f"{', '.join(unknown_trajectory_ids)}"
        )

    for trajectory_id, review in review_by_id.items():
        trajectory = trajectory_by_id[trajectory_id]
        compared_fields = (
            (
                "eval_attempt_id",
                review.eval_attempt_id,
                trajectory.identity.eval_attempt_id,
            ),
            ("task_id", review.task_id, trajectory.identity.task_id),
            ("policy_id", review.policy_id, trajectory.identity.policy_id),
        )
        for field_name, observed, expected in compared_fields:
            if observed != expected:
                raise ValueError(
                    f"Trajectory review row {trajectory_id} {field_name} mismatch: "
                    f"{observed!r} != {expected!r}"
                )


def build_trajectory_record_index(
    records: tuple[TrajectoryRecord, ...],
) -> dict[str, TrajectoryRecord]:
    record_by_id: dict[str, TrajectoryRecord] = {}
    for record in records:
        trajectory_id = record.identity.trajectory_id
        if trajectory_id in record_by_id:
            raise ValueError(
                f"Trajectory export contains duplicate trajectory_id: {trajectory_id}"
            )
        record_by_id[trajectory_id] = record
    return record_by_id


def build_review_record_index(
    reviews: tuple[TrajectoryReviewRecord, ...],
) -> dict[str, TrajectoryReviewRecord]:
    review_by_id: dict[str, TrajectoryReviewRecord] = {}
    for review in reviews:
        if review.trajectory_id in review_by_id:
            raise ValueError(
                "Trajectory review contains duplicate trajectory_id: "
                f"{review.trajectory_id}"
            )
        review_by_id[review.trajectory_id] = review
    return review_by_id


def count_review_statuses(
    reviews: tuple[TrajectoryReviewRecord, ...],
) -> dict[str, int]:
    counts = {"not_reviewed": 0, "reviewed": 0}
    for review in reviews:
        counts[review.review_status] += 1
    return counts


def count_review_decisions(
    reviews: tuple[TrajectoryReviewRecord, ...],
) -> dict[str, int]:
    counts = {"accepted": 0, "rejected": 0, "needs_followup": 0}
    for review in reviews:
        if review.review_decision is not None:
            counts[review.review_decision] += 1
    return counts


def build_initial_review_records(
    records: tuple[TrajectoryRecord, ...],
) -> tuple[TrajectoryReviewRecord, ...]:
    return tuple(build_initial_review_record(record) for record in records)


def build_initial_review_record(record: TrajectoryRecord) -> TrajectoryReviewRecord:
    return TrajectoryReviewRecord(
        trajectory_id=record.identity.trajectory_id,
        eval_attempt_id=record.identity.eval_attempt_id,
        task_id=record.identity.task_id,
        policy_id=record.identity.policy_id,
        review_status="not_reviewed",
    )


def write_trajectory_review_records_jsonl(
    path: Path,
    records: tuple[TrajectoryReviewRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_trajectory_review_records_jsonl(
    path: Path,
) -> tuple[TrajectoryReviewRecord, ...]:
    records: list[TrajectoryReviewRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(TrajectoryReviewRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"TrajectoryReviewRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_trajectory_review_manifest(
    *,
    out_dir: Path,
    source_export: TrajectoryExport,
    review_record_count: int,
) -> TrajectoryReviewManifest:
    reviews_ref = TRAJECTORY_REVIEW_ARTIFACT_REFS["reviews"]
    review_queue_ref = TRAJECTORY_REVIEW_ARTIFACT_REFS["review_queue"]
    if (
        resolve_relative_artifact_ref(out_dir, reviews_ref)
        != (out_dir / reviews_ref).resolve()
    ):
        raise ValueError("Trajectory review JSONL path does not match artifact ref")
    if (
        resolve_relative_artifact_ref(out_dir, review_queue_ref)
        != (out_dir / review_queue_ref).resolve()
    ):
        raise ValueError("Trajectory review queue path does not match artifact ref")

    source_manifest_path = source_export.out_dir / MANIFEST_FILENAME
    return TrajectoryReviewManifest.model_validate(
        {
            "artifact_type": ArtifactType.TRAJECTORY_REVIEW,
            "artifact_schema_version": TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "source_artifact_type": ArtifactType.TRAJECTORY_EXPORT,
            "source_artifact_schema_version": TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "source_artifact_dir": str(source_export.out_dir),
            "source_manifest_path": str(source_manifest_path),
            "source_manifest_hash": hash_file(source_manifest_path),
            "source_eval_run_id": source_export.manifest.source_eval_run_id,
            "source_eval_suite_id": source_export.manifest.source_eval_suite_id,
            "source_trajectories_jsonl_hash": (
                source_export.manifest.trajectories_jsonl_hash
            ),
            "trajectory_record_schema_version": TRAJECTORY_RECORD_SCHEMA_VERSION,
            "trajectory_review_schema_version": TRAJECTORY_REVIEW_SCHEMA_VERSION,
            "record_count": review_record_count,
            "artifacts": dict(TRAJECTORY_REVIEW_ARTIFACT_REFS),
        }
    )


def render_review_queue_markdown(
    source_export: TrajectoryExport,
    reviews: tuple[TrajectoryReviewRecord, ...],
) -> str:
    review_by_trajectory_id = {review.trajectory_id: review for review in reviews}
    lines = [
        "# Trajectory Review Queue",
        "",
        f"Source trajectory export: `{source_export.out_dir}`",
        f"Source artifact type: `{ArtifactType.TRAJECTORY_EXPORT.value}`",
        f"Source eval artifact type: `{source_export.manifest.source_artifact_type}`",
        f"Record count: `{source_export.manifest.record_count}`",
        "",
        "Edit `reviews.jsonl` to record human decisions. Keep one row per trajectory.",
        "",
    ]

    for index, record in enumerate(source_export.records, start=1):
        review = review_by_trajectory_id[record.identity.trajectory_id]
        lines.extend(
            [
                f"## {index}. {record.identity.trajectory_id}",
                "",
                f"- task_id: `{record.identity.task_id}`",
                f"- policy_id: `{record.identity.policy_id}`",
                f"- eval_attempt_id: `{record.identity.eval_attempt_id}`",
                f"- agent_task_run_status: "
                f"`{format_markdown_value(record.statuses.agent_task_run_status)}`",
                f"- prompt_loop_status: "
                f"`{format_markdown_value(record.statuses.prompt_loop_status)}`",
                f"- grade_state: `{record.statuses.grade_state}`",
                f"- task_success: `{record.statuses.task_success}`",
                f"- public_status: "
                f"`{format_markdown_value(record.statuses.public_status)}`",
                f"- hidden_status: "
                f"`{format_markdown_value(record.statuses.hidden_status)}`",
                f"- positive_sft_allowed: "
                f"`{record.training_eligibility.positive_sft_allowed}`",
                f"- negative_example_allowed: "
                f"`{record.training_eligibility.negative_example_allowed}`",
                f"- preference_data_allowed: "
                f"`{record.training_eligibility.preference_data_allowed}`",
                f"- eligibility_reason: "
                f"`{record.training_eligibility.eligibility_reason}`",
                f"- canary_leaked: `{record.leakage.canary_leaked}`",
                f"- hidden_validators_visible_to_model: "
                f"`{record.leakage.hidden_validators_visible_to_model}`",
                "",
                "Inspection refs:",
                "",
            ]
        )
        lines.extend(render_artifact_ref_lines(record))
        lines.extend(
            [
                "",
                "Pending review row:",
                "",
                "```json",
                json.dumps(review.model_dump(mode="json"), sort_keys=True),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def render_artifact_ref_lines(record: TrajectoryRecord) -> list[str]:
    lines = [f"- eval_run_path: `{record.artifacts.eval_run_path}`"]
    for field_name in (
        "agent_task_run_json",
        "agent_task_view_json",
        "prompt_loop_result_json",
        "decoding_config_json",
        "model_config_json",
        "agent_control_script_json",
        "candidate_patch",
        "attempt_json",
        "trace_jsonl",
        "stdout",
        "stderr",
        "error_txt",
        "final_diff",
    ):
        artifact_ref = getattr(record.artifacts, field_name)
        if artifact_ref is None:
            continue
        lines.append(f"- {field_name}: `{artifact_ref.path}`")
    return lines


def format_markdown_value(value: object) -> str:
    if value is None:
        return "null"
    return str(value)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
