from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import ValidationError

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    POSITIVE_SFT_REVIEW_ARTIFACT_REFS,
    POSITIVE_SFT_REVIEW_ARTIFACT_SCHEMA_VERSION,
    PositiveSFTReviewManifest,
    load_positive_sft_review_manifest,
)
from agentenv.artifacts.payloads import load_prompt_loop_result
from agentenv.hashing import hash_file, hash_json
from agentenv.models.schema import Message
from agentenv.training.candidates.export import (
    TrainingCandidateExport,
    load_training_candidate_export_artifact,
)
from agentenv.training.candidates.source_integrity import (
    build_trajectory_record_index,
    load_pinned_candidate_trajectory_export,
    resolve_trajectory_artifact_path,
    validate_artifact_ref_hash,
    validate_pinned_candidate_source_review,
)
from agentenv.training.candidates.hashing import hash_training_candidate_record
from agentenv.training.repairs.redundancy_repair import (
    hash_training_candidate_repair_record,
    hash_training_candidate_repair_review_record,
)
from agentenv.training.repairs.review import (
    TrainingCandidateRepairReviewValidation,
    validate_training_candidate_repair_review_artifact,
)
from agentenv.training.positive_sft.source_selection import (
    SelectedPositiveSFTRepair,
    build_selected_positive_sft_repair_index,
    load_selected_repaired_messages,
    require_artifact_ref,
    validate_positive_sft_candidate_matches_trajectory,
    validate_positive_sft_repair_source_matches_candidate_export,
)
from agentenv.training.positive_sft.schema import (
    POSITIVE_SFT_ACTION_EFFICIENCY_RUBRIC_ID,
    POSITIVE_SFT_REVIEW_RECORD_SCHEMA_VERSION,
    OriginalPositiveSFTReviewSource,
    PositiveSFTReviewRecord,
    PositiveSFTReviewSource,
    RepairedPositiveSFTReviewSource,
)
from agentenv.trajectories.schema import TrajectoryRecord


POSITIVE_SFT_REVIEW_RUBRIC = """## Positive-SFT Prefix And Action-Efficiency Rubric

### Prefix decision

Review assistant actions from the start of the selected source. `accepted`
requires one exact assistant-message boundary that ends a contiguous,
training-eligible prefix. `rejected` means no such prefix should be used.
The persisted `needs_followup` value is reported as an unresolved prefix:
uncertainty remains and no prefix is authorized.

### Efficiency judgment

Apply this dimension only to an accepted prefix, including every assistant
action through the approved boundary.

- `accepted`: every retained assistant action has a defensible causal role.
- `rejected`: at least one exact retained assistant action is avoidable, and
  removing it would preserve coherence, useful information, state changes, and
  validation evidence.
- `needs_followup`: the reviewer abstains because efficiency cannot be judged
  confidently; reports call this an efficiency abstention.

An action has a defensible role when it acquires task-relevant information,
changes the workspace toward the solution, or validates or diagnoses relevant
state. A passing pre-edit public-check run may be prudent baseline diagnosis.
Do not prefer a shorter trajectory merely because it is shorter, and do not
use hindsight alone to declare exploration avoidable.

Efficiency rejection requires exact avoidable assistant message ids. The raw
SFT population is every prefix-accepted row. The filtered population is every
prefix-accepted row whose efficiency judgment is `accepted`. Reviews never
rewrite or delete individual messages.
"""


@dataclass(frozen=True)
class PositiveSFTReviewArtifact:
    out_dir: Path
    manifest: PositiveSFTReviewManifest
    reviews: tuple[PositiveSFTReviewRecord, ...]


@dataclass(frozen=True)
class PositiveSFTReviewValidation:
    source_candidate_export: TrainingCandidateExport
    repair_validation: TrainingCandidateRepairReviewValidation | None
    review_artifact: PositiveSFTReviewArtifact


@dataclass(frozen=True)
class PositiveSFTReviewSelection:
    candidate_hash: str
    task_id: str
    task_success: bool
    source: PositiveSFTReviewSource
    messages: tuple[Message, ...]


