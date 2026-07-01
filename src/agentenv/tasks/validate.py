import json
from pathlib import Path
from typing import Any
import unicodedata

import yaml

from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.tasks.schema import TaskManifest, TaskPackManifest, TaskSplitsLock
from agentenv.tasks.splits import validate_split_membership


class TaskPackValidationResult:
    def __init__(self, task_pack_id: str, task_count: int) -> None:
        self.task_pack_id = task_pack_id
        self.task_count = task_count


def load_task_manifest(path: Path) -> TaskManifest:
    raw_manifest = _load_yaml_mapping(path)
    return TaskManifest.model_validate(raw_manifest)


def load_task_pack_manifest(path: Path) -> TaskPackManifest:
    raw_manifest = _load_yaml_mapping(path)
    return TaskPackManifest.model_validate(raw_manifest)


def load_splits_lock(path: Path) -> TaskSplitsLock:
    raw_lock = json.loads(path.read_text())
    return TaskSplitsLock.model_validate(raw_lock)


def validate_task_manifest_paths(manifest: TaskManifest, manifest_path: Path) -> None:
    task_dir = manifest_path.parent.resolve()
    seed_workspace = _resolve_manifest_path(task_dir, manifest.seed_workspace)
    _require_dir(seed_workspace, "seed_workspace")

    for hidden_validator in manifest.hidden_validators:
        hidden_path = _resolve_manifest_path(task_dir, hidden_validator.path)
        _require_exists(hidden_path, f"hidden validator {hidden_validator.id}")
        if hidden_path.is_relative_to(seed_workspace):
            raise ValueError(
                f"Hidden validator {hidden_validator.id} must not be inside "
                f"seed_workspace: {hidden_path}"
            )

    _require_file(
        _resolve_manifest_path(
            task_dir,
            manifest.controls.scorer_control_patches.oracle,
        ),
        "oracle control",
    )
    _require_file(
        _resolve_manifest_path(
            task_dir,
            manifest.controls.scorer_control_patches.bad.noop,
        ),
        "noop bad control",
    )
    _require_file(
        _resolve_manifest_path(
            task_dir,
            manifest.controls.scorer_control_patches.bad.public_only,
        ),
        "public-only bad control",
    )
    _require_agent_control_script(
        task_dir,
        manifest.controls.agent_control_scripts.happy,
        "happy agent control",
    )
    _require_agent_control_script(
        task_dir,
        manifest.controls.agent_control_scripts.malformed,
        "malformed agent control",
    )
    _require_agent_control_script(
        task_dir,
        manifest.controls.agent_control_scripts.recoverable,
        "recoverable agent control",
    )


