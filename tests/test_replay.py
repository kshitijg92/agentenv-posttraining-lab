import json
from pathlib import Path

from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_task_run import (
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.replay.runner import _normalize_text, run_replay
from agentenv.tracing.schema import ReplayTraceProvenance
from agentenv.tracing.validate import load_trace_events, validate_trace_file


CONTROL_EVAL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")
DEV_BASELINE_EVAL_CONFIG = Path("configs/eval/dev_baseline.yaml")
TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TOY_HAPPY_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/"
    "controls/agent_control_scripts/happy_path.json"
)
SCORER_ATTEMPT_ARTIFACTS = {
    "attempt.json": True,
    "error.txt": True,
    "final.diff": True,
    "run_manifest.json": True,
    "stderr.txt": True,
    "stdout.txt": True,
    "trace.jsonl": True,
}
AGENT_FIELD_MATCHES = {
    "attempt_status": True,
    "candidate_patch_hash": True,
    "error_class": True,
    "error_message": True,
    "prompt_loop_status": True,
    "status": True,
}


def _write_agent_control_source_artifact(
    control_path: Path,
    out_dir: Path,
) -> None:
    control_case = load_agent_control_script_case(control_path)
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )
    run_and_persist_agent_task_attempt_to_dir(
        TOY_TASK_MANIFEST,
        model_client,
        model_client.default_decoding_config(),
        out_dir,
        agent_control_script=control_case,
    )


