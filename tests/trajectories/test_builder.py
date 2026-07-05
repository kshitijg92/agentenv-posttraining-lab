import json
from pathlib import Path

import pytest

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.trajectories.builder import (
    build_trajectory_record_from_eval_attempt,
    build_training_eligibility,
)
from agentenv.trajectories.schema import LeakageEvidence
from agentenv.trajectories.schema import RewardComponents
from agentenv.trajectories.schema import TrajectoryStatuses


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
SCORER_CONTROL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")


def test_build_trajectory_record_from_successful_agent_eval_attempt(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )

    record = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )

    assert record.identity.trajectory_id.startswith("trajectory_")
    assert record.identity.eval_run_id == eval_run.eval_run_id
    assert record.identity.eval_attempt_id == eval_run.attempts[0].eval_attempt_id
    assert record.identity.agent_attempt_id is not None
    assert record.identity.scorer_attempt_id is not None
    assert record.policy.policy_id == "agent-happy"
    assert record.policy.policy_spec.type == "agent_control_script"
    assert record.statuses.agent_task_run_status == "scored"
    assert record.statuses.prompt_loop_status == "completed"
    assert record.statuses.grade_state == "scored_pass"
    assert record.statuses.task_success
    assert record.reward_components.public_validator_success is True
    assert record.reward_components.hidden_validator_success is True
    assert record.reward_components.model_output_format_valid is True
    assert record.reward_components.model_tool_usage_valid is True
    assert not record.reward_components.orchestration_failure
    assert record.leakage.canary_hash is not None
    assert not record.leakage.canary_leaked
    assert not record.leakage.hidden_validators_visible_to_model
    assert record.training_eligibility.positive_sft_allowed
    assert record.training_eligibility.preference_data_allowed
    assert record.artifacts.agent_task_run_json is not None
    assert record.artifacts.agent_task_view_json is not None
    assert record.artifacts.prompt_loop_result_json is not None
    assert record.artifacts.decoding_config_json is not None
    assert record.artifacts.agent_control_script_json is not None
    assert record.artifacts.candidate_patch is not None
    assert record.artifacts.attempt_json is not None
    assert record.artifacts.final_diff is not None


def test_build_trajectory_record_from_scorer_control_eval_attempt(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        SCORER_CONTROL_CONFIG,
        "oracle",
        tmp_path / "oracle",
    )

    record = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )

    assert record.identity.agent_attempt_id is None
    assert record.identity.scorer_attempt_id is not None
    assert record.policy.policy_spec.type == "scorer_control_patch"
    assert record.statuses.agent_task_run_status is None
    assert record.statuses.prompt_loop_status is None
    assert record.statuses.grade_state == "scored_pass"
    assert record.statuses.task_success
    assert record.training_eligibility.analysis_allowed
    assert not record.training_eligibility.positive_sft_allowed
    assert not record.training_eligibility.preference_data_allowed
    assert record.artifacts.agent_task_run_json is None
    assert record.artifacts.agent_task_view_json is None
    assert record.artifacts.attempt_json is not None
    assert record.artifacts.final_diff is not None


def test_training_eligibility_blocks_all_training_flags_on_non_trainable_split() -> (
    None
):
    statuses = TrajectoryStatuses(
        agent_task_run_status="scored",
        prompt_loop_status="completed",
        attempt_status="HIDDEN_TEST_FAIL",
        public_status="PASS",
        hidden_status="FAIL",
        grade_state="scored_fail",
        task_success=False,
    )
    reward_components = RewardComponents(
        reward_config_hash="xxh64:rewardconfig",
        reward_code_hash="xxh64:rewardcode",
        public_validator_success=True,
        hidden_validator_success=False,
        model_output_format_valid=True,
        model_tool_usage_valid=True,
        orchestration_failure=False,
        reward_hack_flag=False,
    )
    leakage = LeakageEvidence(
        canary_hash="xxh64:canary",
        canary_leaked=False,
        hidden_validators_visible_to_model=False,
        leakage_check_version="leakage_check_v0",
    )

    eligibility = build_training_eligibility(
        policy_type="agent_control_script",
        split="heldout_private",
        statuses=statuses,
        reward_components=reward_components,
        leakage=leakage,
    )

    assert eligibility.analysis_allowed
    assert not eligibility.positive_sft_allowed
    assert not eligibility.negative_example_allowed
    assert not eligibility.preference_data_allowed
    assert eligibility.eligibility_reason == "split is not eligible for training"


