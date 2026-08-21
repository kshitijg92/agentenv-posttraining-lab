from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    AgentGenerationEvalAttemptReference,
    EvalRunManifest,
    EvalSuiteManifest,
    EvalSuitePolicyRunManifestRecord,
    load_agent_attempt_manifest,
    load_eval_run_manifest,
    load_eval_suite_manifest,
)
from agentenv.evals.resolve import resolve_task_pack_path
from agentenv.evals.schema import (
    AGENT_CONTROL_LAYER,
    AGENT_CONTROL_SCRIPT_POLICY_TYPE,
    AGENT_MODEL_POLICY_TYPE,
    AGENT_POLICY_FAMILY,
    CONTROL_POLICY_FAMILY,
    SCORER_CONTROL_LAYER,
    SCORER_CONTROL_PATCH_POLICY_TYPE,
    EvalConfig,
    EvalPolicy,
)
from agentenv.evals.suite_declaration import (
    EvalSuiteDeclaration,
    PlannedEvalPolicyRun,
    hash_eval_suite_declaration,
    load_eval_suite_declaration,
)
from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.hashing import hash_file
from agentenv.orchestrators.agent_generation import (
    validate_agent_generation_for_eval_attempt,
)
from agentenv.tasks.hashing import build_eval_task_hashes


@dataclass(frozen=True)
class ValidatedEvalSuite:
    eval_suite_dir: Path
    manifest: EvalSuiteManifest
    config_path: Path
    config: EvalConfig
    declaration: EvalSuiteDeclaration | None


def load_validated_eval_suite(
    eval_suite_dir: Path,
) -> ValidatedEvalSuite:
    """Bind an eval-suite manifest to its current config and task bytes."""

    eval_suite_dir = eval_suite_dir.resolve()
    manifest = load_eval_suite_manifest(eval_suite_dir / MANIFEST_FILENAME)
    config_path = Path(manifest.config_path)
    observed_config_hash = hash_file(config_path)
    if observed_config_hash != manifest.config_hash:
        raise ValueError(
            "Eval suite config hash does not match the current config bytes: "
            f"{observed_config_hash!r} != {manifest.config_hash!r}"
        )

    config = load_eval_config(config_path)
    validate_eval_config_paths(config, config_path)
    _validate_suite_matches_config(manifest, config, config_path)
    declaration = _load_optional_declaration(eval_suite_dir, manifest)
    if declaration is not None:
        _validate_completed_suite_matches_declaration(
            eval_suite_dir,
            manifest,
            declaration,
        )
    return ValidatedEvalSuite(
        eval_suite_dir=eval_suite_dir,
        manifest=manifest,
        config_path=config_path,
        config=config,
        declaration=declaration,
    )


def _load_optional_declaration(
    eval_suite_dir: Path,
    manifest: EvalSuiteManifest,
) -> EvalSuiteDeclaration | None:
    declaration_ref = manifest.artifacts.get("declaration")
    if declaration_ref is None:
        return None
    return load_eval_suite_declaration(
        resolve_relative_artifact_ref(eval_suite_dir, declaration_ref)
    )


def _validate_completed_suite_matches_declaration(
    eval_suite_dir: Path,
    manifest: EvalSuiteManifest,
    declaration: EvalSuiteDeclaration,
) -> None:
    compared_fields = (
        ("eval_suite_id", declaration.eval_suite_id, manifest.eval_suite_id),
        ("created_at", declaration.created_at, manifest.created_at),
        (
            "config_path",
            Path(declaration.config_path).resolve(),
            Path(manifest.config_path).resolve(),
        ),
        ("config_hash", declaration.config_hash, manifest.config_hash),
        ("task_hashes", declaration.task_hashes, manifest.task_hashes),
        (
            "runtime_provenance",
            declaration.runtime_provenance,
            manifest.runtime_provenance,
        ),
    )
    for field_name, declared, completed in compared_fields:
        if declared != completed:
            raise ValueError(
                f"Completed eval suite {field_name} differs from its declaration"
            )

    if len(declaration.policy_runs) != len(manifest.policy_runs):
        raise ValueError("Completed eval suite policy count differs from declaration")
    for planned_policy_run, completed_policy_run in zip(
        declaration.policy_runs,
        manifest.policy_runs,
        strict=True,
    ):
        _validate_completed_policy_run_matches_declaration(
            eval_suite_dir,
            declaration,
            planned_policy_run,
            completed_policy_run,
        )


