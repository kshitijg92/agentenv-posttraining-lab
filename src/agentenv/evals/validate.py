from pathlib import Path

import yaml

from agentenv.evals.resolve import (
    agent_control_script_path,
    resolve_config_file_ref,
    resolve_task_pack_path,
    resolve_eval_tasks,
    scorer_control_patch_path,
)
from agentenv.evals.schema import (
    AGENT_CONTROL_SCRIPT_POLICY_TYPE,
    AGENT_MODEL_POLICY_TYPE,
    SCORER_CONTROL_PATCH_POLICY_TYPE,
    EvalConfig,
)
from agentenv.models.config import (
    load_decoding_config,
    load_model_config,
    load_referenced_model_input_protocol,
    validate_ollama_lora_reference,
)
from agentenv.models.config_schema import OllamaGenerateModelConfig
from agentenv.tasks.hashing import build_eval_task_hashes
from agentenv.tasks.validate import validate_task_manifest_paths


def load_eval_config(path: Path) -> EvalConfig:
    raw_config = yaml.safe_load(path.read_text())
    if not isinstance(raw_config, dict):
        raise ValueError(f"Expected eval config YAML mapping at {path}")
    return EvalConfig.model_validate(raw_config)


def validate_eval_config_paths(config: EvalConfig, config_path: Path) -> None:
    resolved_tasks = resolve_eval_tasks(config, config_path)
    task_pack_path = resolve_task_pack_path(config, config_path)
    if config.expected_task_hash_set is not None:
        observed_task_hash_set = build_eval_task_hashes(
            task_pack_path,
            config.tasks,
        ).selected_task_hash_set
        if observed_task_hash_set != config.expected_task_hash_set:
            raise ValueError(
                "Eval task hash set does not match the config freeze: "
                f"expected={config.expected_task_hash_set} "
                f"observed={observed_task_hash_set}"
            )
    for task in resolved_tasks:
        validate_task_manifest_paths(task.manifest, task.manifest_path)
        for policy in config.policies.values():
            if policy.type == SCORER_CONTROL_PATCH_POLICY_TYPE:
                scorer_control_patch_path(
                    task.manifest_path.parent,
                    task.manifest,
                    policy.control,
                )
            elif policy.type == AGENT_CONTROL_SCRIPT_POLICY_TYPE:
                agent_control_script_path(
                    task.manifest_path.parent,
                    task.manifest,
                    policy.control,
                )
            elif policy.type == AGENT_MODEL_POLICY_TYPE:
                pass
            else:
                raise AssertionError(f"Unhandled eval policy type: {policy.type}")

    adapter_training_task_sets: list[frozenset[str]] = []
    load_adapter_training_task_ids = None
    if config.adapter_training_task_scope is not None:
        # Import lazily: the positive-SFT export path reads eval configs while
        # constructing trajectory-derived records.
        from agentenv.training.positive_sft.lora.workflow import (
            load_positive_sft_lora_training_task_ids,
        )

        load_adapter_training_task_ids = load_positive_sft_lora_training_task_ids

    for policy in config.policies.values():
        if policy.type != AGENT_MODEL_POLICY_TYPE:
            continue
        model_config_path = resolve_config_file_ref(
            config_path,
            policy.model_config_path,
            field_name="model_config",
        )
        model_config = load_model_config(model_config_path)
        model_input_protocol = load_referenced_model_input_protocol(
            model_config,
            model_config_path,
        )
        if config.adapter_training_task_scope is not None:
            if not isinstance(model_config, OllamaGenerateModelConfig):
                raise ValueError(
                    "adapter training task scope requires Ollama model configs"
                )
            if model_input_protocol is None:
                raise ValueError(
                    "adapter training task scope requires a model input protocol"
                )
            adapter_dir = validate_ollama_lora_reference(
                model_config,
                model_config_path,
                model_input_protocol=model_input_protocol,
            )
            if adapter_dir is not None:
                assert load_adapter_training_task_ids is not None
                adapter_training_task_sets.append(
                    load_adapter_training_task_ids(adapter_dir.parent)
                )
        load_decoding_config(
            resolve_config_file_ref(
                config_path,
                policy.decoding_config_path,
                field_name="decoding_config",
            )
        )

    if config.adapter_training_task_scope == "matched_and_disjoint":
        if len(adapter_training_task_sets) < 2:
            raise ValueError(
                "matched adapter training task scope requires at least two adapters"
            )
        if any(
            task_ids != adapter_training_task_sets[0]
            for task_ids in adapter_training_task_sets[1:]
        ):
            raise ValueError("adapted policies must have matching training task ids")
        overlap = set(config.tasks) & adapter_training_task_sets[0]
        if overlap:
            raise ValueError(
                "adapter training tasks must be disjoint from eval tasks: "
                + ", ".join(sorted(overlap))
            )

    configured_task_ids = set(config.tasks)
    resolved_task_ids = {task.task_id for task in resolved_tasks}
    if configured_task_ids != resolved_task_ids:
        raise ValueError(
            "Resolved task ids do not match configured task ids: "
            f"configured={sorted(configured_task_ids)} "
            f"resolved={sorted(resolved_task_ids)}"
        )
