from pathlib import Path
from typing import Any

import pytest

import agentenv.training.builder as training_builder_module
import agentenv.training.export as training_export_module
from agentenv.artifacts.manifests import (
    CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION,
    HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
    TrainingCandidateControlCalibrationManifestRef,
    TrainingCandidateHarnessAuditManifestRef,
)
from agentenv.training.gates import TrainingExportGateValidation


@pytest.fixture
def stub_training_export_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> TrainingExportGateValidation:
    runtime_hash = "xxh64:aaaaaaaaaaaaaaaa"
    validation = TrainingExportGateValidation(
        harness_audit_gate=TrainingCandidateHarnessAuditManifestRef(
            artifact_type="harness_audit",
            artifact_schema_version=HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
            artifact_dir=str(Path("/unit/harness-audit")),
            manifest_hash="xxh64:bbbbbbbbbbbbbbbb",
            harness_audit_run_id="harness_audit_unit",
            harness_runtime_hash=runtime_hash,
            status="PASS",
        ),
        control_calibration_gate=TrainingCandidateControlCalibrationManifestRef(
            artifact_type="control_calibration",
            artifact_schema_version=CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION,
            artifact_dir=str(Path("/unit/control-calibration")),
            manifest_hash="xxh64:cccccccccccccccc",
            control_run_id="controls_unit",
            harness_runtime_hash=runtime_hash,
            task_pack_id="repo_patch_python_v0",
            selected_task_hash_set="xxh64:dddddddddddddddd",
            overall_match=True,
            flake_detection_status="stable",
        ),
        public_check_idempotency_calibrations=(),
    )

    def fake_validation(*args: Any, **kwargs: Any) -> TrainingExportGateValidation:
        return validation

    monkeypatch.setattr(
        training_export_module,
        "validate_training_export_gates",
        fake_validation,
    )
    monkeypatch.setattr(
        training_builder_module,
        "validate_training_export_gates",
        fake_validation,
    )
    return validation
