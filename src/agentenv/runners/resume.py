from __future__ import annotations

import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import agentenv.orchestrators.eval_run as eval_run_module
from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    AGENT_GENERATION_MANIFEST_FILENAME,
    EVAL_RUN_ARTIFACT_REFS,
    EVAL_SUITE_ARTIFACT_REFS,
    AgentTaskRunManifest,
    EvalAttemptReference,
    ScorerAttemptManifest,
    load_attempt_manifest,
    load_scorer_attempt_manifest,
)
from agentenv.artifacts.payloads import (
    DecodingConfigProvenance,
    ModelConfigProvenance,
    load_agent_control_script_artifact,
    load_agent_task_run_result,
    load_attempt_result,
)
from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.evals.resolve import (
    ResolvedEvalTask,
    agent_control_script_path,
    resolve_eval_tasks,
    scorer_control_patch_path,
)
from agentenv.evals.schema import (
    AgentControlScriptPolicy,
    AgentModelPolicy,
    EvalConfig,
    EvalPolicy,
    ScorerControlPatchPolicy,
)
from agentenv.evals.suite_declaration import (
    EVAL_SUITE_DECLARATION_FILENAME,
    EvalSuiteDeclaration,
    PlannedEvalAttempt,
    PlannedEvalPolicyRun,
    hash_eval_suite_declaration,
    load_eval_suite_declaration,
)
from agentenv.evals.validate import load_eval_config
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_generation import (
    ValidatedAgentGeneration,
    load_validated_agent_generation,
    validate_agent_generation_for_eval_attempt,
)
from agentenv.orchestrators.agent_task_run import (
    finish_and_persist_agent_task_attempt_from_generation,
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.eval_run import (
    EvalAttemptRecord,
    EvalMatrixReplayRecord,
    EvalMatrixRun,
    EvalRun,
    validate_current_eval_suite_declaration,
)
from agentenv.orchestrators.attempt_runner import (
    run_and_persist_patch_attempt_to_dir,
)
from agentenv.runners.diff_runner import hash_diff
from agentenv.tracing.validate import validate_trace_file
from agentenv.tasks.schema import TaskManifest
from agentenv.trajectories.builder import (
    resolve_manifest_artifact_path,
    validate_agent_payload_refs_match_manifest,
    validate_agent_result_matches_manifest,
    validate_scorer_result_matches_manifest,
    validate_scorer_result_matches_summary,
)


ResumeAction = Literal[
    "reuse_completed_attempt",
    "reuse_completed_generation",
    "run_attempt",
    "reject_attempt",
]
ResumeReason = Literal[
    "completed_attempt",
    "terminal_generation",
    "not_started",
    "incomplete_without_terminal_result",
    "attempt_path_not_directory",
    "invalid_completed_attempt",
    "invalid_terminal_generation",
    "unexpected_generation_for_policy",
]


@dataclass(frozen=True)
class EvalAttemptResumeDecision:
    policy: str
    eval_run_id: str
    eval_attempt_id: str
    task_id: str
    attempt_index: int
    attempt_dir: Path
    action: ResumeAction
    reason: ResumeReason
    detail: str | None = None


@dataclass(frozen=True)
class EvalSuiteResumeInventory:
    eval_suite_dir: Path
    declaration: EvalSuiteDeclaration
    decisions: tuple[EvalAttemptResumeDecision, ...]


ResumeExecutionStatus = Literal["completed", "rejected"]


@dataclass(frozen=True)
class EvalSuiteResumeResult:
    status: ResumeExecutionStatus
    inventory_before: EvalSuiteResumeInventory
    inventory_after: EvalSuiteResumeInventory
    policy_runs: tuple[EvalRun, ...]
    replay_runs: tuple[EvalMatrixReplayRecord, ...]
    eval_matrix: EvalMatrixRun | None


def classify_eval_suite_resume(
    eval_suite_dir: Path,
) -> EvalSuiteResumeInventory:
    """Classify every predeclared attempt without changing stored evidence."""

    eval_suite_dir = eval_suite_dir.resolve()
    declaration = load_eval_suite_declaration(
        eval_suite_dir / EVAL_SUITE_DECLARATION_FILENAME
    )
    validate_current_eval_suite_declaration(declaration)

    config_path = Path(declaration.config_path).resolve()
    config = load_eval_config(config_path)
    tasks_by_id = {
        task.task_id: task for task in resolve_eval_tasks(config, config_path)
    }
    declaration_hash = hash_eval_suite_declaration(declaration)
    decisions: list[EvalAttemptResumeDecision] = []

    for planned_policy in declaration.policy_runs:
        policy = config.policies[planned_policy.policy]
        policy_dir = resolve_relative_artifact_ref(
            eval_suite_dir,
            planned_policy.artifact_dir,
        )
        for planned_attempt in planned_policy.planned_attempts:
            attempt_path = policy_dir / planned_attempt.artifact_dir
            try:
                attempt_dir = resolve_relative_artifact_ref(
                    policy_dir,
                    planned_attempt.artifact_dir,
                )
            except ValueError as exc:
                decisions.append(
                    _decision(
                        planned_policy,
                        planned_attempt,
                        attempt_path.absolute(),
                        action="reject_attempt",
                        reason="attempt_path_not_directory",
                        detail=_error_detail(exc),
                    )
                )
                continue

            expected_eval_attempt = EvalAttemptReference(
                eval_suite_id=declaration.eval_suite_id,
                eval_run_id=planned_policy.eval_run_id,
                eval_attempt_id=planned_attempt.eval_attempt_id,
                eval_suite_declaration_hash=declaration_hash,
            )
            decisions.append(
                _classify_attempt(
                    attempt_dir=attempt_dir,
                    planned_policy=planned_policy,
                    planned_attempt=planned_attempt,
                    policy=policy,
                    expected_eval_attempt=expected_eval_attempt,
                    task_manifest_path=tasks_by_id[
                        planned_attempt.task_id
                    ].manifest_path,
                    task_manifest=tasks_by_id[planned_attempt.task_id].manifest,
                )
            )

    return EvalSuiteResumeInventory(
        eval_suite_dir=eval_suite_dir,
        declaration=declaration,
        decisions=tuple(decisions),
    )


def resume_eval_suite(eval_suite_dir: Path) -> EvalSuiteResumeResult:
    """Resume an interrupted predeclared suite without resampling terminal work."""

    inventory_before = classify_eval_suite_resume(eval_suite_dir)
    eval_suite_dir = inventory_before.eval_suite_dir
    suite_manifest_path = eval_suite_dir / MANIFEST_FILENAME
    if suite_manifest_path.exists():
        raise ValueError(
            "Cannot resume an eval suite after its terminal suite manifest exists"
        )

    declaration = inventory_before.declaration
    config_path = Path(declaration.config_path).resolve()
    config = load_eval_config(config_path)
    resolved_tasks = resolve_eval_tasks(config, config_path)
    tasks_by_id = {task.task_id: task for task in resolved_tasks}
    decisions_before_by_run = _decisions_by_eval_run(inventory_before)
    declaration_hash = hash_eval_suite_declaration(declaration)

    for planned_policy in declaration.policy_runs:
        policy = config.policies[planned_policy.policy]
        policy_decisions = decisions_before_by_run[planned_policy.eval_run_id]
        run_context = None
        if isinstance(policy, AgentModelPolicy) and any(
            decision.action == "run_attempt" for decision in policy_decisions
        ):
            run_context = eval_run_module._load_agent_model_run_context(
                config_path,
                policy,
            )
        if not isinstance(policy, AgentModelPolicy) or run_context is not None:
            eval_run_module._validate_declared_policy_execution(
                suite_declaration=declaration,
                planned_policy_run=planned_policy,
                config=config,
                config_path=config_path,
                config_hash=declaration.config_hash,
                task_hashes=declaration.task_hashes,
                runtime_provenance=declaration.runtime_provenance,
                agent_model_context=run_context,
            )

        for planned_attempt, decision in zip(
            planned_policy.planned_attempts,
            policy_decisions,
            strict=True,
        ):
            if decision.action in {
                "reuse_completed_attempt",
                "reject_attempt",
            }:
                continue
            if decision.action == "reuse_completed_generation":
                finish_and_persist_agent_task_attempt_from_generation(
                    decision.attempt_dir / AGENT_GENERATION_MANIFEST_FILENAME
                )
                continue
            if decision.action != "run_attempt":
                raise AssertionError(f"Unhandled resume action: {decision.action}")

            _clear_incomplete_attempt(decision.attempt_dir, eval_suite_dir)
            _run_declared_attempt(
                policy=policy,
                task=tasks_by_id[planned_attempt.task_id],
                attempt_dir=decision.attempt_dir,
                expected_eval_attempt=EvalAttemptReference(
                    eval_suite_id=declaration.eval_suite_id,
                    eval_run_id=planned_policy.eval_run_id,
                    eval_attempt_id=planned_attempt.eval_attempt_id,
                    eval_suite_declaration_hash=declaration_hash,
                ),
                run_context=run_context,
            )

    inventory_after = classify_eval_suite_resume(eval_suite_dir)
    unresolved = [
        decision
        for decision in inventory_after.decisions
        if decision.action not in {"reuse_completed_attempt", "reject_attempt"}
    ]
    if unresolved:
        unresolved_ids = ", ".join(decision.eval_attempt_id for decision in unresolved)
        raise RuntimeError(
            "Resume execution did not produce terminal evidence for declared "
            f"attempt(s): {unresolved_ids}"
        )

    _clear_owned_path(
        eval_suite_dir / EVAL_SUITE_ARTIFACT_REFS["replays"],
        root=eval_suite_dir,
    )
    decisions_after_by_run = _decisions_by_eval_run(inventory_after)
    policy_runs: list[EvalRun] = []
    for planned_policy in declaration.policy_runs:
        policy_dir = resolve_relative_artifact_ref(
            eval_suite_dir,
            planned_policy.artifact_dir,
        )
        policy_decisions = decisions_after_by_run[planned_policy.eval_run_id]
        if any(decision.action == "reject_attempt" for decision in policy_decisions):
            _clear_policy_completion_artifacts(policy_dir, eval_suite_dir)
            continue
        policy_run = _rebuild_completed_policy_run(
            declaration=declaration,
            planned_policy=planned_policy,
            config=config,
            config_path=config_path,
            eval_suite_dir=eval_suite_dir,
            policy_dir=policy_dir,
            decisions=policy_decisions,
            actions_before=decisions_before_by_run[planned_policy.eval_run_id],
        )
        policy_runs.append(policy_run)

    replay_runs = eval_run_module._replay_configured_policy_runs(
        config,
        policy_runs,
        eval_suite_dir,
    )
    if len(policy_runs) != len(declaration.policy_runs):
        return EvalSuiteResumeResult(
            status="rejected",
            inventory_before=inventory_before,
            inventory_after=inventory_after,
            policy_runs=tuple(policy_runs),
            replay_runs=tuple(replay_runs),
            eval_matrix=None,
        )

    eval_matrix = EvalMatrixRun(
        eval_suite_id=declaration.eval_suite_id,
        config=config,
        config_path=config_path,
        config_hash=declaration.config_hash,
        task_hashes=declaration.task_hashes,
        runtime_provenance=declaration.runtime_provenance,
        out_dir=eval_suite_dir,
        created_at=declaration.created_at,
        declaration=declaration,
        policy_runs=policy_runs,
        replay_runs=replay_runs,
    )
    eval_run_module._require_unchanged_eval_runtime(eval_matrix.runtime_provenance)
    eval_run_module._validate_eval_matrix_matches_declaration(eval_matrix)
    eval_run_module._write_eval_matrix_manifest(eval_matrix)
    return EvalSuiteResumeResult(
        status="completed",
        inventory_before=inventory_before,
        inventory_after=inventory_after,
        policy_runs=tuple(policy_runs),
        replay_runs=tuple(replay_runs),
        eval_matrix=eval_matrix,
    )


def _decisions_by_eval_run(
    inventory: EvalSuiteResumeInventory,
) -> dict[str, tuple[EvalAttemptResumeDecision, ...]]:
    grouped: dict[str, list[EvalAttemptResumeDecision]] = {
        planned_policy.eval_run_id: []
        for planned_policy in inventory.declaration.policy_runs
    }
    for decision in inventory.decisions:
        try:
            grouped[decision.eval_run_id].append(decision)
        except KeyError as exc:
            raise ValueError(
                "Resume inventory contains an undeclared eval run id"
            ) from exc

    result: dict[str, tuple[EvalAttemptResumeDecision, ...]] = {}
    for planned_policy in inventory.declaration.policy_runs:
        decisions = grouped[planned_policy.eval_run_id]
        observed_ids = [decision.eval_attempt_id for decision in decisions]
        expected_ids = [
            attempt.eval_attempt_id for attempt in planned_policy.planned_attempts
        ]
        if observed_ids != expected_ids:
            raise ValueError(
                "Resume inventory attempt order differs from suite declaration"
            )
        result[planned_policy.eval_run_id] = tuple(decisions)
    return result


def _clear_incomplete_attempt(attempt_dir: Path, eval_suite_dir: Path) -> None:
    terminal_paths = (
        attempt_dir / MANIFEST_FILENAME,
        attempt_dir / AGENT_GENERATION_MANIFEST_FILENAME,
    )
    if any(path.exists() for path in terminal_paths):
        raise ValueError(
            "Terminal attempt evidence appeared after resume classification; "
            "refusing to replace it"
        )
    _clear_owned_path(attempt_dir, root=eval_suite_dir)


def _clear_owned_path(path: Path, *, root: Path) -> None:
    root = root.resolve()
    path = path.resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f"Refusing to clear path outside eval suite: {path}")
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _run_declared_attempt(
    *,
    policy: EvalPolicy,
    task: ResolvedEvalTask,
    attempt_dir: Path,
    expected_eval_attempt: EvalAttemptReference,
    run_context: eval_run_module._AgentModelRunContext | None,
) -> None:
    if isinstance(policy, ScorerControlPatchPolicy):
        submission_path = scorer_control_patch_path(
            task.manifest_path.parent,
            task.manifest,
            policy.control,
        )
        run_and_persist_patch_attempt_to_dir(
            task.manifest_path,
            submission_path,
            attempt_dir,
            eval_attempt=expected_eval_attempt,
        )
        return

    if isinstance(policy, AgentControlScriptPolicy):
        control_case = load_agent_control_script_case(
            agent_control_script_path(
                task.manifest_path.parent,
                task.manifest,
                policy.control,
            )
        )
        model_client = ScriptedFakeModelClient(
            model_id="agent-control-scripted-v0",
            script=control_case.script.steps,
        )
        run_and_persist_agent_task_attempt_to_dir(
            task.manifest_path,
            model_client,
            model_client.default_decoding_config(),
            attempt_dir,
            agent_control_script=control_case,
            eval_attempt=expected_eval_attempt,
        )
        return

    if not isinstance(policy, AgentModelPolicy):
        raise AssertionError(f"Unhandled eval policy: {type(policy).__name__}")
    if run_context is None:
        raise AssertionError("Agent-model attempt requires a prepared run context")
    run_and_persist_agent_task_attempt_to_dir(
        task.manifest_path,
        run_context.model_client,
        run_context.decoding_config,
        attempt_dir,
        max_turns_override=policy.max_turns_override,
        model_config_provenance=run_context.model_config_provenance,
        decoding_config_provenance=run_context.decoding_config_provenance,
        eval_attempt=expected_eval_attempt,
    )


