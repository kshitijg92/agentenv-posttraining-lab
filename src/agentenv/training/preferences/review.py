from __future__ import annotations

import json
import re
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
    PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_SCHEMA_VERSION,
    PreferenceAdjudicationReviewManifest,
    load_preference_adjudication_review_manifest,
)
from agentenv.hashing import hash_file
from agentenv.training.preferences.adjudication import (
    build_pending_preference_adjudication_records,
    validate_preference_adjudication_records,
)
from agentenv.training.preferences.comparison_export import (
    PreferenceComparisonExport,
    load_preference_comparison_export_artifact,
)
from agentenv.training.preferences.schema import (
    PREFERENCE_ADJUDICATION_RECORD_SCHEMA_VERSION,
    PreferenceAdjudicationRecord,
    PreferenceComparisonCandidateRecord,
    PreferenceRubricProvenance,
)
from agentenv.trajectories.schema import ArtifactRef


_RUBRIC_METADATA_FIELDS = (
    "rubric_id",
    "rubric_version",
    "adjudication_scope",
)


@dataclass(frozen=True)
class PreferenceAdjudicationReviewArtifact:
    out_dir: Path
    manifest: PreferenceAdjudicationReviewManifest
    adjudications: tuple[PreferenceAdjudicationRecord, ...]


@dataclass(frozen=True)
class PreferenceAdjudicationReviewValidation:
    source_comparison_export: PreferenceComparisonExport
    review_artifact: PreferenceAdjudicationReviewArtifact
    review_status_counts: dict[str, int]
    review_decision_counts: dict[str, int]


