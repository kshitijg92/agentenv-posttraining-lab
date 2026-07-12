import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from agentenv.agents.schema import PromptLoopResult
from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS,
    TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
    TrainingCandidateExportManifestRef,
    TrainingCandidateRepairExportManifest,
    load_control_calibration_manifest,
    load_training_candidate_repair_export_manifest,
)
from agentenv.artifacts.payloads import load_prompt_loop_result
from agentenv.controls.public_check_idempotency_schema import (
    PublicCheckIdempotencyCalibration,
)
from agentenv.hashing import hash_bytes, hash_file
from agentenv.security.secrets import redact_secrets
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest
from agentenv.training.export import (
    TrainingCandidateExport,
    load_training_candidate_export_artifact,
)
from agentenv.training.repair import (
    MECHANICAL_REDUNDANCY_REPAIRER_VERSION,
    MECHANICAL_REDUNDANCY_REPAIR_METHOD,
    MechanicalRedundancyRepairCannotComplete,
    build_training_candidate_repair_id,
    compute_mechanical_redundancy_repairer_code_hash,
    hash_training_candidate_record,
    repair_prompt_loop_mechanical_redundancy,
)
from agentenv.training.repair_schema import (
    TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION,
    MechanicalRedundancyRepairDetails,
    RepairedTranscriptArtifact,
    TrainingCandidateRepairRecord,
)
from agentenv.training.schema import (
    MechanicalRedundancyAssessment,
    TrainingCandidateRecord,
)
from agentenv.training.sft_builder import (
    build_trajectory_record_index,
    load_pinned_source_trajectory_export,
    resolve_trajectory_artifact_path,
    validate_artifact_ref_hash,
)
from agentenv.trajectories.schema import ArtifactRef, TrajectoryRecord


@dataclass(frozen=True)
class TrainingCandidateRepairExport:
    out_dir: Path
    manifest: TrainingCandidateRepairExportManifest
    records: tuple[TrainingCandidateRepairRecord, ...]


@dataclass(frozen=True)
class _PendingRepairRecord:
    record: TrainingCandidateRepairRecord
    repaired_transcript_bytes: bytes | None


def export_training_candidate_repairs(
    training_candidate_export_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> TrainingCandidateRepairExport:
    candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    trajectory_export = load_pinned_source_trajectory_export(candidate_export)
    trajectories_by_id = build_trajectory_record_index(trajectory_export.records)
    calibrations = _load_source_public_check_calibrations(candidate_export)

    pending_records = tuple(
        _build_pending_repair_record(
            candidate,
            _require_candidate_trajectory(candidate, trajectories_by_id),
            public_check_calibrations=calibrations,
        )
        for candidate in candidate_export.records
        if _candidate_requires_repair(candidate)
    )
    _validate_unique_repair_ids(tuple(pending.record for pending in pending_records))

    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    records = tuple(
        _persist_pending_repair(out_dir, pending) for pending in pending_records
    )
    records_path = resolve_relative_artifact_ref(
        out_dir,
        TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS["repair_records"],
    )
    write_training_candidate_repair_records_jsonl(records_path, records)
    manifest = build_training_candidate_repair_export_manifest(
        out_dir=out_dir,
        candidate_export=candidate_export,
        records_path=records_path,
        records=records,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_training_candidate_repair_export_artifact(out_dir)


def load_training_candidate_repair_export_artifact(
    export_dir: Path,
) -> TrainingCandidateRepairExport:
    export_dir = export_dir.resolve()
    manifest = load_training_candidate_repair_export_manifest(
        export_dir / MANIFEST_FILENAME
    )
    candidate_export = _load_pinned_training_candidate_export(
        export_dir,
        manifest.source_training_candidate_export,
    )
    records_path = resolve_relative_artifact_ref(
        export_dir,
        manifest.artifacts["repair_records"],
    )
    observed_records_hash = hash_file(records_path)
    if observed_records_hash != manifest.repair_records_jsonl_hash:
        raise ValueError(
            "Training candidate repair JSONL hash mismatch: "
            f"{observed_records_hash!r} != "
            f"{manifest.repair_records_jsonl_hash!r}"
        )
    records = load_training_candidate_repair_records_jsonl(records_path)
    validate_training_candidate_repair_counts(manifest, records)
    _validate_unique_repair_ids(records)
    _validate_repair_records_against_source(
        export_dir,
        records,
        candidate_export=candidate_export,
    )
    return TrainingCandidateRepairExport(
        out_dir=export_dir,
        manifest=manifest,
        records=records,
    )


def write_training_candidate_repair_records_jsonl(
    path: Path,
    records: tuple[TrainingCandidateRepairRecord, ...],
) -> None:
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n"
            for record in records
        )
    )


