from pathlib import Path

import yaml

from agentenv.evals.resolve import scorer_control_patch_path, resolve_eval_tasks
from agentenv.evals.schema import EvalConfig
from agentenv.tasks.validate import validate_task_manifest_paths


def load_eval_config(path: Path) -> EvalConfig:
    raw_config = yaml.safe_load(path.read_text())
    if not isinstance(raw_config, dict):
        raise ValueError(f"Expected eval config YAML mapping at {path}")
    return EvalConfig.model_validate(raw_config)


def validate_eval_config_paths(config: EvalConfig, config_path: Path) -> None:
    resolved_tasks = resolve_eval_tasks(config, config_path)
    for task in resolved_tasks:
        validate_task_manifest_paths(task.manifest, task.manifest_path)
        for policy in config.policies.values():
            scorer_control_patch_path(
                task.manifest_path.parent,
                task.manifest,
                policy.control,
            )

    configured_task_ids = set(config.tasks)
    resolved_task_ids = {task.task_id for task in resolved_tasks}
    if configured_task_ids != resolved_task_ids:
        raise ValueError(
            "Resolved task ids do not match configured task ids: "
            f"configured={sorted(configured_task_ids)} "
            f"resolved={sorted(resolved_task_ids)}"
        )
