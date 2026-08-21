from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    AGENT_GENERATION_MANIFEST_FILENAME,
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
    agent_control_script_path,
    resolve_eval_tasks,
    scorer_control_patch_path,
)
from agentenv.evals.schema import (
    AgentControlScriptPolicy,
    AgentModelPolicy,
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
from agentenv.orchestrators.agent_generation import (
    ValidatedAgentGeneration,
    load_validated_agent_generation,
    validate_agent_generation_for_eval_attempt,
)
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.eval_run import (
    validate_current_eval_suite_declaration,
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
        raise ValueError("Terminal attempt task manifest path does not match declaration")

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
        if manifest.artifacts.get(artifact_name) != generation.manifest.artifacts[
            artifact_name
        ]:
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
        candidate = resolve_relative_artifact_ref(attempt_dir, candidate_ref).read_text()
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
