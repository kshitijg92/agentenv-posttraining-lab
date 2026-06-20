import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from agentenv.orchestrators.attempt import AttemptResult, AttemptRun


TraceEvent = dict[str, object]


@dataclass(frozen=True)
class AttemptArtifactPaths:
    run_manifest_json: Path
    attempt_json: Path
    stdout_txt: Path
    stderr_txt: Path
    trace_jsonl: Path
    final_diff: Path


def write_attempt_result(result: AttemptResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    attempt_path = out_dir / "attempt.json"
    attempt_path.write_text(result.model_dump_json(indent=2) + "\n")
    return attempt_path


def write_attempt_artifacts(
    attempt_run: AttemptRun, out_dir: Path
) -> AttemptArtifactPaths:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path = out_dir / "run_manifest.json"
    attempt_path = write_attempt_result(attempt_run.result, out_dir)
    stdout_path = out_dir / "stdout.txt"
    stderr_path = out_dir / "stderr.txt"
    trace_path = out_dir / "trace.jsonl"
    final_diff_path = out_dir / "final.diff"

    stdout_path.write_text(
        _join_streams(result.stdout for result in attempt_run.command_results)
    )
    stderr_path.write_text(
        _join_streams(result.stderr for result in attempt_run.command_results)
    )
    trace_path.write_text(_trace_jsonl(attempt_run))
    final_diff_path.write_text(attempt_run.final_diff)
    run_manifest_path.write_text(
        json.dumps(
            _run_manifest(attempt_run),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    return AttemptArtifactPaths(
        run_manifest_json=run_manifest_path,
        attempt_json=attempt_path,
        stdout_txt=stdout_path,
        stderr_txt=stderr_path,
        trace_jsonl=trace_path,
        final_diff=final_diff_path,
    )


def _join_streams(streams: Iterable[str]) -> str:
    chunks = [stream for stream in streams if stream]
    if not chunks:
        return ""
    return "\n".join(chunks) + "\n"


def _trace_jsonl(attempt_run: AttemptRun) -> str:
    events: list[TraceEvent] = [
        {
            "event": "attempt_started",
            "run_id": attempt_run.result.run_id,
            "attempt_id": attempt_run.result.attempt_id,
            "task_id": attempt_run.result.task_id,
            "task_manifest_path": attempt_run.result.task_manifest_path,
            "submission_path": attempt_run.result.submission_path,
            "orchestrator_version": attempt_run.result.orchestrator_version,
            "started_at": attempt_run.result.started_at,
        }
    ]
    events.extend(
        {
            "event": "command_finished",
            "index": index,
            "phase": command.phase,
            "name": command.name,
            "command": command.result.command,
            "returncode": command.result.returncode,
            "stdout_bytes": len(command.result.stdout.encode()),
            "stderr_bytes": len(command.result.stderr.encode()),
            "stdout_ref": "stdout.txt",
            "stderr_ref": "stderr.txt",
        }
        for index, command in enumerate(attempt_run.commands)
    )
    events.append(
        {
            "event": "attempt_finished",
            "run_id": attempt_run.result.run_id,
            "attempt_id": attempt_run.result.attempt_id,
            "task_id": attempt_run.result.task_id,
            "status": attempt_run.result.status,
            "public_status": attempt_run.result.public_status,
            "hidden_status": attempt_run.result.hidden_status,
            "error_class": attempt_run.result.error_class,
            "final_diff_hash": attempt_run.result.final_diff_hash,
            "final_diff_ref": "final.diff",
            "ended_at": attempt_run.result.ended_at,
            "duration_ms": attempt_run.result.duration_ms,
        }
    )
    return "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n"


def _run_manifest(attempt_run: AttemptRun) -> dict[str, object]:
    return {
        "artifact_version": "run_artifacts_v0",
        "orchestrator_version": attempt_run.result.orchestrator_version,
        "run_id": attempt_run.result.run_id,
        "attempt_id": attempt_run.result.attempt_id,
        "task_id": attempt_run.result.task_id,
        "task_manifest_path": attempt_run.result.task_manifest_path,
        "submission_path": attempt_run.result.submission_path,
        "status": attempt_run.result.status,
        "artifacts": {
            "attempt": "attempt.json",
            "stdout": "stdout.txt",
            "stderr": "stderr.txt",
            "trace": "trace.jsonl",
            "final_diff": "final.diff",
        },
    }
