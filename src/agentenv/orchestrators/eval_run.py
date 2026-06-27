import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import xxhash

from agentenv.evals.schema import EvalConfig, EvalPolicy
from agentenv.evals.resolve import (
    scorer_control_patch_path,
    resolve_eval_tasks,
    select_policy,
)
from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.replay.runner import ReplayRun, run_replay
from agentenv.tracing.schema import TRACE_SCHEMA_VERSION, TraceEventType


EVAL_RUN_ARTIFACT_VERSION = "eval_run_v0"
EVAL_MATRIX_ARTIFACT_VERSION = "eval_matrix_v0"
TraceEvent = dict[str, object]


@dataclass(frozen=True)
class EvalAttemptRecord:
    task_id: str
    attempt_index: int
    attempt_dir: Path
    result: AttemptResult


@dataclass(frozen=True)
class EvalRun:
    eval_run_id: str
    config: EvalConfig
    config_path: Path
    config_hash: str
    policy: str
    out_dir: Path
    created_at: str
    attempts: list[EvalAttemptRecord]


@dataclass(frozen=True)
class EvalMatrixRun:
    eval_matrix_id: str
    config: EvalConfig
    config_path: Path
    config_hash: str
    out_dir: Path
    created_at: str
    policy_runs: list[EvalRun]
    replay_runs: list["EvalMatrixReplayRecord"]


@dataclass(frozen=True)
class EvalMatrixReplayRecord:
    policy: str
    replay_index: int
    replay_dir: Path
    replay_run: ReplayRun


def run_eval_config(config_path: Path, policy: str, out_dir: Path) -> EvalRun:
    config_path = config_path.resolve()
    out_dir = out_dir.resolve()
    config = load_eval_config(config_path)
    validate_eval_config_paths(config, config_path)
    selected_policy = select_policy(config, policy)
    if selected_policy.type != "scorer_control_patch":
        raise NotImplementedError(
            "agent_control_script eval execution is not implemented yet"
        )
    config_hash = _hash_file(config_path)
    eval_run_id = f"eval_{uuid4().hex}"
    created_at = _utc_now()

    out_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir = out_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    resolved_tasks = resolve_eval_tasks(config, config_path)
    trace_events: list[TraceEvent] = []
    base_provenance = _eval_provenance(
        eval_run_id,
        config_hash,
        config.name,
        policy=policy,
    )
    _append_trace(
        trace_events,
        base_provenance,
        "eval_started",
        input_payload={
            "config_path": str(config_path),
            "policy": policy,
            "split": config.split,
            "task_count": len(resolved_tasks),
            "attempts_per_task": config.attempts,
        },
    )

    attempt_records: list[EvalAttemptRecord] = []
    for task_index, task in enumerate(resolved_tasks):
        task_provenance = _eval_provenance(
            eval_run_id,
            config_hash,
            config.name,
            policy=policy,
            task_id=task.task_id,
            task_index=task_index,
        )
        _append_trace(
            trace_events,
            task_provenance,
            "eval_task_started",
            input_payload={
                "task_manifest_path": str(task.manifest_path),
            },
        )
        submission_path = scorer_control_patch_path(
            task.manifest_path.parent,
            task.manifest,
            selected_policy.control,
        )
        task_attempt_records: list[EvalAttemptRecord] = []

        for attempt_index in range(config.attempts):
            attempt_dir = (
                attempts_dir / f"{task.task_id}__attempt_{attempt_index + 1:03d}"
            )
            attempt_provenance = _eval_provenance(
                eval_run_id,
                config_hash,
                config.name,
                policy=policy,
                task_id=task.task_id,
                task_index=task_index,
                attempt_index=attempt_index,
            )
            artifact_dir_ref = str(attempt_dir.relative_to(out_dir))
            _append_trace(
                trace_events,
                attempt_provenance,
                "eval_attempt_started",
                input_payload={
                    "attempt_artifact_dir": artifact_dir_ref,
                    "submission_path": str(submission_path),
                },
            )
            attempt_run = run_and_persist_patch_attempt_to_dir(
                task.manifest_path,
                submission_path,
                attempt_dir,
            )
            attempt_record = EvalAttemptRecord(
                task_id=task.task_id,
                attempt_index=attempt_index,
                attempt_dir=attempt_dir,
                result=attempt_run.result,
            )
            attempt_records.append(attempt_record)
            task_attempt_records.append(attempt_record)
            _append_trace(
                trace_events,
                _eval_provenance(
                    eval_run_id,
                    config_hash,
                    config.name,
                    policy=policy,
                    task_id=task.task_id,
                    task_index=task_index,
                    attempt_index=attempt_index,
                    attempt_id=attempt_run.result.attempt_id,
                ),
                "eval_attempt_finished",
                output_payload={
                    "status": attempt_run.result.status,
                    "public_status": attempt_run.result.public_status,
                    "hidden_status": attempt_run.result.hidden_status,
                    "error_class": attempt_run.result.error_class,
                    "final_diff_hash": attempt_run.result.final_diff_hash,
                },
                payload_refs={
                    "attempt": f"{artifact_dir_ref}/attempt.json",
                    "attempt_trace": f"{artifact_dir_ref}/trace.jsonl",
                },
            )

        _append_trace(
            trace_events,
            task_provenance,
            "eval_task_finished",
            output_payload={
                "attempt_count": len(task_attempt_records),
                "status_counts": _status_counts(task_attempt_records),
            },
        )

    eval_run = EvalRun(
        eval_run_id=eval_run_id,
        config=config,
        config_path=config_path,
        config_hash=config_hash,
        policy=policy,
        out_dir=out_dir,
        created_at=created_at,
        attempts=attempt_records,
    )
    _append_trace(
        trace_events,
        base_provenance,
        "eval_finished",
        output_payload={
            "attempt_count": len(eval_run.attempts),
            "status_counts": _status_counts(eval_run.attempts),
        },
        payload_refs={"run_manifest": "run_manifest.json"},
    )
    _write_eval_trace(eval_run, trace_events)
    _write_eval_run_manifest(eval_run)
    return eval_run


