import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION,
    load_training_candidate_export_manifest,
)
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.export import (
    export_training_candidate_records,
    load_training_candidate_export_artifact,
)
from agentenv.training.schema import TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
from agentenv.trajectories.export import (
    export_trajectory_records_from_eval_artifact,
    hash_file,
)
from agentenv.trajectories.review import (
    TrajectoryReviewArtifact,
    initialize_trajectory_review_artifact,
    write_trajectory_review_records_jsonl,
)
from agentenv.trajectories.schema import (
    TRAJECTORY_RECORD_SCHEMA_VERSION,
    TRAJECTORY_REVIEW_SCHEMA_VERSION,
    ReviewDecision,
    TrajectoryReviewRecord,
)


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
HARNESS_AUDIT_DIR = Path("/unit/harness-audit")
CONTROL_CALIBRATION_DIR = Path("/unit/control-calibration")


def test_export_training_candidate_records_writes_pending_review_artifact(
    tmp_path: Path,
    stub_training_export_gates,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )

    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )

    manifest = load_training_candidate_export_manifest(
        export.out_dir / MANIFEST_FILENAME
    )
    assert manifest.artifact_type == "training_candidate_export"
    assert (
        manifest.artifact_schema_version
        == TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION
    )
    assert manifest.source_trajectory_export_manifest_hash.startswith("xxh64:")
    assert manifest.source_trajectories_jsonl_hash.startswith("xxh64:")
    assert manifest.source_review_manifest_hash.startswith("xxh64:")
    assert manifest.source_reviews_jsonl_hash.startswith("xxh64:")
    assert manifest.harness_audit_gate == (
        stub_training_export_gates.harness_audit_gate
    )
    assert manifest.control_calibration_gate == (
        stub_training_export_gates.control_calibration_gate
    )
    assert manifest.trajectory_record_schema_version == TRAJECTORY_RECORD_SCHEMA_VERSION
    assert manifest.trajectory_review_schema_version == TRAJECTORY_REVIEW_SCHEMA_VERSION
    assert (
        manifest.training_candidate_record_schema_version
        == TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
    )
    assert manifest.record_count == 1
    assert manifest.analysis_allowed_count == 1
    assert manifest.positive_sft_allowed_count == 0
    assert manifest.negative_example_allowed_count == 0
    assert manifest.preference_data_allowed_count == 0
    assert manifest.trainable_count == 0
    assert manifest.analysis_only_count == 1
    assert manifest.not_trainable_count == 0
    assert manifest.artifacts == {
        "training_candidates": "training_candidates.jsonl",
    }

    assert len(export.records) == 1
    assert export.records[0].training_eligibility.is_analysis_only
    assert (export.out_dir / "training_candidates.jsonl").is_file()


def test_export_training_candidate_records_keeps_accepted_controls_analysis_only(
    tmp_path: Path,
    stub_training_export_gates,
) -> None:
    trajectory_export_dir, review_dir, review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    write_single_review_decision(review_artifact, "accepted")

    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )

    assert export.manifest.record_count == 1
    assert export.manifest.analysis_allowed_count == 1
    assert export.manifest.positive_sft_allowed_count == 0
    assert export.manifest.negative_example_allowed_count == 0
    assert export.manifest.preference_data_allowed_count == 0
    assert export.manifest.trainable_count == 0
    assert export.manifest.analysis_only_count == 1
    assert export.manifest.not_trainable_count == 0
    assert export.records[0].training_eligibility.is_analysis_only


def test_load_training_candidate_export_rejects_jsonl_hash_mismatch(
    tmp_path: Path,
    stub_training_export_gates,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )
    candidates_path = export.out_dir / export.manifest.artifacts["training_candidates"]
    candidates_path.write_text(candidates_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Training candidate JSONL hash mismatch"):
        load_training_candidate_export_artifact(export.out_dir)


def test_load_training_candidate_export_rejects_summary_count_mismatch(
    tmp_path: Path,
    stub_training_export_gates,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )
    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["analysis_allowed_count"] = 0
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ValueError,
        match="Training candidate manifest analysis_allowed_count mismatch",
    ):
        load_training_candidate_export_artifact(export.out_dir)


def test_load_training_candidate_export_rejects_rehashed_eligibility_tamper(
    tmp_path: Path,
    stub_training_export_gates,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )
    candidates_path = export.out_dir / export.manifest.artifacts["training_candidates"]
    candidate = json.loads(candidates_path.read_text())
    candidate["training_eligibility"]["analysis_reason"] = "tampered decision"
    candidates_path.write_text(json.dumps(candidate, sort_keys=True) + "\n")

    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["training_candidates_jsonl_hash"] = hash_file(candidates_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ValueError,
        match="do not match eligibility recomputed from their pinned trajectories",
    ):
        load_training_candidate_export_artifact(export.out_dir)


def test_training_candidate_manifest_requires_both_trust_gates(
    tmp_path: Path,
    stub_training_export_gates,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )
    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    del manifest["harness_audit_gate"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValidationError, match="harness_audit_gate"):
        load_training_candidate_export_artifact(export.out_dir)


def test_training_candidate_manifest_requires_one_gate_runtime(
    tmp_path: Path,
    stub_training_export_gates,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )
    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["control_calibration_gate"]["harness_runtime_hash"] = (
        "xxh64:ffffffffffffffff"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValidationError, match="must use the same harness runtime"):
        load_training_candidate_export_artifact(export.out_dir)


def build_review_fixture(
    tmp_path: Path,
    *,
    policy: str,
) -> tuple[Path, Path, TrajectoryReviewArtifact]:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        policy,
        tmp_path / "eval-run",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        tmp_path / "trajectory-export",
    )
    review_artifact = initialize_trajectory_review_artifact(
        trajectory_export.out_dir,
        tmp_path / "trajectory-review",
    )
    return trajectory_export.out_dir, review_artifact.out_dir, review_artifact


def write_single_review_decision(
    review_artifact: TrajectoryReviewArtifact,
    decision: ReviewDecision,
) -> None:
    review = build_reviewed_record(review_artifact.reviews[0], decision)
    write_trajectory_review_records_jsonl(
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"],
        (review,),
    )


def build_reviewed_record(
    review: TrajectoryReviewRecord,
    decision: ReviewDecision,
) -> TrajectoryReviewRecord:
    return review.model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "kshitij",
            "review_decision": decision,
        }
    )
