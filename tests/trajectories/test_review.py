import json
from pathlib import Path

import pytest

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION,
    load_trajectory_export_manifest,
    load_trajectory_review_manifest,
)
from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.orchestrators.eval_run import (
    run_eval_config,
    run_eval_config_all_policies,
)
from agentenv.trajectories.builder import build_trajectory_record_from_eval_attempt
from agentenv.trajectories.export import (
    export_trajectory_records_from_eval_artifact,
    hash_file,
    write_trajectory_records_jsonl,
)
from agentenv.trajectories.review import (
    build_initial_review_record,
    initialize_trajectory_review_artifact,
    load_trajectory_review_artifact,
    validate_trajectory_review_artifact,
    validate_review_records_match_trajectories,
    write_trajectory_review_records_jsonl,
)
from agentenv.trajectories.schema import (
    TRAJECTORY_REVIEW_SCHEMA_VERSION,
    TrajectoryRecord,
)


SCORER_CONTROL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")
AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")


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
    assert review.reward_hack_review is None

    queue = (review_artifact.out_dir / manifest.artifacts["review_queue"]).read_text()
    assert "# Trajectory Review Queue" in queue
    assert "Agent model trajectory count: `0`" in queue
    assert "Control trajectory count: `1`" in queue
    assert "## Agent Model Run Trajectories" in queue
    assert "No trajectories in this section." in queue
    assert "## Control Trajectories" in queue
    assert trajectory.identity.trajectory_id in queue
    assert "- candidate_patch_empty: `null`" in queue
    assert "- policy_type: `scorer_control_patch`" in queue
    assert "- split: `practice`" in queue
    assert "- orchestration_failure: `False`" in queue
    assert "- reward_hack_evaluation_status: `complete`" in queue
    assert "- reward_hack_finding_classification: `not_detected`" in queue
    assert "- reward_hack_detected_checks: `[]`" in queue
    assert "positive_sft_review_eligible" not in queue
    assert "preference_pairing_eligible" not in queue
    assert "Review row" in queue


def test_ambiguous_detection_initializes_pending_reward_hack_review(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "eval-run",
    )
    trajectory = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )
    payload = trajectory.model_dump(mode="json")
    payload["reward_hack_detection"].update(
        {
            "evaluation_status": "complete",
            "finding_classification": "ambiguous",
            "check_results": [
                {
                    "exploit_check_id": "public_test_only_pass.submitted_patch_text",
                    "exploit_classification": "public_test_only_pass",
                    "check_status": "detected",
                    "finding_classification": "ambiguous",
                    "evidence_artifacts": ["candidate_patch", "attempt_json"],
                    "error_class": None,
                    "error_message": None,
                }
            ],
        }
    )
    ambiguous_trajectory = TrajectoryRecord.model_validate(payload)

    review = build_initial_review_record(ambiguous_trajectory)

    assert review.reward_hack_review is not None
    assert review.reward_hack_review.review_status == "not_reviewed"
    assert review.reward_hack_review.review_decision is None

    missing_reward_hack_review = review.model_copy(update={"reward_hack_review": None})
    with pytest.raises(
        ValueError,
        match="requires reward_hack_review for an ambiguous reward-hack finding",
    ):
        validate_review_records_match_trajectories(
            (missing_reward_hack_review,),
            (ambiguous_trajectory,),
        )


def test_initialize_trajectory_review_queue_groups_agent_model_and_control_records(
    tmp_path: Path,
) -> None:
    eval_suite = run_eval_config_all_policies(
        AGENT_CONTROL_CONFIG,
        tmp_path / "eval-suite",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_suite.out_dir,
        tmp_path / "trajectory-export",
    )
    agent_model_record = build_agent_model_trajectory_record(
        trajectory_export.records[0]
    )
    records = (agent_model_record, *trajectory_export.records[1:])
    rewrite_trajectory_export_records(trajectory_export.out_dir, records)

    review_artifact = initialize_trajectory_review_artifact(
        trajectory_export.out_dir,
        tmp_path / "trajectory-review",
    )

    queue = (
        review_artifact.out_dir / review_artifact.manifest.artifacts["review_queue"]
    ).read_text()
    assert len(review_artifact.reviews) == len(records)
    assert "Agent model trajectory count: `1`" in queue
    assert f"Control trajectory count: `{len(records) - 1}`" in queue
    assert "## Agent Model Run Trajectories" in queue
    assert "## Control Trajectories" in queue
    assert agent_model_record.identity.trajectory_id in queue
    assert "- candidate_patch_empty: `False`" in queue
    assert "Review row" in queue
    for control_record in records[1:]:
        assert control_record.identity.trajectory_id in queue


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


def build_agent_model_trajectory_record(
    trajectory: TrajectoryRecord,
) -> TrajectoryRecord:
    payload = trajectory.model_dump(mode="json")
    payload["identity"]["policy_id"] = "local-model"
    payload["policy"] = {
        "policy_id": "local-model",
        "policy_name": "local-model",
        "policy_spec": {
            "type": AGENT_MODEL_POLICY_TYPE,
            "model_config": "configs/models/local_model.yaml",
            "decoding_config": "configs/decoding/local_model.yaml",
            "attempts": 1,
            "replay": {"repeats": 0},
        },
    }
    return type(trajectory).model_validate(payload)


def rewrite_trajectory_export_records(
    trajectory_export_dir: Path,
    records: tuple[TrajectoryRecord, ...],
) -> None:
    trajectories_path = trajectory_export_dir / "trajectories.jsonl"
    write_trajectory_records_jsonl(trajectories_path, list(records))
    manifest = load_trajectory_export_manifest(
        trajectory_export_dir / MANIFEST_FILENAME
    )
    updated_manifest = manifest.model_copy(
        update={
            "record_count": len(records),
            "trajectories_jsonl_hash": hash_file(trajectories_path),
        }
    )
    (trajectory_export_dir / MANIFEST_FILENAME).write_text(
        json.dumps(
            updated_manifest.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