def load_training_candidate_repair_records_jsonl(
    path: Path,
) -> tuple[TrainingCandidateRepairRecord, ...]:
    records: list[TrainingCandidateRepairRecord] = []
    for record_index, payload in enumerate(load_jsonl_objects(path), start=1):
        try:
            records.append(TrainingCandidateRepairRecord.model_validate(payload))
        except ValidationError as exc:
            raise ValidationError.from_exception_data(
                f"TrainingCandidateRepairRecord at {path}:{record_index}",
                cast(Any, exc.errors()),
            ) from exc
    return tuple(records)


def build_training_candidate_repair_export_manifest(
    *,
    out_dir: Path,
    candidate_export: TrainingCandidateExport,
    records_path: Path,
    records: tuple[TrainingCandidateRepairRecord, ...],
) -> TrainingCandidateRepairExportManifest:
    expected_records_path = resolve_relative_artifact_ref(
        out_dir,
        TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS["repair_records"],
    )
    if expected_records_path != records_path.resolve():
        raise ValueError(
            "Training candidate repair JSONL path does not match manifest ref"
        )
    source_manifest_path = candidate_export.out_dir / MANIFEST_FILENAME
    return TrainingCandidateRepairExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.TRAINING_CANDIDATE_REPAIR_EXPORT,
            "artifact_schema_version": (
                TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION
            ),
            "created_at": _utc_now(),
            "source_training_candidate_export": {
                "artifact_dir": str(candidate_export.out_dir),
                "manifest_hash": hash_file(source_manifest_path),
            },
            "training_candidate_repair_record_schema_version": (
                TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION
            ),
            "record_count": len(records),
            "completed_count": sum(
                record.repair_status == "completed" for record in records
            ),
            "cannot_complete_count": sum(
                record.repair_status == "cannot_complete" for record in records
            ),
            "repair_error_count": sum(
                record.repair_status == "repair_error" for record in records
            ),
            "repair_records_jsonl_hash": hash_file(records_path),
            "artifacts": dict(TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS),
        }
    )


def validate_training_candidate_repair_counts(
    manifest: TrainingCandidateRepairExportManifest,
    records: tuple[TrainingCandidateRepairRecord, ...],
) -> None:
    observed = {
        "record_count": len(records),
        "completed_count": sum(
            record.repair_status == "completed" for record in records
        ),
        "cannot_complete_count": sum(
            record.repair_status == "cannot_complete" for record in records
        ),
        "repair_error_count": sum(
            record.repair_status == "repair_error" for record in records
        ),
    }
    for field_name, observed_count in observed.items():
        expected_count = getattr(manifest, field_name)
        if observed_count != expected_count:
            raise ValueError(
                f"Training candidate repair manifest {field_name} mismatch: "
                f"{observed_count} != {expected_count}"
            )


def _candidate_requires_repair(candidate: TrainingCandidateRecord) -> bool:
    assessment = candidate.mechanical_redundancy_assessment
    return assessment.evaluation_status == "complete" and bool(assessment.blocks)


