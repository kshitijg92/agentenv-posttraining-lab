import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.orchestrators.attempt import AttemptResult, AttemptRun
from agentenv.security.secrets import redact_jsonable, redact_secrets
from agentenv.tracing.schema import TRACE_SCHEMA_VERSION, TraceEventType


TraceEvent = dict[str, object]
SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION = "scorer_attempt_artifact_v0"


@dataclass(frozen=True)
class AttemptArtifactPaths:
    manifest_json: Path
    attempt_json: Path
    stdout_txt: Path
    stderr_txt: Path
    error_txt: Path
    trace_jsonl: Path
    final_diff: Path


def write_attempt_result(result: AttemptResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    attempt_path = out_dir / "attempt.json"
    attempt_path.write_text(_redacted_model_json(result))
    return attempt_path


def write_attempt_artifacts(
    attempt_run: AttemptRun, out_dir: Path
) -> AttemptArtifactPaths:
    out_dir = prepare_artifact_output_dir(out_dir)
    manifest_path = out_dir / MANIFEST_FILENAME
    attempt_path = write_attempt_result(attempt_run.result, out_dir)
    stdout_path = out_dir / "stdout.txt"
    stderr_path = out_dir / "stderr.txt"
    error_path = out_dir / "error.txt"
    trace_path = out_dir / "trace.jsonl"
    final_diff_path = out_dir / "final.diff"

    stdout_path.write_text(
        redact_secrets(
            _join_streams(result.stdout for result in attempt_run.command_results)
        )
    )
    stderr_path.write_text(
        redact_secrets(
            _join_streams(result.stderr for result in attempt_run.command_results)
        )
    )
    error_path.write_text(redact_secrets(_error_text(attempt_run)))
    trace_path.write_text(_trace_jsonl(attempt_run))
    final_diff_path.write_text(attempt_run.final_diff)
    manifest_path.write_text(
        json.dumps(
            redact_jsonable(_run_manifest(attempt_run)),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    return AttemptArtifactPaths(
        manifest_json=manifest_path,
        attempt_json=attempt_path,
        stdout_txt=stdout_path,
        stderr_txt=stderr_path,
        error_txt=error_path,
        trace_jsonl=trace_path,
        final_diff=final_diff_path,
    )


def _join_streams(streams: Iterable[str]) -> str:
    chunks = [stream for stream in streams if stream]
    if not chunks:
        return ""
    return "\n".join(chunks) + "\n"


def _error_text(attempt_run: AttemptRun) -> str:
    if attempt_run.error_details is None:
        return ""

    return (
        f"Error class: {attempt_run.error_details.error_class}\n"
        f"Message: {attempt_run.error_details.message}\n"
        "\n"
        "Traceback:\n"
        f"{attempt_run.error_details.traceback}"
    )


def _trace_jsonl(attempt_run: AttemptRun) -> str:
    events: list[TraceEvent] = []
    base_provenance = _attempt_provenance(attempt_run.result)
    _append_trace(
        events,
        base_provenance,
        "attempt_started",
        timestamp_utc=attempt_run.result.started_at,
        input_payload={
            "task_manifest_path": attempt_run.result.task_manifest_path,
            "submission_path": attempt_run.result.submission_path,
            "orchestrator_version": attempt_run.result.orchestrator_version,
        },
    )

    for command in attempt_run.commands:
        _append_trace(
            events,
            {
                **base_provenance,
                "phase": command.phase,
                "name": command.name,
            },
            "command_finished",
            timestamp_utc=attempt_run.result.ended_at,
            input_payload={"command": command.result.command},
            output_payload={
                "returncode": command.result.returncode,
                "stdout_bytes": len(command.result.stdout.encode()),
                "stderr_bytes": len(command.result.stderr.encode()),
            },
            payload_refs={"stdout": "stdout.txt", "stderr": "stderr.txt"},
        )

    payload_refs = {"final_diff": "final.diff"}
    if attempt_run.error_details is not None:
        payload_refs["error"] = "error.txt"

    _append_trace(
        events,
        base_provenance,
        "attempt_finished",
        timestamp_utc=attempt_run.result.ended_at,
        output_payload={
            "status": attempt_run.result.status,
            "public_status": attempt_run.result.public_status,
            "hidden_status": attempt_run.result.hidden_status,
            "error_class": attempt_run.result.error_class,
            "duration_ms": attempt_run.result.duration_ms,
            "final_diff_hash": attempt_run.result.final_diff_hash,
        },
        payload_refs=payload_refs,
        payload_hashes=(
            {"final_diff": attempt_run.result.final_diff_hash}
            if attempt_run.result.final_diff_hash is not None
            else None
        ),
    )
    return (
        "\n".join(
            json.dumps(redact_jsonable(event), sort_keys=True) for event in events
        )
        + "\n"
    )


def _redacted_model_json(result: AttemptResult) -> str:
    return json.dumps(redact_jsonable(result.model_dump(mode="json")), indent=2) + "\n"


def _append_trace(
    events: list[TraceEvent],
    provenance_config: dict[str, object],
    event_type: TraceEventType,
    *,
    timestamp_utc: str | None = None,
    input_payload: dict[str, object] | None = None,
    output_payload: dict[str, object] | None = None,
    payload_refs: dict[str, str] | None = None,
    payload_hashes: dict[str, str] | None = None,
) -> None:
    event: TraceEvent = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "event_index": len(events),
        "timestamp_utc": timestamp_utc or _utc_now(),
        "event_type": event_type,
        "provenance_config": provenance_config,
    }
    if input_payload is not None:
        event["input_payload"] = input_payload
    if output_payload is not None:
        event["output_payload"] = output_payload
    if payload_refs is not None:
        event["payload_refs"] = payload_refs
    if payload_hashes is not None:
        event["payload_hashes"] = payload_hashes
    events.append(event)


def _attempt_provenance(result: AttemptResult) -> dict[str, object]:
    return {
        "run_id": result.run_id,
        "attempt_id": result.attempt_id,
        "task_id": result.task_id,
    }


def _run_manifest(attempt_run: AttemptRun) -> dict[str, object]:
    return {
        "artifact_type": ArtifactType.SCORER_ATTEMPT,
        "artifact_schema_version": SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
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
            "error": "error.txt",
            "trace": "trace.jsonl",
            "final_diff": "final.diff",
        },
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
