import json
from pathlib import Path

from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.orchestrators.eval_run import run_eval_config


CONTROL_EVAL_CONFIG = Path("configs/eval/control_policies.yaml")


def test_control_eval_config_loads() -> None:
    config = load_eval_config(CONTROL_EVAL_CONFIG)

    assert config.name == "control_policies"
    assert config.task_pack == "data/task_packs/repo_patch_python_v0"
    assert config.tasks == ["toy_python_fix_001"]
    assert sorted(config.policies) == ["bad-noop", "bad-public-only", "oracle"]


def test_control_eval_config_paths_are_valid() -> None:
    config = load_eval_config(CONTROL_EVAL_CONFIG)

    validate_eval_config_paths(config, CONTROL_EVAL_CONFIG)


def test_run_eval_config_writes_run_manifest(tmp_path: Path) -> None:
    eval_run = run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "eval")

    run_manifest_path = tmp_path / "eval/run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text())

    assert eval_run.config.name == "control_policies"
    assert eval_run.policy == "oracle"
    assert len(eval_run.attempts) == 1
    assert eval_run.attempts[0].result.status == "PASS"
    assert run_manifest["artifact_version"] == "eval_run_v0"
    assert run_manifest["config_name"] == "control_policies"
    assert run_manifest["policy"] == "oracle"
    assert run_manifest["attempt_count"] == 1
    assert run_manifest["status_counts"] == {"PASS": 1}
    assert run_manifest["attempts"][0]["task_id"] == "toy_python_fix_001"
    assert run_manifest["attempts"][0]["status"] == "PASS"
    assert (tmp_path / "eval/attempts/toy_python_fix_001__attempt_001").is_dir()
    assert (
        tmp_path / "eval/attempts/toy_python_fix_001__attempt_001/attempt.json"
    ).is_file()


def test_run_eval_config_distinguishes_bad_noop(tmp_path: Path) -> None:
    eval_run = run_eval_config(CONTROL_EVAL_CONFIG, "bad-noop", tmp_path / "eval")

    assert len(eval_run.attempts) == 1
    result = eval_run.attempts[0].result
    assert result.status == "HIDDEN_TEST_FAIL"
    assert result.public_status == "PASS"
    assert result.hidden_status == "FAIL"
