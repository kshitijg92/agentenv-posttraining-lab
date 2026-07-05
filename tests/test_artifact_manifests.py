import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.artifacts.manifests import (
    AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION,
    EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
    EVAL_SUITE_ARTIFACT_SCHEMA_VERSION,
    REPLAY_RUN_ARTIFACT_SCHEMA_VERSION,
    SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION,
    AgentTaskRunManifest,
    ControlCalibrationManifest,
    EvalRunManifest,
    EvalSuiteManifest,
    ReplayRunManifest,
    ScorerAttemptManifest,
    TrajectoryExportManifest,
    load_agent_attempt_manifest,
    load_attempt_manifest,
    load_control_calibration_manifest,
    load_eval_artifact_manifest,
    load_eval_run_manifest,
    load_eval_suite_manifest,
    load_replay_run_manifest,
    load_replay_source_manifest,
    load_scorer_attempt_manifest,
    load_trajectory_export_manifest,
)
from agentenv.artifacts.payloads import CONTROL_FLAKE_DETECTION_SCHEMA_VERSION
from agentenv.artifacts.payloads import EVAL_TASK_HASHES_SCHEMA_VERSION


def test_root_manifest_loaders_accept_current_shapes(tmp_path: Path) -> None:
    scorer_path = _write_json(tmp_path / "scorer.json", _scorer_manifest())
    agent_path = _write_json(tmp_path / "agent.json", _agent_manifest())
    eval_run_path = _write_json(tmp_path / "eval_run.json", _eval_run_manifest())
    eval_suite_path = _write_json(tmp_path / "eval_suite.json", _eval_suite_manifest())
    control_path = _write_json(tmp_path / "control.json", _control_manifest())
    replay_path = _write_json(tmp_path / "replay.json", _replay_manifest())
    trajectory_export_path = _write_json(
        tmp_path / "trajectory_export.json",
        _trajectory_export_manifest(),
    )

    assert isinstance(load_scorer_attempt_manifest(scorer_path), ScorerAttemptManifest)
    assert isinstance(load_agent_attempt_manifest(agent_path), AgentTaskRunManifest)
    assert isinstance(load_eval_run_manifest(eval_run_path), EvalRunManifest)
    assert isinstance(load_eval_suite_manifest(eval_suite_path), EvalSuiteManifest)
    assert isinstance(
        load_control_calibration_manifest(control_path),
        ControlCalibrationManifest,
    )
    assert isinstance(load_replay_run_manifest(replay_path), ReplayRunManifest)
    assert isinstance(
        load_trajectory_export_manifest(trajectory_export_path),
        TrajectoryExportManifest,
    )

    assert isinstance(load_attempt_manifest(scorer_path), ScorerAttemptManifest)
    assert isinstance(load_attempt_manifest(agent_path), AgentTaskRunManifest)
    assert isinstance(load_eval_artifact_manifest(eval_run_path), EvalRunManifest)
    assert isinstance(load_eval_artifact_manifest(eval_suite_path), EvalSuiteManifest)
    assert isinstance(load_replay_source_manifest(eval_run_path), EvalRunManifest)
    assert isinstance(load_replay_source_manifest(agent_path), AgentTaskRunManifest)


def test_trajectory_export_manifest_rejects_missing_trajectories_ref(
    tmp_path: Path,
) -> None:
    manifest = _trajectory_export_manifest()
    manifest["artifacts"] = {}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="trajectory export manifests require"):
        load_trajectory_export_manifest(path)


def test_trajectory_export_manifest_rejects_eval_run_with_suite_id(
    tmp_path: Path,
) -> None:
    manifest = _trajectory_export_manifest()
    manifest["source_eval_suite_id"] = "eval_suite_001"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="eval_run trajectory exports cannot include source_eval_suite_id",
    ):
        load_trajectory_export_manifest(path)


def test_root_loader_rejects_wrong_artifact_type(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "manifest.json",
        {**_agent_manifest(), "artifact_type": "scorer_attempt"},
    )

    with pytest.raises(ValidationError, match="artifact_type must be"):
        load_agent_attempt_manifest(path)


def test_root_loader_rejects_wrong_artifact_schema_version(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "manifest.json",
        {**_agent_manifest(), "artifact_schema_version": "agent_attempt_artifact_v999"},
    )

    with pytest.raises(ValidationError, match="artifact_schema_version must be"):
        load_agent_attempt_manifest(path)


