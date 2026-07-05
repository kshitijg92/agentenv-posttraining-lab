import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import xxhash
from pydantic import ValidationError

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
    EVAL_SUITE_ARTIFACT_SCHEMA_VERSION,
    TRAJECTORY_EXPORT_ARTIFACT_REFS,
    TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION,
    EvalRunManifest,
    EvalSuiteManifest,
    TrajectoryExportManifest,
    load_eval_artifact_manifest,
    load_trajectory_export_manifest,
)
from agentenv.trajectories.builder import (
    build_trajectory_records_from_eval_run,
    build_trajectory_records_from_eval_suite,
)
from agentenv.trajectories.schema import (
    TRAJECTORY_RECORD_SCHEMA_VERSION,
    TrajectoryRecord,
)


@dataclass(frozen=True)
class TrajectoryExport:
    out_dir: Path
    manifest: TrajectoryExportManifest
    records: tuple[TrajectoryRecord, ...]


def export_trajectory_records_from_eval_artifact(
    eval_artifact_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> TrajectoryExport:
    eval_artifact_dir = eval_artifact_dir.resolve()
    source_manifest_path = eval_artifact_dir / MANIFEST_FILENAME
    source_manifest = load_eval_artifact_manifest(source_manifest_path)
    records = build_trajectory_records_from_eval_artifact_manifest(
        eval_artifact_dir,
        source_manifest,
    )

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    trajectories_path = out_dir / TRAJECTORY_EXPORT_ARTIFACT_REFS["trajectories"]
    write_trajectory_records_jsonl(trajectories_path, records)

    manifest = build_trajectory_export_manifest(
        out_dir=out_dir,
        source_artifact_dir=eval_artifact_dir,
        source_manifest_path=source_manifest_path,
        source_manifest=source_manifest,
        trajectories_path=trajectories_path,
        record_count=len(records),
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_trajectory_export_artifact(out_dir)


def load_trajectory_export_artifact(export_dir: Path) -> TrajectoryExport:
    export_dir = export_dir.resolve()
    manifest = load_trajectory_export_manifest(export_dir / MANIFEST_FILENAME)
    trajectories_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["trajectories"],
    )
    observed_hash = hash_file(trajectories_path)
    if observed_hash != manifest.trajectories_jsonl_hash:
        raise ValueError(
            f"Trajectory JSONL hash mismatch at {trajectories_path}: "
            f"{observed_hash!r} != {manifest.trajectories_jsonl_hash!r}"
        )

    records = load_trajectory_records_jsonl(trajectories_path)
    if len(records) != manifest.record_count:
        raise ValueError(
            f"Trajectory record count mismatch at {trajectories_path}: "
            f"{len(records)} != {manifest.record_count}"
        )
    return TrajectoryExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


def build_trajectory_records_from_eval_artifact_manifest(
    eval_artifact_dir: Path,
    source_manifest: EvalRunManifest | EvalSuiteManifest,
) -> list[TrajectoryRecord]:
    if isinstance(source_manifest, EvalRunManifest):
        return build_trajectory_records_from_eval_run(eval_artifact_dir)
    return build_trajectory_records_from_eval_suite(eval_artifact_dir)


def write_trajectory_records_jsonl(
    path: Path,
    records: list[TrajectoryRecord],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_trajectory_records_jsonl(path: Path) -> tuple[TrajectoryRecord, ...]:
    records: list[TrajectoryRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(TrajectoryRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"TrajectoryRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_trajectory_export_manifest(
    *,
    out_dir: Path,
    source_artifact_dir: Path,
    source_manifest_path: Path,
    source_manifest: EvalRunManifest | EvalSuiteManifest,
    trajectories_path: Path,
    record_count: int,
) -> TrajectoryExportManifest:
    if isinstance(source_manifest, EvalRunManifest):
        source_artifact_type = ArtifactType.EVAL_RUN.value
        source_artifact_schema_version = EVAL_RUN_ARTIFACT_SCHEMA_VERSION
        source_eval_run_id = source_manifest.eval_run_id
        source_eval_suite_id = None
    else:
        source_artifact_type = ArtifactType.EVAL_SUITE.value
        source_artifact_schema_version = EVAL_SUITE_ARTIFACT_SCHEMA_VERSION
        source_eval_run_id = None
        source_eval_suite_id = source_manifest.eval_suite_id

    trajectory_ref = TRAJECTORY_EXPORT_ARTIFACT_REFS["trajectories"]
    resolved_trajectory_path = resolve_relative_artifact_ref(out_dir, trajectory_ref)
    if resolved_trajectory_path != trajectories_path.resolve():
        raise ValueError("Trajectory JSONL path does not match manifest artifact ref")

    return TrajectoryExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.TRAJECTORY_EXPORT,
            "artifact_schema_version": TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "source_artifact_type": source_artifact_type,
            "source_artifact_schema_version": source_artifact_schema_version,
            "source_artifact_dir": str(source_artifact_dir),
            "source_manifest_path": str(source_manifest_path),
            "source_manifest_hash": hash_file(source_manifest_path),
            "source_eval_run_id": source_eval_run_id,
            "source_eval_suite_id": source_eval_suite_id,
            "trajectory_record_schema_version": TRAJECTORY_RECORD_SCHEMA_VERSION,
            "record_count": record_count,
            "trajectories_jsonl_hash": hash_file(trajectories_path),
            "artifacts": dict(TRAJECTORY_EXPORT_ARTIFACT_REFS),
        }
    )


def hash_file(path: Path) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(path.read_bytes())}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
