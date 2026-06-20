import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir


REPLAY_ARTIFACT_VERSION = "replay_v0"
SOURCE_EVAL_ARTIFACT_VERSION = "eval_run_v0"

ReplayStatus = Literal["PASS", "MISMATCH", "REPLAY_ERROR"]
ComparedField = Literal[
    "status",
    "public_status",
    "hidden_status",
    "error_class",
    "final_diff_hash",
]

COMPARED_FIELDS: tuple[ComparedField, ...] = (
    "status",
    "public_status",
    "hidden_status",
    "error_class",
    "final_diff_hash",
)


@dataclass(frozen=True)
class ReplayAttemptComparison:
    task_id: str
    source_attempt_id: str
    source_attempt_dir: Path
    replay_attempt_id: str
    replay_attempt_dir: Path
    field_matches: dict[ComparedField, bool]

    @property
    def matched(self) -> bool:
        return all(self.field_matches.values())


@dataclass(frozen=True)
class ReplayRun:
    replay_id: str
    status: ReplayStatus
    source_run_dir: Path
    out_dir: Path
    comparisons: list[ReplayAttemptComparison]


def run_replay(source_run_dir: Path, out_dir: Path) -> ReplayRun:
    source_run_dir = source_run_dir.resolve()
    out_dir = out_dir.resolve()
    replay_id = f"replay_{uuid4().hex}"
    created_at = _utc_now()
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_events: list[dict[str, object]] = []
    _append_trace(
        trace_events,
        replay_id,
        "replay_started",
        {"source_run_dir": str(source_run_dir), "out_dir": str(out_dir)},
    )

    try:
        source_manifest_path = source_run_dir / "run_manifest.json"
        source_manifest = _load_json_object(source_manifest_path)
        _require_eval_run_manifest(source_manifest, source_manifest_path)
        _append_trace(
            trace_events,
            replay_id,
            "source_run_manifest_loaded",
            {
                "source_manifest_path": str(source_manifest_path),
                "source_eval_run_id": source_manifest.get("eval_run_id"),
            },
        )

        comparisons = _replay_attempts(
            replay_id,
            source_run_dir,
            out_dir,
            source_manifest,
            trace_events,
        )
        status: ReplayStatus = (
            "PASS" if all(comparison.matched for comparison in comparisons) else "MISMATCH"
        )
    except Exception as exc:
        comparisons = []
        status = "REPLAY_ERROR"
        _append_trace(
            trace_events,
            replay_id,
            "replay_error",
            {"error_class": type(exc).__name__, "message": str(exc)},
        )
        source_manifest = {}

    replay_run = ReplayRun(
        replay_id=replay_id,
        status=status,
        source_run_dir=source_run_dir,
        out_dir=out_dir,
        comparisons=comparisons,
    )
    _write_replay_artifacts(
        replay_run,
        created_at,
        source_manifest,
        trace_events,
    )
    return replay_run


def _replay_attempts(
    replay_id: str,
    source_run_dir: Path,
    out_dir: Path,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
) -> list[ReplayAttemptComparison]:
    attempts = source_manifest.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError("Source eval run manifest is missing attempts list")

    comparisons: list[ReplayAttemptComparison] = []
    replay_attempts_dir = out_dir / "attempts"
    replay_attempts_dir.mkdir(parents=True, exist_ok=True)

    for raw_attempt in attempts:
        if not isinstance(raw_attempt, dict):
            raise ValueError("Source eval run manifest contains non-object attempt")
        comparison = _replay_one_attempt(
            replay_id,
            source_run_dir,
            replay_attempts_dir,
            raw_attempt,
            trace_events,
        )
        comparisons.append(comparison)
    return comparisons


def _replay_one_attempt(
    replay_id: str,
    source_run_dir: Path,
    replay_attempts_dir: Path,
    source_attempt_record: dict[str, object],
    trace_events: list[dict[str, object]],
) -> ReplayAttemptComparison:
    artifact_dir = _required_str(source_attempt_record, "artifact_dir")
    task_id = _required_str(source_attempt_record, "task_id")
    source_attempt_dir = source_run_dir / artifact_dir
    source_attempt = AttemptResult.model_validate(
        _load_json_object(source_attempt_dir / "attempt.json")
    )
    _append_trace(
        trace_events,
        replay_id,
        "source_attempt_loaded",
        {
            "task_id": task_id,
            "source_attempt_id": source_attempt.attempt_id,
            "source_attempt_dir": str(source_attempt_dir),
        },
    )

    replay_attempt_dir = replay_attempts_dir / Path(artifact_dir).name
    _append_trace(
        trace_events,
        replay_id,
        "fresh_attempt_started",
        {
            "task_id": task_id,
            "source_attempt_id": source_attempt.attempt_id,
            "replay_attempt_dir": str(replay_attempt_dir),
        },
    )
    replay_attempt_run = run_and_persist_patch_attempt_to_dir(
        Path(source_attempt.task_manifest_path),
        Path(source_attempt.submission_path),
        replay_attempt_dir,
    )
    replay_attempt = replay_attempt_run.result
    _append_trace(
        trace_events,
        replay_id,
        "fresh_attempt_finished",
        {
            "task_id": task_id,
            "source_attempt_id": source_attempt.attempt_id,
            "replay_attempt_id": replay_attempt.attempt_id,
            "status": replay_attempt.status,
        },
    )

    field_matches: dict[ComparedField, bool] = {
        field: getattr(source_attempt, field) == getattr(replay_attempt, field)
        for field in COMPARED_FIELDS
    }
    comparison = ReplayAttemptComparison(
        task_id=task_id,
        source_attempt_id=source_attempt.attempt_id,
        source_attempt_dir=source_attempt_dir,
        replay_attempt_id=replay_attempt.attempt_id,
        replay_attempt_dir=replay_attempt_dir,
        field_matches=field_matches,
    )
    _append_trace(
        trace_events,
        replay_id,
        "comparison_recorded",
        _comparison_record(comparison, source_run_dir, replay_attempts_dir.parent),
    )
    return comparison