def test_root_loader_rejects_extra_fields(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "manifest.json",
        {**_agent_manifest(), "unexpected": True},
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_agent_attempt_manifest(path)


def test_root_loader_validation_error_includes_manifest_path(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "manifest.json",
        {**_agent_manifest(), "unexpected": True},
    )

    with pytest.raises(ValidationError, match=str(path)):
        load_agent_attempt_manifest(path)


def test_eval_run_manifest_rejects_duplicate_eval_attempt_ids(tmp_path: Path) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"] = [manifest["attempts"][0], manifest["attempts"][0]]
    manifest["attempt_count"] = 2
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="Duplicate eval_attempt_id"):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_missing_root_artifact_refs(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["artifacts"] = {}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="eval run manifests require"):
        load_eval_run_manifest(path)


def test_agent_attempt_manifest_rejects_scored_without_attempt_status(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    manifest["attempt_status"] = None
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="scored agent attempts require attempt_status",
    ):
        load_agent_attempt_manifest(path)


def test_scorer_attempt_manifest_rejects_missing_primary_artifact_ref(
    tmp_path: Path,
) -> None:
    manifest = _scorer_manifest()
    del manifest["artifacts"]["stdout"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="scorer attempt manifests require"):
        load_scorer_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_missing_primary_artifact_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    del manifest["artifacts"]["agent_task_run"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="agent task run manifests require"):
        load_agent_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_missing_decoding_config_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    del manifest["artifacts"]["decoding_config"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="agent task run manifests require"):
        load_agent_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_prompt_loop_without_task_view_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    del manifest["artifacts"]["agent_task_view"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="agent task run manifests with prompt loop results require",
    ):
        load_agent_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_scored_without_attempt_artifact_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    del manifest["artifacts"]["attempt"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="scored agent attempts require attempt artifact ref",
    ):
        load_agent_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_scored_without_candidate_patch_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    del manifest["artifacts"]["candidate_patch"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="scored agent attempts require candidate_patch artifact ref",
    ):
        load_agent_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_scored_without_prompt_loop_result_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    del manifest["artifacts"]["prompt_loop_result"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="agent task run manifests with prompt loop results require",
    ):
        load_agent_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_loop_failure_without_prompt_loop_result_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    manifest["status"] = "agent_loop_failed"
    manifest["prompt_loop_status"] = "model_error"
    manifest["attempt_status"] = None
    del manifest["artifacts"]["prompt_loop_result"]
    del manifest["artifacts"]["attempt"]
    del manifest["artifacts"]["candidate_patch"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="agent task run manifests with prompt loop results require",
    ):
        load_agent_attempt_manifest(path)


def test_attempt_manifest_rejects_escaping_artifact_map_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    manifest["artifacts"]["candidate_patch"] = "../candidate.patch"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="parent traversal"):
        load_agent_attempt_manifest(path)


def test_attempt_manifest_rejects_current_dir_artifact_map_ref(
    tmp_path: Path,
) -> None:
    manifest = _scorer_manifest()
    manifest["artifacts"]["attempt"] = "."
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="parent traversal"):
        load_scorer_attempt_manifest(path)


@pytest.mark.parametrize("artifact_ref", ["..\\outside", "C:\\tmp\\artifact.json"])
def test_attempt_manifest_rejects_windows_style_artifact_map_ref(
    tmp_path: Path,
    artifact_ref: str,
) -> None:
    manifest = _scorer_manifest()
    manifest["artifacts"]["attempt"] = artifact_ref
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="POSIX-style relative path"):
        load_scorer_attempt_manifest(path)


@pytest.mark.parametrize(
    "artifact_ref",
    ["./attempts/task_001", "attempts//task_001", "attempts/task_001/."],
)
def test_eval_run_manifest_rejects_noncanonical_artifact_dir(
    tmp_path: Path,
    artifact_ref: str,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["artifact_dir"] = artifact_ref
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="artifact ref must be canonical"):
        load_eval_run_manifest(path)


def test_agent_attempt_manifest_rejects_noncanonical_attempt_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    manifest["artifacts"]["attempt"] = "attempt/"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="artifact ref must be canonical"):
        load_agent_attempt_manifest(path)


def test_agent_attempt_manifest_rejects_custom_known_artifact_ref(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest()
    manifest["artifacts"]["prompt_loop_result"] = "prompt/result.json"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="agent task run manifests artifact refs must be canonical",
    ):
        load_agent_attempt_manifest(path)