def _clear_policy_completion_artifacts(
    policy_dir: Path,
    eval_suite_dir: Path,
) -> None:
    for artifact_ref in (
        MANIFEST_FILENAME,
        EVAL_RUN_ARTIFACT_REFS["trace"],
    ):
        _clear_owned_path(policy_dir / artifact_ref, root=eval_suite_dir)


def _rebuild_completed_policy_run(
    *,
    declaration: EvalSuiteDeclaration,
    planned_policy: PlannedEvalPolicyRun,
    config: EvalConfig,
    config_path: Path,
    eval_suite_dir: Path,
    policy_dir: Path,
    decisions: tuple[EvalAttemptResumeDecision, ...],
    actions_before: tuple[EvalAttemptResumeDecision, ...],
) -> EvalRun:
    attempt_records = [
        _load_completed_attempt_record(planned_attempt, decision.attempt_dir)
        for planned_attempt, decision in zip(
            planned_policy.planned_attempts,
            decisions,
            strict=True,
        )
    ]
    eval_run = EvalRun(
        eval_run_id=planned_policy.eval_run_id,
        config=config,
        config_path=config_path,
        config_hash=declaration.config_hash,
        task_hashes=declaration.task_hashes,
        runtime_provenance=declaration.runtime_provenance,
        policy=planned_policy.policy,
        out_dir=policy_dir,
        created_at=declaration.created_at,
        attempts=attempt_records,
    )
    eval_run_module._validate_unique_eval_attempt_ids(eval_run.attempts)
    _clear_policy_completion_artifacts(policy_dir, eval_suite_dir)
    policy_dir.mkdir(parents=True, exist_ok=True)

    trace_events: list[eval_run_module.TraceEvent] = []
    provenance = eval_run_module._eval_provenance(
        eval_run.eval_run_id,
        eval_run.config_hash,
        eval_run.config.name,
        policy=eval_run.policy,
    )
    eval_run_module._append_trace(
        trace_events,
        provenance,
        "eval_started",
        input_payload={
            "config_path": str(config_path),
            "policy": planned_policy.policy,
            "split": eval_run.config.split,
            "task_count": len(eval_run.config.tasks),
            "attempts_per_task": eval_run.config.policies[
                planned_policy.policy
            ].attempts,
            "execution_mode": "resume",
            "resume_action_counts": dict(
                Counter(decision.action for decision in actions_before)
            ),
        },
    )
    eval_run_module._append_trace(
        trace_events,
        provenance,
        "eval_finished",
        output_payload={
            "attempt_count": len(eval_run.attempts),
            "layer_counts": eval_run_module.count_eval_run_layers(eval_run),
        },
        payload_refs={"manifest": MANIFEST_FILENAME},
    )
    eval_run_module._write_eval_trace(eval_run, trace_events)
    eval_run_module._require_unchanged_eval_runtime(eval_run.runtime_provenance)
    eval_run_module._write_eval_run_manifest(eval_run)
    return eval_run


