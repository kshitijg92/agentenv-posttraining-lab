from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    EvalRunManifest,
    EvalSuiteManifest,
    load_eval_artifact_manifest,
)
from agentenv.artifacts.payloads import (
    RequiredTaskFileHash as ArtifactRequiredTaskFileHash,
)
from agentenv.artifacts.payloads import (
    SelectedEvalTaskHash,
)


EvalHashArtifactType = Literal["eval_run", "eval_suite"]
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
    artifact_type: EvalHashArtifactType
    artifact_schema_version: str
    task_pack_id: str
    selected_task_hash_set: str
    selected_tasks: tuple[SelectedTaskHash, ...]

    def selected_tasks_by_id(self) -> dict[str, SelectedTaskHash]:
        return {record.task_id: record for record in self.selected_tasks}

    def summary_dict(self) -> dict[str, object]:
        return {
            "manifest_path": str(self.manifest_path),
            "artifact_type": self.artifact_type,
            "artifact_schema_version": self.artifact_schema_version,
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
            f"{comparison.reference.artifact_type}/"
            f"{comparison.reference.artifact_schema_version} "
            f"task_pack={comparison.reference.task_pack_id} "
            f"selected_tasks={len(comparison.reference.selected_tasks)}"
        ),
        (
            "candidate="
            f"{comparison.candidate.artifact_type}/"
            f"{comparison.candidate.artifact_schema_version} "
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
    manifest = load_eval_artifact_manifest(manifest_path)
    task_hashes = manifest.task_hashes
    return EvalTaskHashSource(
        manifest_path=manifest_path,
        artifact_type=_eval_hash_artifact_type(manifest),
        artifact_schema_version=manifest.artifact_schema_version,
        task_pack_id=task_hashes.task_pack_id,
        selected_task_hash_set=task_hashes.selected_task_hash_set,
        selected_tasks=tuple(
            _selected_task_hash(record) for record in task_hashes.selected_tasks
        ),
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

    manifest = path / MANIFEST_FILENAME
    if manifest.is_file():
        return manifest

    raise ValueError(f"No {MANIFEST_FILENAME} found in {path}")


def _eval_hash_artifact_type(
    manifest: EvalRunManifest | EvalSuiteManifest,
) -> EvalHashArtifactType:
    if isinstance(manifest, EvalRunManifest):
        return "eval_run"
    return "eval_suite"


def _selected_task_hash(record: SelectedEvalTaskHash) -> SelectedTaskHash:
    return SelectedTaskHash(
        task_id=record.task_id,
        split=record.split,
        task_record_hash=record.task_record_hash,
        task_yaml_hash=record.task_yaml_hash,
        required_task_files_hash=record.required_task_files_hash,
        full_task_dir_hash=record.full_task_dir_hash,
        required_task_files=tuple(
            _required_task_file_hash(task_file)
            for task_file in record.required_task_files
        ),
    )


def _required_task_file_hash(
    record: ArtifactRequiredTaskFileHash,
) -> RequiredTaskFileHash:
    return RequiredTaskFileHash(
        path=record.path,
        kind=record.kind,
        hash=record.hash,
    )
