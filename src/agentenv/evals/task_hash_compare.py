import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agentenv.tasks.hashing import EVAL_TASK_HASH_SCHEMA_VERSION


EvalHashArtifactVersion = Literal["eval_run_v0", "eval_matrix_v0"]
TaskHashComparisonStatus = Literal["matched", "drifted"]
RequiredTaskFileDriftStatus = Literal["added", "removed", "changed"]


@dataclass(frozen=True)
class RequiredTaskFileHash:
    path: str
    kind: str
    hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "kind": self.kind,
            "hash": self.hash,
        }


@dataclass(frozen=True)
class SelectedTaskHash:
    task_id: str
    split: str
    task_record_hash: str
    task_yaml_hash: str
    required_task_files_hash: str
    full_task_dir_hash: str
    required_task_files: tuple[RequiredTaskFileHash, ...]

    def required_task_files_by_path(self) -> dict[str, RequiredTaskFileHash]:
        return {record.path: record for record in self.required_task_files}

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "split": self.split,
            "task_record_hash": self.task_record_hash,
            "task_yaml_hash": self.task_yaml_hash,
            "required_task_files_hash": self.required_task_files_hash,
            "full_task_dir_hash": self.full_task_dir_hash,
            "required_task_files": [
                record.to_dict() for record in self.required_task_files
            ],
        }


@dataclass(frozen=True)
class EvalTaskHashSource:
    manifest_path: Path
    artifact_version: EvalHashArtifactVersion
    task_pack_id: str
    selected_task_hash_set: str
    selected_tasks: tuple[SelectedTaskHash, ...]

    def selected_tasks_by_id(self) -> dict[str, SelectedTaskHash]:
        return {record.task_id: record for record in self.selected_tasks}

    def summary_dict(self) -> dict[str, object]:
        return {
            "manifest_path": str(self.manifest_path),
            "artifact_version": self.artifact_version,
            "task_pack_id": self.task_pack_id,
            "selected_task_hash_set": self.selected_task_hash_set,
            "selected_task_count": len(self.selected_tasks),
            "selected_task_ids": [task.task_id for task in self.selected_tasks],
        }


@dataclass(frozen=True)
class RequiredTaskFileDrift:
    path: str
    status: RequiredTaskFileDriftStatus
    reference_hash: str | None
    candidate_hash: str | None
    reference_kind: str | None
    candidate_kind: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "status": self.status,
            "reference_hash": self.reference_hash,
            "candidate_hash": self.candidate_hash,
            "reference_kind": self.reference_kind,
            "candidate_kind": self.candidate_kind,
        }


@dataclass(frozen=True)
class SelectedTaskHashDrift:
    task_id: str
    changed_fields: tuple[str, ...]
    required_task_file_drifts: tuple[RequiredTaskFileDrift, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "changed_fields": list(self.changed_fields),
            "required_task_file_drifts": [
                drift.to_dict() for drift in self.required_task_file_drifts
            ],
        }


@dataclass(frozen=True)
class EvalTaskHashComparison:
    status: TaskHashComparisonStatus
    reference: EvalTaskHashSource
    candidate: EvalTaskHashSource
    task_pack_id_match: bool
    selected_task_hash_set_match: bool
    added_task_ids: tuple[str, ...]
    removed_task_ids: tuple[str, ...]
    changed_tasks: tuple[SelectedTaskHashDrift, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reference": self.reference.summary_dict(),
            "candidate": self.candidate.summary_dict(),
            "task_pack_id_match": self.task_pack_id_match,
            "selected_task_hash_set_match": self.selected_task_hash_set_match,
            "added_task_ids": list(self.added_task_ids),
            "removed_task_ids": list(self.removed_task_ids),
            "changed_tasks": [task.to_dict() for task in self.changed_tasks],
        }


def compare_eval_task_hashes(
    reference_path: Path,
    candidate_path: Path,
) -> EvalTaskHashComparison:
    reference = load_eval_task_hash_source(reference_path)
    candidate = load_eval_task_hash_source(candidate_path)
    return compare_eval_task_hash_sources(reference, candidate)


def compare_eval_task_hash_sources(
    reference: EvalTaskHashSource,
    candidate: EvalTaskHashSource,
) -> EvalTaskHashComparison:
    reference_tasks = reference.selected_tasks_by_id()
    candidate_tasks = candidate.selected_tasks_by_id()
    reference_task_ids = set(reference_tasks)
    candidate_task_ids = set(candidate_tasks)

    added_task_ids = tuple(sorted(candidate_task_ids - reference_task_ids))
    removed_task_ids = tuple(sorted(reference_task_ids - candidate_task_ids))
    changed_tasks = tuple(
        drift
        for task_id in sorted(reference_task_ids & candidate_task_ids)
        if (
            drift := _compare_selected_task_hashes(
                reference_tasks[task_id],
                candidate_tasks[task_id],
            )
        )
        is not None
    )
    task_pack_id_match = reference.task_pack_id == candidate.task_pack_id
    selected_task_hash_set_match = (
        reference.selected_task_hash_set == candidate.selected_task_hash_set
    )
    status: TaskHashComparisonStatus = (
        "matched"
        if (
            task_pack_id_match
            and selected_task_hash_set_match
            and not added_task_ids
            and not removed_task_ids
            and not changed_tasks
        )
        else "drifted"
    )
    return EvalTaskHashComparison(
        status=status,
        reference=reference,
        candidate=candidate,
        task_pack_id_match=task_pack_id_match,
        selected_task_hash_set_match=selected_task_hash_set_match,
        added_task_ids=added_task_ids,
        removed_task_ids=removed_task_ids,
        changed_tasks=changed_tasks,
    )


