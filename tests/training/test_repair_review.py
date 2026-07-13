import json
from pathlib import Path

import pytest

import agentenv.training.repairs.review as repair_review_module
from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_SCHEMA_VERSION,
    TrainingCandidateRepairExportManifest,
    load_training_candidate_repair_review_manifest,
)
from agentenv.training.repairs.export import TrainingCandidateRepairExport
from agentenv.training.repairs.redundancy_repair import (
    hash_training_candidate_repair_record,
)
from agentenv.training.repairs.review import (
    initialize_training_candidate_repair_review_artifact,
    validate_training_candidate_repair_review_artifact,
    write_training_candidate_repair_review_records_jsonl,
)
from agentenv.training.repairs.schema import (
    TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION,
    TrainingCandidateRepairRecord,
    TrainingCandidateRepairReviewRecord,
)


def test_initialize_repair_review_covers_every_repair_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _source_export(tmp_path, _repair_records())
    _stub_source_loader(monkeypatch, source_export)

    artifact = initialize_training_candidate_repair_review_artifact(
        source_export.out_dir,
        tmp_path / "repair-review",
    )

    manifest = load_training_candidate_repair_review_manifest(
        artifact.out_dir / MANIFEST_FILENAME
    )
    assert manifest.artifact_type == "training_candidate_repair_review"
    assert (
        manifest.artifact_schema_version
        == TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_SCHEMA_VERSION
    )
    assert (
        manifest.training_candidate_repair_review_record_schema_version
        == TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION
    )
    assert manifest.record_count == 3
    assert [review.repair_id for review in artifact.reviews] == [
        record.repair_id for record in source_export.records
    ]
    assert [
        review.source_training_candidate_repair_record_hash
        for review in artifact.reviews
    ] == [
        hash_training_candidate_repair_record(record)
        for record in source_export.records
    ]
    assert all(review.review_status == "not_reviewed" for review in artifact.reviews)
    queue = (artifact.out_dir / manifest.artifacts["review_queue"]).read_text()
    assert "# Training Candidate Repair Review Queue" in queue
    assert "`completed`" in queue
    assert "`cannot_complete`" in queue
    assert "`repair_error`" in queue
    assert "it never authorizes training use" in queue


def test_repair_review_acceptance_of_noncompleted_outcome_is_audit_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _source_export(tmp_path, _repair_records())
    _stub_source_loader(monkeypatch, source_export)
    artifact = initialize_training_candidate_repair_review_artifact(
        source_export.out_dir,
        tmp_path / "repair-review",
    )
    reviewed = tuple(
        review.model_copy(
            update={
                "review_status": "reviewed",
                "review_id": f"review_{index:04d}",
                "reviewer_id": "reviewer",
                "review_decision": ("needs_followup" if index == 3 else "accepted"),
            }
        )
        for index, review in enumerate(artifact.reviews, start=1)
    )
    write_training_candidate_repair_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        reviewed,
    )

    validation = validate_training_candidate_repair_review_artifact(
        source_export.out_dir,
        artifact.out_dir,
    )

    assert validation.review_status_counts == {"not_reviewed": 0, "reviewed": 3}
    assert validation.review_decision_counts == {
        "accepted": 2,
        "rejected": 0,
        "needs_followup": 1,
    }
    cannot_complete_review = next(
        review
        for review in validation.review_artifact.reviews
        if review.repair_id == "repair_cannot_complete"
    )
    assert cannot_complete_review.review_decision == "accepted"
    assert (
        next(
            record
            for record in validation.source_export.records
            if record.repair_id == cannot_complete_review.repair_id
        ).repair_status
        == "cannot_complete"
    )


def test_repair_review_requires_exact_source_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _source_export(tmp_path, _repair_records())
    _stub_source_loader(monkeypatch, source_export)
    artifact = initialize_training_candidate_repair_review_artifact(
        source_export.out_dir,
        tmp_path / "repair-review",
    )
    reviews = (
        artifact.reviews[0],
        artifact.reviews[1],
        TrainingCandidateRepairReviewRecord(
            repair_id="repair_unknown",
            source_training_candidate_repair_record_hash=("xxh64:9999999999999999"),
            review_status="not_reviewed",
        ),
    )
    write_training_candidate_repair_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        reviews,
    )

    with pytest.raises(ValueError, match="missing repair_id: repair_error"):
        validate_training_candidate_repair_review_artifact(
            source_export.out_dir,
            artifact.out_dir,
        )


def test_repair_review_rejects_duplicate_repair_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _source_export(tmp_path, _repair_records())
    _stub_source_loader(monkeypatch, source_export)
    artifact = initialize_training_candidate_repair_review_artifact(
        source_export.out_dir,
        tmp_path / "repair-review",
    )
    reviews = (
        artifact.reviews[0],
        artifact.reviews[0],
        artifact.reviews[2],
    )
    write_training_candidate_repair_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        reviews,
    )

    with pytest.raises(ValueError, match="duplicate repair_id"):
        validate_training_candidate_repair_review_artifact(
            source_export.out_dir,
            artifact.out_dir,
        )


def test_repair_review_rejects_changed_source_repair_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _source_export(tmp_path, _repair_records())
    _stub_source_loader(monkeypatch, source_export)
    artifact = initialize_training_candidate_repair_review_artifact(
        source_export.out_dir,
        tmp_path / "repair-review",
    )
    reviews = (
        artifact.reviews[0].model_copy(
            update={
                "source_training_candidate_repair_record_hash": (
                    "xxh64:9999999999999999"
                )
            }
        ),
        *artifact.reviews[1:],
    )
    write_training_candidate_repair_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        reviews,
    )

    with pytest.raises(ValueError, match="source repair record hash mismatch"):
        validate_training_candidate_repair_review_artifact(
            source_export.out_dir,
            artifact.out_dir,
        )