def run_eval_config_all_policies(
    config_path: Path,
    out_dir: Path,
) -> EvalMatrixRun:
    config_path = config_path.resolve()
    out_dir = out_dir.resolve()
    config = load_eval_config(config_path)
    validate_eval_config_paths(config, config_path)
    config_hash = _hash_file(config_path)
    eval_matrix_id = f"eval_matrix_{uuid4().hex}"
    created_at = _utc_now()

    out_dir.mkdir(parents=True, exist_ok=True)
    policies_dir = out_dir / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)

    policy_runs = [
        run_eval_config(config_path, policy, policies_dir / policy)
        for policy in config.policies
    ]
    replay_runs = _replay_configured_policy_runs(config, policy_runs, out_dir)
    eval_matrix = EvalMatrixRun(
        eval_matrix_id=eval_matrix_id,
        config=config,
        config_path=config_path,
        config_hash=config_hash,
        out_dir=out_dir,
        created_at=created_at,
        policy_runs=policy_runs,
        replay_runs=replay_runs,
    )
    _write_eval_matrix_manifest(eval_matrix)
    return eval_matrix


def _replay_configured_policy_runs(
    config: EvalConfig,
    policy_runs: list[EvalRun],
    out_dir: Path,
) -> list[EvalMatrixReplayRecord]:
    if not config.replay.enabled:
        return []

    replays_dir = out_dir / "replays"
    replay_records: list[EvalMatrixReplayRecord] = []
    for policy_run in policy_runs:
        policy = config.policies[policy_run.policy]
        if not _should_replay_policy(config, policy):
            continue
        for replay_index in range(config.replay.repeats):
            replay_dir = (
                replays_dir
                / f"{policy_run.policy}__replay_{replay_index + 1:03d}"
            )
            replay_run = run_replay(policy_run.out_dir, replay_dir)
            replay_records.append(
                EvalMatrixReplayRecord(
                    policy=policy_run.policy,
                    replay_index=replay_index,
                    replay_dir=replay_dir,
                    replay_run=replay_run,
                )
            )
    return replay_records


