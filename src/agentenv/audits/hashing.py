"""Canonical hashing helpers shared by harness-audit consumers."""

from pathlib import Path

from agentenv.hashing import (
    hash_bytes,
    hash_json,
    hash_normalized_text,
    iter_hashable_files,
    relative_path,
)
from agentenv.tasks.hashing import build_eval_task_hashes
from agentenv.tasks.validate import load_task_manifest, load_task_pack_manifest


def hash_harness_audit_case_dir(case_dir: Path) -> str:
    case_dir = case_dir.resolve()
    if not case_dir.is_dir():
        raise ValueError(f"Expected harness audit case directory: {case_dir}")

    entries = [
        {
            "path": relative_path(file_path, case_dir),
            "hash": _hash_case_file(file_path),
        }
        for file_path in iter_hashable_files(case_dir)
    ]
    return hash_json(entries)


def build_task_record_hash_for_manifest(
    task_manifest_path: Path,
    *,
    task_id: str,
) -> str:
    """Hash the exact referenced task under its owning task-pack contract."""
    task_manifest_path = task_manifest_path.resolve()
    task_pack_path, tasks_dir = _find_owning_task_pack(task_manifest_path)
    matching_manifests = [
        path.resolve()
        for path in sorted(tasks_dir.glob("*/task.yaml"))
        if load_task_manifest(path).id == task_id
    ]
    if matching_manifests != [task_manifest_path]:
        raise ValueError(
            "Referenced task manifest must be the unique task-pack manifest for "
            f"task id {task_id!r}: {task_manifest_path}"
        )

    selected = build_eval_task_hashes(task_pack_path, [task_id]).selected_tasks
    if len(selected) != 1:
        raise ValueError(f"Expected exactly one task hash record for {task_id!r}")
    return selected[0].task_record_hash


def find_owning_task_pack(task_manifest_path: Path) -> Path:
    task_pack_path, _ = _find_owning_task_pack(task_manifest_path.resolve())
    return task_pack_path


def _hash_case_file(path: Path) -> str:
    if path.name == "notes.md":
        return hash_normalized_text(path.read_text())
    return hash_bytes(path.read_bytes())


def _find_owning_task_pack(task_manifest_path: Path) -> tuple[Path, Path]:
    for candidate in task_manifest_path.parents:
        pack_manifest_path = candidate / "manifest.yaml"
        if not pack_manifest_path.is_file():
            continue
        try:
            pack_manifest = load_task_pack_manifest(pack_manifest_path)
            tasks_dir = _resolve_pack_path(candidate, pack_manifest.tasks_dir)
        except (OSError, ValueError):
            continue
        if task_manifest_path.is_relative_to(tasks_dir):
            return candidate, tasks_dir
    raise ValueError(
        f"Could not find owning task pack for manifest: {task_manifest_path}"
    )


def _resolve_pack_path(task_pack_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Task pack paths must be relative: {raw_path}")
    resolved = (task_pack_path / path).resolve()
    if not resolved.is_relative_to(task_pack_path):
        raise ValueError(f"Task pack path escapes pack directory: {raw_path}")
    return resolved
