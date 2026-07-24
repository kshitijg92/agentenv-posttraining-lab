from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence, cast

from pydantic import ValidationError

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    POSITIVE_SFT_EFFICIENCY_REVIEW_ARTIFACT_REFS,
    POSITIVE_SFT_EFFICIENCY_REVIEW_ARTIFACT_SCHEMA_VERSION,
    PositiveSFTEfficiencyReviewManifest,
    PositiveSFTExportManifest,
    PositiveSFTTrainingMaterializationManifest,
    PositiveSFTTrainingMaterializationArtifactRef,
    load_positive_sft_efficiency_review_manifest,
    load_positive_sft_export_manifest,
    load_positive_sft_training_materialization_manifest,
)
from agentenv.hashing import hash_file, hash_json
from agentenv.training.positive_sft.export import (
    load_positive_sft_example_records_jsonl,
)
from agentenv.training.positive_sft.materialization.export import (
    load_positive_sft_training_materialization_records_jsonl,
)
from agentenv.training.positive_sft.materialization.schema import (
    CompletedPositiveSFTTrainingMaterializationRecord,
    PositiveSFTTrainingMaterializationRecord,
)
from agentenv.training.positive_sft.schema import (
    POSITIVE_SFT_EFFICIENCY_REVIEW_RECORD_SCHEMA_VERSION,
    POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION,
    PositiveSFTEfficiencyReviewRecord,
    PositiveSFTExampleRecord,
)


POSITIVE_SFT_EFFICIENCY_RUBRIC = """# Positive-SFT Action-Efficiency Rubric

## Scope

Review one complete PositiveSFTExampleRecord. Upstream task success, harness
checks, leakage gates, training eligibility, and positive-SFT prefix approval
are trusted provenance. This review asks only whether every retained assistant
action had a defensible causal role in solving the task.

## Decisions

- `accepted`: no exact retained assistant action can defensibly be identified
  as avoidable under this rubric.
- `rejected`: at least one exact assistant message is avoidable, and removing
  it would leave the approved trajectory coherent without removing useful
  information, state change, or validation evidence.
- `needs_followup`: the reviewer cannot make that judgment confidently from
  the available evidence.

## Defensible causal roles

An assistant action is useful when it does at least one of the following:

- acquires new task-relevant information;
- changes the workspace toward the solution;
- validates or diagnoses materially relevant state.

A passing pre-edit public-check run may be prudent baseline diagnosis. A short
trajectory is not automatically better than a long trajectory. Action count,
sequence length, and supervised-token count are review-prioritization and
reporting signals, not decision authority.

Reject only with exact assistant message ids. Do not use hindsight alone to
declare exploration avoidable. When uncertain, use `needs_followup`.

Filtering later operates on the whole source example. This review never
deletes, rewrites, truncates, reorders, or masks individual actions.
"""


@dataclass(frozen=True)
class PositiveSFTEfficiencyReviewSelection:
    materialization_artifact_dir: Path
    materialization: CompletedPositiveSFTTrainingMaterializationRecord
    source_export_artifact_dir: Path
    source_example: PositiveSFTExampleRecord


@dataclass(frozen=True)
class PositiveSFTEfficiencyReviewInventory:
    source_materialization_refs: tuple[
        PositiveSFTTrainingMaterializationArtifactRef, ...
    ]
    selections: tuple[PositiveSFTEfficiencyReviewSelection, ...]


@dataclass(frozen=True)
class PositiveSFTEfficiencyReviewArtifact:
    out_dir: Path
    manifest: PositiveSFTEfficiencyReviewManifest
    reviews: tuple[PositiveSFTEfficiencyReviewRecord, ...]


@dataclass(frozen=True)
class PositiveSFTEfficiencyReviewValidation:
    artifact: PositiveSFTEfficiencyReviewArtifact
    inventory: PositiveSFTEfficiencyReviewInventory
    review_status_counts: dict[str, int]
    review_decision_counts: dict[str, int]


