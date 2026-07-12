import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import xxhash

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.manifests import AGENT_ATTEMPT_ARTIFACT_REFS
from agentenv.artifacts.manifests import EVAL_RUN_ARTIFACT_REFS
from agentenv.artifacts.manifests import EVAL_RUN_ARTIFACT_SCHEMA_VERSION
from agentenv.artifacts.manifests import EVAL_SUITE_ARTIFACT_REFS
from agentenv.artifacts.manifests import EVAL_SUITE_ARTIFACT_SCHEMA_VERSION
from agentenv.artifacts.manifests import EvalRunManifest
from agentenv.artifacts.manifests import EvalSuiteManifest
from agentenv.artifacts.manifests import REPLAY_RUN_ARTIFACT_REFS
from agentenv.artifacts.manifests import SCORER_ATTEMPT_ARTIFACT_REFS
from agentenv.artifacts.payloads import EvalTaskHashes
from agentenv.audits.runtime import (
    capture_harness_runtime_provenance,
    harness_repo_root,
)
from agentenv.audits.schema import HarnessRuntimeProvenance
from agentenv.controls.agent_control_scripts import (
    AgentControlScriptCase,
    load_agent_control_script_case,
)
from agentenv.evals.schema import (
    AGENT_CONTROL_LAYER,
    AGENT_CONTROL_SCRIPT_POLICY_TYPE,
    AGENT_MODEL_POLICY_TYPE,
    AGENT_POLICY_FAMILY,
    CONTROL_POLICY_FAMILY,
    SCORER_CONTROL_LAYER,
    SCORER_CONTROL_PATCH_POLICY_TYPE,
    EvalConfig,
)
from agentenv.evals.resolve import (
    agent_control_script_path,
    ResolvedEvalTask,
    resolve_config_file_ref,
    resolve_task_pack_path,
    resolve_eval_tasks,
    scorer_control_patch_path,
    select_policy,
)
from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.ids import (
    new_eval_attempt_id,
    new_eval_run_id,
    new_eval_suite_id,
)
from agentenv.models.config import load_decoding_config, load_model_config
from agentenv.models.factory import build_model_client
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.agent_task_run import (
    decoding_config_provenance_artifact,
    model_config_provenance_artifact,
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.attempt import AttemptResult, AttemptStatus, CheckStatus
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.tasks.hashing import build_eval_task_hashes
from agentenv.tracing.schema import TRACE_SCHEMA_VERSION, TraceEventType


if TYPE_CHECKING:
    from agentenv.replay.runner import ReplayRun


TraceEvent = dict[str, object]


@dataclass(frozen=True)
class ScorerAttemptSummary:
    scorer_attempt_id: str
    status: AttemptStatus
    public_status: CheckStatus
    hidden_status: CheckStatus
    error_class: str | None
    final_diff_hash: str | None
    duration_ms: int


@dataclass(frozen=True)
class AgentAttemptSummary:
    agent_attempt_id: str
    status: str
    prompt_loop_status: str | None
    error_class: str | None
    candidate_patch_hash: str | None
    duration_ms: int
    scorer_attempt: ScorerAttemptSummary | None


@dataclass(frozen=True)
class EvalAttemptRecord:
    eval_attempt_id: str
    task_id: str
    attempt_index: int
    attempt_dir: Path
    artifact_type: str
    artifact_schema_version: str
    scorer: ScorerAttemptSummary | None
    agent: AgentAttemptSummary | None


@dataclass(frozen=True)
class ArtifactIdentity:
    artifact_type: str
    artifact_schema_version: str


@dataclass(frozen=True)
class EvalRun:
    eval_run_id: str
    config: EvalConfig
    config_path: Path
    config_hash: str
    task_hashes: EvalTaskHashes
    runtime_provenance: HarnessRuntimeProvenance
    policy: str
    out_dir: Path
    created_at: str
    attempts: list[EvalAttemptRecord]


@dataclass(frozen=True)
class EvalMatrixRun:
    eval_suite_id: str
    config: EvalConfig
    config_path: Path
    config_hash: str
    task_hashes: EvalTaskHashes
    runtime_provenance: HarnessRuntimeProvenance
    out_dir: Path
    created_at: str
    policy_runs: list[EvalRun]
    replay_runs: list["EvalMatrixReplayRecord"]


@dataclass(frozen=True)
class EvalMatrixReplayRecord:
    policy: str
    replay_index: int
    replay_dir: Path
    replay_run: "ReplayRun"


def run_eval_config(
    config_path: Path,
    policy: str,
    out_dir: Path,
    *,
    overwrite: bool = False,
    runtime_provenance: HarnessRuntimeProvenance | None = None,
) -> EvalRun:
    config_path = config_path.resolve()
    config = load_eval_config(config_path)
    validate_eval_config_paths(config, config_path)
    selected_policy = select_policy(config, policy)
    config_hash = _hash_file(config_path)
    task_pack_path = resolve_task_pack_path(config, config_path)
    task_hashes = build_eval_task_hashes(task_pack_path, config.tasks)
    if runtime_provenance is None:
        runtime_provenance = capture_harness_runtime_provenance(harness_repo_root())
    eval_run_id = new_eval_run_id()
    created_at = _utc_now()

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    attempts_dir = out_dir / EVAL_RUN_ARTIFACT_REFS["attempts"]
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
            "attempts_per_task": selected_policy.attempts,
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
        task_attempt_records: list[EvalAttemptRecord] = []

        for attempt_index in range(selected_policy.attempts):
            eval_attempt_id = new_eval_attempt_id()
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
                eval_attempt_id=eval_attempt_id,
            )
            artifact_dir_ref = str(attempt_dir.relative_to(out_dir))
            scorer_attempt_id: str | None = None
            agent_attempt_id: str | None = None
            if selected_policy.type == SCORER_CONTROL_PATCH_POLICY_TYPE:
                submission_path = scorer_control_patch_path(
                    task.manifest_path.parent,
                    task.manifest,
                    selected_policy.control,
                )
                started_payload: dict[str, object] = {
                    "attempt_artifact_dir": artifact_dir_ref,
                    "submission_path": str(submission_path),
                }
                _append_trace(
                    trace_events,
                    attempt_provenance,
                    "eval_attempt_started",
                    input_payload=started_payload,
                )
                attempt_record = _run_scorer_eval_attempt(
                    task=task,
                    submission_path=submission_path,
                    eval_attempt_id=eval_attempt_id,
                    attempt_index=attempt_index,
                    attempt_dir=attempt_dir,
                )
                scorer_attempt_id = _required_scorer(attempt_record).scorer_attempt_id
                payload_refs = {
                    "attempt": f"{artifact_dir_ref}/attempt.json",
                    "attempt_trace": f"{artifact_dir_ref}/trace.jsonl",
                }
            elif selected_policy.type == AGENT_CONTROL_SCRIPT_POLICY_TYPE:
                script_path = agent_control_script_path(
                    task.manifest_path.parent,
                    task.manifest,
                    selected_policy.control,
                )
                started_payload = {
                    "attempt_artifact_dir": artifact_dir_ref,
                    "agent_control_script_path": str(script_path),
                }
                _append_trace(
                    trace_events,
                    attempt_provenance,
                    "eval_attempt_started",
                    input_payload=started_payload,
                )
                control_case = load_agent_control_script_case(script_path)
                attempt_record = _run_agent_control_eval_attempt(
                    task=task,
                    control_case=control_case,
                    eval_attempt_id=eval_attempt_id,
                    attempt_index=attempt_index,
                    attempt_dir=attempt_dir,
                )
                agent_attempt = _required_agent(attempt_record)
                agent_attempt_id = agent_attempt.agent_attempt_id
                if agent_attempt.scorer_attempt is not None:
                    scorer_attempt_id = agent_attempt.scorer_attempt.scorer_attempt_id
                payload_refs = _agent_eval_attempt_payload_refs(
                    artifact_dir_ref,
                    attempt_dir,
                )
            elif selected_policy.type == AGENT_MODEL_POLICY_TYPE:
                model_config_path = resolve_config_file_ref(
                    config_path,
                    selected_policy.model_config_path,
                    field_name="model_config",
                )
                decoding_config_path = resolve_config_file_ref(
                    config_path,
                    selected_policy.decoding_config_path,
                    field_name="decoding_config",
                )
                started_payload = {
                    "attempt_artifact_dir": artifact_dir_ref,
                    "model_config_path": str(model_config_path),
                    "model_config_hash": _hash_file(model_config_path),
                    "decoding_config_path": str(decoding_config_path),
                    "decoding_config_hash": _hash_file(decoding_config_path),
                }
                _append_trace(
                    trace_events,
                    attempt_provenance,
                    "eval_attempt_started",
                    input_payload=started_payload,
                )
                attempt_record = _run_agent_model_eval_attempt(
                    task=task,
                    model_config_path=model_config_path,
                    decoding_config_path=decoding_config_path,
                    eval_attempt_id=eval_attempt_id,
                    attempt_index=attempt_index,
                    attempt_dir=attempt_dir,
                )
                agent_attempt = _required_agent(attempt_record)
                agent_attempt_id = agent_attempt.agent_attempt_id
                if agent_attempt.scorer_attempt is not None:
                    scorer_attempt_id = agent_attempt.scorer_attempt.scorer_attempt_id
                payload_refs = _agent_eval_attempt_payload_refs(
                    artifact_dir_ref,
                    attempt_dir,
                )
            else:
                raise AssertionError(
                    f"Unhandled eval policy type: {selected_policy.type}"
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
                    eval_attempt_id=eval_attempt_id,
                    scorer_attempt_id=scorer_attempt_id,
                    agent_attempt_id=agent_attempt_id,
                ),
                "eval_attempt_finished",
                output_payload={
                    "artifact_type": attempt_record.artifact_type,
                    "artifact_schema_version": attempt_record.artifact_schema_version,
                    "scorer": _scorer_summary_json(attempt_record.scorer),
                    "agent": _agent_summary_json(attempt_record.agent),
                },
                payload_refs=payload_refs,
            )

        _append_trace(
            trace_events,
            task_provenance,
            "eval_task_finished",
            output_payload={
                "attempt_count": len(task_attempt_records),
                "layer_counts": count_eval_attempt_layers(task_attempt_records),
            },
        )

    eval_run = EvalRun(
        eval_run_id=eval_run_id,
        config=config,
        config_path=config_path,
        config_hash=config_hash,
        task_hashes=task_hashes,
        runtime_provenance=runtime_provenance,
        policy=policy,
        out_dir=out_dir,
        created_at=created_at,
        attempts=attempt_records,
    )
    _validate_unique_eval_attempt_ids(eval_run.attempts)
    _append_trace(
        trace_events,
        base_provenance,
        "eval_finished",
        output_payload={
            "attempt_count": len(eval_run.attempts),
            "layer_counts": count_eval_run_layers(eval_run),
        },
        payload_refs={"manifest": MANIFEST_FILENAME},
    )
    _write_eval_trace(eval_run, trace_events)
    _require_unchanged_eval_runtime(eval_run.runtime_provenance)
    _write_eval_run_manifest(eval_run)
    return eval_run


