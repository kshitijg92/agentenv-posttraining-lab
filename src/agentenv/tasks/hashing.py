import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import unicodedata
from typing import Any, Literal

import xxhash

from agentenv.tasks.validate import (
    load_splits_lock,
    load_task_manifest,
    load_task_pack_manifest,
)


HASH_SCHEMA_VERSION = "task_hash_report_v0"

_NOISY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


HashableKind = Literal["file", "directory"]


@dataclass(frozen=True)
class TaskHashReport:
    payload: dict[str, Any]

    @property
    def pack_record_hash(self) -> str:
        value = self.payload.get("pack_record_hash")
        if not isinstance(value, str):
            raise ValueError("task hash report is missing pack_record_hash")
        return value

    def write_json(self, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(self.payload, indent=2, sort_keys=True) + "\n",
        )


def build_task_hash_report(task_pack_path: Path) -> TaskHashReport:
    task_pack_path = task_pack_path.resolve()
    if not task_pack_path.is_dir():
        raise ValueError(f"Expected task pack directory: {task_pack_path}")

    pack_manifest_path = task_pack_path / "manifest.yaml"
    pack_manifest = load_task_pack_manifest(pack_manifest_path)
    splits_lock_path = _resolve_pack_path(task_pack_path, pack_manifest.split_lock)
    splits_lock = load_splits_lock(splits_lock_path)
    tasks_dir = _resolve_pack_path(task_pack_path, pack_manifest.tasks_dir)
    task_records = [
        _build_task_hash_record(
            task_manifest_path,
            pack_manifest.required_task_files,
        )
        for task_manifest_path in sorted(tasks_dir.glob("*/task.yaml"))
    ]
    if not task_records:
        raise ValueError(f"No task manifests found under {tasks_dir}")

    pack_record_input = {
        "schema_version": HASH_SCHEMA_VERSION,
        "task_pack_id": pack_manifest.id,
        "manifest_yaml_hash": _hash_file(pack_manifest_path),
        "splits_lock_hash": _hash_file(splits_lock_path),
        "tasks": [
            {
                "task_id": task_record["task_id"],
                "task_record_hash": task_record["task_record_hash"],
            }
            for task_record in task_records
        ],
    }
    pack_record_hash = _hash_json(pack_record_input)

    return TaskHashReport(
        payload={
            "schema_version": HASH_SCHEMA_VERSION,
            "generated_at_utc": _utc_now_iso(),
            "git_sha_or_unknown": _git_sha_or_unknown(task_pack_path),
            "task_pack_id": pack_manifest.id,
            "task_pack_path": _display_path(task_pack_path),
            "task_count": len(task_records),
            "manifest_yaml_hash": _hash_file(pack_manifest_path),
            "splits_lock_hash": _hash_file(splits_lock_path),
            "split_counts": {
                "practice": len(splits_lock.practice),
                "dev": len(splits_lock.dev),
                "heldout_private": len(splits_lock.heldout_private),
                "public_calibration": len(splits_lock.public_calibration),
            },
            "tasks": task_records,
            "pack_record_hash": pack_record_hash,
        }
    )


def write_task_hash_report(task_pack_path: Path, out_path: Path) -> TaskHashReport:
    report = build_task_hash_report(task_pack_path)
    report.write_json(out_path)
    return report


def _build_task_hash_record(
    task_manifest_path: Path,
    required_task_files: list[str],
) -> dict[str, Any]:
    task_manifest = load_task_manifest(task_manifest_path)
    task_dir = task_manifest_path.parent.resolve()
    required_records = [
        _hash_required_task_path(task_dir, required_path)
        for required_path in required_task_files
    ]
    extra_task_files = _extra_task_files(task_dir, required_task_files)
    task_record_input = {
        "task_id": task_manifest.id,
        "split": task_manifest.split,
        "task_yaml_hash": _hash_file(task_manifest_path),
        "instruction_normalized_hash": _hash_normalized_text(task_manifest.instruction),
        "visible_tests_normalized_hash": _hash_normalized_directory_text(
            _resolve_task_path(task_dir, task_manifest.seed_workspace) / "tests"
        ),
        "required_task_files_hash": _hash_json(required_records),
        "full_task_dir_hash": _hash_directory(task_dir),
        "extra_task_files": extra_task_files,
    }
    task_record_hash = _hash_json(task_record_input)
    return {
        **task_record_input,
        "manifest_path": _display_path(task_manifest_path),
        "required_task_files": required_records,
        "task_record_hash": task_record_hash,
    }


def _hash_required_task_path(task_dir: Path, raw_path: str) -> dict[str, str]:
    path = _resolve_task_path(task_dir, raw_path)
    if path.is_file():
        return {
            "path": raw_path,
            "kind": "file",
            "hash": _hash_file(path),
        }
    if path.is_dir():
        return {
            "path": raw_path,
            "kind": "directory",
            "hash": _hash_directory(path),
        }
    raise ValueError(f"Missing required task file for hashing: {path}")


def _extra_task_files(task_dir: Path, required_task_files: list[str]) -> list[str]:
    required_file_paths = set[Path]()
    for raw_path in required_task_files:
        required_path = _resolve_task_path(task_dir, raw_path)
        if required_path.is_file():
            required_file_paths.add(required_path)
        elif required_path.is_dir():
            required_file_paths.update(_iter_hashable_files(required_path))
        else:
            raise ValueError(f"Missing required task file for hashing: {required_path}")

    extras = [
        _relative_path(file_path, task_dir)
        for file_path in _iter_hashable_files(task_dir)
        if file_path not in required_file_paths
    ]
    return sorted(extras)


def _hash_file(path: Path) -> str:
    return _hash_bytes(path.read_bytes())


def _hash_directory(path: Path) -> str:
    entries = [
        {
            "path": _relative_path(file_path, path),
            "hash": _hash_file(file_path),
        }
        for file_path in _iter_hashable_files(path)
    ]
    return _hash_json(entries)


def _hash_normalized_directory_text(path: Path) -> str | None:
    files = _iter_hashable_files(path)
    if not files:
        return None
    entries = [
        {
            "path": _relative_path(file_path, path),
            "hash": _hash_normalized_text(file_path.read_text()),
        }
        for file_path in files
    ]
    return _hash_json(entries)


def _hash_normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = " ".join(normalized.split())
    return _hash_bytes(normalized.encode())


def _hash_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _hash_bytes(payload.encode())


def _hash_bytes(payload: bytes) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(payload)}"


def _iter_hashable_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root.resolve()]

    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if _is_noisy_path(path):
            continue
        if path.is_file():
            files.append(path.resolve())
    return files


def _is_noisy_path(path: Path) -> bool:
    return any(part in _NOISY_NAMES for part in path.parts)


def _resolve_pack_path(task_pack_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Task pack paths must be relative: {raw_path}")

    resolved = (task_pack_path / path).resolve()
    if not resolved.is_relative_to(task_pack_path):
        raise ValueError(f"Task pack path escapes pack directory: {raw_path}")
    return resolved


def _resolve_task_path(task_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Task paths must be relative: {raw_path}")

    resolved = (task_dir / path).resolve()
    if not resolved.is_relative_to(task_dir):
        raise ValueError(f"Task path escapes task directory: {raw_path}")
    return resolved


def _relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_sha_or_unknown(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"

    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        return "unknown"
    return sha
