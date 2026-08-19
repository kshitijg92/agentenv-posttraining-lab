from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    EvalSuiteManifest,
    EvalSuitePolicyRunManifestRecord,
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
from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.hashing import hash_file
from agentenv.tasks.hashing import build_eval_task_hashes


@dataclass(frozen=True)
class ValidatedEvalSuiteDeclaration:
    eval_suite_dir: Path
    manifest: EvalSuiteManifest
    config_path: Path
    config: EvalConfig


def load_validated_eval_suite_declaration(
    eval_suite_dir: Path,
) -> ValidatedEvalSuiteDeclaration:
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
    return ValidatedEvalSuiteDeclaration(
        eval_suite_dir=eval_suite_dir,
        manifest=manifest,
        config_path=config_path,
        config=config,
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