def run_eval_config_all_policies(
    config_path: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> EvalMatrixRun:
    config_path = config_path.resolve()
    config = load_eval_config(config_path)
    validate_eval_config_paths(config, config_path)
    config_hash = _hash_file(config_path)
    task_pack_path = resolve_task_pack_path(config, config_path)
    task_hashes = build_eval_task_hashes(task_pack_path, config.tasks)
    runtime_provenance = capture_harness_runtime_provenance(harness_repo_root())
    eval_suite_id = new_eval_suite_id()
    created_at = _utc_now()

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    policies_dir = out_dir / EVAL_SUITE_ARTIFACT_REFS["policies"]
    policies_dir.mkdir(parents=True, exist_ok=True)

    policy_runs = [
        run_eval_config(
            config_path,
            policy,
            policies_dir / policy,
            runtime_provenance=runtime_provenance,
        )
        for policy in config.policies
    ]
    replay_runs = _replay_configured_policy_runs(config, policy_runs, out_dir)
    eval_matrix = EvalMatrixRun(
        eval_suite_id=eval_suite_id,
        config=config,
        config_path=config_path,
        config_hash=config_hash,
        task_hashes=task_hashes,
        runtime_provenance=runtime_provenance,
        out_dir=out_dir,
        created_at=created_at,
        policy_runs=policy_runs,
        replay_runs=replay_runs,
    )
    _require_unchanged_eval_runtime(eval_matrix.runtime_provenance)
    _write_eval_matrix_manifest(eval_matrix)
    return eval_matrix


def _replay_configured_policy_runs(
    config: EvalConfig,
    policy_runs: list[EvalRun],
    out_dir: Path,
) -> list[EvalMatrixReplayRecord]:
    from agentenv.replay.runner import run_replay

    replays_dir = out_dir / EVAL_SUITE_ARTIFACT_REFS["replays"]
    replay_records: list[EvalMatrixReplayRecord] = []
    for policy_run in policy_runs:
        policy = config.policies[policy_run.policy]
        for replay_index in range(policy.replay.repeats):
            replay_dir = (
                replays_dir / f"{policy_run.policy}__replay_{replay_index + 1:03d}"
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


def _write_eval_trace(eval_run: EvalRun, trace_events: list[TraceEvent]) -> Path:
    trace_path = eval_run.out_dir / EVAL_RUN_ARTIFACT_REFS["trace"]
    trace_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in trace_events)
    )
    return trace_path