def _validate_completed_policy_run_matches_declaration(
    eval_suite_dir: Path,
    declaration: EvalSuiteDeclaration,
    planned: PlannedEvalPolicyRun,
    completed: EvalSuitePolicyRunManifestRecord,
) -> None:
    observed_policy_identity = (
        completed.policy,
        completed.eval_run_id,
        completed.artifact_dir,
    )
    declared_policy_identity = (
        planned.policy,
        planned.eval_run_id,
        planned.artifact_dir,
    )
    if observed_policy_identity != declared_policy_identity:
        raise ValueError("Completed eval policy run differs from its declaration")

    eval_run_manifest_path = resolve_relative_artifact_ref(
        eval_suite_dir,
        completed.manifest,
    )
    eval_run_manifest = load_eval_run_manifest(eval_run_manifest_path)
    _validate_child_run_identity(completed, eval_run_manifest)
    observed_attempts = [
        (
            attempt.eval_attempt_id,
            attempt.task_id,
            attempt.attempt_index,
            attempt.artifact_dir,
        )
        for attempt in eval_run_manifest.attempts
    ]
    declared_attempts = [
        (
            attempt.eval_attempt_id,
            attempt.task_id,
            attempt.attempt_index,
            attempt.artifact_dir,
        )
        for attempt in planned.planned_attempts
    ]
    if observed_attempts != declared_attempts:
        raise ValueError(
            "Completed eval attempts differ from the predeclared attempt set"
        )
    _validate_completed_model_inputs(
        eval_run_manifest_path.parent,
        declaration,
        planned,
        eval_run_manifest,
    )


def _validate_child_run_identity(
    suite_record: EvalSuitePolicyRunManifestRecord,
    child_manifest: EvalRunManifest,
) -> None:
    compared_fields = (
        ("eval_run_id", suite_record.eval_run_id, child_manifest.eval_run_id),
        ("policy", suite_record.policy, child_manifest.policy),
    )
    for field_name, suite_value, child_value in compared_fields:
        if suite_value != child_value:
            raise ValueError(
                "Eval suite policy run record does not match child manifest "
                f"field {field_name!r}"
            )


def _validate_completed_model_inputs(
    eval_run_dir: Path,
    declaration: EvalSuiteDeclaration,
    planned: PlannedEvalPolicyRun,
    eval_run_manifest: EvalRunManifest,
) -> None:
    declared_model = planned.model_config_provenance
    declared_decoding = planned.decoding_config_provenance
    if declared_model is None and declared_decoding is None:
        return
    if declared_model is None or declared_decoding is None:
        raise ValueError("Declared model input provenance is incomplete")

    for attempt in eval_run_manifest.attempts:
        attempt_dir = resolve_relative_artifact_ref(
            eval_run_dir,
            attempt.artifact_dir,
        )
        attempt_manifest = load_agent_attempt_manifest(
            attempt_dir / MANIFEST_FILENAME
        )
        generation_ref = attempt_manifest.artifacts.get("generation")
        if generation_ref is None:
            raise ValueError(
                "Declared agent-model attempt is missing terminal generation"
            )
        expected_eval_attempt = AgentGenerationEvalAttemptReference(
            eval_suite_id=declaration.eval_suite_id,
            eval_run_id=planned.eval_run_id,
            eval_attempt_id=attempt.eval_attempt_id,
            eval_suite_declaration_hash=hash_eval_suite_declaration(declaration),
        )
        if attempt.agent is None:
            raise ValueError("Agent-model eval attempt is missing agent summary")
        if attempt_manifest.prompt_loop_status is None:
            raise ValueError(
                "Declared agent-model attempt is missing prompt-loop status"
            )
        generation = validate_agent_generation_for_eval_attempt(
            resolve_relative_artifact_ref(attempt_dir, generation_ref),
            expected_eval_attempt=expected_eval_attempt,
            expected_agent_attempt_id=attempt_manifest.agent_attempt_id,
            expected_task_id=attempt.task_id,
            expected_task_manifest_path=Path(attempt_manifest.task_manifest_path),
            expected_prompt_loop_status=attempt_manifest.prompt_loop_status,
            expected_candidate_patch_hash=attempt.agent.candidate_patch_hash,
            expected_model_config_provenance=declared_model,
            expected_decoding_config_provenance=declared_decoding,
        )
        if attempt.agent.agent_attempt_id != attempt_manifest.agent_attempt_id:
            raise ValueError("Agent attempt and eval summary ids differ")
        if attempt.agent.prompt_loop_status != attempt_manifest.prompt_loop_status:
            raise ValueError(
                "Agent attempt and eval summary prompt-loop statuses differ"
            )
        model_ref = attempt_manifest.artifacts.get("model_config")
        if model_ref is None:
            raise ValueError("Declared agent-model attempt is missing model config")
        if model_ref != generation.manifest.artifacts["model_config"]:
            raise ValueError(
                "Agent attempt and generation model config references differ"
            )
        decoding_ref = attempt_manifest.artifacts.get("decoding_config")
        if decoding_ref is None:
            raise ValueError("Declared agent-model attempt is missing decoding config")
        if decoding_ref != generation.manifest.artifacts["decoding_config"]:
            raise ValueError(
                "Agent attempt and generation decoding config references differ"
            )