def initialize_positive_sft_review_artifact(
    training_candidate_export_dir: Path,
    out_dir: Path,
    *,
    repair_export_dir: Path | None = None,
    repair_review_dir: Path | None = None,
    selected_repair_ids: tuple[str, ...] = (),
    overwrite: bool = False,
) -> PositiveSFTReviewArtifact:
    candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    repair_validation = _load_selected_repair_sources(
        candidate_export,
        repair_export_dir=repair_export_dir,
        repair_review_dir=repair_review_dir,
        selected_repair_ids=selected_repair_ids,
    )
    selections = build_positive_sft_review_selections(
        candidate_export,
        repair_validation=repair_validation,
        selected_repair_ids=selected_repair_ids,
    )
    reviews = tuple(
        PositiveSFTReviewRecord(
            source_training_candidate_record_hash=selection.candidate_hash,
            source=selection.source,
            review_status="not_reviewed",
            efficiency_judgment=None,
        )
        for selection in selections
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    reviews_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_REVIEW_ARTIFACT_REFS["reviews"],
    )
    queue_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_REVIEW_ARTIFACT_REFS["review_queue"],
    )
    write_positive_sft_review_records_jsonl(reviews_path, reviews)
    queue_path.write_text(render_positive_sft_review_queue(selections, reviews))
    manifest = build_positive_sft_review_manifest(
        out_dir=out_dir,
        candidate_export=candidate_export,
        repair_validation=repair_validation,
        reviews=reviews,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_positive_sft_review_artifact(out_dir)


def load_positive_sft_review_artifact(review_dir: Path) -> PositiveSFTReviewArtifact:
    review_dir = review_dir.resolve()
    manifest = load_positive_sft_review_manifest(review_dir / MANIFEST_FILENAME)
    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["reviews"],
    )
    queue_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["review_queue"],
    )
    if not queue_path.is_file():
        raise ValueError(f"Missing positive-SFT review queue at {queue_path}")
    reviews = load_positive_sft_review_records_jsonl(reviews_path)
    if len(reviews) != manifest.record_count:
        raise ValueError(
            "Positive-SFT review record count mismatch: "
            f"{len(reviews)} != {manifest.record_count}"
        )
    return PositiveSFTReviewArtifact(
        out_dir=review_dir,
        manifest=manifest,
        reviews=reviews,
    )


def validate_positive_sft_review_artifact(
    review_dir: Path,
) -> PositiveSFTReviewValidation:
    artifact = load_positive_sft_review_artifact(review_dir)
    candidate_dir = _resolve_pinned_artifact_dir(
        artifact.out_dir,
        artifact.manifest.source_training_candidate_export.artifact_dir,
    )
    candidate_export = load_training_candidate_export_artifact(candidate_dir)
    _validate_manifest_hash(
        candidate_export.out_dir,
        artifact.manifest.source_training_candidate_export.manifest_hash,
        owner="positive-SFT review source training candidate export",
    )
    repair_validation = _load_pinned_repair_validation(artifact, candidate_export)
    selected_repair_ids = tuple(
        review.source.repair_id
        for review in artifact.reviews
        if isinstance(review.source, RepairedPositiveSFTReviewSource)
    )
    selections = build_positive_sft_review_selections(
        candidate_export,
        repair_validation=repair_validation,
        selected_repair_ids=selected_repair_ids,
    )
    validate_positive_sft_review_records(artifact.reviews, selections)
    return PositiveSFTReviewValidation(
        source_candidate_export=candidate_export,
        repair_validation=repair_validation,
        review_artifact=artifact,
    )