def _write_eval_run_manifest(eval_run: EvalRun) -> Path:
    manifest_path = eval_run.out_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(
            _manifest_payload(_build_eval_run_manifest(eval_run)),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return manifest_path


def _write_eval_matrix_manifest(eval_matrix: EvalMatrixRun) -> Path:
    manifest_path = eval_matrix.out_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(
            _manifest_payload(_build_eval_suite_manifest(eval_matrix)),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return manifest_path


def _build_eval_run_manifest(eval_run: EvalRun) -> EvalRunManifest:
    payload: dict[str, object] = {
        "artifact_type": ArtifactType.EVAL_RUN,
        "artifact_schema_version": EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
        "eval_run_id": eval_run.eval_run_id,
        "created_at": eval_run.created_at,
        "config_path": str(eval_run.config_path),
        "config_hash": eval_run.config_hash,
        "config_name": eval_run.config.name,
        "task_pack": eval_run.config.task_pack,
        "split": eval_run.config.split,
        "task_hashes": eval_run.task_hashes,
        "runtime_provenance": eval_run.runtime_provenance,
        "policy": eval_run.policy,
        "attempt_count": len(eval_run.attempts),
        "layer_counts": count_eval_run_layers(eval_run),
        "artifacts": dict(EVAL_RUN_ARTIFACT_REFS),
        "attempts": [
            _eval_attempt_record(eval_run, attempt) for attempt in eval_run.attempts
        ],
    }
    payload.update(_policy_metadata(eval_run.config, eval_run.policy))
    return EvalRunManifest.model_validate(payload)


def _build_eval_suite_manifest(eval_matrix: EvalMatrixRun) -> EvalSuiteManifest:
    policy_attempt_counts = {
        policy_run.policy: len(policy_run.attempts)
        for policy_run in eval_matrix.policy_runs
    }
    artifacts = {"policies": EVAL_SUITE_ARTIFACT_REFS["policies"]}
    if eval_matrix.replay_runs:
        artifacts["replays"] = EVAL_SUITE_ARTIFACT_REFS["replays"]

    return EvalSuiteManifest.model_validate(
        {
            "artifact_type": ArtifactType.EVAL_SUITE,
            "artifact_schema_version": EVAL_SUITE_ARTIFACT_SCHEMA_VERSION,
            "eval_suite_id": eval_matrix.eval_suite_id,
            "created_at": eval_matrix.created_at,
            "config_path": str(eval_matrix.config_path),
            "config_hash": eval_matrix.config_hash,
            "config_name": eval_matrix.config.name,
            "task_pack": eval_matrix.config.task_pack,
            "split": eval_matrix.config.split,
            "task_hashes": eval_matrix.task_hashes,
            "runtime_provenance": eval_matrix.runtime_provenance,
            "tasks": eval_matrix.config.tasks,
            "task_count": len(eval_matrix.config.tasks),
            "policy_count": len(eval_matrix.policy_runs),
            "attempt_count": sum(policy_attempt_counts.values()),
            "layer_counts": count_eval_matrix_layers(eval_matrix),
            "artifacts": artifacts,
            "policy_runs": [
                {
                    "policy": policy_run.policy,
                    **_policy_metadata(eval_matrix.config, policy_run.policy),
                    "eval_run_id": policy_run.eval_run_id,
                    "artifact_dir": str(
                        policy_run.out_dir.relative_to(eval_matrix.out_dir)
                    ),
                    "manifest": str(
                        (policy_run.out_dir / MANIFEST_FILENAME).relative_to(
                            eval_matrix.out_dir
                        )
                    ),
                    "attempt_count": len(policy_run.attempts),
                    "layer_counts": count_eval_run_layers(policy_run),
                }
                for policy_run in eval_matrix.policy_runs
            ],
            "replay_run_count": len(eval_matrix.replay_runs),
            "replay_policy_count": _replayed_policy_count(eval_matrix.config),
            "replay_run_success_summary": _replay_run_success_summary(
                eval_matrix.replay_runs
            ),
            "replay_runs": [
                _eval_matrix_replay_record(eval_matrix, replay_record)
                for replay_record in eval_matrix.replay_runs
            ],
        }
    )


def _require_unchanged_eval_runtime(
    expected: HarnessRuntimeProvenance,
) -> None:
    observed = capture_harness_runtime_provenance(harness_repo_root())
    if observed != expected:
        raise ValueError(
            "Harness runtime changed while the eval was running; refusing to "
            "persist a manifest with ambiguous execution provenance"
        )


def _manifest_payload(
    manifest: EvalRunManifest | EvalSuiteManifest,
) -> dict[str, object]:
    payload = cast(dict[str, object], manifest.model_dump(mode="json", by_alias=True))
    _remove_null_policy_config_refs(payload)
    return payload


def _remove_null_policy_config_refs(value: object) -> None:
    if isinstance(value, dict):
        for key in ("model_config", "decoding_config"):
            if value.get(key) is None:
                value.pop(key, None)
        for child in value.values():
            _remove_null_policy_config_refs(child)
        return
    if isinstance(value, list):
        for child in value:
            _remove_null_policy_config_refs(child)


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
        "replay_run_id": replay_record.replay_run.replay_run_id,
        "status": replay_record.replay_run.status,
        "artifact_dir": str(replay_record.replay_dir.relative_to(eval_matrix.out_dir)),
        "manifest": str(
            (replay_record.replay_dir / MANIFEST_FILENAME).relative_to(
                eval_matrix.out_dir
            )
        ),
        "replay_result": str(
            (
                replay_record.replay_dir / REPLAY_RUN_ARTIFACT_REFS["replay_result"]
            ).relative_to(eval_matrix.out_dir)
        ),
        "attempt_count": attempt_count,
        "matched_attempts": matched_attempts,
        "mismatched_attempts": attempt_count - matched_attempts,
        "error_count": 1 if replay_record.replay_run.status == "REPLAY_ERROR" else 0,
    }


def _replay_run_success_summary(
    replay_records: list[EvalMatrixReplayRecord],
) -> str:
    passed = sum(
        1
        for replay_record in replay_records
        if replay_record.replay_run.status == "PASS"
    )
    total = len(replay_records)
    return f"{passed}/{total}"


def _replayed_policy_count(config: EvalConfig) -> int:
    return sum(1 for policy in config.policies.values() if policy.replay.repeats > 0)


def _run_scorer_eval_attempt(
    *,
    task: ResolvedEvalTask,
    submission_path: Path,
    eval_attempt_id: str,
    attempt_index: int,
    attempt_dir: Path,
) -> EvalAttemptRecord:
    attempt_run = run_and_persist_patch_attempt_to_dir(
        task.manifest_path,
        submission_path,
        attempt_dir,
    )
    artifact_identity = _child_artifact_identity(attempt_dir)
    return EvalAttemptRecord(
        eval_attempt_id=eval_attempt_id,
        task_id=task.task_id,
        attempt_index=attempt_index,
        attempt_dir=attempt_dir,
        artifact_type=artifact_identity.artifact_type,
        artifact_schema_version=artifact_identity.artifact_schema_version,
        scorer=_scorer_summary(attempt_run.result),
        agent=None,
    )


def _run_agent_control_eval_attempt(
    *,
    task: ResolvedEvalTask,
    control_case: AgentControlScriptCase,
    eval_attempt_id: str,
    attempt_index: int,
    attempt_dir: Path,
) -> EvalAttemptRecord:
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )
    decoding_config = model_client.default_decoding_config()
    agent_task_run = run_and_persist_agent_task_attempt_to_dir(
        task.manifest_path,
        model_client,
        decoding_config,
        attempt_dir,
        agent_control_script=control_case,
    )
    artifact_identity = _child_artifact_identity(attempt_dir)
    return EvalAttemptRecord(
        eval_attempt_id=eval_attempt_id,
        task_id=task.task_id,
        attempt_index=attempt_index,
        attempt_dir=attempt_dir,
        artifact_type=artifact_identity.artifact_type,
        artifact_schema_version=artifact_identity.artifact_schema_version,
        scorer=None,
        agent=_agent_summary(agent_task_run.result),
    )