def test_repair_review_rejects_source_manifest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _source_export(tmp_path, _repair_records())
    _stub_source_loader(monkeypatch, source_export)
    artifact = initialize_training_candidate_repair_review_artifact(
        source_export.out_dir,
        tmp_path / "repair-review",
    )
    source_manifest_path = source_export.out_dir / MANIFEST_FILENAME
    source_manifest_path.write_text(source_manifest_path.read_text() + "\n")

    with pytest.raises(ValueError, match="source manifest hash mismatch"):
        validate_training_candidate_repair_review_artifact(
            source_export.out_dir,
            artifact.out_dir,
        )


def test_repair_review_allows_empty_noop_free_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _source_export(tmp_path, ())
    _stub_source_loader(monkeypatch, source_export)

    artifact = initialize_training_candidate_repair_review_artifact(
        source_export.out_dir,
        tmp_path / "repair-review",
    )
    validation = validate_training_candidate_repair_review_artifact(
        source_export.out_dir,
        artifact.out_dir,
    )

    assert artifact.reviews == ()
    assert validation.record_count == 0
    assert validation.review_status_counts == {"not_reviewed": 0, "reviewed": 0}


def _stub_source_loader(
    monkeypatch: pytest.MonkeyPatch,
    source_export: TrainingCandidateRepairExport,
) -> None:
    def load_source(_path: Path) -> TrainingCandidateRepairExport:
        return source_export

    monkeypatch.setattr(
        repair_review_module,
        "load_training_candidate_repair_export_artifact",
        load_source,
    )


def _source_export(
    tmp_path: Path,
    records: tuple[TrainingCandidateRepairRecord, ...],
) -> TrainingCandidateRepairExport:
    out_dir = tmp_path / "repair-source"
    out_dir.mkdir()
    manifest = TrainingCandidateRepairExportManifest.model_validate(
        {
            "artifact_type": "training_candidate_repair_export",
            "artifact_schema_version": ("training_candidate_repair_export_artifact_v0"),
            "created_at": "2026-07-11T12:00:00Z",
            "source_training_candidate_export": {
                "artifact_dir": "/tmp/candidates",
                "manifest_hash": "xxh64:1111111111111111",
            },
            "training_candidate_repair_record_schema_version": (
                "training_candidate_repair_record_v0"
            ),
            "record_count": len(records),
            "completed_count": sum(
                record.repair_status == "completed" for record in records
            ),
            "cannot_complete_count": sum(
                record.repair_status == "cannot_complete" for record in records
            ),
            "repair_error_count": sum(
                record.repair_status == "repair_error" for record in records
            ),
            "repair_records_jsonl_hash": "xxh64:2222222222222222",
            "artifacts": {"repair_records": "repair_records.jsonl"},
        }
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return TrainingCandidateRepairExport(
        out_dir=out_dir.resolve(),
        manifest=manifest,
        records=records,
    )


def _repair_records() -> tuple[TrainingCandidateRepairRecord, ...]:
    return (
        TrainingCandidateRepairRecord.model_validate(
            _repair_payload("repair_completed", "completed")
        ),
        TrainingCandidateRepairRecord.model_validate(
            _repair_payload("repair_cannot_complete", "cannot_complete")
        ),
        TrainingCandidateRepairRecord.model_validate(
            _repair_payload("repair_error", "repair_error")
        ),
    )


def _repair_payload(repair_id: str, status: str) -> dict[str, object]:
    original_assessment = _assessment_payload(blocks=[_block_payload()])
    payload: dict[str, object] = {
        "repair_id": repair_id,
        "trajectory_id": "trajectory_001",
        "eval_attempt_id": "eval_attempt_001",
        "source_training_candidate_record_hash": "xxh64:3333333333333333",
        "repair_artifact_type": "transcript",
        "repair_status": status,
        "original_artifact_ref": {
            "path": "prompt_loop_result.json",
            "content_hash": "xxh64:original",
        },
        "repaired_artifact_ref": None,
        "repairer_version": "repairer_v0",
        "repairer_code_hash": "xxh64:repairer",
        "repair": {
            "repair_method": "mechanical_redundancy_deletion",
            "original_mechanical_redundancy_assessment": original_assessment,
            "after_repair_mechanical_redundancy_assessment": None,
            "cannot_complete_reason": None,
        },
        "error_class": None,
        "error_message": None,
    }
    repair = payload["repair"]
    assert isinstance(repair, dict)
    if status == "completed":
        payload["repaired_artifact_ref"] = {
            "path": f"transcripts/{repair_id}.json",
            "content_hash": "xxh64:repaired",
        }
        repair["after_repair_mechanical_redundancy_assessment"] = _assessment_payload(
            blocks=[]
        )
    elif status == "cannot_complete":
        repair["cannot_complete_reason"] = "cannot repair"
    else:
        payload["error_class"] = "RepairError"
        payload["error_message"] = "repair failed"
    return payload


def _assessment_payload(*, blocks: list[dict[str, object]]) -> dict[str, object]:
    return {
        "detector_version": "mechanical_redundancy_detector_v0",
        "detector_code_hash": "xxh64:detector",
        "evaluation_status": "complete",
        "blocks": blocks,
        "error_class": None,
        "error_message": None,
    }


def _block_payload() -> dict[str, object]:
    return {
        "tool_name": "read_file",
        "arguments_hash": "xxh64:arguments",
        "baseline_tool_call_id": "tool_call_0001",
        "redundant_tool_call_ids": ["tool_call_0002"],
        "redundant_call_count": 1,
        "stable_workspace_hash": "xxh64:workspace",
        "normalized_observation_hash": "xxh64:observation",
        "public_check_index": None,
    }