def build_positive_sft_review_selections(
    candidate_export: TrainingCandidateExport,
    *,
    repair_validation: TrainingCandidateRepairReviewValidation | None,
    selected_repair_ids: tuple[str, ...],
) -> tuple[PositiveSFTReviewSelection, ...]:
    validate_pinned_candidate_source_review(candidate_export)
    trajectory_export = load_pinned_candidate_trajectory_export(candidate_export)
    trajectories_by_id = build_trajectory_record_index(trajectory_export.records)
    selected_repairs = build_selected_positive_sft_repair_index(
        candidate_export,
        repair_validation=repair_validation,
        selected_repair_ids=selected_repair_ids,
    )
    selections: list[PositiveSFTReviewSelection] = []
    for candidate in candidate_export.records:
        if not candidate.content_eligibility.positive_sft_review_eligible:
            continue
        assessment = candidate.mechanical_redundancy_assessment
        if assessment.evaluation_status != "complete":
            continue
        candidate_hash = hash_training_candidate_record(candidate)
        selected_repair = selected_repairs.get(candidate_hash)
        if assessment.blocks and selected_repair is None:
            continue
        if not assessment.blocks and selected_repair is not None:
            raise ValueError(
                "Positive-SFT review selected a repair for a mechanically clean "
                f"candidate: {candidate.trajectory_id}"
            )
        trajectory = _require_trajectory(candidate.trajectory_id, trajectories_by_id)
        validate_positive_sft_candidate_matches_trajectory(candidate, trajectory)
        source, messages = _build_review_source(trajectory, selected_repair)
        selections.append(
            PositiveSFTReviewSelection(
                candidate_hash=candidate_hash,
                task_id=candidate.task_id,
                task_success=trajectory.statuses.task_success,
                source=source,
                messages=tuple(messages),
            )
        )
    return tuple(selections)


def validate_positive_sft_review_records(
    reviews: tuple[PositiveSFTReviewRecord, ...],
    selections: tuple[PositiveSFTReviewSelection, ...],
) -> None:
    reviews_by_candidate = _index_reviews(reviews)
    selections_by_candidate = _index_selections(selections)
    missing = sorted(set(selections_by_candidate) - set(reviews_by_candidate))
    if missing:
        raise ValueError(
            "Positive-SFT review artifact is missing candidate records: "
            + ", ".join(missing)
        )
    unknown = sorted(set(reviews_by_candidate) - set(selections_by_candidate))
    if unknown:
        raise ValueError(
            "Positive-SFT review artifact contains unknown candidate records: "
            + ", ".join(unknown)
        )
    for candidate_hash, selection in selections_by_candidate.items():
        review = reviews_by_candidate[candidate_hash]
        if review.source != selection.source:
            raise ValueError(
                "Positive-SFT review source provenance mismatch for candidate "
                f"{candidate_hash}"
            )
        if review.review_decision != "accepted":
            continue
        boundary_id = review.last_approved_assistant_message_id
        matching = [
            message
            for message in selection.messages
            if message.message_id == boundary_id
        ]
        if len(matching) != 1:
            raise ValueError(
                "Accepted positive-SFT review boundary must identify exactly one "
                f"source message for candidate {candidate_hash}"
            )
        if matching[0].role != "assistant":
            raise ValueError(
                "Accepted positive-SFT review boundary must identify an assistant "
                f"message for candidate {candidate_hash}"
            )
        boundary_index = next(
            index
            for index, message in enumerate(selection.messages)
            if message.message_id == boundary_id
        )
        retained_messages = selection.messages[: boundary_index + 1]
        efficiency = review.efficiency_judgment
        if efficiency is None or efficiency.review_decision != "rejected":
            continue
        retained_messages_by_id = {
            message.message_id: message for message in retained_messages
        }
        for message_id in efficiency.avoidable_assistant_message_ids:
            message = retained_messages_by_id.get(message_id)
            if message is None:
                raise ValueError(
                    "Positive-SFT efficiency evidence must identify a retained "
                    f"prefix message for candidate {candidate_hash}: {message_id}"
                )
            if message.role != "assistant":
                raise ValueError(
                    "Positive-SFT efficiency evidence must identify an assistant "
                    f"message for candidate {candidate_hash}: {message_id}"
                )


def hash_positive_sft_review_record(record: PositiveSFTReviewRecord) -> str:
    return hash_json(record.model_dump(mode="json"))