def _run_agent_model_eval_attempt(
    *,
    task: ResolvedEvalTask,
    model_config_path: Path,
    decoding_config_path: Path,
    eval_attempt_id: str,
    attempt_index: int,
    attempt_dir: Path,
) -> EvalAttemptRecord:
    model_config = load_model_config(model_config_path)
    decoding_config = load_decoding_config(decoding_config_path)
    model_client = build_model_client(model_config)
    agent_task_run = run_and_persist_agent_task_attempt_to_dir(
        task.manifest_path,
        model_client,
        decoding_config,
        attempt_dir,
        model_config_provenance=model_config_provenance_artifact(
            model_config=model_config,
            model_config_path=model_config_path,
            model_config_hash=_hash_file(model_config_path),
        ),
        decoding_config_provenance=decoding_config_provenance_artifact(
            decoding_config=decoding_config,
            decoding_config_path=decoding_config_path,
            decoding_config_hash=_hash_file(decoding_config_path),
        ),
    )
    artifact_identity = _child_artifact_identity(attempt_dir)
    return EvalAttemptRecord(
        eval_attempt_id=eval_attempt_id,
        task_id=task.task_id,
        attempt_index=attempt_index,
        attempt_dir=attempt_dir,
        artifact_type=artifact_identity.artifact_type,
        artifact_schema_version=artifact_identity.artifact_schema_version,
        scorer=None,
        agent=_agent_summary(agent_task_run.result),
    )