def _build_pending_repair_record(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
    *,
    public_check_calibrations: tuple[PublicCheckIdempotencyCalibration, ...],
) -> _PendingRepairRecord:
    _validate_candidate_trajectory_identity(candidate, trajectory)
    original_ref, prompt_loop_result = _load_original_prompt_loop(trajectory)
    task_manifest, task_manifest_hash = _load_source_task_manifest(trajectory)
    candidate_hash = hash_training_candidate_record(candidate)
    repairer_code_hash = compute_mechanical_redundancy_repairer_code_hash()
    repair_id = build_training_candidate_repair_id(
        source_training_candidate_record_hash=candidate_hash,
        repairer_code_hash=repairer_code_hash,
    )
    common_fields = {
        "repair_id": repair_id,
        "trajectory_id": candidate.trajectory_id,
        "eval_attempt_id": candidate.eval_attempt_id,
        "source_training_candidate_record_hash": candidate_hash,
        "repair_artifact_type": "transcript",
        "original_artifact_ref": original_ref,
        "repairer_version": MECHANICAL_REDUNDANCY_REPAIRER_VERSION,
        "repairer_code_hash": repairer_code_hash,
    }
    original_assessment = candidate.mechanical_redundancy_assessment
    try:
        completed = repair_prompt_loop_mechanical_redundancy(
            prompt_loop_result,
            original_assessment=original_assessment,
            task_manifest=task_manifest,
            task_manifest_hash=task_manifest_hash,
            public_check_calibrations=public_check_calibrations,
        )
        transcript_bytes = _serialize_repaired_transcript(completed.transcript)
        repaired_ref = ArtifactRef(
            path=f"transcripts/{repair_id}.json",
            content_hash=hash_bytes(transcript_bytes),
        )
        record = TrainingCandidateRepairRecord(
            **common_fields,
            repair_status="completed",
            repaired_artifact_ref=repaired_ref,
            repair=MechanicalRedundancyRepairDetails(
                repair_method=MECHANICAL_REDUNDANCY_REPAIR_METHOD,
                original_mechanical_redundancy_assessment=original_assessment,
                after_repair_mechanical_redundancy_assessment=(
                    completed.after_repair_assessment
                ),
            ),
        )
        return _PendingRepairRecord(
            record=record,
            repaired_transcript_bytes=transcript_bytes,
        )
    except MechanicalRedundancyRepairCannotComplete as exc:
        record = TrainingCandidateRepairRecord(
            **common_fields,
            repair_status="cannot_complete",
            repaired_artifact_ref=None,
            repair=MechanicalRedundancyRepairDetails(
                repair_method=MECHANICAL_REDUNDANCY_REPAIR_METHOD,
                original_mechanical_redundancy_assessment=original_assessment,
                cannot_complete_reason=str(exc),
            ),
        )
        return _PendingRepairRecord(record=record, repaired_transcript_bytes=None)
    except Exception as exc:
        record = _build_repair_error_record(
            common_fields=common_fields,
            original_assessment=original_assessment,
            exc=exc,
        )
        return _PendingRepairRecord(record=record, repaired_transcript_bytes=None)


def _persist_pending_repair(
    out_dir: Path,
    pending: _PendingRepairRecord,
) -> TrainingCandidateRepairRecord:
    if pending.record.repair_status != "completed":
        return pending.record
    repaired_ref = pending.record.repaired_artifact_ref
    transcript_bytes = pending.repaired_transcript_bytes
    if repaired_ref is None or transcript_bytes is None:
        raise AssertionError("completed pending repairs require transcript output")
    repaired_path = resolve_relative_artifact_ref(out_dir, repaired_ref.path)
    try:
        repaired_path.parent.mkdir(parents=True, exist_ok=True)
        repaired_path.write_bytes(transcript_bytes)
        if hash_file(repaired_path) != repaired_ref.content_hash:
            raise OSError("persisted repaired transcript hash mismatch")
    except OSError as exc:
        repaired_path.unlink(missing_ok=True)
        return _build_repair_error_record(
            common_fields={
                "repair_id": pending.record.repair_id,
                "trajectory_id": pending.record.trajectory_id,
                "eval_attempt_id": pending.record.eval_attempt_id,
                "source_training_candidate_record_hash": (
                    pending.record.source_training_candidate_record_hash
                ),
                "repair_artifact_type": pending.record.repair_artifact_type,
                "original_artifact_ref": pending.record.original_artifact_ref,
                "repairer_version": pending.record.repairer_version,
                "repairer_code_hash": pending.record.repairer_code_hash,
            },
            original_assessment=(
                pending.record.repair.original_mechanical_redundancy_assessment
            ),
            exc=exc,
        )
    return pending.record


def _build_repair_error_record(
    *,
    common_fields: dict[str, object],
    original_assessment: MechanicalRedundancyAssessment,
    exc: Exception,
) -> TrainingCandidateRepairRecord:
    message = redact_secrets(str(exc)) or type(exc).__name__
    return TrainingCandidateRepairRecord.model_validate(
        {
            **common_fields,
            "repair_status": "repair_error",
            "repaired_artifact_ref": None,
            "repair": MechanicalRedundancyRepairDetails(
                repair_method=MECHANICAL_REDUNDANCY_REPAIR_METHOD,
                original_mechanical_redundancy_assessment=original_assessment,
            ),
            "error_class": type(exc).__name__,
            "error_message": message[:1000],
        }
    )


