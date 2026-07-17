import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import agentenv.cli as cli_module
from agentenv.audits.schema import (
    HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
    derive_harness_runtime_hash,
)
from agentenv.cli import app


def test_eval_cli_writes_optional_eval_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_run"
    report_path = tmp_path / "reports/eval_report.md"

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--policy",
            "oracle",
            "--out",
            str(out_dir),
            "--report-out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "wrote" in result.output
    assert "manifest.json" in result.output
    assert "eval_report.md" in result.output
    assert (out_dir / "manifest.json").is_file()
    assert report_path.is_file()
    assert "# Eval Report" in report_path.read_text()


def test_eval_cli_rejects_non_empty_out_without_overwrite(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_run"
    out_dir.mkdir()
    stale_file = out_dir / "stale.txt"
    stale_file.write_text("stale\n")

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--policy",
            "oracle",
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code != 0
    assert "Output directory is not empty" in result.output
    assert stale_file.read_text() == "stale\n"


def test_eval_cli_overwrite_clears_non_empty_out(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_run"
    out_dir.mkdir()
    stale_file = out_dir / "stale.txt"
    stale_file.write_text("stale\n")

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--policy",
            "oracle",
            "--out",
            str(out_dir),
            "--overwrite",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not stale_file.exists()
    assert (out_dir / "manifest.json").is_file()


def test_eval_cli_writes_optional_eval_matrix_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_matrix"
    report_path = tmp_path / "reports/eval_matrix.md"

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--all-policies",
            "--out",
            str(out_dir),
            "--report-out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "wrote" in result.output
    assert "manifest.json" in result.output
    assert "eval_matrix.md" in result.output
    assert (out_dir / "manifest.json").is_file()
    assert report_path.is_file()
    assert "# Eval Suite Report" in report_path.read_text()


def test_eval_compare_task_hashes_cli_matches_and_writes_json(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    comparison_out = tmp_path / "reports/hash_comparison.json"
    _write_eval_hash_manifest(
        reference / "manifest.json",
        artifact_type="eval_run",
        artifact_schema_version="eval_run_artifact_v0",
        selected_task_hash_set="xxh64:same-set",
        task_record_hash="xxh64:same-task",
    )
    _write_eval_hash_manifest(
        candidate / "manifest.json",
        artifact_type="eval_suite",
        artifact_schema_version="eval_suite_artifact_v0",
        selected_task_hash_set="xxh64:same-set",
        task_record_hash="xxh64:same-task",
    )

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "compare-task-hashes",
            "--reference",
            str(reference),
            "--candidate",
            str(candidate),
            "--out",
            str(comparison_out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "task input provenance matched" in result.output
    assert "reference=eval_run/eval_run_artifact_v0" in result.output
    assert "candidate=eval_suite/eval_suite_artifact_v0" in result.output
    assert comparison_out.is_file()
    comparison = json.loads(comparison_out.read_text())
    assert comparison["status"] == "matched"
    assert comparison["reference"]["artifact_type"] == "eval_run"
    assert comparison["reference"]["artifact_schema_version"] == "eval_run_artifact_v0"
    assert comparison["candidate"]["artifact_type"] == "eval_suite"
    assert (
        comparison["candidate"]["artifact_schema_version"] == "eval_suite_artifact_v0"
    )


def test_eval_compare_task_hashes_cli_exits_nonzero_on_drift(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    _write_eval_hash_manifest(
        reference / "manifest.json",
        artifact_type="eval_run",
        artifact_schema_version="eval_run_artifact_v0",
        selected_task_hash_set="xxh64:reference-set",
        task_record_hash="xxh64:reference-task",
    )
    _write_eval_hash_manifest(
        candidate / "manifest.json",
        artifact_type="eval_run",
        artifact_schema_version="eval_run_artifact_v0",
        selected_task_hash_set="xxh64:candidate-set",
        task_record_hash="xxh64:candidate-task",
    )

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "compare-task-hashes",
            "--reference",
            str(reference),
            "--candidate",
            str(candidate),
        ],
    )

    assert result.exit_code == 1
    assert "task input provenance drifted" in result.output
    assert "selected_task_hash_set_match=false" in result.output
    assert "changed_tasks=1" in result.output
    assert "changed_task=toy_python_fix_001" in result.output


def test_trajectories_export_cli_writes_eval_run_export(tmp_path: Path) -> None:
    eval_out = tmp_path / "eval_run"
    trajectory_out = tmp_path / "trajectory_export"
    runner = CliRunner()
    eval_result = runner.invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--policy",
            "oracle",
            "--out",
            str(eval_out),
        ],
    )
    assert eval_result.exit_code == 0, eval_result.output

    result = runner.invoke(
        app,
        [
            "trajectories",
            "export",
            "--source",
            str(eval_out),
            "--out",
            str(trajectory_out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "trajectory export complete" in result.output
    assert "source=eval_run" in result.output
    assert "records=1" in result.output
    assert "manifest.json" in result.output
    assert "trajectories.jsonl" in result.output
    manifest = json.loads((trajectory_out / "manifest.json").read_text())
    assert manifest["artifact_type"] == "trajectory_export"
    assert manifest["source_artifact_type"] == "eval_run"
    assert manifest["source_eval_run_id"].startswith("eval_run_")
    assert manifest["source_eval_suite_id"] is None
    assert manifest["record_count"] == 1
    assert (trajectory_out / "trajectories.jsonl").is_file()


def test_rewards_audit_cli_writes_reward_hack_audit_artifact(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "reward_hack_audit"
    report_path = tmp_path / "reports/reward_hack_audit.md"

    result = CliRunner().invoke(
        app,
        [
            "rewards",
            "audit",
            "--cases",
            "data/reward_hack_cases",
            "--out",
            str(out_dir),
            "--report-out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "reward-hack audit complete" in result.output
    assert "records=16" in result.output
    assert "passed=16" in result.output
    assert "failed=0" in result.output
    assert "manifest.json" in result.output
    assert "reward_hack_audit_results.jsonl" in result.output
    assert "reward_hack_audit.md" in result.output
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["artifact_type"] == "reward_hack_audit"
    assert manifest["record_count"] == 16
    assert manifest["pass_count"] == 16
    assert manifest["fail_count"] == 0
    assert (out_dir / "reward_hack_audit_results.jsonl").is_file()
    assert (out_dir / "case_runs").is_dir()
    assert report_path.is_file()
    assert "# Reward-Hack Audit Report" in report_path.read_text()


def test_standalone_audit_clis_use_typed_layer_runners(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: dict[str, tuple[Path, Path, bool]] = {}

    def fake_scorer_runner(
        cases: Path,
        out: Path,
        *,
        overwrite: bool,
    ) -> SimpleNamespace:
        calls["scorer"] = (cases, out, overwrite)
        return SimpleNamespace(
            summary=SimpleNamespace(
                status="PASS",
                record_count=12,
                mismatched_count=0,
                audit_error_count=0,
            )
        )

    def fake_agent_runner(
        cases: Path,
        out: Path,
        *,
        overwrite: bool,
    ) -> SimpleNamespace:
        calls["agent"] = (cases, out, overwrite)
        return SimpleNamespace(
            summary=SimpleNamespace(
                status="PASS",
                record_count=21,
                mismatched_count=0,
                audit_error_count=0,
            )
        )

    monkeypatch.setattr(cli_module, "run_scorer_audit_layer", fake_scorer_runner)
    monkeypatch.setattr(cli_module, "run_agent_task_audit_layer", fake_agent_runner)
    runner = CliRunner()
    scorer_cases = tmp_path / "scorer_cases"
    scorer_out = tmp_path / "scorer_out"
    agent_cases = tmp_path / "agent_cases"
    agent_out = tmp_path / "agent_out"

    scorer_result = runner.invoke(
        app,
        [
            "scorers",
            "audit",
            "--cases",
            str(scorer_cases),
            "--out",
            str(scorer_out),
            "--overwrite",
        ],
    )
    agent_result = runner.invoke(
        app,
        [
            "agents",
            "audit",
            "--cases",
            str(agent_cases),
            "--out",
            str(agent_out),
            "--overwrite",
        ],
    )

    assert scorer_result.exit_code == 0, scorer_result.output
    assert "scorer audit PASS records=12 mismatched=0 errors=0" in (
        scorer_result.output
    )
    assert agent_result.exit_code == 0, agent_result.output
    assert "agent-task audit PASS records=21 mismatched=0 errors=0" in (
        agent_result.output
    )
    assert calls == {
        "scorer": (scorer_cases, scorer_out, True),
        "agent": (agent_cases, agent_out, True),
    }


def test_control_calibration_cli_forwards_public_check_repeats(
    tmp_path: Path,
    monkeypatch,
) -> None:
    call: dict[str, object] = {}
    out_dir = tmp_path / "controls"

    def fake_controls_runner(
        task_pack: Path,
        repeats: int,
        out: Path,
        *,
        public_check_idempotency_repeats: int,
    ) -> SimpleNamespace:
        call.update(
            {
                "task_pack": task_pack,
                "repeats": repeats,
                "out": out,
                "public_check_idempotency_repeats": (public_check_idempotency_repeats),
            }
        )
        return SimpleNamespace(
            records=[],
            overall_match=True,
            flake_detection=SimpleNamespace(status="stable"),
            out_dir=out_dir,
        )

    monkeypatch.setattr(cli_module, "run_controls", fake_controls_runner)
    task_pack = tmp_path / "task-pack"

    result = CliRunner().invoke(
        app,
        [
            "controls",
            "run",
            "--task-pack",
            str(task_pack),
            "--repeats",
            "3",
            "--public-check-idempotency-repeats",
            "4",
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "controls PASS records=0 failed=0 flake=stable" in result.output
    assert call == {
        "task_pack": task_pack,
        "repeats": 3,
        "out": out_dir,
        "public_check_idempotency_repeats": 4,
    }


def test_harness_audit_cli_uses_atomic_composer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    call: dict[str, object] = {}

    def fake_harness_runner(**kwargs: object) -> SimpleNamespace:
        call.update(kwargs)
        return SimpleNamespace(
            manifest=SimpleNamespace(status="PASS"),
            agent_audit=SimpleNamespace(summary=SimpleNamespace(status="PASS")),
            scorer_audit=SimpleNamespace(summary=SimpleNamespace(status="PASS")),
        )

    monkeypatch.setattr(cli_module, "run_harness_audit", fake_harness_runner)
    agent_cases = tmp_path / "agent_cases"
    scorer_cases = tmp_path / "scorer_cases"
    out_dir = tmp_path / "harness_out"

    result = CliRunner().invoke(
        app,
        [
            "harness",
            "audit",
            "--agent-cases",
            str(agent_cases),
            "--scorer-cases",
            str(scorer_cases),
            "--out",
            str(out_dir),
            "--overwrite",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "harness audit PASS agent=PASS scorer=PASS" in result.output
    assert call == {
        "agent_case_root": agent_cases,
        "scorer_case_root": scorer_cases,
        "out_dir": out_dir,
        "overwrite": True,
    }


def test_trajectories_export_cli_writes_eval_suite_export(tmp_path: Path) -> None:
    eval_out = tmp_path / "eval_suite"
    trajectory_out = tmp_path / "trajectory_export"
    runner = CliRunner()
    eval_result = runner.invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--all-policies",
            "--out",
            str(eval_out),
        ],
    )
    assert eval_result.exit_code == 0, eval_result.output

    result = runner.invoke(
        app,
        [
            "trajectories",
            "export",
            "--source",
            str(eval_out),
            "--out",
            str(trajectory_out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "trajectory export complete" in result.output
    assert "source=eval_suite" in result.output
    assert "records=3" in result.output
    manifest = json.loads((trajectory_out / "manifest.json").read_text())
    assert manifest["artifact_type"] == "trajectory_export"
    assert manifest["source_artifact_type"] == "eval_suite"
    assert manifest["source_eval_run_id"] is None
    assert manifest["source_eval_suite_id"].startswith("eval_suite_")
    assert manifest["record_count"] == 3
    assert (trajectory_out / "trajectories.jsonl").is_file()


def test_trajectories_review_init_cli_writes_review_artifact(
    tmp_path: Path,
) -> None:
    eval_out = tmp_path / "eval_run"
    trajectory_out = tmp_path / "trajectory_export"
    review_out = tmp_path / "trajectory_review"
    runner = CliRunner()
    eval_result = runner.invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--policy",
            "oracle",
            "--out",
            str(eval_out),
        ],
    )
    assert eval_result.exit_code == 0, eval_result.output

    export_result = runner.invoke(
        app,
        [
            "trajectories",
            "export",
            "--source",
            str(eval_out),
            "--out",
            str(trajectory_out),
        ],
    )
    assert export_result.exit_code == 0, export_result.output

    result = runner.invoke(
        app,
        [
            "trajectories",
            "review-init",
            "--source",
            str(trajectory_out),
            "--out",
            str(review_out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "trajectory review initialized" in result.output
    assert "source=trajectory_export" in result.output
    assert "records=1" in result.output
    assert "manifest.json" in result.output
    assert "reviews.jsonl" in result.output
    assert "review_queue.md" in result.output
    manifest = json.loads((review_out / "manifest.json").read_text())
    assert manifest["artifact_type"] == "trajectory_review"
    assert manifest["source_artifact_type"] == "trajectory_export"
    assert manifest["source_eval_run_id"].startswith("eval_run_")
    assert manifest["source_eval_suite_id"] is None
    assert manifest["record_count"] == 1
    assert (review_out / "reviews.jsonl").is_file()
    assert (review_out / "review_queue.md").is_file()

    validate_result = runner.invoke(
        app,
        [
            "trajectories",
            "review-validate",
            "--source",
            str(trajectory_out),
            "--reviews",
            str(review_out),
        ],
    )

    assert validate_result.exit_code == 0, validate_result.output
    assert "trajectory review valid" in validate_result.output
    assert "records=1" in validate_result.output
    assert "not_reviewed=1" in validate_result.output
    assert "reviewed=0" in validate_result.output
    assert "accepted=0" in validate_result.output
    assert "rejected=0" in validate_result.output
    assert "needs_followup=0" in validate_result.output

    training_out = tmp_path / "training_candidates"
    training_result = runner.invoke(
        app,
        [
            "training",
            "candidates",
            "export",
            "--trajectories",
            str(trajectory_out),
            "--reviews",
            str(review_out),
            "--out",
            str(training_out),
        ],
    )

    assert training_result.exit_code == 0, training_result.output
    assert "training candidate export complete" in training_result.output
    assert "records=1" in training_result.output
    assert "training_authorization=not_authorized" in training_result.output
    assert "objective_use_eligible=0" in training_result.output
    assert "analysis_only=1" in training_result.output
    assert "fully_ineligible=0" in training_result.output
    assert "positive_sft_review=0" in training_result.output
    assert "negative_examples=0" in training_result.output
    assert "preference_pairing=0" in training_result.output
    assert "manifest.json" in training_result.output
    assert "training_candidates.jsonl" in training_result.output
    training_manifest = json.loads((training_out / "manifest.json").read_text())
    assert training_manifest["artifact_type"] == "training_candidate_export"
    assert training_manifest["record_count"] == 1
    assert training_manifest["any_objective_use_eligible_count"] == 0
    assert training_manifest["analysis_only_count"] == 1
    assert training_manifest["training_authorization"] == "not_authorized"
    assert (training_out / "training_candidates.jsonl").is_file()

    sft_review_out = tmp_path / "positive_sft_review"
    sft_review_result = runner.invoke(
        app,
        [
            "training",
            "positive-sft",
            "review-init",
            "--candidates",
            str(training_out),
            "--out",
            str(sft_review_out),
        ],
    )
    assert sft_review_result.exit_code == 0, sft_review_result.output
    assert "positive SFT review initialized" in sft_review_result.output
    assert "records=0" in sft_review_result.output

    sft_out = tmp_path / "positive_sft"
    sft_result = runner.invoke(
        app,
        [
            "training",
            "positive-sft",
            "export",
            "--candidates",
            str(training_out),
            "--reviews",
            str(sft_review_out),
            "--out",
            str(sft_out),
        ],
    )

    assert sft_result.exit_code == 0, sft_result.output
    assert "positive SFT export complete" in sft_result.output
    assert "training_authorization=not_authorized" in sft_result.output
    assert "records=0" in sft_result.output
    assert "manifest.json" in sft_result.output
    assert "positive_sft_examples.jsonl" in sft_result.output
    sft_manifest = json.loads((sft_out / "manifest.json").read_text())
    assert sft_manifest["artifact_type"] == "positive_sft_export"
    assert sft_manifest["record_count"] == 0
    assert (sft_out / "positive_sft_examples.jsonl").is_file()

    sft_overwrite_result = runner.invoke(
        app,
        [
            "training",
            "positive-sft",
            "export",
            "--candidates",
            str(training_out),
            "--reviews",
            str(sft_review_out),
            "--out",
            str(sft_out),
            "--overwrite",
        ],
    )

    assert sft_overwrite_result.exit_code == 0, sft_overwrite_result.output
    assert "positive SFT export complete" in sft_overwrite_result.output
    assert "records=0" in sft_overwrite_result.output


def _write_eval_hash_manifest(
    path: Path,
    *,
    artifact_type: str,
    artifact_schema_version: str,
    selected_task_hash_set: str,
    task_record_hash: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    task_hashes = {
        "schema_version": "eval_task_hashes_v0",
        "task_pack_id": "repo_patch_python_v0",
        "selected_task_hash_set": selected_task_hash_set,
        "selected_tasks": [
            {
                "task_id": "toy_python_fix_001",
                "split": "practice",
                "task_record_hash": task_record_hash,
                "task_yaml_hash": "xxh64:task-yaml",
                "required_task_files_hash": "xxh64:required-files",
                "full_task_dir_hash": "xxh64:full-task-dir",
                "required_task_files": [
                    {
                        "path": "task.yaml",
                        "kind": "file",
                        "hash": "xxh64:task-yaml",
                    }
                ],
            }
        ],
    }
    payload = (
        _eval_hash_run_manifest(
            artifact_schema_version=artifact_schema_version,
            task_hashes=task_hashes,
        )
        if artifact_type == "eval_run"
        else _eval_hash_suite_manifest(
            artifact_schema_version=artifact_schema_version,
            task_hashes=task_hashes,
        )
    )
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _eval_hash_run_manifest(
    *,
    artifact_schema_version: str,
    task_hashes: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_type": "eval_run",
        "artifact_schema_version": artifact_schema_version,
        "eval_run_id": "eval_run_test",
        "created_at": "2026-06-30T00:00:00Z",
        "config_path": "configs/eval/test.yaml",
        "config_hash": "xxh64:config",
        "config_name": "test",
        "task_pack": "data/task_packs/repo_patch_python_v0",
        "split": "practice",
        "task_hashes": task_hashes,
        "runtime_provenance": _runtime_provenance(),
        "policy": "oracle",
        "policy_type": "scorer_control_patch",
        "policy_family": "control",
        "control_layer": "scorer",
        "control_name": "oracle",
        "attempts_per_task": 1,
        "replay_repeats": 0,
        "attempt_count": 1,
        "layer_counts": _eval_hash_layer_counts(),
        "artifacts": {"trace": "trace.jsonl", "attempts": "attempts"},
        "attempts": [_eval_hash_attempt_record()],
    }


def _eval_hash_suite_manifest(
    *,
    artifact_schema_version: str,
    task_hashes: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_type": "eval_suite",
        "artifact_schema_version": artifact_schema_version,
        "eval_suite_id": "eval_suite_test",
        "created_at": "2026-06-30T00:00:00Z",
        "config_path": "configs/eval/test.yaml",
        "config_hash": "xxh64:config",
        "config_name": "test",
        "task_pack": "data/task_packs/repo_patch_python_v0",
        "split": "practice",
        "task_hashes": task_hashes,
        "runtime_provenance": _runtime_provenance(),
        "tasks": ["toy_python_fix_001"],
        "task_count": 1,
        "policy_count": 1,
        "attempt_count": 1,
        "layer_counts": _eval_hash_layer_counts(),
        "artifacts": {"policies": "policies"},
        "policy_runs": [
            {
                "policy": "oracle",
                "policy_type": "scorer_control_patch",
                "policy_family": "control",
                "control_layer": "scorer",
                "control_name": "oracle",
                "attempts_per_task": 1,
                "replay_repeats": 0,
                "eval_run_id": "eval_run_test",
                "artifact_dir": "policies/oracle",
                "manifest": "policies/oracle/manifest.json",
                "attempt_count": 1,
                "layer_counts": _eval_hash_layer_counts(),
            }
        ],
        "replay_run_count": 0,
        "replay_policy_count": 0,
        "replay_run_success_summary": "0/0",
        "replay_runs": [],
    }


def _runtime_provenance() -> dict[str, object]:
    harness_source_hash = "xxh64:aaaaaaaaaaaaaaaa"
    pyproject_hash = "xxh64:bbbbbbbbbbbbbbbb"
    uv_lock_hash = "xxh64:cccccccccccccccc"
    runtime_hash = derive_harness_runtime_hash(
        harness_source_hash=harness_source_hash,
        root_pyproject_hash=pyproject_hash,
        root_uv_lock_hash=uv_lock_hash,
        python_implementation="cpython",
        python_version="3.11.14",
        sys_platform="linux",
        platform_machine="x86_64",
    )
    return {
        "schema_version": HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
        "harness_source_root": "src/agentenv",
        "harness_source_hash": harness_source_hash,
        "root_pyproject_path": "pyproject.toml",
        "root_pyproject_hash": pyproject_hash,
        "root_uv_lock_path": "uv.lock",
        "root_uv_lock_hash": uv_lock_hash,
        "python_implementation": "cpython",
        "python_version": "3.11.14",
        "sys_platform": "linux",
        "platform_machine": "x86_64",
        "harness_runtime_hash": runtime_hash,
    }


def _eval_hash_attempt_record() -> dict[str, object]:
    return {
        "eval_attempt_id": "eval_attempt_test",
        "task_id": "toy_python_fix_001",
        "attempt_index": 0,
        "artifact_dir": "attempts/toy_python_fix_001__attempt_001",
        "artifact_type": "scorer_attempt",
        "artifact_schema_version": "scorer_attempt_artifact_v0",
        "scorer": {
            "scorer_attempt_id": "scorer_attempt_test",
            "status": "PASS",
            "public_status": "PASS",
            "hidden_status": "PASS",
            "error_class": None,
            "final_diff_hash": "xxh64:final-diff",
            "duration_ms": 0,
        },
        "agent": None,
    }


def _eval_hash_layer_counts() -> dict[str, dict[str, int]]:
    return {
        "scorer_status": {"PASS": 1},
        "scorer_public_status": {"PASS": 1},
        "scorer_hidden_status": {"PASS": 1},
    }