def _agent_eval_attempt_payload_refs(
    artifact_dir_ref: str,
    attempt_dir: Path,
) -> dict[str, str]:
    payload_refs = {
        "agent_task_run": (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['agent_task_run']}"
        ),
        "decoding_config": (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['decoding_config']}"
        ),
    }
    if (attempt_dir / AGENT_ATTEMPT_ARTIFACT_REFS["agent_task_view"]).is_file():
        payload_refs["agent_task_view"] = (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['agent_task_view']}"
        )
    if (attempt_dir / AGENT_ATTEMPT_ARTIFACT_REFS["model_config"]).is_file():
        payload_refs["model_config"] = (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['model_config']}"
        )
    if (attempt_dir / AGENT_ATTEMPT_ARTIFACT_REFS["agent_control_script"]).is_file():
        payload_refs["agent_control_script"] = (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['agent_control_script']}"
        )
    if (attempt_dir / AGENT_ATTEMPT_ARTIFACT_REFS["prompt_loop_result"]).is_file():
        payload_refs["prompt_loop_result"] = (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['prompt_loop_result']}"
        )
    if (attempt_dir / AGENT_ATTEMPT_ARTIFACT_REFS["candidate_patch"]).is_file():
        payload_refs["candidate_patch"] = (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['candidate_patch']}"
        )
    nested_attempt_ref = (
        f"{AGENT_ATTEMPT_ARTIFACT_REFS['attempt']}/"
        f"{SCORER_ATTEMPT_ARTIFACT_REFS['attempt']}"
    )
    if (attempt_dir / nested_attempt_ref).is_file():
        payload_refs["nested_attempt"] = f"{artifact_dir_ref}/{nested_attempt_ref}"
    return payload_refs


