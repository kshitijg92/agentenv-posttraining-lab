import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import agentenv.training.gates as gates_module
from agentenv.audits.runner import load_harness_audit_artifact
from agentenv.audits.runner import run_harness_audit
from agentenv.audits.schema import derive_harness_runtime_hash
from agentenv.controls.controls_run import run_controls
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.export import (
    export_training_candidate_records,
    load_training_candidate_export_artifact,
)
from agentenv.trajectories.export import export_trajectory_records_from_eval_artifact
from agentenv.trajectories.review import initialize_trajectory_review_artifact


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
AGENT_CASE_ROOT = Path("data/harness_audit/agent_task_cases")
SCORER_CASE_ROOT = Path("data/harness_audit/scorer_cases")
AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")


@dataclass(frozen=True)
class RealTrainingGateFixture:
    trajectory_export_dir: Path
    review_dir: Path
    harness_audit_dir: Path
    control_calibration_dir: Path


@pytest.fixture(scope="module")
def real_training_gates(
    tmp_path_factory: pytest.TempPathFactory,
) -> RealTrainingGateFixture:
    root = tmp_path_factory.mktemp("real-training-gates")
    harness_audit = run_harness_audit(
        agent_case_root=AGENT_CASE_ROOT,
        scorer_case_root=SCORER_CASE_ROOT,
        out_dir=root / "harness-audit",
    )
    controls = run_controls(
        TASK_PACK,
        repeats=1,
        out_dir=root / "control-calibration",
    )
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        root / "eval-run",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        root / "trajectory-export",
    )
    review = initialize_trajectory_review_artifact(
        trajectory_export.out_dir,
        root / "trajectory-review",
    )
    return RealTrainingGateFixture(
        trajectory_export_dir=trajectory_export.out_dir,
        review_dir=review.out_dir,
        harness_audit_dir=harness_audit.out_dir,
        control_calibration_dir=controls.out_dir,
    )