def _load_completed_attempt_record(
    planned_attempt: PlannedEvalAttempt,
    attempt_dir: Path,
) -> EvalAttemptRecord:
    manifest = load_attempt_manifest(attempt_dir / MANIFEST_FILENAME)
    artifact_identity = eval_run_module._child_artifact_identity(attempt_dir)
    if isinstance(manifest, ScorerAttemptManifest):
        result = load_attempt_result(
            resolve_manifest_artifact_path(
                attempt_dir,
                manifest.artifacts,
                "attempt",
            )
        )
        scorer = eval_run_module._scorer_summary(result)
        agent = None
    elif isinstance(manifest, AgentTaskRunManifest):
        result = load_agent_task_run_result(
            resolve_manifest_artifact_path(
                attempt_dir,
                manifest.artifacts,
                "agent_task_run",
            )
        )
        scorer = None
        agent = eval_run_module._agent_summary(result)
    else:
        raise AssertionError(f"Unhandled attempt manifest: {type(manifest).__name__}")
    return EvalAttemptRecord(
        eval_attempt_id=planned_attempt.eval_attempt_id,
        task_id=planned_attempt.task_id,
        attempt_index=planned_attempt.attempt_index,
        attempt_dir=attempt_dir,
        artifact_type=artifact_identity.artifact_type,
        artifact_schema_version=artifact_identity.artifact_schema_version,
        scorer=scorer,
        agent=agent,
    )