def _policy_metadata(config: EvalConfig, policy_name: str) -> dict[str, object]:
    policy = config.policies[policy_name]
    common_metadata: dict[str, object] = {
        "attempts_per_task": policy.attempts,
        "replay_repeats": policy.replay.repeats,
    }
    if policy.type == SCORER_CONTROL_PATCH_POLICY_TYPE:
        return {
            "policy_type": policy.type,
            "policy_family": CONTROL_POLICY_FAMILY,
            "control_layer": SCORER_CONTROL_LAYER,
            "control_name": policy.control,
            **common_metadata,
        }
    if policy.type == AGENT_CONTROL_SCRIPT_POLICY_TYPE:
        return {
            "policy_type": policy.type,
            "policy_family": CONTROL_POLICY_FAMILY,
            "control_layer": AGENT_CONTROL_LAYER,
            "control_name": policy.control,
            **common_metadata,
        }
    if policy.type == AGENT_MODEL_POLICY_TYPE:
        return {
            "policy_type": policy.type,
            "policy_family": AGENT_POLICY_FAMILY,
            "control_layer": None,
            "control_name": None,
            "model_config": policy.model_config_path,
            "decoding_config": policy.decoding_config_path,
            **common_metadata,
        }
    raise AssertionError(f"Unhandled eval policy type: {policy.type}")


