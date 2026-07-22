import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import agentenv.training.release.trust as trust_module
from agentenv.audits.runner import load_harness_audit_artifact
from agentenv.audits.runner import run_harness_audit
from agentenv.audits.schema import derive_harness_runtime_hash
from agentenv.controls.controls_run import run_controls
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.hashing import hash_file
from agentenv.training.release.trust import validate_training_release_trust
from agentenv.trajectories.export import export_trajectory_records_from_eval_artifact
from agentenv.trajectories.review import (
    initialize_trajectory_review_artifact,
    validate_trajectory_review_artifact,
)


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
AGENT_CASE_ROOT = Path("data/harness_audit/agent_task_cases")
SCORER_CASE_ROOT = Path("data/harness_audit/scorer_cases")
AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")


@dataclass(frozen=True)
class RealTrainingTrustFixture:
    trajectory_export_dir: Path
    review_dir: Path
    harness_audit_dir: Path
    control_calibration_dir: Path


@pytest.fixture(scope="module")
def real_training_trust(
    tmp_path_factory: pytest.TempPathFactory,
) -> RealTrainingTrustFixture:
    root = tmp_path_factory.mktemp("real-training-trust")
    harness_audit = run_harness_audit(
        agent_case_root=AGENT_CASE_ROOT,
        scorer_case_root=SCORER_CASE_ROOT,
        out_dir=root / "harness-audit",
    )
    controls = run_controls(
        TASK_PACK,
        repeats=2,
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
    return RealTrainingTrustFixture(
        trajectory_export_dir=trajectory_export.out_dir,
        review_dir=review.out_dir,
        harness_audit_dir=harness_audit.out_dir,
        control_calibration_dir=controls.out_dir,
    )


def test_training_release_trust_accepts_matching_real_artifacts(
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    trust = _validate_release_trust(real_training_trust)

    assert trust.harness_audit.status == "PASS"
    assert trust.control_calibration.overall_match is True
    assert trust.control_calibration.flake_detection_status == "stable"
    assert (
        trust.harness_audit.harness_runtime_hash
        == trust.control_calibration.harness_runtime_hash
    )


def test_training_release_trust_rejects_missing_artifacts(
    tmp_path: Path,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    validation = _trajectory_review_validation(real_training_trust)

    with pytest.raises(ValueError, match="Expected harness-audit artifact directory"):
        validate_training_release_trust(
            validation,
            harness_audit_dir=tmp_path / "missing-harness-audit",
            control_calibration_dir=tmp_path / "missing-control-calibration",
        )


def test_training_release_trust_rejects_non_pass_harness_audit(
    monkeypatch: pytest.MonkeyPatch,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    artifact = load_harness_audit_artifact(real_training_trust.harness_audit_dir)
    failed_artifact = replace(
        artifact,
        manifest=artifact.manifest.model_copy(update={"status": "FAIL"}),
    )
    monkeypatch.setattr(
        trust_module,
        "load_harness_audit_artifact",
        lambda _path: failed_artifact,
    )
    with pytest.raises(ValueError, match="requires harness audit status PASS"):
        _validate_release_trust(real_training_trust)


def test_training_release_trust_rejects_incomplete_public_check_coverage(
    tmp_path: Path,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_trust.control_calibration_dir, control_dir)
    manifest_path = control_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    calibrations = manifest["flake_detection"]["public_check_idempotency"]
    assert calibrations
    manifest["flake_detection"]["public_check_idempotency"] = calibrations[1:]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with pytest.raises(
        ValueError,
        match="public-check coverage mismatch",
    ):
        validate_training_release_trust(
            _trajectory_review_validation(real_training_trust),
            harness_audit_dir=real_training_trust.harness_audit_dir,
            control_calibration_dir=control_dir,
        )


def test_training_release_trust_rejects_control_runtime_drift(
    tmp_path: Path,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_trust.control_calibration_dir, control_dir)
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
    with pytest.raises(
        ValueError,
        match="Control calibration runtime does not match",
    ):
        validate_training_release_trust(
            _trajectory_review_validation(real_training_trust),
            harness_audit_dir=real_training_trust.harness_audit_dir,
            control_calibration_dir=control_dir,
        )


def test_training_release_trust_rejects_source_eval_runtime_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    trajectory_manifest = json.loads(
        (real_training_trust.trajectory_export_dir / "manifest.json").read_text()
    )
    source_manifest_path = Path(trajectory_manifest["source_manifest_path"])
    source_manifest = trust_module.load_eval_artifact_manifest(source_manifest_path)
    source_runtime = source_manifest.runtime_provenance
    changed_runtime = source_runtime.model_copy(
        update={"python_version": f"{source_runtime.python_version}-changed"}
    )
    changed_manifest = source_manifest.model_copy(
        update={"runtime_provenance": changed_runtime}
    )
    monkeypatch.setattr(
        trust_module,
        "load_eval_artifact_manifest",
        lambda _path: changed_manifest,
    )

    with pytest.raises(
        ValueError,
        match="Source eval runtime does not match the audited harness runtime",
    ):
        _validate_release_trust(real_training_trust)


def test_training_release_trust_rejects_single_control_repeat(
    monkeypatch: pytest.MonkeyPatch,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    manifest_path = real_training_trust.control_calibration_dir / "manifest.json"
    manifest = trust_module.load_control_calibration_manifest(manifest_path)
    weak_flake_detection = manifest.flake_detection.model_copy(update={"repeats": 1})
    weak_manifest = manifest.model_copy(
        update={
            "repeats": 1,
            "flake_detection": weak_flake_detection,
        }
    )
    monkeypatch.setattr(
        trust_module,
        "load_control_calibration_manifest",
        lambda _path: weak_manifest,
    )

    with pytest.raises(
        ValueError,
        match="requires at least 2 control repeats",
    ):
        _validate_release_trust(real_training_trust)


def test_training_release_trust_rejects_failed_control_outcome(
    tmp_path: Path,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_trust.control_calibration_dir, control_dir)
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
    with pytest.raises(
        ValueError,
        match="requires control calibration overall_match=true",
    ):
        validate_training_release_trust(
            _trajectory_review_validation(real_training_trust),
            harness_audit_dir=real_training_trust.harness_audit_dir,
            control_calibration_dir=control_dir,
        )


def test_training_release_trust_rejects_task_hash_mismatch(
    tmp_path: Path,
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    control_dir = tmp_path / "control-calibration"
    shutil.copytree(real_training_trust.control_calibration_dir, control_dir)
    manifest_path = control_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    toy_task = next(
        task
        for task in manifest["task_hashes"]["selected_tasks"]
        if task["task_id"] == "toy_python_fix_001"
    )
    toy_task["task_record_hash"] = "xxh64:ffffffffffffffff"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with pytest.raises(
        ValueError,
        match="task hash differs for trajectory task toy_python_fix_001",
    ):
        validate_training_release_trust(
            _trajectory_review_validation(real_training_trust),
            harness_audit_dir=real_training_trust.harness_audit_dir,
            control_calibration_dir=control_dir,
        )


def test_training_release_trust_pins_manifest_hashes(
    real_training_trust: RealTrainingTrustFixture,
) -> None:
    trust = _validate_release_trust(real_training_trust)

    assert trust.harness_audit.manifest_hash == hash_file(
        real_training_trust.harness_audit_dir / "manifest.json"
    )
    assert trust.control_calibration.manifest_hash == hash_file(
        real_training_trust.control_calibration_dir / "manifest.json"
    )


def _trajectory_review_validation(fixture: RealTrainingTrustFixture):
    return validate_trajectory_review_artifact(
        fixture.trajectory_export_dir,
        fixture.review_dir,
    )


def _validate_release_trust(fixture: RealTrainingTrustFixture):
    return validate_training_release_trust(
        _trajectory_review_validation(fixture),
        harness_audit_dir=fixture.harness_audit_dir,
        control_calibration_dir=fixture.control_calibration_dir,
    )