def _validate_suite_matches_config(
    manifest: EvalSuiteManifest,
    config: EvalConfig,
    config_path: Path,
) -> None:
    compared_fields = (
        ("config_name", config.name, manifest.config_name),
        ("task_pack", config.task_pack, manifest.task_pack),
        ("split", config.split, manifest.split),
        ("tasks", config.tasks, manifest.tasks),
    )
    for field_name, config_value, suite_value in compared_fields:
        if config_value != suite_value:
            raise ValueError(
                f"Eval suite {field_name} does not match its config: "
                f"{suite_value!r} != {config_value!r}"
            )

    live_task_hashes = build_eval_task_hashes(
        resolve_task_pack_path(config, config_path),
        config.tasks,
    )
    if live_task_hashes != manifest.task_hashes:
        raise ValueError("Eval suite task hashes do not match current task bytes")

    expected_policy_order = tuple(config.policies)
    observed_policy_order = tuple(
        policy_run.policy for policy_run in manifest.policy_runs
    )
    if observed_policy_order != expected_policy_order:
        raise ValueError(
            "Eval suite policy order does not match its config: "
            f"{observed_policy_order!r} != {expected_policy_order!r}"
        )

    for policy_run in manifest.policy_runs:
        _validate_policy_run_matches_config(
            policy_run,
            config.policies[policy_run.policy],
        )


def _validate_policy_run_matches_config(
    policy_run: EvalSuitePolicyRunManifestRecord,
    policy: EvalPolicy,
) -> None:
    expected = _expected_policy_metadata(policy)
    observed = {
        "policy_type": policy_run.policy_type,
        "policy_family": policy_run.policy_family,
        "control_layer": policy_run.control_layer,
        "control_name": policy_run.control_name,
        "model_config": policy_run.model_config_ref,
        "decoding_config": policy_run.decoding_config_ref,
        "max_turns_override": policy_run.max_turns_override,
        "attempts_per_task": policy_run.attempts_per_task,
        "replay_repeats": policy_run.replay_repeats,
    }
    for field_name, expected_value in expected.items():
        observed_value = observed[field_name]
        if observed_value != expected_value:
            raise ValueError(
                f"Eval suite policy {policy_run.policy!r} {field_name} does not "
                f"match its config: {observed_value!r} != {expected_value!r}"
            )


def _expected_policy_metadata(policy: EvalPolicy) -> dict[str, object]:
    common: dict[str, object] = {
        "model_config": None,
        "decoding_config": None,
        "max_turns_override": None,
        "attempts_per_task": policy.attempts,
        "replay_repeats": policy.replay.repeats,
    }
    if policy.type == SCORER_CONTROL_PATCH_POLICY_TYPE:
        return {
            "policy_type": policy.type,
            "policy_family": CONTROL_POLICY_FAMILY,
            "control_layer": SCORER_CONTROL_LAYER,
            "control_name": policy.control,
            **common,
        }
    if policy.type == AGENT_CONTROL_SCRIPT_POLICY_TYPE:
        return {
            "policy_type": policy.type,
            "policy_family": CONTROL_POLICY_FAMILY,
            "control_layer": AGENT_CONTROL_LAYER,
            "control_name": policy.control,
            **common,
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
            "attempts_per_task": policy.attempts,
            "replay_repeats": policy.replay.repeats,
        }
    raise AssertionError(f"Unhandled eval policy type: {policy.type}")
