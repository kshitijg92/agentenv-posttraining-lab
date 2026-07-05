import json
from pathlib import Path

import pytest

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION,
    load_trajectory_review_manifest,
)
from agentenv.orchestrators.eval_run import (
    run_eval_config,
    run_eval_config_all_policies,
)
from agentenv.trajectories.export import export_trajectory_records_from_eval_artifact
from agentenv.trajectories.review import (
    initialize_trajectory_review_artifact,
    load_trajectory_review_artifact,
    validate_trajectory_review_artifact,
    write_trajectory_review_records_jsonl,
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


def test_validate_trajectory_review_artifact_accepts_pending_reviews(
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

    validation = validate_trajectory_review_artifact(
        trajectory_export.out_dir,
        review_artifact.out_dir,
    )

    assert validation.record_count == 1
    assert validation.review_status_counts == {"not_reviewed": 1, "reviewed": 0}
    assert validation.review_decision_counts == {
        "accepted": 0,
        "rejected": 0,
        "needs_followup": 0,
    }


def test_validate_trajectory_review_artifact_counts_reviewed_decisions(
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
    reviewed_record = review_artifact.reviews[0].model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "kshitij",
            "review_decision": "accepted",
        }
    )
    write_trajectory_review_records_jsonl(
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"],
        (reviewed_record,),
    )

    validation = validate_trajectory_review_artifact(
        trajectory_export.out_dir,
        review_artifact.out_dir,
    )

    assert validation.review_status_counts == {"not_reviewed": 0, "reviewed": 1}
    assert validation.review_decision_counts == {
        "accepted": 1,
        "rejected": 0,
        "needs_followup": 0,
    }


def test_validate_trajectory_review_artifact_rejects_source_manifest_drift(
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
    source_manifest_path = trajectory_export.out_dir / MANIFEST_FILENAME
    source_manifest = json.loads(source_manifest_path.read_text())
    source_manifest["created_at"] = "2099-01-01T00:00:00Z"
    source_manifest_path.write_text(json.dumps(source_manifest, sort_keys=True) + "\n")

    with pytest.raises(
        ValueError,
        match="Trajectory review manifest source_manifest_hash mismatch",
    ):
        validate_trajectory_review_artifact(
            trajectory_export.out_dir,
            review_artifact.out_dir,
        )


def test_validate_trajectory_review_artifact_rejects_identity_mismatch(
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
    mismatched_record = review_artifact.reviews[0].model_copy(
        update={"task_id": "other_task"}
    )
    write_trajectory_review_records_jsonl(
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"],
        (mismatched_record,),
    )

    with pytest.raises(ValueError, match="task_id mismatch"):
        validate_trajectory_review_artifact(
            trajectory_export.out_dir,
            review_artifact.out_dir,
        )


def test_validate_trajectory_review_artifact_rejects_duplicate_review_rows(
    tmp_path: Path,
) -> None:
    eval_suite = run_eval_config_all_policies(
        SCORER_CONTROL_CONFIG,
        tmp_path / "eval-suite",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_suite.out_dir,
        tmp_path / "trajectory-export",
    )
    review_artifact = initialize_trajectory_review_artifact(
        trajectory_export.out_dir,
        tmp_path / "trajectory-review",
    )
    duplicate_reviews = (
        review_artifact.reviews[0],
        review_artifact.reviews[0],
        review_artifact.reviews[2],
    )
    write_trajectory_review_records_jsonl(
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"],
        duplicate_reviews,
    )

    with pytest.raises(ValueError, match="duplicate trajectory_id"):
        validate_trajectory_review_artifact(
            trajectory_export.out_dir,
            review_artifact.out_dir,
        )