def initialize_preference_adjudication_review_artifact(
    comparison_export_dir: Path,
    rubric_path: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> PreferenceAdjudicationReviewArtifact:
    comparison_export = load_preference_comparison_export_artifact(
        comparison_export_dir
    )
    rubric_bytes = rubric_path.resolve().read_bytes()
    rubric_metadata = _parse_rubric_metadata(rubric_bytes.decode("utf-8"))

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    rubric_artifact_path = resolve_relative_artifact_ref(
        out_dir,
        PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS["rubric"],
    )
    rubric_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    rubric_artifact_path.write_bytes(rubric_bytes)
    rubric_provenance = PreferenceRubricProvenance.model_validate(
        {
            **rubric_metadata,
            "rubric_ref": ArtifactRef(
                path=PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS["rubric"],
                content_hash=hash_file(rubric_artifact_path),
            ).model_dump(mode="json"),
        }
    )
    adjudications = build_pending_preference_adjudication_records(
        comparison_export.records,
        rubric_provenance=rubric_provenance,
    )
    adjudications_path = resolve_relative_artifact_ref(
        out_dir,
        PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS["adjudications"],
    )
    review_queue_path = resolve_relative_artifact_ref(
        out_dir,
        PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS["review_queue"],
    )
    write_preference_adjudication_records_jsonl(
        adjudications_path,
        adjudications,
    )
    review_queue_path.write_text(
        render_preference_adjudication_review_queue(
            comparison_export,
            adjudications,
            rubric_provenance=rubric_provenance,
        )
    )
    manifest = build_preference_adjudication_review_manifest(
        out_dir=out_dir,
        comparison_export=comparison_export,
        rubric_provenance=rubric_provenance,
        record_count=len(adjudications),
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_preference_adjudication_review_artifact(out_dir)


def load_preference_adjudication_review_artifact(
    review_dir: Path,
) -> PreferenceAdjudicationReviewArtifact:
    review_dir = review_dir.resolve()
    manifest = load_preference_adjudication_review_manifest(
        review_dir / MANIFEST_FILENAME
    )
    _validate_pinned_rubric(review_dir, manifest.rubric_provenance)

    review_queue_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["review_queue"],
    )
    if not review_queue_path.is_file():
        raise ValueError(
            f"Missing preference adjudication review queue at {review_queue_path}"
        )
    adjudications_path = resolve_relative_artifact_ref(
        review_dir,
        manifest.artifacts["adjudications"],
    )
    adjudications = load_preference_adjudication_records_jsonl(adjudications_path)
    if len(adjudications) != manifest.record_count:
        raise ValueError(
            "Preference adjudication record count mismatch: "
            f"{len(adjudications)} != {manifest.record_count}"
        )
    return PreferenceAdjudicationReviewArtifact(
        out_dir=review_dir,
        manifest=manifest,
        adjudications=adjudications,
    )


def validate_preference_adjudication_review_artifact(
    review_dir: Path,
) -> PreferenceAdjudicationReviewValidation:
    review_artifact = load_preference_adjudication_review_artifact(review_dir)
    source_ref = review_artifact.manifest.source_preference_comparison_export
    source_dir = _resolve_pinned_artifact_dir(
        review_artifact.out_dir,
        source_ref.artifact_dir,
    )
    source_manifest_hash = hash_file(source_dir / MANIFEST_FILENAME)
    if source_manifest_hash != source_ref.manifest_hash:
        raise ValueError(
            "Preference adjudication source comparison manifest hash mismatch: "
            f"{source_manifest_hash!r} != {source_ref.manifest_hash!r}"
        )
    comparison_export = load_preference_comparison_export_artifact(source_dir)
    if (
        comparison_export.manifest.comparison_candidates_jsonl_hash
        != source_ref.comparison_candidates_jsonl_hash
    ):
        raise ValueError(
            "Preference adjudication source comparison candidate hash mismatch"
        )
    if len(comparison_export.records) != review_artifact.manifest.record_count:
        raise ValueError(
            "Preference adjudication review count does not match its source "
            "comparison export"
        )
    validate_preference_adjudication_records(
        review_artifact.adjudications,
        comparison_export.records,
        rubric_provenance=review_artifact.manifest.rubric_provenance,
    )
    return PreferenceAdjudicationReviewValidation(
        source_comparison_export=comparison_export,
        review_artifact=review_artifact,
        review_status_counts=count_preference_review_statuses(
            review_artifact.adjudications
        ),
        review_decision_counts=count_preference_review_decisions(
            review_artifact.adjudications
        ),
    )


def write_preference_adjudication_records_jsonl(
    path: Path,
    records: tuple[PreferenceAdjudicationRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_preference_adjudication_records_jsonl(
    path: Path,
) -> tuple[PreferenceAdjudicationRecord, ...]:
    records: list[PreferenceAdjudicationRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(PreferenceAdjudicationRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"PreferenceAdjudicationRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_preference_adjudication_review_manifest(
    *,
    out_dir: Path,
    comparison_export: PreferenceComparisonExport,
    rubric_provenance: PreferenceRubricProvenance,
    record_count: int,
) -> PreferenceAdjudicationReviewManifest:
    for artifact_ref in PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS.values():
        resolve_relative_artifact_ref(out_dir, artifact_ref)
    source_manifest_path = comparison_export.out_dir / MANIFEST_FILENAME
    return PreferenceAdjudicationReviewManifest.model_validate(
        {
            "artifact_type": ArtifactType.PREFERENCE_ADJUDICATION_REVIEW,
            "artifact_schema_version": (
                PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "source_preference_comparison_export": {
                "artifact_dir": str(comparison_export.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
                "comparison_candidates_jsonl_hash": (
                    comparison_export.manifest.comparison_candidates_jsonl_hash
                ),
            },
            "training_authorization": "not_authorized",
            "preference_adjudication_record_schema_version": (
                PREFERENCE_ADJUDICATION_RECORD_SCHEMA_VERSION
            ),
            "rubric_provenance": rubric_provenance.model_dump(mode="json"),
            "record_count": record_count,
            "artifacts": dict(PREFERENCE_ADJUDICATION_REVIEW_ARTIFACT_REFS),
        }
    )


def render_preference_adjudication_review_queue(
    comparison_export: PreferenceComparisonExport,
    adjudications: tuple[PreferenceAdjudicationRecord, ...],
    *,
    rubric_provenance: PreferenceRubricProvenance,
) -> str:
    adjudications_by_id = {
        record.source.comparison_candidate_id: record for record in adjudications
    }
    lines = [
        "# Preference Adjudication Review Queue",
        "",
        f"Source comparison export: `{comparison_export.out_dir}`",
        f"Comparison count: `{len(comparison_export.records)}`",
        f"Rubric: `{rubric_provenance.rubric_version}`",
        "",
        "Edit `adjudications.jsonl` and keep exactly one row per comparison.",
        "Use the copied rubric; terminal task outcome is evidence, not a label.",
        "",
    ]
    for index, candidate in enumerate(comparison_export.records, start=1):
        adjudication = adjudications_by_id[candidate.comparison_candidate_id]
        lines.extend(
            [
                f"## {index}. `{candidate.comparison_candidate_id}`",
                "",
                f"- shared_context_id: `{candidate.shared_context.shared_context_id}`",
                f"- task_id: `{candidate.shared_context.task_provenance.task_id}`",
                f"- alternative_a_id: `{candidate.alternative_a.alternative_id}`",
                f"- alternative_b_id: `{candidate.alternative_b.alternative_id}`",
                "",
                "Alternative A:",
                "",
                "```json",
                json.dumps(candidate.alternative_a.assistant_content),
                "```",
                "",
                "Alternative B:",
                "",
                "```json",
                json.dumps(candidate.alternative_b.assistant_content),
                "```",
                "",
                "Rollout evidence:",
                "",
                *(
                    "- " + json.dumps(summary, sort_keys=True)
                    for summary in _render_rollout_evidence_summaries(candidate)
                ),
                "",
                "Adjudication row:",
                "",
                "```json",
                json.dumps(adjudication.model_dump(mode="json"), sort_keys=True),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def count_preference_review_statuses(
    records: tuple[PreferenceAdjudicationRecord, ...],
) -> dict[str, int]:
    counts = {"not_reviewed": 0, "reviewed": 0}
    for record in records:
        counts[record.review_status] += 1
    return counts


def count_preference_review_decisions(
    records: tuple[PreferenceAdjudicationRecord, ...],
) -> dict[str, int]:
    counts = {"preferred": 0, "tie": 0, "ambiguous": 0, "invalid": 0}
    for record in records:
        if record.review_decision is not None:
            counts[record.review_decision] += 1
    return counts


def _render_rollout_evidence_summaries(
    candidate: PreferenceComparisonCandidateRecord,
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for label, alternative in (
        ("A", candidate.alternative_a),
        ("B", candidate.alternative_b),
    ):
        for evidence in alternative.rollout_evidence:
            summaries.append(
                {
                    "alternative": label,
                    "evidence_id": evidence.evidence_id,
                    "trajectory_id": evidence.trajectory_id,
                    "eval_run_id": evidence.eval_run_id,
                    "eval_attempt_id": evidence.eval_attempt_id,
                    "assistant_message_id": evidence.assistant_message_id,
                    "continuation_message_count": evidence.continuation_message_count,
                    "prompt_loop_result_ref": (
                        evidence.source_prompt_loop_result_ref.model_dump(mode="json")
                    ),
                }
            )
    return summaries


def _parse_rubric_metadata(content: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for field_name in _RUBRIC_METADATA_FIELDS:
        matches = re.findall(
            rf"^{re.escape(field_name)}:\s*(\S+)\s*$",
            content,
            flags=re.MULTILINE,
        )
        if len(matches) != 1:
            raise ValueError(f"Preference rubric must declare exactly one {field_name}")
        metadata[field_name] = matches[0]
    return metadata


def _validate_pinned_rubric(
    review_dir: Path,
    rubric_provenance: PreferenceRubricProvenance,
) -> None:
    rubric_path = resolve_relative_artifact_ref(
        review_dir,
        rubric_provenance.rubric_ref.path,
    )
    observed_hash = hash_file(rubric_path)
    expected_hash = rubric_provenance.rubric_ref.content_hash
    if observed_hash != expected_hash:
        raise ValueError(
            "Preference adjudication rubric hash mismatch: "
            f"{observed_hash!r} != {expected_hash!r}"
        )
    observed_metadata = _parse_rubric_metadata(rubric_path.read_text())
    expected_metadata = {
        "rubric_id": rubric_provenance.rubric_id,
        "rubric_version": rubric_provenance.rubric_version,
        "adjudication_scope": rubric_provenance.adjudication_scope,
    }
    if observed_metadata != expected_metadata:
        raise ValueError(
            "Preference adjudication rubric metadata differs from its provenance"
        )


def _resolve_pinned_artifact_dir(owner_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = owner_dir / path
    return path.resolve()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
