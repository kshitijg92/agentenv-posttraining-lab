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
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    AGENT_ATTEMPT_ARTIFACT_REFS,
    AgentGenerationEvalAttemptReference,
    load_agent_attempt_manifest,
)
from agentenv.artifacts.manifests import EVAL_RUN_ARTIFACT_REFS
from agentenv.artifacts.manifests import EVAL_RUN_ARTIFACT_SCHEMA_VERSION
from agentenv.artifacts.manifests import EVAL_SUITE_ARTIFACT_REFS
from agentenv.artifacts.manifests import EVAL_SUITE_ARTIFACT_SCHEMA_VERSION
from agentenv.artifacts.manifests import EvalRunManifest
from agentenv.artifacts.manifests import EvalSuiteManifest
from agentenv.artifacts.manifests import REPLAY_RUN_ARTIFACT_REFS
from agentenv.artifacts.manifests import SCORER_ATTEMPT_ARTIFACT_REFS
from agentenv.artifacts.payloads import (
    DecodingConfigProvenance,
    EvalTaskHashes,
    ModelConfigProvenance,
)
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
    AgentModelPolicy,
    EvalConfig,
)
from agentenv.evals.suite_declaration import (
    EVAL_SUITE_DECLARATION_FILENAME,
    EVAL_SUITE_DECLARATION_SCHEMA_VERSION,
    EvalSuiteDeclaration,
    PlannedEvalAttempt,
    PlannedEvalPolicyRun,
    hash_eval_suite_declaration,
    load_eval_suite_declaration,
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
from agentenv.models.config import (
    load_decoding_config,
    load_model_config,
    load_referenced_model_input_protocol,
)
from agentenv.models.client import ModelClient
from agentenv.models.factory import build_model_client
from agentenv.models.provider_runtime import capture_provider_runtime_provenance
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.agent_task_run import (
    decoding_config_provenance_artifact,
    model_config_provenance_artifact,
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.agent_generation import (
    validate_agent_generation_for_eval_attempt,
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
    declaration: EvalSuiteDeclaration
    policy_runs: list[EvalRun]
    replay_runs: list["EvalMatrixReplayRecord"]


@dataclass(frozen=True)
class EvalMatrixReplayRecord:
    policy: str
    replay_index: int
    replay_dir: Path
    replay_run: "ReplayRun"


@dataclass(frozen=True)
class _AgentModelRunContext:
    model_config_path: Path
    model_config_hash: str
    decoding_config_path: Path
    decoding_config_hash: str
    model_client: ModelClient
    decoding_config: DecodingConfig
    model_config_provenance: ModelConfigProvenance
    decoding_config_provenance: DecodingConfigProvenance


def run_eval_config(
    config_path: Path,
    policy: str,
    out_dir: Path,
    *,
    overwrite: bool = False,
    runtime_provenance: HarnessRuntimeProvenance | None = None,
    suite_declaration: EvalSuiteDeclaration | None = None,
    agent_model_context: _AgentModelRunContext | None = None,
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
    created_at = _utc_now()

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    attempts_dir = out_dir / EVAL_RUN_ARTIFACT_REFS["attempts"]
    attempts_dir.mkdir(parents=True, exist_ok=True)

    resolved_tasks = resolve_eval_tasks(config, config_path)
    if isinstance(selected_policy, AgentModelPolicy):
        if agent_model_context is None:
            agent_model_context = _load_agent_model_run_context(
                config_path,
                selected_policy,
            )
    elif agent_model_context is not None:
        raise ValueError("agent_model_context requires an agent-model policy")

    planned_policy_run = (
        _declared_policy_run(suite_declaration, policy)
        if suite_declaration is not None
        else None
    )
    if planned_policy_run is None:
        eval_run_id = new_eval_run_id()
        planned_attempts = _new_planned_eval_attempts(
            config.tasks,
            attempts_per_task=selected_policy.attempts,
        )
    else:
        if suite_declaration is None:
            raise AssertionError("Declared policy run requires suite declaration")
        _validate_declared_policy_execution(
            suite_declaration=suite_declaration,
            planned_policy_run=planned_policy_run,
            config=config,
            config_path=config_path,
            config_hash=config_hash,
            task_hashes=task_hashes,
            runtime_provenance=runtime_provenance,
            agent_model_context=agent_model_context,
        )
        eval_run_id = planned_policy_run.eval_run_id
        planned_attempts = planned_policy_run.planned_attempts
    planned_attempts_by_identity = {
        (attempt.task_id, attempt.attempt_index): attempt
        for attempt in planned_attempts
    }
    _validate_planned_attempt_coverage(
        planned_attempts,
        task_ids=config.tasks,
        attempts_per_task=selected_policy.attempts,
    )
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
            planned_attempt = planned_attempts_by_identity[
                (task.task_id, attempt_index)
            ]
            eval_attempt_id = planned_attempt.eval_attempt_id
            attempt_dir = resolve_relative_artifact_ref(
                out_dir,
                planned_attempt.artifact_dir,
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
                if agent_model_context is None:
                    raise AssertionError("Agent-model run context was not loaded")
                started_payload = {
                    "attempt_artifact_dir": artifact_dir_ref,
                    "model_config_path": str(agent_model_context.model_config_path),
                    "model_config_hash": agent_model_context.model_config_hash,
                    "decoding_config_path": str(
                        agent_model_context.decoding_config_path
                    ),
                    "decoding_config_hash": (agent_model_context.decoding_config_hash),
                    "max_turns_override": selected_policy.max_turns_override,
                }
                _append_trace(
                    trace_events,
                    attempt_provenance,
                    "eval_attempt_started",
                    input_payload=started_payload,
                )
                attempt_record = _run_agent_model_eval_attempt(
                    task=task,
                    run_context=agent_model_context,
                    eval_attempt_id=eval_attempt_id,
                    attempt_index=attempt_index,
                    attempt_dir=attempt_dir,
                    max_turns_override=selected_policy.max_turns_override,
                    generation_eval_attempt=(
                        AgentGenerationEvalAttemptReference(
                            eval_suite_id=suite_declaration.eval_suite_id,
                            eval_run_id=eval_run_id,
                            eval_attempt_id=eval_attempt_id,
                            eval_suite_declaration_hash=(
                                hash_eval_suite_declaration(suite_declaration)
                            ),
                        )
                        if suite_declaration is not None
                        else None
                    ),
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
    agent_model_contexts = _load_agent_model_contexts(config_path, config)
    declaration = _build_eval_suite_declaration(
        eval_suite_id=eval_suite_id,
        created_at=created_at,
        config=config,
        config_path=config_path,
        config_hash=config_hash,
        task_hashes=task_hashes,
        runtime_provenance=runtime_provenance,
        agent_model_contexts=agent_model_contexts,
    )
    _require_current_declaration_inputs(declaration)
    _write_eval_suite_declaration(out_dir, declaration)

    policies_dir = out_dir / EVAL_SUITE_ARTIFACT_REFS["policies"]
    policies_dir.mkdir(parents=True, exist_ok=True)

    policy_runs = [
        run_eval_config(
            config_path,
            policy,
            policies_dir / policy,
            runtime_provenance=runtime_provenance,
            suite_declaration=declaration,
            agent_model_context=agent_model_contexts.get(policy),
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
        declaration=declaration,
        policy_runs=policy_runs,
        replay_runs=replay_runs,
    )
    _require_unchanged_eval_runtime(eval_matrix.runtime_provenance)
    _validate_eval_matrix_matches_declaration(eval_matrix)
    _write_eval_matrix_manifest(eval_matrix)
    return eval_matrix


def _load_agent_model_contexts(
    config_path: Path,
    config: EvalConfig,
) -> dict[str, _AgentModelRunContext]:
    return {
        policy_name: _load_agent_model_run_context(config_path, policy)
        for policy_name, policy in config.policies.items()
        if isinstance(policy, AgentModelPolicy)
    }


def _build_eval_suite_declaration(
    *,
    eval_suite_id: str,
    created_at: str,
    config: EvalConfig,
    config_path: Path,
    config_hash: str,
    task_hashes: EvalTaskHashes,
    runtime_provenance: HarnessRuntimeProvenance,
    agent_model_contexts: dict[str, _AgentModelRunContext],
) -> EvalSuiteDeclaration:
    policy_runs: list[PlannedEvalPolicyRun] = []
    for policy_name, policy in config.policies.items():
        context = agent_model_contexts.get(policy_name)
        if isinstance(policy, AgentModelPolicy):
            if context is None:
                raise ValueError(
                    f"Missing prepared agent-model context for policy {policy_name!r}"
                )
            model_config_provenance = context.model_config_provenance
            decoding_config_provenance = context.decoding_config_provenance
        else:
            if context is not None:
                raise ValueError(
                    f"Unexpected agent-model context for policy {policy_name!r}"
                )
            model_config_provenance = None
            decoding_config_provenance = None

        policy_runs.append(
            PlannedEvalPolicyRun(
                policy=policy_name,
                eval_run_id=new_eval_run_id(),
                artifact_dir=f"policies/{policy_name}",
                model_config_provenance=model_config_provenance,
                decoding_config_provenance=decoding_config_provenance,
                planned_attempts=_new_planned_eval_attempts(
                    config.tasks,
                    attempts_per_task=policy.attempts,
                ),
            )
        )

    return EvalSuiteDeclaration(
        schema_version=EVAL_SUITE_DECLARATION_SCHEMA_VERSION,
        eval_suite_id=eval_suite_id,
        created_at=created_at,
        config_path=str(config_path),
        config_hash=config_hash,
        task_hashes=task_hashes,
        runtime_provenance=runtime_provenance,
        policy_runs=policy_runs,
    )


def _new_planned_eval_attempts(
    task_ids: list[str],
    *,
    attempts_per_task: int,
) -> list[PlannedEvalAttempt]:
    return [
        PlannedEvalAttempt(
            eval_attempt_id=new_eval_attempt_id(),
            task_id=task_id,
            attempt_index=attempt_index,
            artifact_dir=(
                f"attempts/{task_id}__attempt_{attempt_index + 1:03d}"
            ),
        )
        for task_id in task_ids
        for attempt_index in range(attempts_per_task)
    ]


def _declared_policy_run(
    declaration: EvalSuiteDeclaration,
    policy: str,
) -> PlannedEvalPolicyRun:
    matching = [
        policy_run
        for policy_run in declaration.policy_runs
        if policy_run.policy == policy
    ]
    if len(matching) != 1:
        raise ValueError(
            f"Eval suite declaration must contain exactly one policy {policy!r}"
        )
    return matching[0]


def _validate_declared_policy_execution(
    *,
    suite_declaration: EvalSuiteDeclaration,
    planned_policy_run: PlannedEvalPolicyRun,
    config: EvalConfig,
    config_path: Path,
    config_hash: str,
    task_hashes: EvalTaskHashes,
    runtime_provenance: HarnessRuntimeProvenance,
    agent_model_context: _AgentModelRunContext | None,
) -> None:
    _require_unchanged_eval_runtime(suite_declaration.runtime_provenance)
    compared_suite_fields = (
        ("config_path", Path(suite_declaration.config_path).resolve(), config_path),
        ("config_hash", suite_declaration.config_hash, config_hash),
        ("task_hashes", suite_declaration.task_hashes, task_hashes),
        (
            "runtime_provenance",
            suite_declaration.runtime_provenance,
            runtime_provenance,
        ),
        (
            "policy_order",
            tuple(policy_run.policy for policy_run in suite_declaration.policy_runs),
            tuple(config.policies),
        ),
    )
    for field_name, declared, observed in compared_suite_fields:
        if declared != observed:
            raise ValueError(
                f"Eval suite declaration {field_name} changed before policy execution"
            )

    expected_policy_dir = f"policies/{planned_policy_run.policy}"
    if planned_policy_run.artifact_dir != expected_policy_dir:
        raise ValueError("Declared policy artifact directory is not canonical")
    policy = config.policies[planned_policy_run.policy]
    _validate_planned_attempt_coverage(
        planned_policy_run.planned_attempts,
        task_ids=config.tasks,
        attempts_per_task=policy.attempts,
    )
    if isinstance(policy, AgentModelPolicy):
        if agent_model_context is None:
            raise ValueError("Declared agent-model policy is missing prepared context")
        if (
            planned_policy_run.model_config_provenance
            != agent_model_context.model_config_provenance
            or planned_policy_run.decoding_config_provenance
            != agent_model_context.decoding_config_provenance
        ):
            raise ValueError(
                "Declared model inputs changed before policy execution"
            )
        _require_live_model_inputs(
            config_path,
            policy,
            planned_policy_run,
        )
    elif (
        planned_policy_run.model_config_provenance is not None
        or planned_policy_run.decoding_config_provenance is not None
    ):
        raise ValueError("Control policies cannot declare model input provenance")


def _validate_planned_attempt_coverage(
    planned_attempts: list[PlannedEvalAttempt],
    *,
    task_ids: list[str],
    attempts_per_task: int,
) -> None:
    expected = [
        (
            task_id,
            attempt_index,
            f"attempts/{task_id}__attempt_{attempt_index + 1:03d}",
        )
        for task_id in task_ids
        for attempt_index in range(attempts_per_task)
    ]
    observed = [
        (attempt.task_id, attempt.attempt_index, attempt.artifact_dir)
        for attempt in planned_attempts
    ]
    if observed != expected:
        raise ValueError(
            "Planned eval attempts must cover every configured task and attempt "
            "index in config order"
        )


def _require_live_model_inputs(
    config_path: Path,
    policy: AgentModelPolicy,
    planned_policy_run: PlannedEvalPolicyRun,
) -> None:
    model_provenance = planned_policy_run.model_config_provenance
    decoding_provenance = planned_policy_run.decoding_config_provenance
    if model_provenance is None or decoding_provenance is None:
        raise ValueError("Agent-model policies require resolved input provenance")
    if (
        decoding_provenance.source_path is None
        or decoding_provenance.source_hash is None
    ):
        raise ValueError("Agent-model policies require file-backed decoding config")

    model_config_path = resolve_config_file_ref(
        config_path,
        policy.model_config_path,
        field_name="model_config",
    )
    decoding_config_path = resolve_config_file_ref(
        config_path,
        policy.decoding_config_path,
        field_name="decoding_config",
    )
    compared_paths = (
        ("model config", Path(model_provenance.source_path), model_config_path),
        (
            "decoding config",
            Path(decoding_provenance.source_path),
            decoding_config_path,
        ),
    )
    for label, declared_path, live_path in compared_paths:
        if declared_path.resolve() != live_path:
            raise ValueError(f"Declared {label} path changed")
    if _hash_file(model_config_path) != model_provenance.source_hash:
        raise ValueError("Declared model config bytes changed")
    if _hash_file(decoding_config_path) != decoding_provenance.source_hash:
        raise ValueError("Declared decoding config bytes changed")
    input_protocol = model_provenance.model_input_protocol
    if input_protocol is not None:
        protocol_path = Path(input_protocol.source_path)
        if _hash_file(protocol_path) != input_protocol.source_hash:
            raise ValueError("Declared model input protocol bytes changed")


def _require_current_declaration_inputs(
    declaration: EvalSuiteDeclaration,
) -> None:
    config_path = Path(declaration.config_path).resolve()
    if _hash_file(config_path) != declaration.config_hash:
        raise ValueError("Eval config changed after suite declaration was prepared")
    config = load_eval_config(config_path)
    validate_eval_config_paths(config, config_path)
    live_task_hashes = build_eval_task_hashes(
        resolve_task_pack_path(config, config_path),
        config.tasks,
    )
    if live_task_hashes != declaration.task_hashes:
        raise ValueError("Task bytes changed after suite declaration was prepared")
    _require_unchanged_eval_runtime(declaration.runtime_provenance)

    declared_policy_order = tuple(
        policy_run.policy for policy_run in declaration.policy_runs
    )
    if declared_policy_order != tuple(config.policies):
        raise ValueError("Policy order changed after suite declaration was prepared")
    for planned_policy_run in declaration.policy_runs:
        policy = config.policies[planned_policy_run.policy]
        _validate_planned_attempt_coverage(
            planned_policy_run.planned_attempts,
            task_ids=config.tasks,
            attempts_per_task=policy.attempts,
        )
        if isinstance(policy, AgentModelPolicy):
            _require_live_model_inputs(config_path, policy, planned_policy_run)
        elif (
            planned_policy_run.model_config_provenance is not None
            or planned_policy_run.decoding_config_provenance is not None
        ):
            raise ValueError("Control policies cannot declare model input provenance")


def _validate_eval_matrix_matches_declaration(
    eval_matrix: EvalMatrixRun,
) -> None:
    declaration = eval_matrix.declaration
    _require_current_declaration_inputs(declaration)
    if load_eval_suite_declaration(
        eval_matrix.out_dir / EVAL_SUITE_DECLARATION_FILENAME
    ) != declaration:
        raise ValueError("Persisted eval suite declaration changed during execution")

    compared_suite_fields = (
        ("eval_suite_id", declaration.eval_suite_id, eval_matrix.eval_suite_id),
        ("created_at", declaration.created_at, eval_matrix.created_at),
        ("config_path", Path(declaration.config_path), eval_matrix.config_path),
        ("config_hash", declaration.config_hash, eval_matrix.config_hash),
        ("task_hashes", declaration.task_hashes, eval_matrix.task_hashes),
        (
            "runtime_provenance",
            declaration.runtime_provenance,
            eval_matrix.runtime_provenance,
        ),
    )
    for field_name, declared, observed in compared_suite_fields:
        if declared != observed:
            raise ValueError(
                f"Completed eval suite {field_name} differs from its declaration"
            )

    if len(declaration.policy_runs) != len(eval_matrix.policy_runs):
        raise ValueError("Completed eval suite policy count differs from declaration")
    for planned_policy_run, policy_run in zip(
        declaration.policy_runs,
        eval_matrix.policy_runs,
        strict=True,
    ):
        observed_policy_identity = (
            policy_run.policy,
            policy_run.eval_run_id,
            str(policy_run.out_dir.relative_to(eval_matrix.out_dir)),
        )
        declared_policy_identity = (
            planned_policy_run.policy,
            planned_policy_run.eval_run_id,
            planned_policy_run.artifact_dir,
        )
        if observed_policy_identity != declared_policy_identity:
            raise ValueError(
                "Completed eval policy run differs from its declaration"
            )
        observed_attempts = [
            (
                attempt.eval_attempt_id,
                attempt.task_id,
                attempt.attempt_index,
                str(attempt.attempt_dir.relative_to(policy_run.out_dir)),
            )
            for attempt in policy_run.attempts
        ]
        declared_attempts = [
            (
                attempt.eval_attempt_id,
                attempt.task_id,
                attempt.attempt_index,
                attempt.artifact_dir,
            )
            for attempt in planned_policy_run.planned_attempts
        ]
        if observed_attempts != declared_attempts:
            raise ValueError(
                "Completed eval attempts differ from the predeclared attempt set"
            )
        _validate_policy_generations_before_suite_completion(
            declaration,
            planned_policy_run,
            policy_run,
        )


def _validate_policy_generations_before_suite_completion(
    declaration: EvalSuiteDeclaration,
    planned_policy_run: PlannedEvalPolicyRun,
    policy_run: EvalRun,
) -> None:
    declared_model = planned_policy_run.model_config_provenance
    declared_decoding = planned_policy_run.decoding_config_provenance
    if declared_model is None and declared_decoding is None:
        return
    if declared_model is None or declared_decoding is None:
        raise ValueError("Declared model input provenance is incomplete")

    for attempt in policy_run.attempts:
        if attempt.agent is None:
            raise ValueError("Agent-model eval attempt is missing agent summary")
        attempt_manifest = load_agent_attempt_manifest(
            attempt.attempt_dir / MANIFEST_FILENAME
        )
        generation_ref = attempt_manifest.artifacts.get("generation")
        if generation_ref is None:
            raise ValueError(
                "Declared agent-model attempt is missing terminal generation"
            )
        if attempt_manifest.prompt_loop_status is None:
            raise ValueError(
                "Declared agent-model attempt is missing prompt-loop status"
            )
        if attempt_manifest.task_id != attempt.task_id:
            raise ValueError("Agent attempt and eval task ids differ")
        if attempt_manifest.agent_attempt_id != attempt.agent.agent_attempt_id:
            raise ValueError("Agent attempt and eval summary ids differ")
        if attempt_manifest.status != attempt.agent.status:
            raise ValueError("Agent attempt and eval summary statuses differ")
        if attempt_manifest.prompt_loop_status != attempt.agent.prompt_loop_status:
            raise ValueError(
                "Agent attempt and eval summary prompt-loop statuses differ"
            )

        generation = validate_agent_generation_for_eval_attempt(
            resolve_relative_artifact_ref(attempt.attempt_dir, generation_ref),
            expected_eval_attempt=AgentGenerationEvalAttemptReference(
                eval_suite_id=declaration.eval_suite_id,
                eval_run_id=planned_policy_run.eval_run_id,
                eval_attempt_id=attempt.eval_attempt_id,
                eval_suite_declaration_hash=hash_eval_suite_declaration(
                    declaration
                ),
            ),
            expected_agent_attempt_id=attempt_manifest.agent_attempt_id,
            expected_task_id=attempt.task_id,
            expected_task_manifest_path=Path(attempt_manifest.task_manifest_path),
            expected_prompt_loop_status=attempt_manifest.prompt_loop_status,
            expected_candidate_patch_hash=attempt.agent.candidate_patch_hash,
            expected_model_config_provenance=declared_model,
            expected_decoding_config_provenance=declared_decoding,
        )
        for artifact_name in ("model_config", "decoding_config"):
            if attempt_manifest.artifacts.get(artifact_name) != (
                generation.manifest.artifacts[artifact_name]
            ):
                raise ValueError(
                    "Agent attempt and generation input references differ"
                )


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


def _write_eval_suite_declaration(
    out_dir: Path,
    declaration: EvalSuiteDeclaration,
) -> Path:
    declaration_path = out_dir / EVAL_SUITE_DECLARATION_FILENAME
    temporary_path = out_dir / f".{EVAL_SUITE_DECLARATION_FILENAME}.tmp"
    temporary_path.write_text(
        json.dumps(
            declaration.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    temporary_path.replace(declaration_path)
    if load_eval_suite_declaration(declaration_path) != declaration:
        raise ValueError("Persisted eval suite declaration failed exact readback")
    return declaration_path


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
    artifacts = {
        "declaration": EVAL_SUITE_ARTIFACT_REFS["declaration"],
        "policies": EVAL_SUITE_ARTIFACT_REFS["policies"],
    }
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
    run_context: _AgentModelRunContext,
    eval_attempt_id: str,
    attempt_index: int,
    attempt_dir: Path,
    max_turns_override: int | None,
    generation_eval_attempt: AgentGenerationEvalAttemptReference | None,
) -> EvalAttemptRecord:
    agent_task_run = run_and_persist_agent_task_attempt_to_dir(
        task.manifest_path,
        run_context.model_client,
        run_context.decoding_config,
        attempt_dir,
        max_turns_override=max_turns_override,
        model_config_provenance=run_context.model_config_provenance,
        decoding_config_provenance=run_context.decoding_config_provenance,
        eval_attempt=generation_eval_attempt,
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


def _load_agent_model_run_context(
    eval_config_path: Path,
    policy: AgentModelPolicy,
) -> _AgentModelRunContext:
    model_config_path = resolve_config_file_ref(
        eval_config_path,
        policy.model_config_path,
        field_name="model_config",
    )
    decoding_config_path = resolve_config_file_ref(
        eval_config_path,
        policy.decoding_config_path,
        field_name="decoding_config",
    )
    model_config_hash = _hash_file(model_config_path)
    decoding_config_hash = _hash_file(decoding_config_path)
    model_config = load_model_config(model_config_path)
    decoding_config = load_decoding_config(decoding_config_path)
    provider_runtime_provenance = capture_provider_runtime_provenance(model_config)
    model_input_protocol = load_referenced_model_input_protocol(
        model_config,
        model_config_path,
    )
    model_client = build_model_client(
        model_config,
        model_input_protocol=model_input_protocol,
        model_config_path=model_config_path,
    )
    return _AgentModelRunContext(
        model_config_path=model_config_path,
        model_config_hash=model_config_hash,
        decoding_config_path=decoding_config_path,
        decoding_config_hash=decoding_config_hash,
        model_client=model_client,
        decoding_config=decoding_config,
        model_config_provenance=model_config_provenance_artifact(
            model_config=model_config,
            model_config_path=model_config_path,
            model_config_hash=model_config_hash,
            provider_runtime_provenance=provider_runtime_provenance,
            model_input_protocol=model_input_protocol,
        ),
        decoding_config_provenance=decoding_config_provenance_artifact(
            decoding_config=decoding_config,
            decoding_config_path=decoding_config_path,
            decoding_config_hash=decoding_config_hash,
        ),
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
    if (attempt_dir / AGENT_ATTEMPT_ARTIFACT_REFS["generation"]).is_file():
        payload_refs["generation"] = (
            f"{artifact_dir_ref}/{AGENT_ATTEMPT_ARTIFACT_REFS['generation']}"
        )
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
            "max_turns_override": policy.max_turns_override,
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