def test_build_trajectory_record_from_unscored_agent_eval_attempt(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-malformed",
        tmp_path / "agent-malformed",
    )

    record = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )

    assert record.identity.agent_attempt_id is not None
    assert record.identity.scorer_attempt_id is None
    assert record.statuses.agent_task_run_status == "agent_loop_failed"
    assert record.statuses.prompt_loop_status == "invalid_model_output"
    assert record.statuses.attempt_status is None
    assert record.statuses.grade_state == "cannot_grade"
    assert not record.statuses.task_success
    assert record.reward_components.model_output_format_valid is False
    assert record.reward_components.model_tool_usage_valid is None
    assert not record.training_eligibility.positive_sft_allowed
    assert record.training_eligibility.negative_example_allowed
    assert not record.training_eligibility.preference_data_allowed
    assert record.artifacts.agent_task_view_json is not None
    assert record.artifacts.prompt_loop_result_json is not None
    assert record.artifacts.decoding_config_json is not None
    assert record.artifacts.candidate_patch is None
    assert record.artifacts.attempt_json is None


def test_build_trajectory_record_blocks_positive_sft_when_agent_artifact_leaks(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )
    prompt_loop_path = (
        eval_run.out_dir
        / eval_run.attempts[0].attempt_dir.relative_to(eval_run.out_dir)
        / "prompt_loop_result.json"
    )
    prompt_loop_payload = json.loads(prompt_loop_path.read_text())
    prompt_loop_payload["messages"][0]["content"] += "\nhidden_tests"
    prompt_loop_path.write_text(json.dumps(prompt_loop_payload, indent=2) + "\n")

    record = build_trajectory_record_from_eval_attempt(
        eval_run.out_dir,
        eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
    )

    assert record.leakage.hidden_validators_visible_to_model
    assert not record.training_eligibility.positive_sft_allowed
    assert not record.training_eligibility.preference_data_allowed


def test_build_trajectory_record_rejects_eval_suite_manifest(
    tmp_path: Path,
) -> None:
    eval_suite_dir = tmp_path / "eval-suite"
    eval_suite_dir.mkdir()
    (eval_suite_dir / MANIFEST_FILENAME).write_text(
        json.dumps({"artifact_type": "eval_suite"}) + "\n"
    )

    with pytest.raises(ValueError, match="artifact_schema_version"):
        build_trajectory_record_from_eval_attempt(
            eval_suite_dir,
            eval_attempt_id="eval_attempt_missing",
        )


def test_build_trajectory_record_rejects_unknown_eval_attempt(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )

    with pytest.raises(ValueError, match="Eval attempt not found"):
        build_trajectory_record_from_eval_attempt(
            eval_run.out_dir,
            eval_attempt_id="eval_attempt_missing",
        )


def test_build_trajectory_record_rejects_invalid_eval_manifest_status(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )
    manifest_path = eval_run.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["attempts"][0]["agent"]["scorer_attempt"]["hidden_status"] = "FAIL"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    with pytest.raises(
        ValueError,
        match="PASS attempts require public and hidden PASS",
    ):
        build_trajectory_record_from_eval_attempt(
            eval_run.out_dir,
            eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
        )


def test_build_trajectory_record_rejects_agent_payload_summary_mismatch(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )
    agent_task_run_path = (
        eval_run.out_dir
        / eval_run.attempts[0].attempt_dir.relative_to(eval_run.out_dir)
        / "agent_task_run.json"
    )
    agent_task_run = json.loads(agent_task_run_path.read_text())
    agent_task_run["candidate_patch_hash"] = "xxh64:wrong"
    agent_task_run_path.write_text(json.dumps(agent_task_run, indent=2) + "\n")

    with pytest.raises(
        ValueError,
        match="candidate_patch_hash mismatch",
    ):
        build_trajectory_record_from_eval_attempt(
            eval_run.out_dir,
            eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
        )


def test_build_trajectory_record_rejects_malformed_prompt_loop_payload(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )
    prompt_loop_path = (
        eval_run.out_dir
        / eval_run.attempts[0].attempt_dir.relative_to(eval_run.out_dir)
        / "prompt_loop_result.json"
    )
    prompt_loop = json.loads(prompt_loop_path.read_text())
    del prompt_loop["status"]
    prompt_loop_path.write_text(json.dumps(prompt_loop, indent=2) + "\n")

    with pytest.raises(ValueError, match="PromptLoopResult at"):
        build_trajectory_record_from_eval_attempt(
            eval_run.out_dir,
            eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
        )


def test_build_trajectory_record_rejects_live_task_split_drift(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )
    manifest_path = eval_run.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["split"] = "heldout_private"
    manifest["task_hashes"]["selected_tasks"][0]["split"] = "heldout_private"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    with pytest.raises(ValueError, match="Live task split mismatch"):
        build_trajectory_record_from_eval_attempt(
            eval_run.out_dir,
            eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
        )


def test_build_trajectory_record_rejects_live_task_hash_drift(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "agent-happy",
    )
    manifest_path = eval_run.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["task_hashes"]["selected_tasks"][0]["task_yaml_hash"] = "xxh64:stale"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    with pytest.raises(ValueError, match="Live task manifest hash mismatch"):
        build_trajectory_record_from_eval_attempt(
            eval_run.out_dir,
            eval_attempt_id=eval_run.attempts[0].eval_attempt_id,
        )