def validate_task_pack(task_pack_path: Path) -> TaskPackValidationResult:
    task_pack_path = task_pack_path.resolve()
    if not task_pack_path.is_dir():
        raise ValueError(f"Expected task pack directory: {task_pack_path}")

    pack_manifest_path = task_pack_path / "manifest.yaml"
    _require_file(pack_manifest_path, "task pack manifest")
    pack_manifest = load_task_pack_manifest(pack_manifest_path)

    splits_path = _resolve_pack_path(task_pack_path, pack_manifest.split_lock)
    _require_file(splits_path, "split lock")
    splits_lock = load_splits_lock(splits_path)

    if splits_lock.task_pack != pack_manifest.id:
        raise ValueError(
            f"Split lock task_pack {splits_lock.task_pack!r} does not match "
            f"pack id {pack_manifest.id!r}"
        )

    tasks_dir = _resolve_pack_path(task_pack_path, pack_manifest.tasks_dir)
    _require_dir(tasks_dir, "tasks directory")
    task_manifest_paths = sorted(tasks_dir.glob("*/task.yaml"))
    if not task_manifest_paths:
        raise ValueError(f"No task manifests found under {tasks_dir}")

    manifests: dict[str, TaskManifest] = {}
    for manifest_path in task_manifest_paths:
        manifest = load_task_manifest(manifest_path)
        if manifest.id in manifests:
            raise ValueError(f"Duplicate task id in task pack: {manifest.id}")
        validate_task_manifest_paths(manifest, manifest_path)
        _validate_task_required_files(
            manifest_path.parent,
            pack_manifest.required_task_files,
        )
        _validate_task_pack_domain(pack_manifest, manifest, manifest_path)
        _validate_workspace_private_assets_absent(manifest, manifest_path)
        _validate_hidden_tests_not_public_duplicates(manifest, manifest_path)
        manifests[manifest.id] = manifest

    validate_split_membership(manifests, splits_lock)

    return TaskPackValidationResult(
        task_pack_id=pack_manifest.id,
        task_count=len(manifests),
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


def _resolve_pack_path(task_pack_path: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Task pack paths must be relative: {raw_path}")

    resolved = (task_pack_path / path).resolve()
    if not resolved.is_relative_to(task_pack_path):
        raise ValueError(f"Task pack path escapes pack directory: {raw_path}")
    return resolved


def _validate_task_required_files(
    task_dir: Path,
    required_task_files: list[str],
) -> None:
    for raw_required_path in required_task_files:
        required_path = _resolve_manifest_path(task_dir, raw_required_path)
        _require_exists(required_path, f"required task file {raw_required_path}")
        if _is_agent_control_script_path(raw_required_path):
            _validate_agent_control_script(required_path, raw_required_path)


def _is_agent_control_script_path(raw_path: str) -> bool:
    path = Path(raw_path)
    return (
        len(path.parts) >= 3
        and path.parts[0] == "controls"
        and path.parts[1] == "agent_control_scripts"
        and path.suffix == ".json"
    )


def _validate_agent_control_script(path: Path, raw_path: str) -> None:
    try:
        load_agent_control_script_case(path)
    except ValueError as exc:
        raise ValueError(f"Invalid agent control script {raw_path}: {exc}") from exc


def _require_agent_control_script(
    task_dir: Path,
    raw_path: str,
    label: str,
) -> None:
    path = _resolve_manifest_path(task_dir, raw_path)
    _require_file(path, label)
    _validate_agent_control_script(path, raw_path)


def _validate_task_pack_domain(
    pack_manifest: TaskPackManifest,
    manifest: TaskManifest,
    manifest_path: Path,
) -> None:
    if manifest.domain != pack_manifest.domain:
        raise ValueError(
            f"Task {manifest.id} at {manifest_path} has domain "
            f"{manifest.domain!r}; expected {pack_manifest.domain!r}"
        )


def _validate_workspace_private_assets_absent(
    manifest: TaskManifest,
    manifest_path: Path,
) -> None:
    task_dir = manifest_path.parent.resolve()
    seed_workspace = _resolve_manifest_path(task_dir, manifest.seed_workspace)

    forbidden_paths = [
        seed_workspace / "task.yaml",
        seed_workspace / "hidden_tests",
        seed_workspace / "controls",
    ]
    for forbidden_path in forbidden_paths:
        if forbidden_path.exists():
            raise ValueError(
                f"Private task asset must not be inside seed_workspace: "
                f"{forbidden_path}"
            )

    forbidden_markers = [
        manifest.leakage_canary,
        "hidden_tests",
        manifest.controls.scorer_control_patches.oracle,
        manifest.controls.scorer_control_patches.bad.noop,
        manifest.controls.scorer_control_patches.bad.public_only,
    ]
    for file_path in _iter_files(seed_workspace):
        content = file_path.read_bytes()
        for marker in forbidden_markers:
            if marker.encode() in content:
                raise ValueError(
                    f"Private task marker {marker!r} appears in workspace file "
                    f"{file_path}"
                )


def _validate_hidden_tests_not_public_duplicates(
    manifest: TaskManifest,
    manifest_path: Path,
) -> None:
    task_dir = manifest_path.parent.resolve()
    seed_workspace = _resolve_manifest_path(task_dir, manifest.seed_workspace)
    public_test_hashes = {
        _normalized_text_hash(path): path
        for path in _iter_python_files(seed_workspace / "tests")
    }
    if not public_test_hashes:
        return

    for hidden_validator in manifest.hidden_validators:
        hidden_path = _resolve_manifest_path(task_dir, hidden_validator.path)
        for hidden_file in _iter_python_files(hidden_path):
            hidden_hash = _normalized_text_hash(hidden_file)
            if hidden_hash in public_test_hashes:
                public_file = public_test_hashes[hidden_hash]
                raise ValueError(
                    f"Hidden validator {hidden_file} duplicates public test "
                    f"{public_file}"
                )


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("*") if path.is_file())


def _iter_python_files(root: Path) -> list[Path]:
    return [
        path
        for path in _iter_files(root)
        if path.suffix == ".py" and "__pycache__" not in path.parts
    ]


def _normalized_text_hash(path: Path) -> str:
    text = path.read_text()
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = " ".join(normalized.split())
    return normalized


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