def render_eval_task_hash_comparison_summary(
    comparison: EvalTaskHashComparison,
) -> list[str]:
    lines = [
        f"task input provenance {comparison.status}",
        (
            "reference="
            f"{comparison.reference.artifact_version} "
            f"task_pack={comparison.reference.task_pack_id} "
            f"selected_tasks={len(comparison.reference.selected_tasks)}"
        ),
        (
            "candidate="
            f"{comparison.candidate.artifact_version} "
            f"task_pack={comparison.candidate.task_pack_id} "
            f"selected_tasks={len(comparison.candidate.selected_tasks)}"
        ),
    ]
    if comparison.status == "matched":
        return lines

    lines.append(
        "drift "
        f"task_pack_id_match={str(comparison.task_pack_id_match).lower()} "
        "selected_task_hash_set_match="
        f"{str(comparison.selected_task_hash_set_match).lower()} "
        f"added_tasks={len(comparison.added_task_ids)} "
        f"removed_tasks={len(comparison.removed_task_ids)} "
        f"changed_tasks={len(comparison.changed_tasks)}"
    )
    if comparison.added_task_ids:
        lines.append("added_task_ids=" + ",".join(comparison.added_task_ids))
    if comparison.removed_task_ids:
        lines.append("removed_task_ids=" + ",".join(comparison.removed_task_ids))
    lines.extend(
        f"changed_task={changed_task.task_id} "
        f"fields={','.join(changed_task.changed_fields)} "
        f"required_file_drifts={len(changed_task.required_task_file_drifts)}"
        for changed_task in comparison.changed_tasks
    )
    return lines


def load_eval_task_hash_source(path: Path) -> EvalTaskHashSource:
    manifest_path = _resolve_eval_manifest_path(path)
    manifest = _load_json_object(manifest_path)
    artifact_version = _artifact_version(manifest, manifest_path)
    task_hashes = _required_object(manifest, "task_hashes", manifest_path)
    schema_version = _required_str(task_hashes, "schema_version", manifest_path)
    if schema_version != EVAL_TASK_HASH_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported task_hashes schema_version {schema_version!r} "
            f"at {manifest_path}"
        )
    return EvalTaskHashSource(
        manifest_path=manifest_path,
        artifact_version=artifact_version,
        task_pack_id=_required_str(task_hashes, "task_pack_id", manifest_path),
        selected_task_hash_set=_required_str(
            task_hashes,
            "selected_task_hash_set",
            manifest_path,
        ),
        selected_tasks=_selected_task_hashes(task_hashes, manifest_path),
    )


def _compare_selected_task_hashes(
    reference: SelectedTaskHash,
    candidate: SelectedTaskHash,
) -> SelectedTaskHashDrift | None:
    changed_fields = tuple(
        field_name
        for field_name in (
            "split",
            "task_record_hash",
            "task_yaml_hash",
            "required_task_files_hash",
            "full_task_dir_hash",
        )
        if getattr(reference, field_name) != getattr(candidate, field_name)
    )
    required_task_file_drifts = _compare_required_task_files(reference, candidate)
    if not changed_fields and not required_task_file_drifts:
        return None
    return SelectedTaskHashDrift(
        task_id=reference.task_id,
        changed_fields=changed_fields,
        required_task_file_drifts=required_task_file_drifts,
    )


def _compare_required_task_files(
    reference: SelectedTaskHash,
    candidate: SelectedTaskHash,
) -> tuple[RequiredTaskFileDrift, ...]:
    reference_files = reference.required_task_files_by_path()
    candidate_files = candidate.required_task_files_by_path()
    drifts: list[RequiredTaskFileDrift] = []
    for path in sorted(set(reference_files) - set(candidate_files)):
        reference_file = reference_files[path]
        drifts.append(
            RequiredTaskFileDrift(
                path=path,
                status="removed",
                reference_hash=reference_file.hash,
                candidate_hash=None,
                reference_kind=reference_file.kind,
                candidate_kind=None,
            )
        )
    for path in sorted(set(candidate_files) - set(reference_files)):
        candidate_file = candidate_files[path]
        drifts.append(
            RequiredTaskFileDrift(
                path=path,
                status="added",
                reference_hash=None,
                candidate_hash=candidate_file.hash,
                reference_kind=None,
                candidate_kind=candidate_file.kind,
            )
        )
    for path in sorted(set(reference_files) & set(candidate_files)):
        reference_file = reference_files[path]
        candidate_file = candidate_files[path]
        if (
            reference_file.hash != candidate_file.hash
            or reference_file.kind != candidate_file.kind
        ):
            drifts.append(
                RequiredTaskFileDrift(
                    path=path,
                    status="changed",
                    reference_hash=reference_file.hash,
                    candidate_hash=candidate_file.hash,
                    reference_kind=reference_file.kind,
                    candidate_kind=candidate_file.kind,
                )
            )
    return tuple(drifts)