def initialize_positive_sft_efficiency_review_artifact(
    materialization_dirs: Sequence[Path],
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> PositiveSFTEfficiencyReviewArtifact:
    inventory = load_positive_sft_efficiency_review_inventory(materialization_dirs)
    reviews = tuple(
        PositiveSFTEfficiencyReviewRecord(
            source_positive_sft_example_id=selection.source_example.example_id,
            source_positive_sft_example_record_hash=hash_json(
                selection.source_example.model_dump(mode="json")
            ),
            review_status="not_reviewed",
        )
        for selection in inventory.selections
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    reviews_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_EFFICIENCY_REVIEW_ARTIFACT_REFS["reviews"],
    )
    queue_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_EFFICIENCY_REVIEW_ARTIFACT_REFS["review_queue"],
    )
    rubric_path = resolve_relative_artifact_ref(
        out_dir,
        POSITIVE_SFT_EFFICIENCY_REVIEW_ARTIFACT_REFS["rubric"],
    )
    write_positive_sft_efficiency_review_records_jsonl(reviews_path, reviews)
    rubric_path.write_text(POSITIVE_SFT_EFFICIENCY_RUBRIC)
    queue_path.write_text(
        render_positive_sft_efficiency_review_queue(inventory.selections, reviews)
    )
    manifest = build_positive_sft_efficiency_review_manifest(
        inventory=inventory,
        rubric_path=rubric_path,
        record_count=len(reviews),
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_positive_sft_efficiency_review_artifact(out_dir)


def load_positive_sft_efficiency_review_artifact(
    review_dir: Path,
) -> PositiveSFTEfficiencyReviewArtifact:
    review_dir = review_dir.resolve()
    manifest = load_positive_sft_efficiency_review_manifest(
        review_dir / MANIFEST_FILENAME
    )
    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["reviews"],
    )
    queue_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["review_queue"],
    )
    rubric_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["rubric"],
    )
    if not queue_path.is_file():
        raise ValueError(f"Missing positive-SFT efficiency review queue: {queue_path}")
    observed_rubric_hash = hash_file(rubric_path)
    if observed_rubric_hash != manifest.rubric_hash:
        raise ValueError(
            "Positive-SFT efficiency rubric hash mismatch: "
            f"{observed_rubric_hash!r} != {manifest.rubric_hash!r}"
        )
    reviews = load_positive_sft_efficiency_review_records_jsonl(reviews_path)
    if len(reviews) != manifest.record_count:
        raise ValueError(
            "Positive-SFT efficiency review record count mismatch: "
            f"{len(reviews)} != {manifest.record_count}"
        )
    return PositiveSFTEfficiencyReviewArtifact(
        out_dir=review_dir,
        manifest=manifest,
        reviews=reviews,
    )


def validate_positive_sft_efficiency_review_artifact(
    review_dir: Path,
) -> PositiveSFTEfficiencyReviewValidation:
    artifact = load_positive_sft_efficiency_review_artifact(review_dir)
    source_dirs = [
        _resolve_pinned_artifact_dir(artifact.out_dir, source.artifact_dir)
        for source in (artifact.manifest.source_positive_sft_training_materializations)
    ]
    inventory = load_positive_sft_efficiency_review_inventory(source_dirs)
    if (
        inventory.source_materialization_refs
        != artifact.manifest.source_positive_sft_training_materializations
    ):
        raise ValueError(
            "Positive-SFT efficiency review materialization provenance differs "
            "from the pinned manifest"
        )
    validate_positive_sft_efficiency_review_records(
        artifact.reviews,
        inventory.selections,
        review_dir=artifact.out_dir,
    )
    status_counts = Counter(review.review_status for review in artifact.reviews)
    decision_counts = Counter(
        review.review_decision
        for review in artifact.reviews
        if review.review_decision is not None
    )
    return PositiveSFTEfficiencyReviewValidation(
        artifact=artifact,
        inventory=inventory,
        review_status_counts={
            "not_reviewed": status_counts["not_reviewed"],
            "reviewed": status_counts["reviewed"],
        },
        review_decision_counts={
            "accepted": decision_counts["accepted"],
            "rejected": decision_counts["rejected"],
            "needs_followup": decision_counts["needs_followup"],
        },
    )


def load_positive_sft_efficiency_review_inventory(
    materialization_dirs: Sequence[Path],
) -> PositiveSFTEfficiencyReviewInventory:
    resolved_dirs = sorted(path.resolve() for path in materialization_dirs)
    if not resolved_dirs:
        raise ValueError(
            "Positive-SFT efficiency review requires materialization artifacts"
        )
    if len(resolved_dirs) != len(set(resolved_dirs)):
        raise ValueError(
            "Positive-SFT efficiency review materialization artifacts must be unique"
        )

    refs: list[PositiveSFTTrainingMaterializationArtifactRef] = []
    selections: list[PositiveSFTEfficiencyReviewSelection] = []
    for materialization_dir in resolved_dirs:
        source_ref, source_selections = _load_materialization_source(
            materialization_dir
        )
        refs.append(source_ref)
        selections.extend(source_selections)

    if not selections:
        raise ValueError(
            "Positive-SFT efficiency review sources contain no completed records"
        )
    example_ids = [selection.source_example.example_id for selection in selections]
    duplicates = sorted(
        example_id for example_id, count in Counter(example_ids).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            "Positive-SFT source examples appear in multiple materializations: "
            + ", ".join(duplicates)
        )
    return PositiveSFTEfficiencyReviewInventory(
        source_materialization_refs=tuple(refs),
        selections=tuple(
            sorted(
                selections,
                key=lambda selection: selection.source_example.example_id,
            )
        ),
    )