def test_run_replay_matches_oracle_eval_run(tmp_path: Path) -> None:
    source_run = run_eval_config(
        CONTROL_EVAL_CONFIG,
        "oracle",
        tmp_path / "source_run",
    )

    replay_run = run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_manifest = json.loads(
        (tmp_path / "replay_run/replay_manifest.json").read_text()
    )
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_result["status"] == "PASS"
    assert replay_result["attempt_count"] == 1
    assert replay_result["matched_attempts"] == 1
    assert replay_manifest["artifact_version"] == "replay_v0"
    assert replay_manifest["source_eval_run_id"] == source_run.eval_run_id
    assert len(replay_records) == 1
    assert replay_records[0]["matched"] is True
    assert replay_records[0]["comparison_type"] == "scorer_attempt"
    assert (
        replay_records[0]["source_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert (
        replay_records[0]["replay_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert replay_records[0]["source_artifact_path"] == str(
        tmp_path / "source_run/attempts/toy_python_fix_001__attempt_001"
    )
    assert replay_records[0]["replay_artifact_path"] == str(
        tmp_path / "replay_run/attempts/toy_python_fix_001__attempt_001"
    )
    assert "source_attempt_artifact_ref" not in replay_records[0]
    assert "replay_attempt_artifact_ref" not in replay_records[0]
    assert "source_agent_artifact_ref" not in replay_records[0]
    assert "replay_agent_artifact_ref" not in replay_records[0]
    assert replay_records[0]["field_matches"] == {
        "error_class": True,
        "final_diff_hash": True,
        "hidden_status": True,
        "public_status": True,
        "status": True,
    }
    assert replay_records[0]["artifact_matches"] == SCORER_ATTEMPT_ARTIFACTS
    assert (
        tmp_path / "replay_run/attempts/toy_python_fix_001__attempt_001/attempt.json"
    ).is_file()
    validate_trace_file(tmp_path / "replay_run/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "replay_run/trace.jsonl")
    assert trace_events[0].schema_version == "trace_v0"
    assert trace_events[0].event_type == "replay_started"
    first_provenance = trace_events[0].provenance_config
    assert isinstance(first_provenance, ReplayTraceProvenance)
    assert first_provenance.replay_id == replay_run.replay_id
    second_provenance = trace_events[1].provenance_config
    assert isinstance(second_provenance, ReplayTraceProvenance)
    assert second_provenance.source_eval_run_id == source_run.eval_run_id


def test_run_replay_detects_durable_attempt_artifact_mismatch(
    tmp_path: Path,
) -> None:
    run_eval_config(
        CONTROL_EVAL_CONFIG,
        "oracle",
        tmp_path / "source_run",
    )
    source_manifest = json.loads((tmp_path / "source_run/run_manifest.json").read_text())
    source_attempt_ref = source_manifest["attempts"][0]["artifact_dir"]
    source_stdout = tmp_path / "source_run" / source_attempt_ref / "stdout.txt"
    source_stdout.write_text(source_stdout.read_text() + "deterministic tamper\n")

    replay_run = run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "MISMATCH"
    assert replay_result["status"] == "MISMATCH"
    assert replay_result["matched_attempts"] == 0
    assert replay_result["mismatched_attempts"] == 1
    assert replay_records[0]["matched"] is False
    assert replay_records[0]["field_matches"] == {
        "error_class": True,
        "final_diff_hash": True,
        "hidden_status": True,
        "public_status": True,
        "status": True,
    }
    assert replay_records[0]["artifact_matches"] == {
        **SCORER_ATTEMPT_ARTIFACTS,
        "stdout.txt": False,
    }


def test_run_replay_normalizes_pytest_tmp_paths_for_dev_controls(
    tmp_path: Path,
) -> None:
    run_eval_config(
        DEV_BASELINE_EVAL_CONFIG,
        "noop",
        tmp_path / "source_run",
    )

    replay_run = run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_result["status"] == "PASS"
    assert replay_result["matched_attempts"] == 3
    assert all(record["artifact_matches"]["stdout.txt"] for record in replay_records)


def test_replay_normalizes_elided_pytest_tmp_path_fragments() -> None:
    first = _normalize_text(
        "...pytest-1119/test_duplicate_id_exits_with_i0/records.jsonl",
        repo_roots=(),
    )
    second = _normalize_text(
        "...ytest-1123/test_duplicate_id_exits_with_i0/records.jsonl",
        repo_roots=(),
    )

    assert first == second == (
        "...<PYTEST_TMP>/test_duplicate_id_exits_with_i0/records.jsonl"
    )


def test_run_replay_matches_agent_control_artifact(tmp_path: Path) -> None:
    _write_agent_control_source_artifact(
        TOY_HAPPY_AGENT_CONTROL,
        tmp_path / "source_agent",
    )

    replay_run = run_replay(tmp_path / "source_agent", tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_manifest = json.loads(
        (tmp_path / "replay_run/replay_manifest.json").read_text()
    )
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_result["status"] == "PASS"
    assert replay_manifest["source_artifact_version"] == "agent_task_run_artifacts_v0"
    assert replay_manifest["artifacts"]["agent_task_run"] == "agent_task_run"
    assert len(replay_records) == 1
    assert replay_records[0]["comparison_type"] == "agent_task_run"
    assert replay_records[0]["matched"] is True
    assert replay_records[0]["field_matches"] == AGENT_FIELD_MATCHES
    assert all(replay_records[0]["artifact_matches"].values())
    assert {
        "agent_control_script.json",
        "agent_task_run.json",
        "agent_task_view.json",
        "attempt/attempt.json",
        "attempt/final.diff",
        "attempt/trace.jsonl",
        "candidate.patch",
        "decoding_config.json",
        "error.txt",
        "prompt_loop_result.json",
        "run_manifest.json",
    }.issubset(set(replay_records[0]["artifact_matches"]))
    assert (tmp_path / "replay_run/agent_task_run/agent_task_run.json").is_file()
    validate_trace_file(tmp_path / "replay_run/trace.jsonl")


def test_run_replay_dispatches_eval_agent_attempt_artifact(tmp_path: Path) -> None:
    source_eval_dir = tmp_path / "source_eval"
    source_agent_attempt_dir = (
        source_eval_dir / "attempts/toy_python_fix_001__attempt_001"
    )
    _write_agent_control_source_artifact(
        TOY_HAPPY_AGENT_CONTROL,
        source_agent_attempt_dir,
    )
    source_eval_dir.mkdir(parents=True, exist_ok=True)
    (source_eval_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "artifact_version": "eval_run_v0",
                "eval_run_id": "eval_agent_001",
                "attempts": [
                    {
                        "task_id": "toy_python_fix_001",
                        "artifact_dir": "attempts/toy_python_fix_001__attempt_001",
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")

    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_records[0]["comparison_type"] == "agent_task_run"
    assert (
        replay_records[0]["source_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert (
        replay_records[0]["replay_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert (
        tmp_path
        / "replay_run/attempts/toy_python_fix_001__attempt_001/agent_task_run.json"
    ).is_file()
    validate_trace_file(tmp_path / "replay_run/trace.jsonl")


def test_run_replay_detects_agent_trajectory_artifact_mismatch(
    tmp_path: Path,
) -> None:
    source_agent_dir = tmp_path / "source_agent"
    _write_agent_control_source_artifact(TOY_HAPPY_AGENT_CONTROL, source_agent_dir)
    prompt_loop_path = source_agent_dir / "prompt_loop_result.json"
    prompt_loop_result = json.loads(prompt_loop_path.read_text())
    prompt_loop_result["messages"][0]["content"] += "\ndeterministic tamper"
    prompt_loop_path.write_text(json.dumps(prompt_loop_result, indent=2) + "\n")

    replay_run = run_replay(source_agent_dir, tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "MISMATCH"
    assert replay_result["status"] == "MISMATCH"
    assert replay_result["matched_attempts"] == 0
    assert replay_result["mismatched_attempts"] == 1
    assert replay_records[0]["comparison_type"] == "agent_task_run"
    assert replay_records[0]["matched"] is False
    assert replay_records[0]["field_matches"] == AGENT_FIELD_MATCHES
    assert replay_records[0]["artifact_matches"]["prompt_loop_result.json"] is False


def test_run_replay_rejects_replay_artifact_input(tmp_path: Path) -> None:
    run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "source_run")
    run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    replay_run = run_replay(tmp_path / "replay_run", tmp_path / "nested_replay")
    replay_result = json.loads(
        (tmp_path / "nested_replay/replay_result.json").read_text()
    )

    assert replay_run.status == "REPLAY_ERROR"
    assert replay_result["status"] == "REPLAY_ERROR"
    assert replay_result["error_count"] == 1
