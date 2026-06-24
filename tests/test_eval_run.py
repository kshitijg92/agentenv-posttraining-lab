import json
from pathlib import Path

from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.orchestrators.eval_run import (
    run_eval_config,
    run_eval_config_all_policies,
)
from agentenv.tracing.schema import EvalTraceProvenance
from agentenv.tracing.validate import load_trace_events, validate_trace_file


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
    assert run_manifest["artifacts"] == {
        "attempts": "attempts",
        "trace": "trace.jsonl",
    }
    assert run_manifest["attempts"][0]["task_id"] == "toy_python_fix_001"
    assert run_manifest["attempts"][0]["status"] == "PASS"
    validate_trace_file(tmp_path / "eval/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "eval/trace.jsonl")
    assert [event.event_type for event in trace_events] == [
        "eval_started",
        "eval_task_started",
        "eval_attempt_started",
        "eval_attempt_finished",
        "eval_task_finished",
        "eval_finished",
    ]
    first_provenance = trace_events[0].provenance_config
    assert isinstance(first_provenance, EvalTraceProvenance)
    assert first_provenance.eval_run_id == eval_run.eval_run_id
    assert first_provenance.config_name == "control_policies"
    assert first_provenance.policy == "oracle"
    attempt_finished_provenance = trace_events[3].provenance_config
    assert isinstance(attempt_finished_provenance, EvalTraceProvenance)
    assert attempt_finished_provenance.task_id == "toy_python_fix_001"
    assert attempt_finished_provenance.task_index == 0
    assert attempt_finished_provenance.attempt_index == 0
    assert (
        attempt_finished_provenance.attempt_id
        == run_manifest["attempts"][0]["attempt_id"]
    )
    assert trace_events[3].output_payload is not None
    assert trace_events[3].output_payload["status"] == "PASS"
    assert trace_events[3].payload_refs == {
        "attempt": "attempts/toy_python_fix_001__attempt_001/attempt.json",
        "attempt_trace": "attempts/toy_python_fix_001__attempt_001/trace.jsonl",
    }
    assert (tmp_path / "eval/attempts/toy_python_fix_001__attempt_001").is_dir()
    assert (
        tmp_path / "eval/attempts/toy_python_fix_001__attempt_001/attempt.json"
    ).is_file()
    assert (tmp_path / "eval/trace.jsonl").is_file()


def test_run_eval_config_distinguishes_bad_noop(tmp_path: Path) -> None:
    eval_run = run_eval_config(CONTROL_EVAL_CONFIG, "bad-noop", tmp_path / "eval")

    assert len(eval_run.attempts) == 1
    result = eval_run.attempts[0].result
    assert result.status == "HIDDEN_TEST_FAIL"
    assert result.public_status == "PASS"
    assert result.hidden_status == "FAIL"


def test_run_eval_config_all_policies_writes_matrix_manifest(
    tmp_path: Path,
) -> None:
    eval_matrix = run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )

    matrix_manifest_path = tmp_path / "eval_matrix/eval_matrix_manifest.json"
    matrix_manifest = json.loads(matrix_manifest_path.read_text())

    assert eval_matrix.config.name == "control_policies"
    assert [run.policy for run in eval_matrix.policy_runs] == [
        "oracle",
        "bad-noop",
        "bad-public-only",
    ]
    assert matrix_manifest["artifact_version"] == "eval_matrix_v0"
    assert matrix_manifest["config_name"] == "control_policies"
    assert matrix_manifest["policy_count"] == 3
    assert matrix_manifest["attempt_count"] == 3
    assert matrix_manifest["status_counts"] == {
        "HIDDEN_TEST_FAIL": 2,
        "PASS": 1,
    }
    assert matrix_manifest["artifacts"] == {"policies": "policies"}
    assert matrix_manifest["policy_runs"] == [
        {
            "policy": "oracle",
            "eval_run_id": eval_matrix.policy_runs[0].eval_run_id,
            "artifact_dir": "policies/oracle",
            "run_manifest": "policies/oracle/run_manifest.json",
            "attempt_count": 1,
            "status_counts": {"PASS": 1},
        },
        {
            "policy": "bad-noop",
            "eval_run_id": eval_matrix.policy_runs[1].eval_run_id,
            "artifact_dir": "policies/bad-noop",
            "run_manifest": "policies/bad-noop/run_manifest.json",
            "attempt_count": 1,
            "status_counts": {"HIDDEN_TEST_FAIL": 1},
        },
        {
            "policy": "bad-public-only",
            "eval_run_id": eval_matrix.policy_runs[2].eval_run_id,
            "artifact_dir": "policies/bad-public-only",
            "run_manifest": "policies/bad-public-only/run_manifest.json",
            "attempt_count": 1,
            "status_counts": {"HIDDEN_TEST_FAIL": 1},
        },
    ]
    assert (tmp_path / "eval_matrix/policies/oracle/run_manifest.json").is_file()
    assert (tmp_path / "eval_matrix/policies/bad-noop/run_manifest.json").is_file()
    assert (
        tmp_path / "eval_matrix/policies/bad-public-only/run_manifest.json"
    ).is_file()