def _load_pinned_training_candidate_export(
    repair_export_dir: Path,
    source_ref: TrainingCandidateExportManifestRef,
) -> TrainingCandidateExport:
    source_dir = Path(source_ref.artifact_dir)
    if not source_dir.is_absolute():
        source_dir = repair_export_dir / source_dir
    source_dir = source_dir.resolve()
    manifest_path = source_dir / MANIFEST_FILENAME
    observed_hash = hash_file(manifest_path)
    if observed_hash != source_ref.manifest_hash:
        raise ValueError(
            "Source training candidate manifest hash mismatch: "
            f"{observed_hash!r} != {source_ref.manifest_hash!r}"
        )
    export = load_training_candidate_export_artifact(source_dir)
    if hash_file(manifest_path) != source_ref.manifest_hash:
        raise ValueError("Source training candidate manifest changed while loading")
    return export


def _validate_repair_records_against_source(
    repair_export_dir: Path,
    records: tuple[TrainingCandidateRepairRecord, ...],
    *,
    candidate_export: TrainingCandidateExport,
) -> None:
    candidates_by_identity = _index_training_candidates(candidate_export.records)
    trajectory_export = load_pinned_source_trajectory_export(candidate_export)
    trajectories_by_id = build_trajectory_record_index(trajectory_export.records)
    calibrations = _load_source_public_check_calibrations(candidate_export)
    current_repairer_hash = compute_mechanical_redundancy_repairer_code_hash()

    for record in records:
        identity = (record.trajectory_id, record.eval_attempt_id)
        candidate = candidates_by_identity.get(identity)
        if candidate is None:
            raise ValueError(
                "Repair record references unknown training candidate: "
                f"{record.trajectory_id} / {record.eval_attempt_id}"
            )
        observed_candidate_hash = hash_training_candidate_record(candidate)
        if observed_candidate_hash != record.source_training_candidate_record_hash:
            raise ValueError("Repair record source training candidate hash mismatch")
        if (
            record.repair.original_mechanical_redundancy_assessment
            != candidate.mechanical_redundancy_assessment
        ):
            raise ValueError(
                "Repair original assessment does not match training candidate"
            )
        if record.repairer_version != MECHANICAL_REDUNDANCY_REPAIRER_VERSION or (
            record.repairer_code_hash != current_repairer_hash
        ):
            raise ValueError("Repair record repairer provenance is stale")
        expected_repair_id = build_training_candidate_repair_id(
            source_training_candidate_record_hash=observed_candidate_hash,
            repairer_code_hash=current_repairer_hash,
        )
        if record.repair_id != expected_repair_id:
            raise ValueError("Repair record repair_id does not match its source")

        trajectory = _require_candidate_trajectory(candidate, trajectories_by_id)
        original_ref, prompt_loop_result = _load_original_prompt_loop(trajectory)
        if record.original_artifact_ref != original_ref:
            raise ValueError(
                "Repair original artifact ref does not match source trajectory"
            )
        if record.repair_status == "repair_error":
            continue

        task_manifest, task_manifest_hash = _load_source_task_manifest(trajectory)
        try:
            expected = repair_prompt_loop_mechanical_redundancy(
                prompt_loop_result,
                original_assessment=candidate.mechanical_redundancy_assessment,
                task_manifest=task_manifest,
                task_manifest_hash=task_manifest_hash,
                public_check_calibrations=calibrations,
            )
        except MechanicalRedundancyRepairCannotComplete as exc:
            if record.repair_status != "cannot_complete" or (
                record.repair.cannot_complete_reason != str(exc)
            ):
                raise ValueError(
                    "Persisted repair outcome does not match deterministic repair"
                ) from exc
            continue

        if record.repair_status != "completed":
            raise ValueError(
                "Persisted repair outcome does not match deterministic repair"
            )
        _validate_completed_repair_artifact(
            repair_export_dir,
            record,
            expected_transcript=expected.transcript,
        )
        if (
            record.repair.after_repair_mechanical_redundancy_assessment
            != expected.after_repair_assessment
        ):
            raise ValueError(
                "Persisted after-repair assessment does not match recomputation"
            )