def _resolve_eval_manifest_path(path: Path) -> Path:
    if path.is_file():
        return path
    if not path.is_dir():
        raise ValueError(f"Expected eval artifact directory or manifest file: {path}")

    matrix_manifest = path / "eval_matrix_manifest.json"
    if matrix_manifest.is_file():
        return matrix_manifest

    run_manifest = path / "run_manifest.json"
    if run_manifest.is_file():
        return run_manifest

    raise ValueError(
        f"No eval_matrix_manifest.json or run_manifest.json found in {path}"
    )


def _artifact_version(
    manifest: dict[str, Any],
    manifest_path: Path,
) -> EvalHashArtifactVersion:
    artifact_version = _required_str(manifest, "artifact_version", manifest_path)
    if artifact_version == "eval_run_v0":
        return "eval_run_v0"
    if artifact_version == "eval_matrix_v0":
        return "eval_matrix_v0"
    raise ValueError(
        f"Expected eval_run_v0 or eval_matrix_v0 artifact_version at "
        f"{manifest_path}; got {artifact_version!r}"
    )


def _selected_task_hashes(
    task_hashes: dict[str, Any],
    manifest_path: Path,
) -> tuple[SelectedTaskHash, ...]:
    raw_selected_tasks = _required_list(task_hashes, "selected_tasks", manifest_path)
    selected_tasks = [
        _selected_task_hash(raw_task, manifest_path)
        for raw_task in raw_selected_tasks
    ]
    seen_task_ids = set[str]()
    for task in selected_tasks:
        if task.task_id in seen_task_ids:
            raise ValueError(
                f"Duplicate selected task id {task.task_id!r} at {manifest_path}"
            )
        seen_task_ids.add(task.task_id)
    return tuple(selected_tasks)


def _selected_task_hash(
    raw_task: Any,
    manifest_path: Path,
) -> SelectedTaskHash:
    if not isinstance(raw_task, dict):
        raise ValueError(f"Expected selected task object at {manifest_path}")
    return SelectedTaskHash(
        task_id=_required_str(raw_task, "task_id", manifest_path),
        split=_required_str(raw_task, "split", manifest_path),
        task_record_hash=_required_str(raw_task, "task_record_hash", manifest_path),
        task_yaml_hash=_required_str(raw_task, "task_yaml_hash", manifest_path),
        required_task_files_hash=_required_str(
            raw_task,
            "required_task_files_hash",
            manifest_path,
        ),
        full_task_dir_hash=_required_str(raw_task, "full_task_dir_hash", manifest_path),
        required_task_files=_required_task_file_hashes(
            raw_task.get("required_task_files", []),
            manifest_path,
        ),
    )


def _required_task_file_hashes(
    raw_records: Any,
    manifest_path: Path,
) -> tuple[RequiredTaskFileHash, ...]:
    if not isinstance(raw_records, list):
        raise ValueError(f"Expected required_task_files list at {manifest_path}")
    records = [
        _required_task_file_hash(raw_record, manifest_path)
        for raw_record in raw_records
    ]
    seen_paths = set[str]()
    for record in records:
        if record.path in seen_paths:
            raise ValueError(
                f"Duplicate required task file path {record.path!r} at "
                f"{manifest_path}"
            )
        seen_paths.add(record.path)
    return tuple(records)


def _required_task_file_hash(
    raw_record: Any,
    manifest_path: Path,
) -> RequiredTaskFileHash:
    if not isinstance(raw_record, dict):
        raise ValueError(f"Expected required task file hash object at {manifest_path}")
    return RequiredTaskFileHash(
        path=_required_str(raw_record, "path", manifest_path),
        kind=_required_str(raw_record, "kind", manifest_path),
        hash=_required_str(raw_record, "hash", manifest_path),
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _required_object(
    value: dict[str, Any],
    key: str,
    path: Path,
) -> dict[str, Any]:
    raw_value = value.get(key)
    if not isinstance(raw_value, dict):
        raise ValueError(f"Expected object field {key!r} at {path}")
    return raw_value


def _required_list(
    value: dict[str, Any],
    key: str,
    path: Path,
) -> list[Any]:
    raw_value = value.get(key)
    if not isinstance(raw_value, list):
        raise ValueError(f"Expected list field {key!r} at {path}")
    return raw_value


def _required_str(
    value: dict[str, Any],
    key: str,
    path: Path,
) -> str:
    raw_value = value.get(key)
    if not isinstance(raw_value, str) or not raw_value:
        raise ValueError(f"Expected non-empty string field {key!r} at {path}")
    return raw_value