def validate_positive_sft_efficiency_review_records(
    reviews: Sequence[PositiveSFTEfficiencyReviewRecord],
    selections: Sequence[PositiveSFTEfficiencyReviewSelection],
    *,
    review_dir: Path,
) -> None:
    reviews_by_example_id = _index_reviews(reviews)
    selections_by_example_id = _index_selections(selections)
    missing = sorted(set(selections_by_example_id) - set(reviews_by_example_id))
    if missing:
        raise ValueError(
            "Positive-SFT efficiency review is missing source examples: "
            + ", ".join(missing)
        )
    unknown = sorted(set(reviews_by_example_id) - set(selections_by_example_id))
    if unknown:
        raise ValueError(
            "Positive-SFT efficiency review contains unknown source examples: "
            + ", ".join(unknown)
        )

    for example_id, selection in selections_by_example_id.items():
        review = reviews_by_example_id[example_id]
        expected_source_hash = hash_json(
            selection.source_example.model_dump(mode="json")
        )
        if review.source_positive_sft_example_record_hash != expected_source_hash:
            raise ValueError(
                f"Positive-SFT efficiency review source hash mismatch for {example_id}"
            )

        messages_by_id = {
            message.message_id: message for message in selection.source_example.messages
        }
        for message_id in review.avoidable_assistant_message_ids:
            message = messages_by_id.get(message_id)
            if message is None:
                raise ValueError(
                    "Positive-SFT efficiency review references an unknown message "
                    f"for {example_id}: {message_id}"
                )
            if message.role != "assistant":
                raise ValueError(
                    "Positive-SFT efficiency review avoidable evidence must identify "
                    f"assistant messages for {example_id}: {message_id}"
                )

        if review.review_notes_ref is not None:
            notes_path = resolve_relative_artifact_ref(
                review_dir,
                review.review_notes_ref.path,
            )
            observed_notes_hash = hash_file(notes_path)
            if observed_notes_hash != review.review_notes_ref.content_hash:
                raise ValueError(
                    "Positive-SFT efficiency review notes hash mismatch for "
                    f"{example_id}"
                )