def _classify_attempt(
    *,
    attempt_dir: Path,
    planned_policy: PlannedEvalPolicyRun,
    planned_attempt: PlannedEvalAttempt,
    policy: EvalPolicy,
    expected_eval_attempt: EvalAttemptReference,
    task_manifest_path: Path,
    task_manifest: TaskManifest,
) -> EvalAttemptResumeDecision:
    if not attempt_dir.exists():
        return _decision(
            planned_policy,
            planned_attempt,
            attempt_dir,
            action="run_attempt",
            reason="not_started",
        )
    if not attempt_dir.is_dir():
        return _decision(
            planned_policy,
            planned_attempt,
            attempt_dir,
            action="reject_attempt",
            reason="attempt_path_not_directory",
        )

    attempt_manifest_path = attempt_dir / MANIFEST_FILENAME
    if attempt_manifest_path.exists():
        try:
            if not attempt_manifest_path.is_file():
                raise ValueError("Terminal attempt manifest path is not a file")
            _validate_completed_attempt(
                attempt_dir=attempt_dir,
                expected_eval_attempt=expected_eval_attempt,
                task_manifest_path=task_manifest_path,
                task_manifest=task_manifest,
                policy=policy,
                planned_policy=planned_policy,
            )
        except (OSError, ValueError) as exc:
            return _decision(
                planned_policy,
                planned_attempt,
                attempt_dir,
                action="reject_attempt",
                reason="invalid_completed_attempt",
                detail=_error_detail(exc),
            )
        return _decision(
            planned_policy,
            planned_attempt,
            attempt_dir,
            action="reuse_completed_attempt",
            reason="completed_attempt",
        )

    generation_path = attempt_dir / AGENT_GENERATION_MANIFEST_FILENAME
    if generation_path.exists():
        if not isinstance(policy, AgentModelPolicy):
            return _decision(
                planned_policy,
                planned_attempt,
                attempt_dir,
                action="reject_attempt",
                reason="unexpected_generation_for_policy",
            )
        try:
            if not generation_path.is_file():
                raise ValueError("Terminal generation manifest path is not a file")
            _validate_generation_for_declaration(
                generation_path,
                planned_policy=planned_policy,
                expected_eval_attempt=expected_eval_attempt,
                expected_task_id=task_manifest.id,
                task_manifest_path=task_manifest_path,
            )
        except (OSError, ValueError) as exc:
            return _decision(
                planned_policy,
                planned_attempt,
                attempt_dir,
                action="reject_attempt",
                reason="invalid_terminal_generation",
                detail=_error_detail(exc),
            )
        return _decision(
            planned_policy,
            planned_attempt,
            attempt_dir,
            action="reuse_completed_generation",
            reason="terminal_generation",
        )

    return _decision(
        planned_policy,
        planned_attempt,
        attempt_dir,
        action="run_attempt",
        reason="incomplete_without_terminal_result",
    )


