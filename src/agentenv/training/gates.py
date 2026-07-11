"""Fail-closed trust gates for training-candidate construction."""

from dataclasses import dataclass
from pathlib import Path

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION,
    HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
    ControlCalibrationManifest,
    EvalRunManifest,
    EvalSuiteManifest,
    TrainingCandidateControlCalibrationManifestRef,
    TrainingCandidateHarnessAuditManifestRef,
    load_control_calibration_manifest,
    load_eval_artifact_manifest,
)
from agentenv.artifacts.payloads import (
    EvalTaskHashes,
    load_control_calibration_result_records,
)
from agentenv.audits.runner import (
    HarnessAuditArtifact,
    load_harness_audit_artifact,
)
from agentenv.audits.runtime import (
    capture_harness_runtime_provenance,
    harness_repo_root,
)
from agentenv.hashing import hash_directory, hash_file
from agentenv.tasks.hashing import build_eval_task_hashes
from agentenv.tasks.validate import load_task_manifest, load_task_pack_manifest
from agentenv.trajectories.review import TrajectoryReviewValidation


@dataclass(frozen=True)
class TrainingExportGateValidation:
    harness_audit_gate: TrainingCandidateHarnessAuditManifestRef
    control_calibration_gate: TrainingCandidateControlCalibrationManifestRef


def validate_training_export_gates(
    validation: TrajectoryReviewValidation,
    *,
    harness_audit_dir: Path,
    control_calibration_dir: Path,
) -> TrainingExportGateValidation:
    """Validate both suite-level trust artifacts against the trajectory source."""
    harness_audit_dir = harness_audit_dir.resolve()
    control_calibration_dir = control_calibration_dir.resolve()
    if not harness_audit_dir.is_dir():
        raise ValueError(
            f"Expected harness-audit artifact directory: {harness_audit_dir}"
        )
    if not control_calibration_dir.is_dir():
        raise ValueError(
            "Expected control-calibration artifact directory: "
            f"{control_calibration_dir}"
        )
    harness_artifact = load_harness_audit_artifact(harness_audit_dir)
    control_manifest_path = control_calibration_dir / MANIFEST_FILENAME
    control_manifest = load_control_calibration_manifest(control_manifest_path)

    _require_successful_harness_audit(harness_artifact)
    _require_successful_control_calibration(
        control_calibration_dir,
        control_manifest,
    )
    current_runtime = capture_harness_runtime_provenance(harness_repo_root())
    if harness_artifact.manifest.runtime_provenance != current_runtime:
        raise ValueError(
            "Harness audit runtime does not match the current harness runtime"
        )
    if control_manifest.runtime_provenance != current_runtime:
        raise ValueError(
            "Control calibration runtime does not match the current harness runtime"
        )
    if (
        harness_artifact.manifest.runtime_provenance
        != control_manifest.runtime_provenance
    ):
        raise ValueError(
            "Harness audit and control calibration used different harness runtimes"
        )

    _require_current_harness_audit_cases(harness_artifact)
    source_task_hashes = _load_source_eval_task_hashes(validation)
    _require_matching_control_tasks(
        validation,
        source_task_hashes=source_task_hashes,
        control_manifest=control_manifest,
    )

    runtime_hash = current_runtime.harness_runtime_hash
    return TrainingExportGateValidation(
        harness_audit_gate=TrainingCandidateHarnessAuditManifestRef(
            artifact_type="harness_audit",
            artifact_schema_version=HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
            artifact_dir=str(harness_audit_dir),
            manifest_hash=hash_file(harness_audit_dir / MANIFEST_FILENAME),
            harness_audit_run_id=harness_artifact.manifest.harness_audit_run_id,
            harness_runtime_hash=runtime_hash,
            status="PASS",
        ),
        control_calibration_gate=TrainingCandidateControlCalibrationManifestRef(
            artifact_type="control_calibration",
            artifact_schema_version=CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION,
            artifact_dir=str(control_calibration_dir),
            manifest_hash=hash_file(control_manifest_path),
            control_run_id=control_manifest.control_run_id,
            harness_runtime_hash=runtime_hash,
            task_pack_id=control_manifest.task_hashes.task_pack_id,
            selected_task_hash_set=(
                control_manifest.task_hashes.selected_task_hash_set
            ),
            overall_match=True,
            flake_detection_status="stable",
        ),
    )