def build_positive_sft_efficiency_review_manifest(
    *,
    inventory: PositiveSFTEfficiencyReviewInventory,
    rubric_path: Path,
    record_count: int,
) -> PositiveSFTEfficiencyReviewManifest:
    return PositiveSFTEfficiencyReviewManifest.model_validate(
        {
            "artifact_type": ArtifactType.POSITIVE_SFT_EFFICIENCY_REVIEW,
            "artifact_schema_version": (
                POSITIVE_SFT_EFFICIENCY_REVIEW_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "source_positive_sft_training_materializations": [
                source.model_dump(mode="json")
                for source in inventory.source_materialization_refs
            ],
            "positive_sft_example_record_schema_version": (
                POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
            ),
            "positive_sft_efficiency_review_record_schema_version": (
                POSITIVE_SFT_EFFICIENCY_REVIEW_RECORD_SCHEMA_VERSION
            ),
            "rubric_hash": hash_file(rubric_path),
            "record_count": record_count,
            "artifacts": dict(POSITIVE_SFT_EFFICIENCY_REVIEW_ARTIFACT_REFS),
        }
    )


def write_positive_sft_efficiency_review_records_jsonl(
    path: Path,
    reviews: Sequence[PositiveSFTEfficiencyReviewRecord],
) -> None:
    path.write_text(
        "".join(
            json.dumps(review.model_dump(mode="json"), sort_keys=True) + "\n"
            for review in reviews
        )
    )


def load_positive_sft_efficiency_review_records_jsonl(
    path: Path,
) -> tuple[PositiveSFTEfficiencyReviewRecord, ...]:
    reviews: list[PositiveSFTEfficiencyReviewRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            reviews.append(PositiveSFTEfficiencyReviewRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PositiveSFTEfficiencyReviewRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(reviews)


def render_positive_sft_efficiency_review_queue(
    selections: Sequence[PositiveSFTEfficiencyReviewSelection],
    reviews: Sequence[PositiveSFTEfficiencyReviewRecord],
) -> str:
    reviews_by_example_id = _index_reviews(reviews)
    lines = [
        "# Positive-SFT Efficiency Review Queue",
        "",
        "Apply `efficiency_rubric.md` to every exact source example.",
        "Edit `reviews.jsonl`; never edit or rewrite the source messages.",
        "",
    ]
    for index, selection in enumerate(selections, start=1):
        example = selection.source_example
        materialization = selection.materialization
        review = reviews_by_example_id[example.example_id]
        assistant_message_ids = [
            message.message_id
            for message in example.messages
            if message.role == "assistant"
        ]
        lines.extend(
            [
                f"## {index}. `{example.example_id}`",
                "",
                f"- task_id: `{example.task_input.task_id}`",
                f"- source_policy_id: `{example.provenance_ids.policy_id}`",
                "- source_record_hash: "
                f"`{review.source_positive_sft_example_record_hash}`",
                "- materialization_artifact: "
                f"`{selection.materialization_artifact_dir}`",
                f"- sequence_length: `{materialization.sequence_length}`",
                f"- supervised_token_count: `{materialization.supervised_token_count}`",
                f"- assistant_action_count: `{len(assistant_message_ids)}`",
                f"- assistant_message_ids: `{json.dumps(assistant_message_ids)}`",
                "",
                "Review row:",
                "",
                "```json",
                json.dumps(review.model_dump(mode="json"), sort_keys=True),
                "```",
                "",
                "Exact source messages:",
                "",
                "```json",
                json.dumps(
                    [message.model_dump(mode="json") for message in example.messages],
                    indent=2,
                    sort_keys=True,
                ),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _load_materialization_source(
    materialization_dir: Path,
) -> tuple[
    PositiveSFTTrainingMaterializationArtifactRef,
    tuple[PositiveSFTEfficiencyReviewSelection, ...],
]:
    materialization_dir = materialization_dir.resolve()
    manifest_path = materialization_dir / MANIFEST_FILENAME
    manifest = load_positive_sft_training_materialization_manifest(manifest_path)
    records_path = resolve_relative_artifact_ref(
        materialization_dir,
        manifest.artifacts["materializations"],
    )
    observed_records_hash = hash_file(records_path)
    if observed_records_hash != manifest.materializations_jsonl_hash:
        raise ValueError(
            "Positive-SFT materialization JSONL hash mismatch at "
            f"{records_path}: {observed_records_hash!r} != "
            f"{manifest.materializations_jsonl_hash!r}"
        )
    materializations = load_positive_sft_training_materialization_records_jsonl(
        records_path
    )
    _validate_materialization_counts(manifest, materializations)
    failed = [
        record.source_positive_sft_example_id
        for record in materializations
        if record.status != "completed"
    ]
    if failed:
        raise ValueError(
            "Positive-SFT efficiency review sources must contain only completed "
            "materializations: " + ", ".join(sorted(failed))
        )

    source_ref = manifest.source_positive_sft_export
    source_export_dir = _resolve_pinned_artifact_dir(
        materialization_dir,
        source_ref.artifact_dir,
    )
    source_manifest_path = source_export_dir / MANIFEST_FILENAME
    observed_source_manifest_hash = hash_file(source_manifest_path)
    if observed_source_manifest_hash != source_ref.manifest_hash:
        raise ValueError(
            "Source positive-SFT export manifest hash mismatch: "
            f"{observed_source_manifest_hash!r} != {source_ref.manifest_hash!r}"
        )
    source_manifest = load_positive_sft_export_manifest(source_manifest_path)
    source_examples_path = resolve_relative_artifact_ref(
        source_export_dir,
        source_manifest.artifacts["positive_sft_examples"],
    )
    observed_examples_hash = hash_file(source_examples_path)
    if observed_examples_hash != source_ref.positive_sft_examples_jsonl_hash:
        raise ValueError(
            "Source positive-SFT examples JSONL hash mismatch: "
            f"{observed_examples_hash!r} != "
            f"{source_ref.positive_sft_examples_jsonl_hash!r}"
        )
    if observed_examples_hash != source_manifest.positive_sft_examples_jsonl_hash:
        raise ValueError(
            "Source positive-SFT export manifest does not match its examples JSONL"
        )
    examples = load_positive_sft_example_records_jsonl(source_examples_path)
    _validate_source_example_counts(source_manifest, examples)
    if len(examples) != len(materializations):
        raise ValueError(
            "Positive-SFT materialization count does not equal source example count"
        )

    selections: list[PositiveSFTEfficiencyReviewSelection] = []
    for record_index, (example, materialization) in enumerate(
        zip(examples, materializations, strict=True)
    ):
        if materialization.source_positive_sft_example_id != example.example_id:
            raise ValueError(
                "Positive-SFT materialization source order/id mismatch; "
                f"record_index={record_index}"
            )
        expected_source_hash = hash_json(example.model_dump(mode="json"))
        if (
            materialization.source_positive_sft_example_record_hash
            != expected_source_hash
        ):
            raise ValueError(
                "Positive-SFT materialization source record hash mismatch; "
                f"record_index={record_index}"
            )
        if not isinstance(
            materialization,
            CompletedPositiveSFTTrainingMaterializationRecord,
        ):
            raise ValueError(
                "Positive-SFT efficiency review source was not completed; "
                f"record_index={record_index}"
            )
        selections.append(
            PositiveSFTEfficiencyReviewSelection(
                materialization_artifact_dir=materialization_dir,
                materialization=materialization,
                source_export_artifact_dir=source_export_dir,
                source_example=example,
            )
        )

    return (
        PositiveSFTTrainingMaterializationArtifactRef(
            artifact_dir=str(materialization_dir),
            manifest_hash=hash_file(manifest_path),
            materializations_jsonl_hash=observed_records_hash,
        ),
        tuple(selections),
    )


def _validate_materialization_counts(
    manifest: PositiveSFTTrainingMaterializationManifest,
    records: Sequence[PositiveSFTTrainingMaterializationRecord],
) -> None:
    if len(records) != manifest.record_count:
        raise ValueError(
            "Positive-SFT materialization record count mismatch: "
            f"{len(records)} != {manifest.record_count}"
        )
    completed_count = sum(record.status == "completed" for record in records)
    failed_count = len(records) - completed_count
    sequence_length_exceeded_count = sum(
        record.status == "failed" and record.failure_kind == "sequence_length_exceeded"
        for record in records
    )
    materialization_error_count = sum(
        record.status == "failed" and record.failure_kind == "materialization_error"
        for record in records
    )
    observed = (
        completed_count,
        failed_count,
        sequence_length_exceeded_count,
        materialization_error_count,
    )
    expected = (
        manifest.completed_count,
        manifest.failed_count,
        manifest.sequence_length_exceeded_count,
        manifest.materialization_error_count,
    )
    if observed != expected:
        raise ValueError(
            "Positive-SFT materialization manifest counts do not match records"
        )


def _validate_source_example_counts(
    manifest: PositiveSFTExportManifest,
    examples: Sequence[PositiveSFTExampleRecord],
) -> None:
    if len(examples) != manifest.record_count:
        raise ValueError(
            "Positive-SFT source example count mismatch: "
            f"{len(examples)} != {manifest.record_count}"
        )
    original_count = sum(
        example.source_provenance.source_type == "original" for example in examples
    )
    repaired_count = len(examples) - original_count
    if (
        original_count,
        repaired_count,
    ) != (
        manifest.original_record_count,
        manifest.repaired_record_count,
    ):
        raise ValueError("Positive-SFT source type counts do not match export manifest")


def _index_reviews(
    reviews: Sequence[PositiveSFTEfficiencyReviewRecord],
) -> dict[str, PositiveSFTEfficiencyReviewRecord]:
    example_ids = [review.source_positive_sft_example_id for review in reviews]
    duplicates = sorted(
        example_id for example_id, count in Counter(example_ids).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            "Duplicate positive-SFT efficiency review source examples: "
            + ", ".join(duplicates)
        )
    return {review.source_positive_sft_example_id: review for review in reviews}


def _index_selections(
    selections: Sequence[PositiveSFTEfficiencyReviewSelection],
) -> dict[str, PositiveSFTEfficiencyReviewSelection]:
    example_ids = [selection.source_example.example_id for selection in selections]
    duplicates = sorted(
        example_id for example_id, count in Counter(example_ids).items() if count > 1
    )
    if duplicates:
        raise ValueError(
            "Duplicate positive-SFT efficiency review selections: "
            + ", ".join(duplicates)
        )
    return {selection.source_example.example_id: selection for selection in selections}


def _resolve_pinned_artifact_dir(owner_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = owner_dir / path
    return path.resolve()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