def _should_replay_policy(config: EvalConfig, policy: EvalPolicy) -> bool:
    if config.replay.scope == "control_policies":
        return policy.type in {"scorer_control_patch", "agent_control_script"}
    return False


def _write_eval_trace(eval_run: EvalRun, trace_events: list[TraceEvent]) -> Path:
    trace_path = eval_run.out_dir / "trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in trace_events)
    )
    return trace_path


def _write_eval_run_manifest(eval_run: EvalRun) -> Path:
    manifest_path = eval_run.out_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(
            _eval_run_manifest(eval_run),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return manifest_path


def _write_eval_matrix_manifest(eval_matrix: EvalMatrixRun) -> Path:
    manifest_path = eval_matrix.out_dir / "eval_matrix_manifest.json"
    manifest_path.write_text(
        json.dumps(
            _eval_matrix_manifest(eval_matrix),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return manifest_path


def _eval_run_manifest(eval_run: EvalRun) -> dict[str, object]:
    return {
        "artifact_version": EVAL_RUN_ARTIFACT_VERSION,
        "eval_run_id": eval_run.eval_run_id,
        "created_at": eval_run.created_at,
        "config_path": str(eval_run.config_path),
        "config_hash": eval_run.config_hash,
        "config_name": eval_run.config.name,
        "task_pack": eval_run.config.task_pack,
        "split": eval_run.config.split,
        "policy": eval_run.policy,
        "attempt_count": len(eval_run.attempts),
        "status_counts": _status_counts(eval_run.attempts),
        "artifacts": {
            "trace": "trace.jsonl",
            "attempts": "attempts",
        },
        "attempts": [
            {
                "task_id": attempt.task_id,
                "attempt_index": attempt.attempt_index,
                "attempt_run_id": attempt.result.run_id,
                "attempt_id": attempt.result.attempt_id,
                "status": attempt.result.status,
                "public_status": attempt.result.public_status,
                "hidden_status": attempt.result.hidden_status,
                "final_diff_hash": attempt.result.final_diff_hash,
                "artifact_dir": str(attempt.attempt_dir.relative_to(eval_run.out_dir)),
            }
            for attempt in eval_run.attempts
        ],
    }


def _eval_matrix_manifest(eval_matrix: EvalMatrixRun) -> dict[str, object]:
    policy_attempt_counts = {
        policy_run.policy: len(policy_run.attempts)
        for policy_run in eval_matrix.policy_runs
    }
    artifacts = {
        "policies": "policies",
    }
    if eval_matrix.replay_runs:
        artifacts["replays"] = "replays"

    return {
        "artifact_version": EVAL_MATRIX_ARTIFACT_VERSION,
        "eval_matrix_id": eval_matrix.eval_matrix_id,
        "created_at": eval_matrix.created_at,
        "config_path": str(eval_matrix.config_path),
        "config_hash": eval_matrix.config_hash,
        "config_name": eval_matrix.config.name,
        "task_pack": eval_matrix.config.task_pack,
        "split": eval_matrix.config.split,
        "tasks": eval_matrix.config.tasks,
        "policy_count": len(eval_matrix.policy_runs),
        "attempt_count": sum(policy_attempt_counts.values()),
        "status_counts": _matrix_status_counts(eval_matrix.policy_runs),
        "artifacts": artifacts,
        "policy_runs": [
            {
                "policy": policy_run.policy,
                "eval_run_id": policy_run.eval_run_id,
                "artifact_dir": str(
                    policy_run.out_dir.relative_to(eval_matrix.out_dir)
                ),
                "run_manifest": str(
                    (policy_run.out_dir / "run_manifest.json").relative_to(
                        eval_matrix.out_dir
                    )
                ),
                "attempt_count": len(policy_run.attempts),
                "status_counts": _status_counts(policy_run.attempts),
            }
            for policy_run in eval_matrix.policy_runs
        ],
        "replay_policy_scope": (
            eval_matrix.config.replay.scope
            if eval_matrix.config.replay.enabled
            else "not_run"
        ),
        "replay_repeats": (
            eval_matrix.config.replay.repeats
            if eval_matrix.config.replay.enabled
            else 0
        ),
        "replay_runs": [
            _eval_matrix_replay_record(eval_matrix, replay_record)
            for replay_record in eval_matrix.replay_runs
        ],
    }


def _eval_matrix_replay_record(
    eval_matrix: EvalMatrixRun,
    replay_record: EvalMatrixReplayRecord,
) -> dict[str, object]:
    matched_attempts = sum(
        1 for comparison in replay_record.replay_run.comparisons if comparison.matched
    )
    attempt_count = len(replay_record.replay_run.comparisons)
    return {
        "policy": replay_record.policy,
        "replay_index": replay_record.replay_index,
        "status": replay_record.replay_run.status,
        "artifact_dir": str(replay_record.replay_dir.relative_to(eval_matrix.out_dir)),
        "replay_manifest": str(
            (replay_record.replay_dir / "replay_manifest.json").relative_to(
                eval_matrix.out_dir
            )
        ),
        "replay_result": str(
            (replay_record.replay_dir / "replay_result.json").relative_to(
                eval_matrix.out_dir
            )
        ),
        "attempt_count": attempt_count,
        "matched_attempts": matched_attempts,
        "mismatched_attempts": attempt_count - matched_attempts,
        "error_count": 1 if replay_record.replay_run.status == "REPLAY_ERROR" else 0,
    }


def _status_counts(attempts: list[EvalAttemptRecord]) -> dict[str, int]:
    status_counts: dict[str, int] = {}
    for attempt in attempts:
        status_counts[attempt.result.status] = (
            status_counts.get(attempt.result.status, 0) + 1
        )
    return status_counts


def _matrix_status_counts(policy_runs: list[EvalRun]) -> dict[str, int]:
    status_counts: dict[str, int] = {}
    for policy_run in policy_runs:
        for status, count in _status_counts(policy_run.attempts).items():
            status_counts[status] = status_counts.get(status, 0) + count
    return status_counts


def _append_trace(
    trace_events: list[TraceEvent],
    provenance_config: dict[str, object],
    event_type: TraceEventType,
    *,
    input_payload: dict[str, object] | None = None,
    output_payload: dict[str, object] | None = None,
    payload_refs: dict[str, str] | None = None,
    payload_hashes: dict[str, str] | None = None,
) -> None:
    event: TraceEvent = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "event_index": len(trace_events),
        "timestamp_utc": _utc_now(),
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
    trace_events.append(event)


def _eval_provenance(
    eval_run_id: str,
    config_hash: str,
    config_name: str,
    *,
    policy: str | None = None,
    task_id: str | None = None,
    task_index: int | None = None,
    attempt_index: int | None = None,
    attempt_id: str | None = None,
) -> dict[str, object]:
    provenance: dict[str, object] = {
        "eval_run_id": eval_run_id,
        "config_hash": config_hash,
        "config_name": config_name,
    }
    if policy is not None:
        provenance["policy"] = policy
    if task_id is not None:
        provenance["task_id"] = task_id
    if task_index is not None:
        provenance["task_index"] = task_index
    if attempt_index is not None:
        provenance["attempt_index"] = attempt_index
    if attempt_id is not None:
        provenance["attempt_id"] = attempt_id
    return provenance


def _hash_file(path: Path) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(path.read_bytes())}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
