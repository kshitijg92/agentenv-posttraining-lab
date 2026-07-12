import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.artifacts.manifests import (
    TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS,
    TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
    TrainingCandidateRepairExportManifest,
    load_training_candidate_repair_export_manifest,
)
from agentenv.training.repair_schema import (
    TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION,
)


def _manifest_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "artifact_type": "training_candidate_repair_export",
        "artifact_schema_version": ("training_candidate_repair_export_artifact_v0"),
        "created_at": "2026-07-11T12:00:00Z",
        "source_training_candidate_export": {
            "artifact_dir": "/tmp/training_candidates",
            "manifest_hash": "xxh64:1111111111111111",
        },
        "training_candidate_repair_record_schema_version": (
            "training_candidate_repair_record_v0"
        ),
        "record_count": 3,
        "completed_count": 1,
        "cannot_complete_count": 1,
        "repair_error_count": 1,
        "repair_records_jsonl_hash": "xxh64:2222222222222222",
        "artifacts": {
            "repair_records": "repair_records.jsonl",
        },
    }
    payload.update(updates)
    return payload


def test_training_candidate_repair_manifest_accepts_pinned_source_export() -> None:
    manifest = TrainingCandidateRepairExportManifest.model_validate(_manifest_payload())

    assert (
        manifest.artifact_schema_version
        == TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION
    )
    assert (
        manifest.training_candidate_repair_record_schema_version
        == TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION
    )
    assert manifest.source_training_candidate_export.manifest_hash == (
        "xxh64:1111111111111111"
    )
    assert manifest.artifacts == TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS


def test_training_candidate_repair_manifest_allows_empty_export() -> None:
    manifest = TrainingCandidateRepairExportManifest.model_validate(
        _manifest_payload(
            record_count=0,
            completed_count=0,
            cannot_complete_count=0,
            repair_error_count=0,
        )
    )

    assert manifest.record_count == 0


def test_training_candidate_repair_manifest_requires_status_counts_to_sum() -> None:
    with pytest.raises(
        ValidationError,
        match="repair status counts must sum to record_count",
    ):
        TrainingCandidateRepairExportManifest.model_validate(
            _manifest_payload(completed_count=0)
        )


@pytest.mark.parametrize(
    ("field_name", "invalid_hash"),
    [
        ("source_training_candidate_export", "not-a-content-hash"),
        ("repair_records_jsonl_hash", "xxh64:short"),
    ],
)
def test_training_candidate_repair_manifest_requires_content_hashes(
    field_name: str,
    invalid_hash: str,
) -> None:
    payload = _manifest_payload()
    if field_name == "source_training_candidate_export":
        payload[field_name]["manifest_hash"] = invalid_hash
    else:
        payload[field_name] = invalid_hash

    with pytest.raises(ValidationError):
        TrainingCandidateRepairExportManifest.model_validate(payload)


def test_training_candidate_export_ref_rejects_duplicated_source_fields() -> None:
    payload = _manifest_payload()
    payload["source_training_candidate_export"]["training_candidates_jsonl_hash"] = (
        "xxh64:3333333333333333"
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TrainingCandidateRepairExportManifest.model_validate(payload)


@pytest.mark.parametrize(
    "artifacts",
    [
        {},
        {"repair_records": "other.jsonl"},
        {
            "repair_records": "repair_records.jsonl",
            "unexpected": "unexpected.json",
        },
    ],
)
def test_training_candidate_repair_manifest_requires_exact_artifact_map(
    artifacts: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        TrainingCandidateRepairExportManifest.model_validate(
            _manifest_payload(artifacts=artifacts)
        )


def test_load_training_candidate_repair_export_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest_payload()))

    manifest = load_training_candidate_repair_export_manifest(manifest_path)

    assert manifest.artifact_type == "training_candidate_repair_export"


def test_training_candidate_repair_manifest_rejects_wrong_artifact_identity() -> None:
    with pytest.raises(ValidationError, match="artifact_type must be"):
        TrainingCandidateRepairExportManifest.model_validate(
            _manifest_payload(artifact_type="training_candidate_export")
        )


def test_training_candidate_repair_manifest_rejects_stale_record_schema() -> None:
    with pytest.raises(
        ValidationError,
        match="Input should be 'training_candidate_repair_record_v0'",
    ):
        TrainingCandidateRepairExportManifest.model_validate(
            _manifest_payload(
                training_candidate_repair_record_schema_version=(
                    "training_candidate_repair_record_v999"
                )
            )
        )
