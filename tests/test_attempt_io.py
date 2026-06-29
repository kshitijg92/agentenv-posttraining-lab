import json
from pathlib import Path

import pytest

import agentenv.orchestrators.attempt as attempt_module
from agentenv.orchestrators.attempt import (
    AttemptCommand,
    AttemptErrorDetails,
    AttemptResult,
    AttemptRun,
    run_patch_attempt,
)
from agentenv.orchestrators.attempt_io import write_attempt_artifacts
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.runners.diff_runner import hash_diff
from agentenv.runners.command_runner import CommandResult
from agentenv.security.secrets import REDACTED_SECRET
from agentenv.tracing.schema import AttemptTraceProvenance
from agentenv.tracing.validate import load_trace_events, validate_trace_file


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
CANARY = "agentenv-canary-secret-000000000000"


def test_write_attempt_artifacts(tmp_path: Path) -> None:
    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/scorer_control_patches/oracle.patch",
        workspace_parent=tmp_path / "workspace_parent",
    )

    artifact_paths = write_attempt_artifacts(attempt_run, tmp_path / "out")
    run_manifest_data = json.loads(artifact_paths.run_manifest_json.read_text())
    attempt_data = json.loads(artifact_paths.attempt_json.read_text())

    assert artifact_paths.run_manifest_json == tmp_path / "out/run_manifest.json"
    assert artifact_paths.attempt_json == tmp_path / "out/attempt.json"
    assert artifact_paths.stdout_txt == tmp_path / "out/stdout.txt"
    assert artifact_paths.stderr_txt == tmp_path / "out/stderr.txt"
    assert artifact_paths.error_txt == tmp_path / "out/error.txt"
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
        "error": "error.txt",
        "trace": "trace.jsonl",
        "final_diff": "final.diff",
    }
    assert artifact_paths.error_txt.read_text() == ""
    assert "passed" in artifact_paths.stdout_txt.read_text()
    final_diff = artifact_paths.final_diff.read_text()
    assert "raise ValueError" in final_diff
    assert attempt_data["final_diff_hash"] == hash_diff(final_diff)

    validate_trace_file(artifact_paths.trace_jsonl)
    trace_events = load_trace_events(artifact_paths.trace_jsonl)
    assert trace_events[0].event_type == "attempt_started"
    first_provenance = trace_events[0].provenance_config
    assert isinstance(first_provenance, AttemptTraceProvenance)
    assert first_provenance.attempt_id == attempt_data["attempt_id"]
    assert trace_events[0].input_payload is not None
    assert (
        trace_events[0].input_payload["task_manifest_path"]
        == attempt_data["task_manifest_path"]
    )
    assert trace_events[-1].event_type == "attempt_finished"
    assert trace_events[-1].output_payload is not None
    assert trace_events[-1].output_payload["status"] == "PASS"
    assert trace_events[-1].payload_refs == {"final_diff": "final.diff"}
    assert trace_events[-1].payload_hashes == {
        "final_diff": attempt_data["final_diff_hash"]
    }
    command_phases: list[str | None] = []
    for event in trace_events:
        if event.event_type == "command_finished":
            provenance = event.provenance_config
            assert isinstance(provenance, AttemptTraceProvenance)
            command_phases.append(provenance.phase)
    assert command_phases == ["patch_apply", "public_check", "hidden_score"]


def test_write_attempt_artifacts_preserves_orchestrator_error_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_workspace_error(*args: object, **kwargs: object) -> None:
        raise ValueError("synthetic workspace failure")

    monkeypatch.setattr(
        attempt_module,
        "prepare_agent_workspace",
        raise_workspace_error,
    )

    attempt_run = run_patch_attempt(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/scorer_control_patches/oracle.patch",
        workspace_parent=tmp_path / "workspace_parent",
    )

    artifact_paths = write_attempt_artifacts(attempt_run, tmp_path / "out")
    error_text = artifact_paths.error_txt.read_text()

    assert attempt_run.result.status == "ORCHESTRATOR_ERROR"
    assert "Error class: ValueError" in error_text
    assert "Message: synthetic workspace failure" in error_text
    assert "Traceback:" in error_text
    assert "raise_workspace_error" in error_text

    trace_events = load_trace_events(artifact_paths.trace_jsonl)
    assert trace_events[-1].event_type == "attempt_finished"
    assert trace_events[-1].payload_refs == {
        "error": "error.txt",
        "final_diff": "final.diff",
    }


def test_write_attempt_artifacts_redacts_secret_canary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", CANARY)
    attempt_run = AttemptRun(
        result=AttemptResult(
            run_id="run_001",
            task_id="task_001",
            task_manifest_path="tasks/task.yaml",
            attempt_id="attempt_001",
            submission_path="submissions/attempt.patch",
            status="ORCHESTRATOR_ERROR",
            public_status="NOT_RUN",
            hidden_status="NOT_RUN",
            error_class="ValueError",
            started_at="2026-06-19T00:00:00Z",
            ended_at="2026-06-19T00:00:01Z",
            duration_ms=1,
            final_diff_hash=None,
            orchestrator_version="attempt_v0",
        ),
        commands=[
            AttemptCommand(
                phase="public_check",
                name="leaky_check",
                result=CommandResult(
                    command=["python", "-c", f"print('{CANARY}')"],
                    returncode=1,
                    stdout=f"stdout {CANARY}\n",
                    stderr=f"stderr {CANARY}\n",
                ),
            )
        ],
        final_diff="",
        error_details=AttemptErrorDetails(
            error_class="ValueError",
            message=f"message {CANARY}",
            traceback=f"traceback {CANARY}",
        ),
    )

    artifact_paths = write_attempt_artifacts(attempt_run, tmp_path / "out")
    written_text = "\n".join(
        path.read_text()
        for path in [
            artifact_paths.run_manifest_json,
            artifact_paths.attempt_json,
            artifact_paths.stdout_txt,
            artifact_paths.stderr_txt,
            artifact_paths.error_txt,
            artifact_paths.trace_jsonl,
        ]
    )

    assert CANARY not in written_text
    assert REDACTED_SECRET in artifact_paths.stdout_txt.read_text()
    assert REDACTED_SECRET in artifact_paths.stderr_txt.read_text()
    assert REDACTED_SECRET in artifact_paths.error_txt.read_text()
    assert REDACTED_SECRET in artifact_paths.trace_jsonl.read_text()


def test_run_and_persist_patch_attempt_to_dir(tmp_path: Path) -> None:
    attempt_run = run_and_persist_patch_attempt_to_dir(
        TOY_TASK_MANIFEST,
        TOY_TASK_MANIFEST.parent / "controls/scorer_control_patches/oracle.patch",
        tmp_path / "out",
    )

    attempt_data = json.loads((tmp_path / "out/attempt.json").read_text())

    assert attempt_run.result.status == "PASS"
    assert attempt_data["status"] == "PASS"
    assert (tmp_path / "out/run_manifest.json").is_file()
    assert (tmp_path / "out/trace.jsonl").is_file()
    assert (tmp_path / "out/final.diff").is_file()
