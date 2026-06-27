from dataclasses import dataclass
from pathlib import Path

from agentenv.evals.schema import ControlName, EvalConfig, ScorerControlPatchPolicy
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest


@dataclass(frozen=True)
class ResolvedEvalTask:
    task_id: str
    manifest_path: Path
    manifest: TaskManifest


def resolve_task_pack_path(config: EvalConfig, config_path: Path) -> Path:
    relative_to_config = (config_path.parent / config.task_pack).resolve()
    if relative_to_config.exists():
        return relative_to_config

    relative_to_cwd = Path(config.task_pack).resolve()
    if relative_to_cwd.exists():
        return relative_to_cwd

    raise ValueError(f"Task pack path does not exist: {config.task_pack}")


def resolve_eval_tasks(config: EvalConfig, config_path: Path) -> list[ResolvedEvalTask]:
    task_pack_path = resolve_task_pack_path(config, config_path)
    return [
        _resolve_eval_task(task_pack_path, config, task_id)
        for task_id in config.tasks
    ]


def select_policy(config: EvalConfig, policy: str) -> ScorerControlPatchPolicy:
    try:
        return config.policies[policy]
    except KeyError as exc:
        available = ", ".join(sorted(config.policies))
        raise ValueError(f"Unknown policy {policy!r}; available: {available}") from exc


def scorer_control_patch_path(
    task_dir: Path,
    manifest: TaskManifest,
    control: ControlName,
) -> Path:
    if control == "oracle":
        relative_path = manifest.controls.oracle
    elif control == "bad.noop":
        relative_path = manifest.controls.bad.noop
    else:
        relative_path = manifest.controls.bad.public_only

    patch_path = (task_dir / relative_path).resolve()
    if not patch_path.is_file():
        raise ValueError(f"Control patch does not exist: {patch_path}")
    return patch_path


def _resolve_eval_task(
    task_pack_path: Path,
    config: EvalConfig,
    task_id: str,
) -> ResolvedEvalTask:
    manifest_path, manifest = _find_task_manifest(task_pack_path, task_id)
    if manifest.split != config.split:
        raise ValueError(
            f"Task {manifest.id} at {manifest_path} has split {manifest.split!r}; "
            f"expected {config.split!r}"
        )
    return ResolvedEvalTask(
        task_id=task_id,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def _find_task_manifest(
    task_pack_path: Path,
    task_id: str,
) -> tuple[Path, TaskManifest]:
    task_roots = sorted((task_pack_path / "tasks").glob("*/task.yaml"))
    for manifest_path in task_roots:
        manifest = load_task_manifest(manifest_path)
        if manifest.id == task_id:
            return manifest_path, manifest
    raise ValueError(f"Task id {task_id!r} not found in task pack {task_pack_path}")