def _eval_attempt_record(
    eval_run: EvalRun,
    attempt: EvalAttemptRecord,
) -> dict[str, object]:
    return {
        "eval_attempt_id": attempt.eval_attempt_id,
        "task_id": attempt.task_id,
        "attempt_index": attempt.attempt_index,
        "artifact_dir": str(attempt.attempt_dir.relative_to(eval_run.out_dir)),
        "artifact_type": attempt.artifact_type,
        "artifact_schema_version": attempt.artifact_schema_version,
        "scorer": _scorer_summary_json(attempt.scorer),
        "agent": _agent_summary_json(attempt.agent),
    }


def _scorer_summary(result: AttemptResult) -> ScorerAttemptSummary:
    return ScorerAttemptSummary(
        scorer_attempt_id=result.scorer_attempt_id,
        status=result.status,
        public_status=result.public_status,
        hidden_status=result.hidden_status,
        error_class=result.error_class,
        final_diff_hash=result.final_diff_hash,
        duration_ms=result.duration_ms,
    )


def _agent_summary(result: AgentTaskRunResult) -> AgentAttemptSummary:
    return AgentAttemptSummary(
        agent_attempt_id=result.agent_attempt_id,
        status=result.status,
        prompt_loop_status=result.prompt_loop_status,
        error_class=result.error_class,
        candidate_patch_hash=result.candidate_patch_hash,
        duration_ms=result.duration_ms,
        scorer_attempt=(
            _scorer_summary(result.attempt_result)
            if result.attempt_result is not None
            else None
        ),
    )


def _scorer_summary_json(
    scorer: ScorerAttemptSummary | None,
) -> dict[str, object] | None:
    if scorer is None:
        return None
    return {
        "scorer_attempt_id": scorer.scorer_attempt_id,
        "status": scorer.status,
        "public_status": scorer.public_status,
        "hidden_status": scorer.hidden_status,
        "error_class": scorer.error_class,
        "final_diff_hash": scorer.final_diff_hash,
        "duration_ms": scorer.duration_ms,
    }


def _agent_summary_json(
    agent: AgentAttemptSummary | None,
) -> dict[str, object] | None:
    if agent is None:
        return None
    return {
        "agent_attempt_id": agent.agent_attempt_id,
        "status": agent.status,
        "prompt_loop_status": agent.prompt_loop_status,
        "error_class": agent.error_class,
        "candidate_patch_hash": agent.candidate_patch_hash,
        "duration_ms": agent.duration_ms,
        "scorer_attempt": _scorer_summary_json(agent.scorer_attempt),
    }


def _required_scorer(attempt: EvalAttemptRecord) -> ScorerAttemptSummary:
    if attempt.scorer is None:
        raise ValueError("Expected scorer eval attempt summary")
    return attempt.scorer


