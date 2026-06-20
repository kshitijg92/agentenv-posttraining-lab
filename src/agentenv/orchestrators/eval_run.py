import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import xxhash

from agentenv.evals.schema import EvalConfig
from agentenv.evals.resolve import (
    control_patch_path,
    resolve_eval_tasks,
    select_policy,
)
from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir


EVAL_RUN_ARTIFACT_VERSION = "eval_run_v0"


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


def run_eval_config(config_path: Path, policy: str, out_dir: Path) -> EvalRun:
    config_path = config_path.resolve()
    out_dir = out_dir.resolve()
    config = load_eval_config(config_path)
    validate_eval_config_paths(config, config_path)
    selected_policy = select_policy(config, policy)
    eval_run_id = f"eval_{uuid4().hex}"
    created_at = _utc_now()

    out_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir = out_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    attempt_records: list[EvalAttemptRecord] = []
    for task in resolve_eval_tasks(config, config_path):
        submission_path = control_patch_path(
            task.manifest_path.parent,
            task.manifest,
            selected_policy.control,
        )

        for attempt_index in range(config.attempts):
            attempt_dir = (
                attempts_dir / f"{task.task_id}__attempt_{attempt_index + 1:03d}"
            )
            attempt_run = run_and_persist_patch_attempt_to_dir(
                task.manifest_path,
                submission_path,
                attempt_dir,
            )
            attempt_records.append(
                EvalAttemptRecord(
                    task_id=task.task_id,
                    attempt_index=attempt_index,
                    attempt_dir=attempt_dir,
                    result=attempt_run.result,
                )
            )

    eval_run = EvalRun(
        eval_run_id=eval_run_id,
        config=config,
        config_path=config_path,
        config_hash=_hash_file(config_path),
        policy=policy,
        out_dir=out_dir,
        created_at=created_at,
        attempts=attempt_records,
    )
    _write_eval_run_manifest(eval_run)
    return eval_run


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


def _eval_run_manifest(eval_run: EvalRun) -> dict[str, object]:
    status_counts: dict[str, int] = {}
    for attempt in eval_run.attempts:
        status_counts[attempt.result.status] = (
            status_counts.get(attempt.result.status, 0) + 1
        )

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
        "status_counts": status_counts,
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


def _hash_file(path: Path) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(path.read_bytes())}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