def _validate_completed_attempt(
    *,
    attempt_dir: Path,
    expected_eval_attempt: EvalAttemptReference,
    task_manifest_path: Path,
    task_manifest: TaskManifest,
    policy: EvalPolicy,
    planned_policy: PlannedEvalPolicyRun,
) -> None:
    manifest = load_attempt_manifest(attempt_dir / MANIFEST_FILENAME)
    if manifest.eval_attempt != expected_eval_attempt:
        raise ValueError("Terminal attempt does not match its declared eval identity")
    expected_task_id = task_manifest.id
    if manifest.task_id != expected_task_id:
        raise ValueError("Terminal attempt task id does not match declaration")
    if Path(manifest.task_manifest_path).resolve() != task_manifest_path.resolve():
        raise ValueError(
            "Terminal attempt task manifest path does not match declaration"
        )

    if isinstance(policy, ScorerControlPatchPolicy):
        if not isinstance(manifest, ScorerAttemptManifest):
            raise ValueError("Scorer policy has a non-scorer terminal attempt")
        expected_submission = scorer_control_patch_path(
            task_manifest_path.parent,
            task_manifest,
            policy.control,
        )
        if Path(manifest.submission_path).resolve() != expected_submission.resolve():
            raise ValueError("Scorer attempt submission does not match policy")
        _validate_scorer_attempt(attempt_dir, manifest)
        return

    if not isinstance(manifest, AgentTaskRunManifest):
        raise ValueError("Agent policy has a non-agent terminal attempt")
    agent_result = _validate_agent_attempt(attempt_dir, manifest)

    if isinstance(policy, AgentControlScriptPolicy):
        stored_control = load_agent_control_script_artifact(
            resolve_manifest_artifact_path(
                attempt_dir,
                manifest.artifacts,
                "agent_control_script",
            )
        )
        expected_control = load_agent_control_script_case(
            agent_control_script_path(
                task_manifest_path.parent,
                task_manifest,
                policy.control,
            )
        )
        if stored_control != expected_control:
            raise ValueError("Agent control attempt does not match policy script")
        if "generation" in manifest.artifacts:
            raise ValueError("Agent control attempt cannot contain model generation")
        return

    if not isinstance(policy, AgentModelPolicy):
        raise AssertionError(f"Unhandled eval policy: {type(policy).__name__}")
    generation_ref = manifest.artifacts.get("generation")
    if generation_ref is None:
        raise ValueError("Agent-model attempt is missing terminal generation")
    if manifest.prompt_loop_status is None:
        raise ValueError("Agent-model attempt is missing prompt-loop status")
    generation = validate_agent_generation_for_eval_attempt(
        resolve_relative_artifact_ref(attempt_dir, generation_ref),
        expected_eval_attempt=expected_eval_attempt,
        expected_agent_attempt_id=manifest.agent_attempt_id,
        expected_task_id=expected_task_id,
        expected_task_manifest_path=task_manifest_path,
        expected_prompt_loop_status=manifest.prompt_loop_status,
        expected_candidate_patch_hash=agent_result.candidate_patch_hash,
        expected_model_config_provenance=_required_model_provenance(planned_policy),
        expected_decoding_config_provenance=_required_decoding_provenance(
            planned_policy
        ),
    )
    for artifact_name in ("model_config", "decoding_config"):
        if (
            manifest.artifacts.get(artifact_name)
            != generation.manifest.artifacts[artifact_name]
        ):
            raise ValueError(
                "Agent attempt and terminal generation input references differ"
            )


