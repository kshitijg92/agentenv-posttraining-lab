from pathlib import Path
from typing import Any

import yaml

from agentenv.tasks.schema import TaskManifest


def load_task_manifest(path: Path) -> TaskManifest:
    raw_manifest = _load_yaml_mapping(path)
    return TaskManifest.model_validate(raw_manifest)


def validate_task_manifest_paths(manifest: TaskManifest, manifest_path: Path) -> None:
    task_dir = manifest_path.parent.resolve()
    workspace_seed = _resolve_manifest_path(task_dir, manifest.workspace_seed)
    _require_dir(workspace_seed, "workspace_seed")

    for hidden_validator in manifest.hidden_validators:
        hidden_path = _resolve_manifest_path(task_dir, hidden_validator.path)
        _require_exists(hidden_path, f"hidden validator {hidden_validator.id}")
        if hidden_path.is_relative_to(workspace_seed):
            raise ValueError(
                f"Hidden validator {hidden_validator.id} must not be inside "
                f"workspace_seed: {hidden_path}"
            )

    _require_file(
        _resolve_manifest_path(task_dir, manifest.controls.oracle),
        "oracle control",
    )
    _require_file(
        _resolve_manifest_path(task_dir, manifest.controls.bad.noop),
        "noop bad control",
    )
    _require_file(
        _resolve_manifest_path(task_dir, manifest.controls.bad.public_only),
        "public-only bad control",
    )


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected task manifest YAML mapping at {path}")
    return raw


def _resolve_manifest_path(task_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Manifest paths must be relative: {raw_path}")

    resolved = (task_dir / path).resolve()
    if not resolved.is_relative_to(task_dir):
        raise ValueError(f"Manifest path escapes task directory: {raw_path}")
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