def _validate_completed_repair_artifact(
    repair_export_dir: Path,
    record: TrainingCandidateRepairRecord,
    *,
    expected_transcript: RepairedTranscriptArtifact,
) -> None:
    repaired_ref = record.repaired_artifact_ref
    if repaired_ref is None or repaired_ref.content_hash is None:
        raise ValueError("Completed repair is missing hash-pinned transcript")
    expected_ref = f"transcripts/{record.repair_id}.json"
    if repaired_ref.path != expected_ref:
        raise ValueError("Completed repair transcript path is not canonical")
    repaired_path = resolve_relative_artifact_ref(
        repair_export_dir,
        repaired_ref.path,
    )
    observed_hash = hash_file(repaired_path)
    if observed_hash != repaired_ref.content_hash:
        raise ValueError(
            "Repaired transcript hash mismatch: "
            f"{observed_hash!r} != {repaired_ref.content_hash!r}"
        )
    observed_transcript = load_repaired_transcript_artifact(repaired_path)
    if observed_transcript != expected_transcript:
        raise ValueError(
            "Persisted repaired transcript does not match deterministic repair"
        )


def load_repaired_transcript_artifact(path: Path) -> RepairedTranscriptArtifact:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid repaired transcript JSON at {path}") from exc
    return RepairedTranscriptArtifact.model_validate(payload)


def _serialize_repaired_transcript(
    transcript: RepairedTranscriptArtifact,
) -> bytes:
    return (
        json.dumps(transcript.model_dump(mode="json"), sort_keys=True) + "\n"
    ).encode()


def _load_original_prompt_loop(
    trajectory: TrajectoryRecord,
) -> tuple[ArtifactRef, PromptLoopResult]:
    original_ref = trajectory.artifacts.prompt_loop_result_json
    if original_ref is None:
        raise ValueError("Repair source trajectory is missing prompt-loop artifact")
    original_path = resolve_trajectory_artifact_path(trajectory, original_ref)
    validate_artifact_ref_hash(original_path, original_ref)
    return original_ref, load_prompt_loop_result(original_path)


def _load_source_task_manifest(
    trajectory: TrajectoryRecord,
) -> tuple[TaskManifest, str]:
    task_manifest_path = Path(trajectory.source_provenance.task_manifest_path)
    if not task_manifest_path.is_absolute():
        task_manifest_path = Path.cwd() / task_manifest_path
    task_manifest_path = task_manifest_path.resolve()
    observed_hash = hash_file(task_manifest_path)
    if observed_hash != trajectory.source_provenance.task_manifest_hash:
        raise ValueError("Repair source task manifest hash mismatch")
    return load_task_manifest(task_manifest_path), observed_hash


def _load_source_public_check_calibrations(
    candidate_export: TrainingCandidateExport,
) -> tuple[PublicCheckIdempotencyCalibration, ...]:
    gate = candidate_export.manifest.control_calibration_gate
    artifact_dir = Path(gate.artifact_dir)
    if not artifact_dir.is_absolute():
        artifact_dir = candidate_export.out_dir / artifact_dir
    artifact_dir = artifact_dir.resolve()
    manifest_path = artifact_dir / MANIFEST_FILENAME
    observed_hash = hash_file(manifest_path)
    if observed_hash != gate.manifest_hash:
        raise ValueError("Repair source control-calibration manifest hash mismatch")
    manifest = load_control_calibration_manifest(manifest_path)
    return tuple(manifest.flake_detection.public_check_idempotency)


def _require_candidate_trajectory(
    candidate: TrainingCandidateRecord,
    trajectories_by_id: dict[str, TrajectoryRecord],
) -> TrajectoryRecord:
    trajectory = trajectories_by_id.get(candidate.trajectory_id)
    if trajectory is None:
        raise ValueError(
            f"Repair candidate references unknown trajectory: {candidate.trajectory_id}"
        )
    return trajectory


def _validate_candidate_trajectory_identity(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
) -> None:
    if candidate.trajectory_id != trajectory.identity.trajectory_id or (
        candidate.eval_attempt_id != trajectory.identity.eval_attempt_id
    ):
        raise ValueError("Repair candidate identity does not match trajectory")


def _index_training_candidates(
    records: tuple[TrainingCandidateRecord, ...],
) -> dict[tuple[str, str], TrainingCandidateRecord]:
    indexed: dict[tuple[str, str], TrainingCandidateRecord] = {}
    for record in records:
        identity = (record.trajectory_id, record.eval_attempt_id)
        if identity in indexed:
            raise ValueError(
                "Training candidate export contains duplicate repair identities"
            )
        indexed[identity] = record
    return indexed


def _validate_unique_repair_ids(
    records: tuple[TrainingCandidateRepairRecord, ...],
) -> None:
    repair_ids = [record.repair_id for record in records]
    if len(repair_ids) != len(set(repair_ids)):
        raise ValueError("Training candidate repair records require unique repair_id")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
