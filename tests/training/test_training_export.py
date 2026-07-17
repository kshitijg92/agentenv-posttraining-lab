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
from agentenv.training.candidates.export import (
    export_training_candidate_records,
    load_training_candidate_export_artifact,
)
from agentenv.training.candidates.schema import (
    TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION,
)
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


def test_export_training_candidate_records_writes_pending_review_artifact(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )

    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
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
    assert manifest.training_authorization == "not_authorized"
    assert manifest.trajectory_record_schema_version == TRAJECTORY_RECORD_SCHEMA_VERSION
    assert manifest.trajectory_review_schema_version == TRAJECTORY_REVIEW_SCHEMA_VERSION
    assert (
        manifest.training_candidate_record_schema_version
        == TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
    )
    assert manifest.record_count == 1
    assert manifest.analysis_eligible_count == 1
    assert manifest.positive_sft_review_eligible_count == 0
    assert manifest.negative_example_eligible_count == 0
    assert manifest.preference_pairing_eligible_count == 0
    assert manifest.any_objective_use_eligible_count == 0
    assert manifest.analysis_only_count == 1
    assert manifest.fully_ineligible_count == 0
    assert manifest.artifacts == {
        "training_candidates": "training_candidates.jsonl",
    }

    assert len(export.records) == 1
    assert export.records[0].content_eligibility.is_analysis_only
    assert (export.out_dir / "training_candidates.jsonl").is_file()


def test_export_training_candidate_records_keeps_accepted_controls_analysis_only(
    tmp_path: Path,
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
    )

    assert export.manifest.record_count == 1
    assert export.manifest.analysis_eligible_count == 1
    assert export.manifest.positive_sft_review_eligible_count == 0
    assert export.manifest.negative_example_eligible_count == 0
    assert export.manifest.preference_pairing_eligible_count == 0
    assert export.manifest.any_objective_use_eligible_count == 0
    assert export.manifest.analysis_only_count == 1
    assert export.manifest.fully_ineligible_count == 0
    assert export.records[0].content_eligibility.is_analysis_only


def test_load_training_candidate_export_rejects_jsonl_hash_mismatch(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
    )
    candidates_path = export.out_dir / export.manifest.artifacts["training_candidates"]
    candidates_path.write_text(candidates_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Training candidate JSONL hash mismatch"):
        load_training_candidate_export_artifact(export.out_dir)


def test_load_training_candidate_export_rejects_summary_count_mismatch(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
    )
    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["analysis_eligible_count"] = 0
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ValueError,
        match="Training candidate manifest analysis_eligible_count mismatch",
    ):
        load_training_candidate_export_artifact(export.out_dir)


def test_load_training_candidate_export_rejects_rehashed_eligibility_tamper(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
    )
    candidates_path = export.out_dir / export.manifest.artifacts["training_candidates"]
    candidate = json.loads(candidates_path.read_text())
    candidate["content_eligibility"]["analysis_reason"] = "tampered decision"
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


def test_training_candidate_manifest_requires_non_authorized_status(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
    )
    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    del manifest["training_authorization"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValidationError, match="training_authorization"):
        load_training_candidate_export_artifact(export.out_dir)


def test_training_candidate_manifest_cannot_claim_training_authorization(
    tmp_path: Path,
) -> None:
    trajectory_export_dir, review_dir, _review_artifact = build_review_fixture(
        tmp_path,
        policy="agent-happy",
    )
    export = export_training_candidate_records(
        trajectory_export_dir,
        review_dir,
        tmp_path / "training-candidates",
    )
    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["training_authorization"] = "authorized"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(ValidationError, match="Input should be 'not_authorized'"):
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
