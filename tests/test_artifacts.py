import json

from agentenv.artifacts import ArtifactType


def test_artifact_type_values_are_stable_json_strings() -> None:
    assert ArtifactType.SCORER_ATTEMPT == "scorer_attempt"
    assert ArtifactType.AGENT_ATTEMPT == "agent_attempt"
    assert ArtifactType.EVAL_RUN == "eval_run"
    assert ArtifactType.EVAL_SUITE == "eval_suite"
    assert ArtifactType.CONTROL_CALIBRATION == "control_calibration"
    assert ArtifactType.REPLAY_RUN == "replay_run"
    assert ArtifactType.TRAJECTORY_EXPORT == "trajectory_export"
    assert ArtifactType.TRAJECTORY_REVIEW == "trajectory_review"
    assert ArtifactType.TRAINING_CANDIDATE_EXPORT == "training_candidate_export"
    assert (
        ArtifactType.TRAINING_CANDIDATE_REPAIR_EXPORT
        == "training_candidate_repair_export"
    )
    assert (
        ArtifactType.TRAINING_CANDIDATE_REPAIR_REVIEW
        == "training_candidate_repair_review"
    )
    assert ArtifactType.POSITIVE_SFT_REVIEW == "positive_sft_review"
    assert ArtifactType.POSITIVE_SFT_EXPORT == "positive_sft_export"
    assert (
        ArtifactType.POSITIVE_SFT_TRAINING_MATERIALIZATION
        == "positive_sft_training_materialization"
    )
    assert ArtifactType.SCORER_AUDIT == "scorer_audit"
    assert ArtifactType.AGENT_TASK_AUDIT == "agent_task_audit"
    assert ArtifactType.HARNESS_AUDIT == "harness_audit"
    assert ArtifactType.REWARD_HACK_AUDIT == "reward_hack_audit"
    assert json.dumps({"artifact_type": ArtifactType.EVAL_RUN}) == (
        '{"artifact_type": "eval_run"}'
    )
