import json
from pathlib import Path

from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.replay.runner import run_replay
from agentenv.tracing.validate import load_trace_events, validate_trace_file


CONTROL_EVAL_CONFIG = Path("configs/eval/control_policies.yaml")


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
    assert (
        replay_records[0]["source_attempt_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert (
        replay_records[0]["replay_attempt_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert replay_records[0]["source_attempt_artifact_path"] == str(
        tmp_path / "source_run/attempts/toy_python_fix_001__attempt_001"
    )
    assert replay_records[0]["replay_attempt_artifact_path"] == str(
        tmp_path / "replay_run/attempts/toy_python_fix_001__attempt_001"
    )
    assert replay_records[0]["field_matches"] == {
        "error_class": True,
        "final_diff_hash": True,
        "hidden_status": True,
        "public_status": True,
        "status": True,
    }
    assert (
        tmp_path
        / "replay_run/attempts/toy_python_fix_001__attempt_001/attempt.json"
    ).is_file()
    validate_trace_file(tmp_path / "replay_run/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "replay_run/trace.jsonl")
    assert trace_events[0].schema_version == "trace_v0"
    assert trace_events[0].event_type == "replay_started"
    assert trace_events[0].provenance_config["replay_id"] == replay_run.replay_id
    assert (
        trace_events[1].provenance_config["source_eval_run_id"]
        == source_run.eval_run_id
    )


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