def _require_successful_harness_audit(artifact: HarnessAuditArtifact) -> None:
    if artifact.manifest.status != "PASS":
        raise ValueError(
            "Training-candidate export requires harness audit status PASS; "
            f"observed {artifact.manifest.status}"
        )


def _require_successful_control_calibration(
    artifact_dir: Path,
    manifest: ControlCalibrationManifest,
) -> None:
    if not manifest.overall_match:
        raise ValueError(
            "Training-candidate export requires control calibration overall_match=true"
        )
    if manifest.flake_detection.status != "stable":
        raise ValueError(
            "Training-candidate export requires stable control flake detection; "
            f"observed {manifest.flake_detection.status}"
        )
    results_path = resolve_relative_artifact_ref(
        artifact_dir,
        manifest.artifacts["results"],
    )
    loaded_records = load_control_calibration_result_records(results_path)
    if list(loaded_records) != manifest.records:
        raise ValueError(
            "Control calibration results JSONL does not match manifest records"
        )
    for calibration in manifest.flake_detection.public_check_idempotency:
        for run in calibration.runs:
            for stream_name, artifact_ref in (
                ("stdout", run.stdout),
                ("stderr", run.stderr),
            ):
                if artifact_ref is None:
                    continue
                path = resolve_relative_artifact_ref(artifact_dir, artifact_ref.path)
                observed_hash = hash_file(path)
                if observed_hash != artifact_ref.content_hash:
                    raise ValueError(
                        "Control calibration public-check "
                        f"{stream_name} hash mismatch at {path}: "
                        f"{observed_hash!r} != {artifact_ref.content_hash!r}"
                    )


def _require_current_harness_audit_cases(artifact: HarnessAuditArtifact) -> None:
    repo_root = harness_repo_root()
    for layer_name, summary in (
        ("agent-task", artifact.agent_audit.summary),
        ("scorer", artifact.scorer_audit.summary),
    ):
        case_root = (repo_root / summary.case_root).resolve()
        if not case_root.is_relative_to(repo_root):
            raise ValueError(
                f"{layer_name} harness-audit case root escapes the harness repo"
            )
        observed_hash = hash_directory(case_root)
        if observed_hash != summary.case_root_hash:
            raise ValueError(
                f"{layer_name} harness-audit cases drifted after calibration: "
                f"{observed_hash!r} != {summary.case_root_hash!r}"
            )


def _load_source_eval_task_hashes(
    validation: TrajectoryReviewValidation,
) -> EvalTaskHashes:
    trajectory_manifest = validation.source_export.manifest
    source_artifact_dir = _external_path(trajectory_manifest.source_artifact_dir)
    expected_manifest_path = source_artifact_dir / MANIFEST_FILENAME
    declared_manifest_path = _external_path(trajectory_manifest.source_manifest_path)
    if declared_manifest_path != expected_manifest_path:
        raise ValueError(
            "Trajectory export source manifest path does not match its source "
            "artifact directory"
        )
    observed_hash = hash_file(declared_manifest_path)
    if observed_hash != trajectory_manifest.source_manifest_hash:
        raise ValueError(
            "Trajectory export source eval manifest hash mismatch: "
            f"{observed_hash!r} != {trajectory_manifest.source_manifest_hash!r}"
        )
    source_manifest = load_eval_artifact_manifest(declared_manifest_path)
    if source_manifest.artifact_type != trajectory_manifest.source_artifact_type:
        raise ValueError("Trajectory export source eval artifact type mismatch")
    if (
        source_manifest.artifact_schema_version
        != trajectory_manifest.source_artifact_schema_version
    ):
        raise ValueError("Trajectory export source eval artifact schema mismatch")
    if trajectory_manifest.source_eval_run_id is not None:
        if not isinstance(source_manifest, EvalRunManifest) or (
            source_manifest.eval_run_id != trajectory_manifest.source_eval_run_id
        ):
            raise ValueError("Trajectory export source eval run identity mismatch")
    else:
        if not isinstance(source_manifest, EvalSuiteManifest) or (
            source_manifest.eval_suite_id != trajectory_manifest.source_eval_suite_id
        ):
            raise ValueError("Trajectory export source eval suite identity mismatch")
    return source_manifest.task_hashes