def _write_replay_artifacts(
    replay_run: ReplayRun,
    created_at: str,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
) -> None:
    _append_trace(
        trace_events,
        replay_run.replay_id,
        "replay_finished",
        {
            "status": replay_run.status,
            "attempt_count": len(replay_run.comparisons),
            "matched_attempts": sum(
                1 for comparison in replay_run.comparisons if comparison.matched
            ),
        },
    )

    (replay_run.out_dir / "replay_manifest.json").write_text(
        json.dumps(
            _replay_manifest(replay_run, created_at, source_manifest),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (replay_run.out_dir / "replay_result.json").write_text(
        json.dumps(
            _replay_result(replay_run),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (replay_run.out_dir / "replay_results.jsonl").write_text(
        "".join(
            json.dumps(
                _comparison_record(
                    comparison,
                    replay_run.source_run_dir,
                    replay_run.out_dir,
                ),
                sort_keys=True,
            )
            + "\n"
            for comparison in replay_run.comparisons
        )
    )
    (replay_run.out_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in trace_events)
    )


def _replay_manifest(
    replay_run: ReplayRun,
    created_at: str,
    source_manifest: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_version": REPLAY_ARTIFACT_VERSION,
        "replay_id": replay_run.replay_id,
        "created_at": created_at,
        "source_run_dir": str(replay_run.source_run_dir),
        "source_eval_run_id": source_manifest.get("eval_run_id"),
        "source_artifact_version": source_manifest.get("artifact_version"),
        "artifacts": {
            "replay_result": "replay_result.json",
            "replay_results": "replay_results.jsonl",
            "trace": "trace.jsonl",
            "attempts": "attempts",
        },
    }


def _replay_result(replay_run: ReplayRun) -> dict[str, object]:
    matched_attempts = sum(
        1 for comparison in replay_run.comparisons if comparison.matched
    )
    attempt_count = len(replay_run.comparisons)
    return {
        "artifact_version": REPLAY_ARTIFACT_VERSION,
        "replay_id": replay_run.replay_id,
        "status": replay_run.status,
        "attempt_count": attempt_count,
        "matched_attempts": matched_attempts,
        "mismatched_attempts": attempt_count - matched_attempts,
        "error_count": 1 if replay_run.status == "REPLAY_ERROR" else 0,
    }


def _comparison_record(
    comparison: ReplayAttemptComparison,
    source_run_dir: Path,
    replay_out_dir: Path,
) -> dict[str, object]:
    return {
        "task_id": comparison.task_id,
        "source_attempt_id": comparison.source_attempt_id,
        "source_attempt_artifact_ref": str(
            comparison.source_attempt_dir.relative_to(source_run_dir)
        ),
        "source_attempt_artifact_path": str(comparison.source_attempt_dir),
        "replay_attempt_id": comparison.replay_attempt_id,
        "replay_attempt_artifact_ref": str(
            comparison.replay_attempt_dir.relative_to(replay_out_dir)
        ),
        "replay_attempt_artifact_path": str(comparison.replay_attempt_dir),
        "matched": comparison.matched,
        "field_matches": comparison.field_matches,
    }


def _load_json_object(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _require_eval_run_manifest(
    source_manifest: dict[str, object],
    source_manifest_path: Path,
) -> None:
    artifact_version = source_manifest.get("artifact_version")
    if artifact_version != SOURCE_EVAL_ARTIFACT_VERSION:
        raise ValueError(
            f"Replay input must be {SOURCE_EVAL_ARTIFACT_VERSION}, got "
            f"{artifact_version!r} at {source_manifest_path}"
        )


def _required_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected string field {key!r}")
    return value


def _append_trace(
    trace_events: list[dict[str, object]],
    replay_id: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    trace_events.append(
        {
            "event_index": len(trace_events),
            "event_type": event_type,
            "replay_id": replay_id,
            "timestamp_utc": _utc_now(),
            "payload": payload,
        }
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