def test_eval_run_manifest_rejects_scored_agent_without_scorer_summary(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["agent"]["scorer_attempt"] = None
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="scored agent attempts require scorer_attempt",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_scored_agent_with_error_class(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["agent"]["error_class"] = "UnexpectedError"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="scored agent attempts cannot include error_class",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_unscored_agent_without_error_class(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["agent"] = {
        "agent_attempt_id": "agent_attempt_001",
        "status": "agent_loop_failed",
        "prompt_loop_status": "model_error",
        "error_class": None,
        "candidate_patch_hash": None,
        "duration_ms": 1,
        "scorer_attempt": None,
    }
    manifest["layer_counts"] = {
        "agent_status": {"agent_loop_failed": 1},
        "prompt_loop_status": {"model_error": 1},
    }
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="unscored agent attempts require error_class",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_agent_loop_failed_with_completed_loop(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["agent"] = {
        "agent_attempt_id": "agent_attempt_001",
        "status": "agent_loop_failed",
        "prompt_loop_status": "completed",
        "error_class": "UnexpectedError",
        "candidate_patch_hash": None,
        "duration_ms": 1,
        "scorer_attempt": None,
    }
    manifest["layer_counts"] = {
        "agent_status": {"agent_loop_failed": 1},
        "prompt_loop_status": {"completed": 1},
    }
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="agent loop failures cannot have completed prompt loop",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_scored_agent_without_candidate_patch_hash(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["agent"]["candidate_patch_hash"] = None
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="scored agent attempts require candidate_patch_hash",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_pass_summary_without_final_diff_hash(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["agent"]["scorer_attempt"]["final_diff_hash"] = None
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="PASS scorer summaries require final_diff_hash",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_missing_selected_task_attempt_coverage(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts_per_task"] = 2
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="eval attempts must cover every selected task attempts_per_task times",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_duplicate_attempt_index_per_task(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    second_attempt = {
        **manifest["attempts"][0],
        "eval_attempt_id": "eval_attempt_002",
        "artifact_dir": "attempts/task_001__attempt_002",
    }
    manifest["attempts"] = [manifest["attempts"][0], second_attempt]
    manifest["attempt_count"] = 2
    manifest["attempts_per_task"] = 2
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="eval attempt indexes must cover 0..attempts_per_task-1 per task",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_duplicate_attempt_artifact_dir(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    second_attempt = {
        **manifest["attempts"][0],
        "eval_attempt_id": "eval_attempt_002",
        "attempt_index": 1,
    }
    manifest["attempts"] = [manifest["attempts"][0], second_attempt]
    manifest["attempt_count"] = 2
    manifest["attempts_per_task"] = 2
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="Duplicate eval attempt artifact_dir",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_child_artifact_schema_mismatch(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["artifact_schema_version"] = (
        SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION
    )
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="artifact_schema_version does not match artifact_type",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_escaping_attempt_artifact_dir(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["artifact_dir"] = "../outside"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="parent traversal"):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_bool_attempt_index(tmp_path: Path) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["attempt_index"] = False
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="valid integer"):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_bad_task_hash_schema_version(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["task_hashes"] = {
        **manifest["task_hashes"],
        "schema_version": "eval_task_hashes_v999",
    }
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="Input should be"):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_selected_task_split_mismatch(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["task_hashes"]["selected_tasks"][0]["split"] = "heldout_private"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="selected task hashes contain tasks outside manifest split",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_unknown_attempt_task_id(tmp_path: Path) -> None:
    manifest = _eval_run_manifest()
    manifest["attempts"][0]["task_id"] = "task_missing"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="eval attempts reference task ids outside selected task hashes",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_attempt_type_that_conflicts_with_policy(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["policy_type"] = "scorer_control_patch"
    manifest["control_layer"] = "scorer"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="eval attempt artifact_type must match policy_type",
    ):
        load_eval_run_manifest(path)


def test_eval_run_manifest_rejects_false_layer_counts(tmp_path: Path) -> None:
    manifest = _eval_run_manifest()
    manifest["layer_counts"] = {"agent_status": {"agent_loop_failed": 1}}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="layer_counts must reflect eval attempts",
    ):
        load_eval_run_manifest(path)


def test_eval_manifest_rejects_invalid_policy_metadata(tmp_path: Path) -> None:
    manifest = _eval_run_manifest()
    manifest["policy_type"] = "agent_model"
    manifest["policy_family"] = "agent"
    manifest["control_layer"] = None
    manifest["control_name"] = None
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="agent_model policies require model_config and decoding_config",
    ):
        load_eval_run_manifest(path)


def test_eval_manifest_rejects_field_name_alias_for_model_config(
    tmp_path: Path,
) -> None:
    manifest = _eval_run_manifest()
    manifest["policy_type"] = "agent_model"
    manifest["policy_family"] = "agent"
    manifest["control_layer"] = None
    manifest["control_name"] = None
    manifest["model_config_ref"] = "model_config.json"
    manifest["decoding_config_ref"] = "decoding_config.json"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_eval_run_manifest(path)


def test_eval_suite_manifest_rejects_tasks_not_matching_task_hashes(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["tasks"] = ["task_missing"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="tasks must match selected task hash order",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_false_replay_summary(tmp_path: Path) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["replay_repeats"] = 1
    manifest["replay_run_count"] = 1
    manifest["replay_policy_count"] = 1
    manifest["replay_run_success_summary"] = "1/1"
    manifest["artifacts"]["replays"] = "replays"
    manifest["replay_runs"] = [
        {
            "policy": "agent-happy",
            "replay_index": 0,
            "replay_run_id": "replay_run_001",
            "status": "MISMATCH",
            "artifact_dir": "replays/agent-happy/replay_001",
            "manifest": "replays/agent-happy/replay_001/manifest.json",
            "replay_result": "replays/agent-happy/replay_001/replay_result.json",
            "attempt_count": 1,
            "matched_attempts": 0,
            "mismatched_attempts": 1,
            "error_count": 0,
        }
    ]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="replay_run_success_summary must reflect replay runs",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_duplicate_replay_index(tmp_path: Path) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["replay_repeats"] = 2
    replay_run = {
        "policy": "agent-happy",
        "replay_index": 0,
        "replay_run_id": "replay_run_001",
        "status": "PASS",
        "artifact_dir": "replays/agent-happy/replay_001",
        "manifest": "replays/agent-happy/replay_001/manifest.json",
        "replay_result": "replays/agent-happy/replay_001/replay_result.json",
        "attempt_count": 1,
        "matched_attempts": 1,
        "mismatched_attempts": 0,
        "error_count": 0,
    }
    manifest["replay_run_count"] = 2
    manifest["replay_policy_count"] = 1
    manifest["replay_run_success_summary"] = "2/2"
    manifest["artifacts"]["replays"] = "replays"
    manifest["replay_runs"] = [
        replay_run,
        {
            **replay_run,
            "replay_run_id": "replay_run_002",
            "artifact_dir": "replays/agent-happy/replay_002",
            "manifest": "replays/agent-happy/replay_002/manifest.json",
            "replay_result": "replays/agent-happy/replay_002/replay_result.json",
        },
    ]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="replay indexes must cover 0..replay_repeats-1",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_missing_configured_replay_runs(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["replay_repeats"] = 1
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="replay runs must match policy replay_repeats",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_policy_attempt_count_inflation(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["attempt_count"] = 2
    manifest["attempt_count"] = 2
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="policy attempt_count must equal task_count \\* attempts_per_task",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_policy_primary_layer_count_mismatch(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["layer_counts"]["agent_status"] = {}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="policy layer_counts primary status totals must equal attempt_count",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_partial_non_error_replay_run(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["attempts_per_task"] = 2
    manifest["policy_runs"][0]["attempt_count"] = 2
    manifest["policy_runs"][0]["replay_repeats"] = 1
    manifest["policy_runs"][0]["layer_counts"] = {
        layer_name: {status: count * 2 for status, count in counts.items()}
        for layer_name, counts in manifest["policy_runs"][0]["layer_counts"].items()
    }
    manifest["attempt_count"] = 2
    manifest["layer_counts"] = manifest["policy_runs"][0]["layer_counts"]
    manifest["replay_run_count"] = 1
    manifest["replay_policy_count"] = 1
    manifest["replay_run_success_summary"] = "1/1"
    manifest["artifacts"]["replays"] = "replays"
    manifest["replay_runs"] = [
        {
            "policy": "agent-happy",
            "replay_index": 0,
            "replay_run_id": "replay_run_001",
            "status": "PASS",
            "artifact_dir": "replays/agent-happy/replay_001",
            "manifest": "replays/agent-happy/replay_001/manifest.json",
            "replay_result": "replays/agent-happy/replay_001/replay_result.json",
            "attempt_count": 1,
            "matched_attempts": 1,
            "mismatched_attempts": 0,
            "error_count": 0,
        }
    ]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="non-error replay runs must cover the source policy attempt_count",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_escaping_replay_artifact_ref(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["artifact_dir"] = "../policies/agent-happy"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="parent traversal"):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_policy_manifest_outside_artifact_dir(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["manifest"] = "policies/other/manifest.json"
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="manifest must be under artifact_dir"):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_duplicate_policy_name(tmp_path: Path) -> None:
    manifest = _eval_suite_manifest()
    second_policy_run = {
        **manifest["policy_runs"][0],
        "eval_run_id": "eval_run_002",
        "artifact_dir": "policies/agent-happy-copy",
        "manifest": "policies/agent-happy-copy/manifest.json",
    }
    manifest["policy_runs"] = [manifest["policy_runs"][0], second_policy_run]
    manifest["policy_count"] = 2
    manifest["attempt_count"] = 2
    manifest["layer_counts"] = {
        layer_name: {status: count * 2 for status, count in counts.items()}
        for layer_name, counts in manifest["layer_counts"].items()
    }
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="Duplicate policy value"):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_replay_result_outside_artifact_dir(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["replay_repeats"] = 1
    manifest["replay_run_count"] = 1
    manifest["replay_policy_count"] = 1
    manifest["replay_run_success_summary"] = "1/1"
    manifest["artifacts"]["replays"] = "replays"
    manifest["replay_runs"] = [
        {
            "policy": "agent-happy",
            "replay_index": 0,
            "replay_run_id": "replay_run_001",
            "status": "PASS",
            "artifact_dir": "replays/agent-happy/replay_001",
            "manifest": "replays/agent-happy/replay_001/manifest.json",
            "replay_result": "replays/agent-happy/replay_result.json",
            "attempt_count": 1,
            "matched_attempts": 1,
            "mismatched_attempts": 0,
            "error_count": 0,
        }
    ]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="replay_result must be under artifact_dir",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_duplicate_replay_run_id(tmp_path: Path) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["replay_repeats"] = 2
    replay_run = {
        "policy": "agent-happy",
        "replay_index": 0,
        "replay_run_id": "replay_run_001",
        "status": "PASS",
        "artifact_dir": "replays/agent-happy/replay_001",
        "manifest": "replays/agent-happy/replay_001/manifest.json",
        "replay_result": "replays/agent-happy/replay_001/replay_result.json",
        "attempt_count": 1,
        "matched_attempts": 1,
        "mismatched_attempts": 0,
        "error_count": 0,
    }
    manifest["replay_run_count"] = 2
    manifest["replay_policy_count"] = 1
    manifest["replay_run_success_summary"] = "2/2"
    manifest["artifacts"]["replays"] = "replays"
    manifest["replay_runs"] = [
        replay_run,
        {
            **replay_run,
            "replay_index": 1,
            "artifact_dir": "replays/agent-happy/replay_002",
            "manifest": "replays/agent-happy/replay_002/manifest.json",
            "replay_result": "replays/agent-happy/replay_002/replay_result.json",
        },
    ]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="Duplicate replay_run_id"):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_false_layer_counts(tmp_path: Path) -> None:
    manifest = _eval_suite_manifest()
    manifest["layer_counts"] = {"agent_status": {"agent_loop_failed": 1}}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="layer_counts must reflect policy runs",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_missing_root_artifact_refs(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["artifacts"] = {}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="eval suite manifests require"):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_missing_replays_artifact_ref(
    tmp_path: Path,
) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_runs"][0]["replay_repeats"] = 1
    manifest["replay_run_count"] = 1
    manifest["replay_policy_count"] = 1
    manifest["replay_run_success_summary"] = "1/1"
    manifest["replay_runs"] = [
        {
            "policy": "agent-happy",
            "replay_index": 0,
            "replay_run_id": "replay_run_001",
            "status": "PASS",
            "artifact_dir": "replays/agent-happy/replay_001",
            "manifest": "replays/agent-happy/replay_001/manifest.json",
            "replay_result": "replays/agent-happy/replay_001/replay_result.json",
            "attempt_count": 1,
            "matched_attempts": 1,
            "mismatched_attempts": 0,
            "error_count": 0,
        }
    ]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="eval suite manifests require replays artifact ref",
    ):
        load_eval_suite_manifest(path)


def test_eval_suite_manifest_rejects_zero_policy_runs(tmp_path: Path) -> None:
    manifest = _eval_suite_manifest()
    manifest["policy_count"] = 0
    manifest["attempt_count"] = 0
    manifest["layer_counts"] = {}
    manifest["policy_runs"] = []
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="greater than 0|at least 1 item"):
        load_eval_suite_manifest(path)


def test_control_manifest_rejects_empty_successful_calibration(tmp_path: Path) -> None:
    manifest = _control_manifest()
    manifest["record_count"] = 0
    manifest["records"] = []
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="control calibration manifests require records",
    ):
        load_control_calibration_manifest(path)


def test_control_manifest_rejects_missing_root_artifact_refs(tmp_path: Path) -> None:
    manifest = _control_manifest()
    manifest["artifacts"] = {}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="control calibration manifests require"):
        load_control_calibration_manifest(path)


def test_replay_error_manifest_accepts_null_source_identity(tmp_path: Path) -> None:
    manifest = _replay_manifest()
    manifest["source_eval_run_id"] = None
    manifest["source_agent_attempt_id"] = None
    manifest["source_artifact_type"] = None
    manifest["source_artifact_schema_version"] = None
    del manifest["artifacts"]["attempts"]
    path = _write_json(tmp_path / "manifest.json", manifest)

    loaded = load_replay_run_manifest(path)

    assert loaded.source_artifact_type is None
    assert loaded.source_artifact_schema_version is None


def test_replay_manifest_requires_source_id_matching_source_type(
    tmp_path: Path,
) -> None:
    manifest = _replay_manifest()
    manifest["source_eval_run_id"] = None
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="eval run replay sources require source_eval_run_id",
    ):
        load_replay_run_manifest(path)

    direct_agent_manifest = _replay_manifest()
    direct_agent_manifest["source_eval_run_id"] = None
    direct_agent_manifest["source_agent_attempt_id"] = "agent_attempt_001"
    direct_agent_manifest["source_artifact_type"] = "agent_attempt"
    direct_agent_manifest["source_artifact_schema_version"] = (
        AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION
    )
    del direct_agent_manifest["artifacts"]["attempts"]
    direct_agent_manifest["artifacts"]["agent_task_run"] = "agent_task_run"
    direct_agent_path = _write_json(
        tmp_path / "direct_agent.json", direct_agent_manifest
    )

    loaded = load_replay_run_manifest(direct_agent_path)

    assert loaded.source_agent_attempt_id == "agent_attempt_001"


def test_replay_manifest_rejects_missing_root_artifact_refs(tmp_path: Path) -> None:
    manifest = _replay_manifest()
    manifest["artifacts"] = {}
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="replay run manifests require"):
        load_replay_run_manifest(path)


def test_control_manifest_rejects_false_overall_match(tmp_path: Path) -> None:
    manifest = _control_manifest()
    manifest["record_count"] = 1
    manifest["records"] = [
        {
            "control_run_id": "controls_001",
            "task_id": "task_001",
            "control_layer": "agent",
            "control_name": "happy",
            "repeat_index": 0,
            "artifact_dir": "agent_control_scripts/task_001__happy__repeat_001",
            "expected": {
                "prompt_loop_status": "completed",
            },
            "actual": {
                "agent_attempt_id": "agent_attempt_001",
                "agent_run_status": "agent_loop_failed",
                "prompt_loop_status": "max_turns_exceeded",
                "tool_results": [],
                "attempt_status": None,
                "public_status": None,
                "hidden_status": None,
                "error_class": "MaxTurnsExceeded",
            },
            "match": False,
        }
    ]
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="overall_match must reflect records and flake detection",
    ):
        load_control_calibration_manifest(path)


def test_control_manifest_rejects_flake_detection_repeat_mismatch(
    tmp_path: Path,
) -> None:
    manifest = _control_manifest()
    manifest["repeats"] = 2
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(
        ValidationError,
        match="flake_detection repeats must match control repeats",
    ):
        load_control_calibration_manifest(path)


def test_control_manifest_rejects_bad_flake_detection_schema(
    tmp_path: Path,
) -> None:
    manifest = _control_manifest()
    manifest["flake_detection"] = {
        **manifest["flake_detection"],
        "schema_version": "control_flake_detection_v999",
    }
    path = _write_json(tmp_path / "manifest.json", manifest)

    with pytest.raises(ValidationError, match="Input should be"):
        load_control_calibration_manifest(path)


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _scorer_manifest() -> dict[str, Any]:
    return {
        "artifact_type": "scorer_attempt",
        "artifact_schema_version": SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        "orchestrator_version": "scorer_attempt_orchestrator_v0",
        "scorer_attempt_id": "scorer_attempt_001",
        "task_id": "task_001",
        "task_manifest_path": "tasks/task_001/task.yaml",
        "submission_path": "submission.patch",
        "status": "PASS",
        "artifacts": {
            "attempt": "attempt.json",
            "stdout": "stdout.txt",
            "stderr": "stderr.txt",
            "error": "error.txt",
            "trace": "trace.jsonl",
            "final_diff": "final.diff",
        },
    }


def _agent_manifest() -> dict[str, Any]:
    return {
        "artifact_type": "agent_attempt",
        "artifact_schema_version": AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        "orchestrator_version": "agent_task_run_orchestrator_v0",
        "agent_attempt_id": "agent_attempt_001",
        "task_id": "task_001",
        "task_manifest_path": "tasks/task_001/task.yaml",
        "status": "scored",
        "prompt_loop_status": "completed",
        "attempt_status": "PASS",
        "artifacts": {
            "agent_task_run": "agent_task_run.json",
            "decoding_config": "decoding_config.json",
            "agent_task_view": "agent_task_view.json",
            "prompt_loop_result": "prompt_loop_result.json",
            "candidate_patch": "candidate.patch",
            "attempt": "attempt",
            "error": "error.txt",
        },
    }


def _eval_task_hashes() -> dict[str, Any]:
    return {
        "schema_version": EVAL_TASK_HASHES_SCHEMA_VERSION,
        "task_pack_id": "repo_patch_python_v0",
        "selected_task_hash_set": "xxh64:selected",
        "selected_tasks": [
            {
                "task_id": "task_001",
                "split": "dev",
                "task_record_hash": "xxh64:task",
                "task_yaml_hash": "xxh64:yaml",
                "required_task_files_hash": "xxh64:required",
                "full_task_dir_hash": "xxh64:full",
                "required_task_files": [
                    {
                        "path": "task.yaml",
                        "kind": "file",
                        "hash": "xxh64:file",
                    }
                ],
            }
        ],
    }


def _eval_run_manifest() -> dict[str, Any]:
    layer_counts = _agent_happy_layer_counts()
    return {
        "artifact_type": "eval_run",
        "artifact_schema_version": EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
        "eval_run_id": "eval_run_001",
        "created_at": "2026-01-01T00:00:00Z",
        "config_path": "configs/eval.yaml",
        "config_hash": "xxh64:config",
        "config_name": "unit",
        "task_pack": "data/task_packs/repo_patch_python_v0",
        "split": "dev",
        "task_hashes": _eval_task_hashes(),
        "policy": "agent-happy",
        "policy_type": "agent_control_script",
        "policy_family": "control",
        "control_layer": "agent",
        "control_name": "happy",
        "attempts_per_task": 1,
        "replay_repeats": 0,
        "attempt_count": 1,
        "layer_counts": layer_counts,
        "artifacts": {
            "trace": "trace.jsonl",
            "attempts": "attempts",
        },
        "attempts": [
            {
                "eval_attempt_id": "eval_attempt_001",
                "task_id": "task_001",
                "attempt_index": 0,
                "artifact_dir": "attempts/task_001__attempt_001",
                "artifact_type": "agent_attempt",
                "artifact_schema_version": AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
                "scorer": None,
                "agent": {
                    "agent_attempt_id": "agent_attempt_001",
                    "status": "scored",
                    "prompt_loop_status": "completed",
                    "error_class": None,
                    "candidate_patch_hash": "xxh64:candidate",
                    "duration_ms": 1,
                    "scorer_attempt": {
                        "scorer_attempt_id": "scorer_attempt_001",
                        "status": "PASS",
                        "public_status": "PASS",
                        "hidden_status": "PASS",
                        "error_class": None,
                        "final_diff_hash": "xxh64:diff",
                        "duration_ms": 1,
                    },
                },
            }
        ],
    }


def _eval_suite_manifest() -> dict[str, Any]:
    layer_counts = _agent_happy_layer_counts()
    return {
        "artifact_type": "eval_suite",
        "artifact_schema_version": EVAL_SUITE_ARTIFACT_SCHEMA_VERSION,
        "eval_suite_id": "eval_suite_001",
        "created_at": "2026-01-01T00:00:00Z",
        "config_path": "configs/eval.yaml",
        "config_hash": "xxh64:config",
        "config_name": "unit",
        "task_pack": "data/task_packs/repo_patch_python_v0",
        "split": "dev",
        "task_hashes": _eval_task_hashes(),
        "tasks": ["task_001"],
        "task_count": 1,
        "policy_count": 1,
        "attempt_count": 1,
        "layer_counts": layer_counts,
        "artifacts": {
            "policies": "policies",
        },
        "policy_runs": [
            {
                "policy": "agent-happy",
                "policy_type": "agent_control_script",
                "policy_family": "control",
                "control_layer": "agent",
                "control_name": "happy",
                "attempts_per_task": 1,
                "replay_repeats": 0,
                "eval_run_id": "eval_run_001",
                "artifact_dir": "policies/agent-happy",
                "manifest": "policies/agent-happy/manifest.json",
                "attempt_count": 1,
                "layer_counts": layer_counts,
            }
        ],
        "replay_run_count": 0,
        "replay_policy_count": 0,
        "replay_run_success_summary": "0/0",
        "replay_runs": [],
    }


def _agent_happy_layer_counts() -> dict[str, dict[str, int]]:
    return {
        "agent_scorer_hidden_status": {"PASS": 1},
        "agent_scorer_public_status": {"PASS": 1},
        "agent_scorer_status": {"PASS": 1},
        "agent_status": {"scored": 1},
        "prompt_loop_status": {"completed": 1},
    }


def _control_manifest() -> dict[str, Any]:
    return {
        "artifact_type": "control_calibration",
        "artifact_schema_version": CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION,
        "control_run_id": "controls_001",
        "created_at": "2026-01-01T00:00:00Z",
        "task_pack_path": "data/task_packs/repo_patch_python_v0",
        "repeats": 1,
        "record_count": 1,
        "overall_match": True,
        "flake_detection": {
            "schema_version": CONTROL_FLAKE_DETECTION_SCHEMA_VERSION,
            "status": "stable",
            "repeats": 1,
            "groups_checked": 0,
            "drifted_groups": 0,
            "groups": {
                "scorer": [],
                "agent": [],
            },
        },
        "artifacts": {
            "agent_control_scripts": "agent_control_scripts",
            "scorer_control_patches": "scorer_control_patches",
            "report": "control_report.md",
            "results": "control_results.jsonl",
        },
        "records": [_agent_control_record(match=True)],
    }


def _agent_control_record(*, match: bool) -> dict[str, Any]:
    return {
        "control_run_id": "controls_001",
        "task_id": "task_001",
        "control_layer": "agent",
        "control_name": "happy",
        "repeat_index": 0,
        "artifact_dir": "agent_control_scripts/task_001__happy__repeat_001",
        "expected": {
            "prompt_loop_status": "completed",
        },
        "actual": {
            "agent_attempt_id": "agent_attempt_001",
            "agent_run_status": "scored" if match else "agent_loop_failed",
            "prompt_loop_status": "completed" if match else "max_turns_exceeded",
            "tool_results": [],
            "attempt_status": "PASS" if match else None,
            "public_status": "PASS" if match else None,
            "hidden_status": "PASS" if match else None,
            "error_class": None if match else "MaxTurnsExceeded",
        },
        "match": match,
    }


def _replay_manifest() -> dict[str, Any]:
    return {
        "artifact_type": "replay_run",
        "artifact_schema_version": REPLAY_RUN_ARTIFACT_SCHEMA_VERSION,
        "replay_run_id": "replay_run_001",
        "created_at": "2026-01-01T00:00:00Z",
        "source_run_dir": "runs/eval",
        "source_eval_run_id": "eval_run_001",
        "source_agent_attempt_id": None,
        "source_artifact_type": "eval_run",
        "source_artifact_schema_version": EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
        "artifacts": {
            "replay_result": "replay_result.json",
            "replay_results": "replay_results.jsonl",
            "trace": "trace.jsonl",
            "attempts": "attempts",
        },
    }


def _trajectory_export_manifest() -> dict[str, Any]:
    return {
        "artifact_type": "trajectory_export",
        "artifact_schema_version": TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION,
        "created_at": "2026-01-01T00:00:00Z",
        "source_artifact_type": "eval_run",
        "source_artifact_schema_version": EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
        "source_artifact_dir": "runs/eval",
        "source_manifest_path": "runs/eval/manifest.json",
        "source_manifest_hash": "xxh64:source",
        "source_eval_run_id": "eval_run_001",
        "source_eval_suite_id": None,
        "trajectory_record_schema_version": "trajectory_record_v0",
        "record_count": 1,
        "trajectories_jsonl_hash": "xxh64:trajectories",
        "artifacts": {
            "trajectories": "trajectories.jsonl",
        },
    }