def write_positive_sft_review_records_jsonl(
    path: Path,
    records: tuple[PositiveSFTReviewRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_positive_sft_review_records_jsonl(
    path: Path,
) -> tuple[PositiveSFTReviewRecord, ...]:
    records: list[PositiveSFTReviewRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(PositiveSFTReviewRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PositiveSFTReviewRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_positive_sft_review_manifest(
    *,
    out_dir: Path,
    candidate_export: TrainingCandidateExport,
    repair_validation: TrainingCandidateRepairReviewValidation | None,
    reviews: tuple[PositiveSFTReviewRecord, ...],
) -> PositiveSFTReviewManifest:
    for artifact_ref in POSITIVE_SFT_REVIEW_ARTIFACT_REFS.values():
        resolve_relative_artifact_ref(out_dir, artifact_ref)
    candidate_ref = {
        "artifact_dir": str(candidate_export.out_dir),
        "manifest_hash": hash_file(candidate_export.out_dir / MANIFEST_FILENAME),
    }
    repaired_count = sum(
        isinstance(review.source, RepairedPositiveSFTReviewSource) for review in reviews
    )
    repair_export_ref: dict[str, str] | None = None
    repair_review_ref: dict[str, str] | None = None
    if repaired_count:
        if repair_validation is None:
            raise ValueError("Repaired positive-SFT reviews require repair provenance")
        repair_export = repair_validation.source_export
        repair_review = repair_validation.review_artifact
        repair_export_ref = {
            "artifact_dir": str(repair_export.out_dir),
            "manifest_hash": hash_file(repair_export.out_dir / MANIFEST_FILENAME),
        }
        repair_reviews_path = resolve_relative_artifact_ref(
            repair_review.out_dir,
            repair_review.manifest.artifacts["reviews"],
        )
        repair_review_ref = {
            "artifact_dir": str(repair_review.out_dir),
            "manifest_hash": hash_file(repair_review.out_dir / MANIFEST_FILENAME),
            "reviews_jsonl_hash": hash_file(repair_reviews_path),
        }
    return PositiveSFTReviewManifest.model_validate(
        {
            "artifact_type": ArtifactType.POSITIVE_SFT_REVIEW,
            "artifact_schema_version": POSITIVE_SFT_REVIEW_ARTIFACT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "source_training_candidate_export": candidate_ref,
            "source_training_candidate_repair_export": repair_export_ref,
            "source_training_candidate_repair_review": repair_review_ref,
            "positive_sft_review_record_schema_version": (
                POSITIVE_SFT_REVIEW_RECORD_SCHEMA_VERSION
            ),
            "record_count": len(reviews),
            "original_record_count": len(reviews) - repaired_count,
            "repaired_record_count": repaired_count,
            "artifacts": dict(POSITIVE_SFT_REVIEW_ARTIFACT_REFS),
        }
    )


def render_positive_sft_review_queue(
    selections: tuple[PositiveSFTReviewSelection, ...],
    reviews: tuple[PositiveSFTReviewRecord, ...],
) -> str:
    reviews_by_candidate = _index_reviews(reviews)
    lines = [
        "# Positive-SFT Combined Review Queue",
        "",
        "This one row owns both the prefix decision and, when that prefix is",
        "accepted, the action-efficiency judgment. Edit `reviews.jsonl`.",
        "",
        *POSITIVE_SFT_REVIEW_RUBRIC.splitlines(),
        "",
        "An accepted prefix with `efficiency_judgment: null` is still pending.",
        "Fill it using this shape:",
        "",
        "```json",
        json.dumps(
            {
                "rubric_id": POSITIVE_SFT_ACTION_EFFICIENCY_RUBRIC_ID,
                "review_id": "<review id>",
                "reviewer_id": "<reviewer id>",
                "review_decision": "accepted|rejected|needs_followup",
                "decision_reason": "<brief reason>",
                "review_notes_ref": None,
                "avoidable_assistant_message_ids": [],
            },
            sort_keys=True,
        ),
        "```",
        "",
    ]
    for index, selection in enumerate(selections, start=1):
        review = reviews_by_candidate[selection.candidate_hash]
        review_messages = _positive_sft_review_context_messages(selection, review)
        assistant_ids = [
            message.message_id
            for message in review_messages
            if message.role == "assistant"
        ]
        efficiency_status = derive_positive_sft_efficiency_review_status(review)
        context_label = (
            "Exact retained prefix"
            if review.review_decision == "accepted"
            else "Exact source messages"
        )
        lines.extend(
            [
                f"## {index}. `{selection.candidate_hash}`",
                "",
                f"- task_id: `{selection.task_id}`",
                f"- task_success: `{str(selection.task_success).lower()}`",
                f"- source_type: `{selection.source.source_type}`",
                f"- prefix_review_status: `{review.review_status}`",
                f"- prefix_decision: `{review.review_decision}`",
                f"- efficiency_review_status: `{efficiency_status}`",
                f"- assistant_action_count: `{len(assistant_ids)}`",
                f"- assistant_message_ids: `{json.dumps(assistant_ids)}`",
                "",
                "Review row:",
                "",
                "```json",
                json.dumps(review.model_dump(mode="json"), sort_keys=True),
                "```",
                "",
                f"{context_label}:",
                "",
                "```json",
                json.dumps(
                    [message.model_dump(mode="json") for message in review_messages],
                    indent=2,
                    sort_keys=True,
                ),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def derive_positive_sft_efficiency_review_status(
    review: PositiveSFTReviewRecord,
) -> Literal["blocked", "not_applicable", "not_reviewed", "reviewed"]:
    if review.review_status != "reviewed":
        return "blocked"
    if review.review_decision != "accepted":
        return "not_applicable"
    if review.efficiency_judgment is None:
        return "not_reviewed"
    return "reviewed"


def _positive_sft_review_context_messages(
    selection: PositiveSFTReviewSelection,
    review: PositiveSFTReviewRecord,
) -> tuple[Message, ...]:
    boundary_id = review.last_approved_assistant_message_id
    if review.review_decision != "accepted" or boundary_id is None:
        return selection.messages
    boundary_index = next(
        (
            index
            for index, message in enumerate(selection.messages)
            if message.message_id == boundary_id
        ),
        None,
    )
    if boundary_index is None:
        return selection.messages
    return selection.messages[: boundary_index + 1]


def _build_review_source(
    trajectory: TrajectoryRecord,
    selected_repair: SelectedPositiveSFTRepair | None,
) -> tuple[PositiveSFTReviewSource, list[Message]]:
    if selected_repair is None:
        prompt_loop_ref = require_artifact_ref(
            trajectory.artifacts.prompt_loop_result_json,
            "prompt_loop_result_json",
            trajectory,
        )
        prompt_loop_path = resolve_trajectory_artifact_path(trajectory, prompt_loop_ref)
        validate_artifact_ref_hash(prompt_loop_path, prompt_loop_ref)
        prompt_loop = load_prompt_loop_result(prompt_loop_path)
        return (
            OriginalPositiveSFTReviewSource(
                source_type="original",
                source_artifact_ref=prompt_loop_ref,
            ),
            prompt_loop.messages,
        )

    repair = selected_repair.record
    repair_review = selected_repair.review
    repaired_ref = repair.repaired_artifact_ref
    if repaired_ref is None:
        raise ValueError("Selected positive-SFT repair is missing repaired artifact")
    if repair_review.review_id is None:
        raise ValueError("Selected positive-SFT repair review is missing review_id")
    return (
        RepairedPositiveSFTReviewSource(
            source_type="repaired",
            source_artifact_ref=repaired_ref,
            repair_id=repair.repair_id,
            source_training_candidate_repair_record_hash=(
                hash_training_candidate_repair_record(repair)
            ),
            source_training_candidate_repair_review_record_hash=(
                hash_training_candidate_repair_review_record(repair_review)
            ),
            repair_review_id=repair_review.review_id,
        ),
        load_selected_repaired_messages(selected_repair),
    )


def _load_selected_repair_sources(
    candidate_export: TrainingCandidateExport,
    *,
    repair_export_dir: Path | None,
    repair_review_dir: Path | None,
    selected_repair_ids: tuple[str, ...],
) -> TrainingCandidateRepairReviewValidation | None:
    if not selected_repair_ids:
        if repair_export_dir is not None or repair_review_dir is not None:
            raise ValueError(
                "Positive-SFT review repair artifacts require selected repair IDs"
            )
        return None
    if repair_export_dir is None or repair_review_dir is None:
        raise ValueError(
            "Selected positive-SFT review repairs require repair export and review"
        )
    repair_validation = validate_training_candidate_repair_review_artifact(
        repair_export_dir,
        repair_review_dir,
    )
    validate_positive_sft_repair_source_matches_candidate_export(
        candidate_export,
        repair_validation,
    )
    return repair_validation


def _load_pinned_repair_validation(
    artifact: PositiveSFTReviewArtifact,
    candidate_export: TrainingCandidateExport,
) -> TrainingCandidateRepairReviewValidation | None:
    repair_ref = artifact.manifest.source_training_candidate_repair_export
    review_ref = artifact.manifest.source_training_candidate_repair_review
    if repair_ref is None and review_ref is None:
        return None
    if repair_ref is None or review_ref is None:
        raise ValueError(
            "Positive-SFT review manifest has incomplete repair provenance"
        )
    repair_dir = _resolve_pinned_artifact_dir(
        artifact.out_dir,
        repair_ref.artifact_dir,
    )
    review_dir = _resolve_pinned_artifact_dir(
        artifact.out_dir,
        review_ref.artifact_dir,
    )
    repair_validation = validate_training_candidate_repair_review_artifact(
        repair_dir,
        review_dir,
    )
    _validate_manifest_hash(
        repair_dir,
        repair_ref.manifest_hash,
        owner="positive-SFT review source repair export",
    )
    _validate_manifest_hash(
        review_dir,
        review_ref.manifest_hash,
        owner="positive-SFT review source repair review",
    )
    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        repair_validation.review_artifact.manifest.artifacts["reviews"],
    )
    if hash_file(reviews_path) != review_ref.reviews_jsonl_hash:
        raise ValueError("Positive-SFT review source repair reviews hash mismatch")
    validate_positive_sft_repair_source_matches_candidate_export(
        candidate_export,
        repair_validation,
    )
    return repair_validation


def _resolve_pinned_artifact_dir(owner_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = owner_dir / path
    return path.resolve()


def _validate_manifest_hash(
    artifact_dir: Path, expected_hash: str, *, owner: str
) -> None:
    observed_hash = hash_file(artifact_dir / MANIFEST_FILENAME)
    if observed_hash != expected_hash:
        raise ValueError(
            f"{owner} manifest hash mismatch: {observed_hash!r} != {expected_hash!r}"
        )


def _require_trajectory(
    trajectory_id: str,
    trajectories_by_id: dict[str, TrajectoryRecord],
) -> TrajectoryRecord:
    trajectory = trajectories_by_id.get(trajectory_id)
    if trajectory is None:
        raise ValueError(
            f"Training candidate references unknown trajectory_id: {trajectory_id}"
        )
    return trajectory


def _index_reviews(
    reviews: tuple[PositiveSFTReviewRecord, ...],
) -> dict[str, PositiveSFTReviewRecord]:
    indexed: dict[str, PositiveSFTReviewRecord] = {}
    for review in reviews:
        candidate_hash = review.source_training_candidate_record_hash
        if candidate_hash in indexed:
            raise ValueError(
                "Positive-SFT review contains duplicate source candidate hash: "
                f"{candidate_hash}"
            )
        indexed[candidate_hash] = review
    return indexed


def _index_selections(
    selections: tuple[PositiveSFTReviewSelection, ...],
) -> dict[str, PositiveSFTReviewSelection]:
    indexed: dict[str, PositiveSFTReviewSelection] = {}
    for selection in selections:
        if selection.candidate_hash in indexed:
            raise ValueError(
                "Positive-SFT review selections contain duplicate candidate hash: "
                f"{selection.candidate_hash}"
            )
        indexed[selection.candidate_hash] = selection
    return indexed


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