def _validate_generation_for_declaration(
    generation_path: Path,
    *,
    planned_policy: PlannedEvalPolicyRun,
    expected_eval_attempt: EvalAttemptReference,
    expected_task_id: str,
    task_manifest_path: Path,
) -> ValidatedAgentGeneration:
    generation = load_validated_agent_generation(generation_path)
    compared_fields = (
        ("eval identity", generation.manifest.eval_attempt, expected_eval_attempt),
        ("task id", generation.manifest.task_id, expected_task_id),
        (
            "task manifest path",
            Path(generation.manifest.task_manifest_path).resolve(),
            task_manifest_path.resolve(),
        ),
        (
            "model provenance",
            generation.model_config_provenance,
            _required_model_provenance(planned_policy),
        ),
        (
            "decoding provenance",
            generation.decoding_config_provenance,
            _required_decoding_provenance(planned_policy),
        ),
    )
    for field_name, observed, expected in compared_fields:
        if observed != expected:
            raise ValueError(
                f"Terminal generation {field_name} does not match declaration"
            )
    return generation


def _validate_agent_attempt(
    attempt_dir: Path,
    manifest: AgentTaskRunManifest,
) -> AgentTaskRunResult:
    for artifact_name, artifact_ref in manifest.artifacts.items():
        artifact_path = resolve_relative_artifact_ref(attempt_dir, artifact_ref)
        if artifact_name == "attempt":
            if not artifact_path.is_dir():
                raise ValueError(
                    f"Agent nested scorer directory is missing: {artifact_path}"
                )
        elif not artifact_path.is_file():
            raise ValueError(f"Agent attempt artifact is missing: {artifact_path}")

    agent_result = load_agent_task_run_result(
        resolve_manifest_artifact_path(
            attempt_dir,
            manifest.artifacts,
            "agent_task_run",
        )
    )
    validate_agent_result_matches_manifest(agent_result, manifest, attempt_dir)
    validate_agent_payload_refs_match_manifest(manifest, attempt_dir)

    candidate_ref = manifest.artifacts.get("candidate_patch")
    if agent_result.candidate_patch_hash is not None:
        if candidate_ref is None:
            raise ValueError("Agent result candidate is missing from manifest")
        candidate = resolve_relative_artifact_ref(
            attempt_dir, candidate_ref
        ).read_text()
        if hash_diff(candidate) != agent_result.candidate_patch_hash:
            raise ValueError("Agent candidate patch hash does not match result")
    elif candidate_ref is not None:
        raise ValueError("Agent manifest has an unexpected candidate patch")

    nested_attempt_ref = manifest.artifacts.get("attempt")
    if nested_attempt_ref is None:
        if agent_result.attempt_result is not None:
            raise ValueError("Agent result has an unreferenced scorer attempt")
        return agent_result
    if agent_result.attempt_result is None:
        raise ValueError("Agent result is missing its referenced scorer attempt")
    nested_attempt_dir = resolve_relative_artifact_ref(
        attempt_dir,
        nested_attempt_ref,
    )
    nested_manifest = load_scorer_attempt_manifest(
        nested_attempt_dir / MANIFEST_FILENAME
    )
    if nested_manifest.eval_attempt is not None:
        raise ValueError("Nested scorer attempt cannot claim a planned eval attempt")
    nested_result = _validate_scorer_attempt(nested_attempt_dir, nested_manifest)
    validate_scorer_result_matches_summary(
        nested_result,
        agent_result.attempt_result,
        attempt_dir,
        context="agent task run nested attempt result",
    )
    return agent_result


