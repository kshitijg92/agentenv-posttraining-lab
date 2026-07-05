from pathlib import Path

import pytest

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION,
    load_trajectory_review_manifest,
)
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.trajectories.export import export_trajectory_records_from_eval_artifact
from agentenv.trajectories.review import (
    initialize_trajectory_review_artifact,
    load_trajectory_review_artifact,
)
from agentenv.trajectories.schema import TRAJECTORY_REVIEW_SCHEMA_VERSION


SCORER_CONTROL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")


def test_initialize_trajectory_review_artifact_writes_pending_review_rows(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        SCORER_CONTROL_CONFIG,
        "oracle",
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

    manifest = load_trajectory_review_manifest(
        review_artifact.out_dir / MANIFEST_FILENAME
    )
    assert manifest.artifact_type == "trajectory_review"
    assert manifest.artifact_schema_version == TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION
    assert manifest.source_artifact_type == "trajectory_export"
    assert manifest.source_artifact_schema_version == "trajectory_export_artifact_v0"
    assert manifest.source_eval_run_id == eval_run.eval_run_id
    assert manifest.source_eval_suite_id is None
    assert manifest.source_manifest_hash.startswith("xxh64:")
    assert (
        manifest.source_trajectories_jsonl_hash
        == trajectory_export.manifest.trajectories_jsonl_hash
    )
    assert manifest.trajectory_review_schema_version == TRAJECTORY_REVIEW_SCHEMA_VERSION
    assert manifest.record_count == trajectory_export.manifest.record_count
    assert manifest.artifacts == {
        "reviews": "reviews.jsonl",
        "review_queue": "review_queue.md",
    }

    assert len(review_artifact.reviews) == len(trajectory_export.records)
    review = review_artifact.reviews[0]
    trajectory = trajectory_export.records[0]
    assert review.trajectory_id == trajectory.identity.trajectory_id
    assert review.eval_attempt_id == trajectory.identity.eval_attempt_id
    assert review.task_id == trajectory.identity.task_id
    assert review.policy_id == trajectory.identity.policy_id
    assert review.review_status == "not_reviewed"
    assert review.review_id is None
    assert review.reviewer_id is None
    assert review.review_decision is None

    queue = (review_artifact.out_dir / manifest.artifacts["review_queue"]).read_text()
    assert "# Trajectory Review Queue" in queue
    assert trajectory.identity.trajectory_id in queue
    assert "Pending review row" in queue


def test_load_trajectory_review_artifact_rejects_record_count_mismatch(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        SCORER_CONTROL_CONFIG,
        "oracle",
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
    reviews_path = (
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"]
    )
    reviews_path.write_text("")

    with pytest.raises(ValueError, match="Trajectory review record count mismatch"):
        load_trajectory_review_artifact(review_artifact.out_dir)