def _required_agent(attempt: EvalAttemptRecord) -> AgentAttemptSummary:
    if attempt.agent is None:
        raise ValueError("Expected agent eval attempt summary")
    return attempt.agent


def _validate_unique_eval_attempt_ids(attempts: list[EvalAttemptRecord]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for attempt in attempts:
        if attempt.eval_attempt_id in seen:
            duplicates.add(attempt.eval_attempt_id)
        seen.add(attempt.eval_attempt_id)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate eval_attempt_id value(s): {duplicate_list}")


def _child_artifact_identity(attempt_dir: Path) -> ArtifactIdentity:
    manifest_path = attempt_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise ValueError(f"Expected {MANIFEST_FILENAME} object at {attempt_dir}")
    artifact_type = manifest.get("artifact_type")
    if not isinstance(artifact_type, str):
        raise ValueError(f"Missing artifact_type in {manifest_path}")
    artifact_schema_version = manifest.get("artifact_schema_version")
    if not isinstance(artifact_schema_version, str):
        raise ValueError(f"Missing artifact_schema_version in {manifest_path}")
    return ArtifactIdentity(
        artifact_type=artifact_type,
        artifact_schema_version=artifact_schema_version,
    )


def count_eval_attempt_layers(
    attempts: list[EvalAttemptRecord],
) -> dict[str, dict[str, int]]:
    layer_counts: dict[str, dict[str, int]] = {}
    for attempt in attempts:
        if attempt.scorer is not None:
            _increment_layer_count(
                layer_counts,
                "scorer_status",
                attempt.scorer.status,
            )
            _increment_layer_count(
                layer_counts,
                "scorer_public_status",
                attempt.scorer.public_status,
            )
            _increment_layer_count(
                layer_counts,
                "scorer_hidden_status",
                attempt.scorer.hidden_status,
            )
        if attempt.agent is not None:
            _increment_layer_count(
                layer_counts,
                "agent_status",
                attempt.agent.status,
            )
            if attempt.agent.prompt_loop_status is not None:
                _increment_layer_count(
                    layer_counts,
                    "prompt_loop_status",
                    attempt.agent.prompt_loop_status,
                )
            if attempt.agent.scorer_attempt is not None:
                _increment_layer_count(
                    layer_counts,
                    "agent_scorer_status",
                    attempt.agent.scorer_attempt.status,
                )
                _increment_layer_count(
                    layer_counts,
                    "agent_scorer_public_status",
                    attempt.agent.scorer_attempt.public_status,
                )
                _increment_layer_count(
                    layer_counts,
                    "agent_scorer_hidden_status",
                    attempt.agent.scorer_attempt.hidden_status,
                )
    return layer_counts


def count_eval_run_layers(eval_run: EvalRun) -> dict[str, dict[str, int]]:
    return count_eval_attempt_layers(eval_run.attempts)


def count_eval_matrix_layers(
    eval_matrix: EvalMatrixRun,
) -> dict[str, dict[str, int]]:
    matrix_counts: dict[str, dict[str, int]] = {}
    for policy_run in eval_matrix.policy_runs:
        for layer_name, status_counts in count_eval_run_layers(policy_run).items():
            for status, count in status_counts.items():
                matrix_counts.setdefault(layer_name, {})[status] = (
                    matrix_counts.setdefault(layer_name, {}).get(status, 0) + count
                )
    return matrix_counts


def _increment_layer_count(
    layer_counts: dict[str, dict[str, int]],
    layer_name: str,
    status: str,
) -> None:
    counts = layer_counts.setdefault(layer_name, {})
    counts[status] = counts.get(status, 0) + 1


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
    eval_attempt_id: str | None = None,
    scorer_attempt_id: str | None = None,
    agent_attempt_id: str | None = None,
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
    if eval_attempt_id is not None:
        provenance["eval_attempt_id"] = eval_attempt_id
    if scorer_attempt_id is not None:
        provenance["scorer_attempt_id"] = scorer_attempt_id
    if agent_attempt_id is not None:
        provenance["agent_attempt_id"] = agent_attempt_id
    return provenance


def _hash_file(path: Path) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(path.read_bytes())}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
