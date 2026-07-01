from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import yaml

from agentenv.tasks.schema import TaskManifest, TaskPackManifest, TaskSplitsLock


SPLIT_NAMES = (
    "practice",
    "dev",
    "heldout_private",
    "public_calibration",
)


@dataclass(frozen=True)
class SplitCheckResult:
    task_pack_id: str
    task_count: int
    split_counts: dict[str, int]


def check_splits_lock(splits_lock_path: Path) -> SplitCheckResult:
    splits_lock_path = splits_lock_path.resolve()
    _require_file(splits_lock_path, "split lock")

    task_pack_path = splits_lock_path.parent
    pack_manifest_path = task_pack_path / "manifest.yaml"
    _require_file(pack_manifest_path, "task pack manifest")

    pack_manifest = _load_task_pack_manifest(pack_manifest_path)
    expected_splits_path = _resolve_pack_path(
        task_pack_path,
        pack_manifest.split_lock,
    )
    if expected_splits_path != splits_lock_path:
        raise ValueError(
            f"Task pack manifest split_lock {pack_manifest.split_lock!r} "
            f"resolves to {expected_splits_path}, not {splits_lock_path}"
        )

    splits_lock = _load_splits_lock(splits_lock_path)
    if splits_lock.task_pack != pack_manifest.id:
        raise ValueError(
            f"Split lock task_pack {splits_lock.task_pack!r} does not match "
            f"pack id {pack_manifest.id!r}"
        )

    tasks_dir = _resolve_pack_path(task_pack_path, pack_manifest.tasks_dir)
    _require_dir(tasks_dir, "tasks directory")
    manifests = _load_pack_task_manifests(tasks_dir)
    validate_split_membership(manifests, splits_lock)

    return SplitCheckResult(
        task_pack_id=pack_manifest.id,
        task_count=len(manifests),
        split_counts={
            split_name: len(_split_task_ids(splits_lock, split_name))
            for split_name in SPLIT_NAMES
        },
    )


def validate_split_membership(
    manifests: dict[str, TaskManifest],
    splits_lock: TaskSplitsLock,
) -> None:
    split_memberships = {
        split_name: _split_task_ids(splits_lock, split_name)
        for split_name in SPLIT_NAMES
    }

    seen: dict[str, str] = {}
    for split, task_ids in split_memberships.items():
        for task_id in task_ids:
            if task_id in seen:
                raise ValueError(
                    f"Task {task_id!r} appears in both "
                    f"{seen[task_id]!r} and {split!r}"
                )
            seen[task_id] = split

    discovered_ids = set(manifests)
    locked_ids = set(seen)
    missing_from_lock = discovered_ids - locked_ids
    if missing_from_lock:
        raise ValueError(
            "Task manifests missing from splits.lock.json: "
            + ", ".join(sorted(missing_from_lock))
        )

    missing_from_pack = locked_ids - discovered_ids
    if missing_from_pack:
        raise ValueError(
            "splits.lock.json references missing task ids: "
            + ", ".join(sorted(missing_from_pack))
        )

    for task_id, manifest in manifests.items():
        locked_split = seen[task_id]
        if manifest.split != locked_split:
            raise ValueError(
                f"Task {task_id} manifest split {manifest.split!r} does not "
                f"match splits.lock.json split {locked_split!r}"
            )


def _load_pack_task_manifests(tasks_dir: Path) -> dict[str, TaskManifest]:
    task_manifest_paths = sorted(tasks_dir.glob("*/task.yaml"))
    if not task_manifest_paths:
        raise ValueError(f"No task manifests found under {tasks_dir}")

    manifests: dict[str, TaskManifest] = {}
    for manifest_path in task_manifest_paths:
        manifest = _load_task_manifest(manifest_path)
        if manifest.id in manifests:
            raise ValueError(f"Duplicate task id in task pack: {manifest.id}")
        manifests[manifest.id] = manifest
    return manifests


def _split_task_ids(splits_lock: TaskSplitsLock, split_name: str) -> list[str]:
    return getattr(splits_lock, split_name)


def _load_task_manifest(path: Path) -> TaskManifest:
    raw_manifest = _load_yaml_mapping(path)
    return TaskManifest.model_validate(raw_manifest)


def _load_task_pack_manifest(path: Path) -> TaskPackManifest:
    raw_manifest = _load_yaml_mapping(path)
    return TaskPackManifest.model_validate(raw_manifest)


def _load_splits_lock(path: Path) -> TaskSplitsLock:
    raw_lock = json.loads(path.read_text())
    return TaskSplitsLock.model_validate(raw_lock)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected task manifest YAML mapping at {path}")
    return raw


def _resolve_pack_path(task_pack_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Task pack paths must be relative: {raw_path}")

    resolved = (task_pack_path / path).resolve()
    if not resolved.is_relative_to(task_pack_path):
        raise ValueError(f"Task pack path escapes pack directory: {raw_path}")
    return resolved


def _require_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise ValueError(f"Missing {label}: {path}")


def _require_dir(path: Path, label: str) -> None:
    _require_exists(path, label)
    if not path.is_dir():
        raise ValueError(f"Expected {label} to be a directory: {path}")


def _require_file(path: Path, label: str) -> None:
    _require_exists(path, label)
    if not path.is_file():
        raise ValueError(f"Expected {label} to be a file: {path}")
