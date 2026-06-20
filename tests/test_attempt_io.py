import json
from pathlib import Path

from agentenv.orchestrators.attempt import run_patch_attempt
from agentenv.orchestrators.attempt_io import write_attempt_artifacts
from agentenv.runners.diff_runner import hash_diff


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_write_attempt_artifacts(tmp_path: Path) -> None:
    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/oracle.patch",
        workspace_parent=tmp_path / "workspace_parent",
    )

    artifact_paths = write_attempt_artifacts(attempt_run, tmp_path / "out")
    run_manifest_data = json.loads(artifact_paths.run_manifest_json.read_text())
    attempt_data = json.loads(artifact_paths.attempt_json.read_text())

    assert artifact_paths.run_manifest_json == tmp_path / "out/run_manifest.json"
    assert artifact_paths.attempt_json == tmp_path / "out/attempt.json"
    assert artifact_paths.stdout_txt == tmp_path / "out/stdout.txt"
    assert artifact_paths.stderr_txt == tmp_path / "out/stderr.txt"
    assert artifact_paths.trace_jsonl == tmp_path / "out/trace.jsonl"
    assert artifact_paths.final_diff == tmp_path / "out/final.diff"
    assert attempt_data["task_id"] == "toy_python_fix_001"
    assert attempt_data["task_manifest_path"].endswith("toy_python_fix/task.yaml")
    assert attempt_data["status"] == "PASS"
    assert attempt_data["public_status"] == "PASS"
    assert attempt_data["hidden_status"] == "PASS"
    assert run_manifest_data["artifact_version"] == "run_artifacts_v0"
    assert run_manifest_data["run_id"] == attempt_data["run_id"]
    assert run_manifest_data["attempt_id"] == attempt_data["attempt_id"]
    assert run_manifest_data["status"] == attempt_data["status"]
    assert run_manifest_data["artifacts"] == {
        "attempt": "attempt.json",
        "stdout": "stdout.txt",
        "stderr": "stderr.txt",
        "trace": "trace.jsonl",
        "final_diff": "final.diff",
    }
    assert "passed" in artifact_paths.stdout_txt.read_text()
    final_diff = artifact_paths.final_diff.read_text()
    assert "raise ValueError" in final_diff
    assert attempt_data["final_diff_hash"] == hash_diff(final_diff)

    trace_events = [
        json.loads(line) for line in artifact_paths.trace_jsonl.read_text().splitlines()
    ]
    assert trace_events[0]["event"] == "attempt_started"
    assert trace_events[0]["task_manifest_path"] == attempt_data["task_manifest_path"]
    assert trace_events[-1]["event"] == "attempt_finished"
    assert trace_events[-1]["status"] == "PASS"
    assert trace_events[-1]["final_diff_ref"] == "final.diff"
    assert trace_events[-1]["final_diff_hash"] == attempt_data["final_diff_hash"]
    assert [
        event["phase"]
        for event in trace_events
        if event["event"] == "command_finished"
    ] == ["patch_apply", "public_check", "hidden_score"]