def _validate_scorer_attempt(
    attempt_dir: Path,
    manifest: ScorerAttemptManifest,
) -> AttemptResult:
    for artifact_ref in manifest.artifacts.values():
        artifact_path = resolve_relative_artifact_ref(attempt_dir, artifact_ref)
        if not artifact_path.is_file():
            raise ValueError(f"Scorer attempt artifact is missing: {artifact_path}")

    result = load_attempt_result(
        resolve_manifest_artifact_path(
            attempt_dir,
            manifest.artifacts,
            "attempt",
        )
    )
    validate_scorer_result_matches_manifest(result, manifest, attempt_dir)
    validate_trace_file(
        resolve_manifest_artifact_path(
            attempt_dir,
            manifest.artifacts,
            "trace",
        )
    )
    if result.final_diff_hash is not None:
        final_diff = resolve_manifest_artifact_path(
            attempt_dir,
            manifest.artifacts,
            "final_diff",
        ).read_text()
        if hash_diff(final_diff) != result.final_diff_hash:
            raise ValueError("Scorer final diff hash does not match result")
    return result


def _required_model_provenance(
    planned_policy: PlannedEvalPolicyRun,
) -> ModelConfigProvenance:
    provenance = planned_policy.model_config_provenance
    if provenance is None:
        raise ValueError("Agent-model declaration is missing model provenance")
    return provenance


def _required_decoding_provenance(
    planned_policy: PlannedEvalPolicyRun,
) -> DecodingConfigProvenance:
    provenance = planned_policy.decoding_config_provenance
    if provenance is None:
        raise ValueError("Agent-model declaration is missing decoding provenance")
    return provenance


def _decision(
    planned_policy: PlannedEvalPolicyRun,
    planned_attempt: PlannedEvalAttempt,
    attempt_dir: Path,
    *,
    action: ResumeAction,
    reason: ResumeReason,
    detail: str | None = None,
) -> EvalAttemptResumeDecision:
    return EvalAttemptResumeDecision(
        policy=planned_policy.policy,
        eval_run_id=planned_policy.eval_run_id,
        eval_attempt_id=planned_attempt.eval_attempt_id,
        task_id=planned_attempt.task_id,
        attempt_index=planned_attempt.attempt_index,
        attempt_dir=attempt_dir,
        action=action,
        reason=reason,
        detail=detail,
    )


def _error_detail(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