def _require_matching_control_tasks(
    validation: TrajectoryReviewValidation,
    *,
    source_task_hashes: EvalTaskHashes,
    control_manifest: ControlCalibrationManifest,
) -> None:
    trajectory_task_ids = {
        record.identity.task_id for record in validation.source_export.records
    }
    source_by_id = {task.task_id: task for task in source_task_hashes.selected_tasks}
    control_by_id = {
        task.task_id: task for task in control_manifest.task_hashes.selected_tasks
    }
    missing_source = sorted(trajectory_task_ids - set(source_by_id))
    if missing_source:
        raise ValueError(
            "Trajectory tasks are missing source eval task hashes: "
            + ", ".join(missing_source)
        )
    missing_controls = sorted(trajectory_task_ids - set(control_by_id))
    if missing_controls:
        raise ValueError(
            "Control calibration does not cover trajectory tasks: "
            + ", ".join(missing_controls)
        )
    if source_task_hashes.task_pack_id != control_manifest.task_hashes.task_pack_id:
        raise ValueError("Control calibration task pack differs from trajectory source")
    for task_id in sorted(trajectory_task_ids):
        if source_by_id[task_id] != control_by_id[task_id]:
            raise ValueError(
                f"Control calibration task hash differs for trajectory task {task_id}"
            )
    for trajectory in validation.source_export.records:
        expected_manifest_hash = source_by_id[
            trajectory.identity.task_id
        ].task_yaml_hash
        if trajectory.source_provenance.task_manifest_hash != expected_manifest_hash:
            raise ValueError(
                "Trajectory task manifest hash differs from source eval task hash "
                f"for {trajectory.identity.task_id}"
            )

    task_pack_path = _external_path(control_manifest.task_pack_path)
    calibrated_task_ids = [
        task.task_id for task in control_manifest.task_hashes.selected_tasks
    ]
    current_task_hashes = build_eval_task_hashes(
        task_pack_path,
        calibrated_task_ids,
    )
    if current_task_hashes != control_manifest.task_hashes:
        raise ValueError("Control-calibrated task inputs have drifted")
    _require_public_check_calibration_coverage(
        task_pack_path,
        calibrated_task_ids=calibrated_task_ids,
        control_manifest=control_manifest,
    )


def _require_public_check_calibration_coverage(
    task_pack_path: Path,
    *,
    calibrated_task_ids: list[str],
    control_manifest: ControlCalibrationManifest,
) -> None:
    pack_manifest = load_task_pack_manifest(task_pack_path / "manifest.yaml")
    tasks_dir = (task_pack_path / pack_manifest.tasks_dir).resolve()
    if not tasks_dir.is_relative_to(task_pack_path):
        raise ValueError("Control task-pack tasks directory escapes the task pack")
    manifests_by_id = {}
    for path in sorted(tasks_dir.glob("*/task.yaml")):
        task_manifest = load_task_manifest(path)
        manifests_by_id[task_manifest.id] = (path, task_manifest)

    expected = {}
    for task_id in calibrated_task_ids:
        task_entry = manifests_by_id.get(task_id)
        if task_entry is None:
            raise ValueError(f"Control-calibrated task is missing: {task_id}")
        manifest_path, task_manifest = task_entry
        manifest_hash = hash_file(manifest_path)
        for index, public_check in enumerate(task_manifest.public_checks):
            if public_check.are_tests_idempotent:
                expected[(task_id, index)] = (
                    manifest_hash,
                    public_check.command,
                )

    observed = {
        (calibration.task_id, calibration.public_check_index): calibration
        for calibration in control_manifest.flake_detection.public_check_idempotency
    }
    if set(observed) != set(expected):
        missing = sorted(set(expected) - set(observed))
        unexpected = sorted(set(observed) - set(expected))
        raise ValueError(
            "Control calibration public-check coverage mismatch: "
            f"missing={missing!r} unexpected={unexpected!r}"
        )
    for identity, (manifest_hash, command) in expected.items():
        calibration = observed[identity]
        if calibration.status != "IDEMPOTENT":
            raise ValueError(
                "Training-candidate export requires IDEMPOTENT public checks; "
                f"{identity!r} was {calibration.status}"
            )
        if calibration.task_manifest_hash != manifest_hash:
            raise ValueError(
                f"Public-check calibration task hash drifted for {identity!r}"
            )
        if calibration.command != command:
            raise ValueError(
                f"Public-check calibration command drifted for {identity!r}"
            )


def _external_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()