def test_training_candidate_export_pins_and_revalidates_real_gates(
    tmp_path: Path,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    export = _export_with_gates(
        tmp_path / "training-candidates",
        real_training_gates,
    )

    assert export.manifest.harness_audit_gate.status == "PASS"
    assert export.manifest.control_calibration_gate.overall_match is True
    assert export.manifest.control_calibration_gate.flake_detection_status == "stable"
    assert (
        export.manifest.harness_audit_gate.harness_runtime_hash
        == export.manifest.control_calibration_gate.harness_runtime_hash
    )
    assert load_training_candidate_export_artifact(export.out_dir) == export


def test_training_candidate_export_fails_before_output_without_gate_artifacts(
    tmp_path: Path,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    out_dir = tmp_path / "training-candidates"

    with pytest.raises(ValueError, match="Expected harness-audit artifact directory"):
        export_training_candidate_records(
            real_training_gates.trajectory_export_dir,
            real_training_gates.review_dir,
            out_dir,
            harness_audit_dir=tmp_path / "missing-harness-audit",
            control_calibration_dir=tmp_path / "missing-control-calibration",
        )

    assert not out_dir.exists()


def test_training_candidate_export_rejects_non_pass_harness_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    artifact = load_harness_audit_artifact(real_training_gates.harness_audit_dir)
    failed_artifact = replace(
        artifact,
        manifest=artifact.manifest.model_copy(update={"status": "FAIL"}),
    )
    monkeypatch.setattr(
        gates_module,
        "load_harness_audit_artifact",
        lambda _path: failed_artifact,
    )
    out_dir = tmp_path / "training-candidates"

    with pytest.raises(ValueError, match="requires harness audit status PASS"):
        export_training_candidate_records(
            real_training_gates.trajectory_export_dir,
            real_training_gates.review_dir,
            out_dir,
            harness_audit_dir=real_training_gates.harness_audit_dir,
            control_calibration_dir=real_training_gates.control_calibration_dir,
        )

    assert not out_dir.exists()


def test_training_candidate_export_rejects_incomplete_public_check_coverage(
    tmp_path: Path,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_gates.control_calibration_dir, control_dir)
    manifest_path = control_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    calibrations = manifest["flake_detection"]["public_check_idempotency"]
    assert calibrations
    manifest["flake_detection"]["public_check_idempotency"] = calibrations[1:]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    out_dir = tmp_path / "training-candidates"

    with pytest.raises(
        ValueError,
        match="public-check coverage mismatch",
    ):
        export_training_candidate_records(
            real_training_gates.trajectory_export_dir,
            real_training_gates.review_dir,
            out_dir,
            harness_audit_dir=real_training_gates.harness_audit_dir,
            control_calibration_dir=control_dir,
        )

    assert not out_dir.exists()


def test_training_candidate_export_rejects_control_runtime_drift(
    tmp_path: Path,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_gates.control_calibration_dir, control_dir)
    manifest_path = control_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    runtime = manifest["runtime_provenance"]
    runtime["harness_source_hash"] = "xxh64:ffffffffffffffff"
    runtime["harness_runtime_hash"] = derive_harness_runtime_hash(
        harness_source_hash=runtime["harness_source_hash"],
        root_pyproject_hash=runtime["root_pyproject_hash"],
        root_uv_lock_hash=runtime["root_uv_lock_hash"],
        python_implementation=runtime["python_implementation"],
        python_version=runtime["python_version"],
        sys_platform=runtime["sys_platform"],
        platform_machine=runtime["platform_machine"],
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    out_dir = tmp_path / "training-candidates"

    with pytest.raises(
        ValueError,
        match="Control calibration runtime does not match",
    ):
        export_training_candidate_records(
            real_training_gates.trajectory_export_dir,
            real_training_gates.review_dir,
            out_dir,
            harness_audit_dir=real_training_gates.harness_audit_dir,
            control_calibration_dir=control_dir,
        )

    assert not out_dir.exists()


def test_training_candidate_export_rejects_failed_control_outcome(
    tmp_path: Path,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_gates.control_calibration_dir, control_dir)
    manifest_path = control_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    record = manifest["records"][0]
    assert record["control_layer"] == "scorer"
    record["expected"]["attempt_status"] = "HIDDEN_TEST_FAIL"
    record["expected"]["public_status"] = "PASS"
    record["expected"]["hidden_status"] = "FAIL"
    record["match"] = False
    manifest["overall_match"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    out_dir = tmp_path / "training-candidates"

    with pytest.raises(
        ValueError,
        match="requires control calibration overall_match=true",
    ):
        export_training_candidate_records(
            real_training_gates.trajectory_export_dir,
            real_training_gates.review_dir,
            out_dir,
            harness_audit_dir=real_training_gates.harness_audit_dir,
            control_calibration_dir=control_dir,
        )

    assert not out_dir.exists()


def test_training_candidate_export_rejects_task_hash_mismatch(
    tmp_path: Path,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_gates.control_calibration_dir, control_dir)
    manifest_path = control_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    toy_task = next(
        task
        for task in manifest["task_hashes"]["selected_tasks"]
        if task["task_id"] == "toy_python_fix_001"
    )
    toy_task["task_record_hash"] = "xxh64:ffffffffffffffff"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    out_dir = tmp_path / "training-candidates"

    with pytest.raises(
        ValueError,
        match="task hash differs for trajectory task toy_python_fix_001",
    ):
        export_training_candidate_records(
            real_training_gates.trajectory_export_dir,
            real_training_gates.review_dir,
            out_dir,
            harness_audit_dir=real_training_gates.harness_audit_dir,
            control_calibration_dir=control_dir,
        )

    assert not out_dir.exists()


def test_training_candidate_loader_rejects_gate_manifest_drift(
    tmp_path: Path,
    real_training_gates: RealTrainingGateFixture,
) -> None:
    harness_dir = tmp_path / "harness-audit"
    shutil.copytree(real_training_gates.harness_audit_dir, harness_dir)
    local_gates = RealTrainingGateFixture(
        trajectory_export_dir=real_training_gates.trajectory_export_dir,
        review_dir=real_training_gates.review_dir,
        harness_audit_dir=harness_dir,
        control_calibration_dir=real_training_gates.control_calibration_dir,
    )
    export = _export_with_gates(
        tmp_path / "training-candidates",
        local_gates,
    )
    manifest_path = harness_dir / "manifest.json"
    manifest_path.write_text(manifest_path.read_text() + "\n")

    with pytest.raises(
        ValueError,
        match="harness-audit gate provenance drifted",
    ):
        load_training_candidate_export_artifact(export.out_dir)


def _export_with_gates(
    out_dir: Path,
    gates: RealTrainingGateFixture,
):
    return export_training_candidate_records(
        gates.trajectory_export_dir,
        gates.review_dir,
        out_dir,
        harness_audit_dir=gates.harness_audit_dir,
        control_calibration_dir=gates.control_calibration_dir,
    )
