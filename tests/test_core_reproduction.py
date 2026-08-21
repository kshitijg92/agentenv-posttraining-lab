import os
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
from typer.testing import CliRunner

import agentenv.cli as cli_module
import agentenv.reproduction.core as core_module
from agentenv.audits.schema import (
    HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
    HarnessRuntimeProvenance,
    derive_harness_runtime_hash,
)
from agentenv.cli import app
from agentenv.reproduction.core import (
    CanonicalArtifactIdentity,
    CoreReproductionCheck,
    CoreReproductionResult,
    run_core_reproduction,
)
from agentenv.reproduction.deterministic_suite import (
    EvalSuiteOperationalCheck,
    EvalSuiteOperationalVerification,
)
from agentenv.reproduction.schema import StoredEvidencePlan
from agentenv.reproduction.stored_evidence import (
    StoredEvidenceCheck,
    StoredEvidenceVerification,
)


@pytest.mark.parametrize("stored_status", ("PASS", "FAIL"))
def test_core_reproduction_composes_required_levels_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stored_status: Literal["PASS", "FAIL"],
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    out_dir = tmp_path / f"core-{stored_status.lower()}"
    plan = _plan()
    config = SimpleNamespace(name="deterministic_controls")
    monkeypatch.delenv("UV_OFFLINE", raising=False)

    monkeypatch.setattr(core_module, "load_stored_evidence_plan", lambda path: plan)
    monkeypatch.setattr(core_module, "load_eval_config", lambda path: config)
    monkeypatch.setattr(
        core_module,
        "capture_harness_runtime_provenance",
        lambda root: _runtime(),
    )
    monkeypatch.setattr(core_module, "git_sha_or_unknown", lambda root: "abc123")
    monkeypatch.setattr(
        core_module,
        "git_worktree_state",
        lambda root: (False, "xxh64:9999999999999999"),
    )

    def verify_stored(
        plan_path: Path,
        stored_out: Path,
        *,
        repo_root: Path,
    ) -> StoredEvidenceVerification:
        stored_out.mkdir(parents=True)
        return StoredEvidenceVerification(
            plan_name=plan.name,
            plan_hash="xxh64:aaaaaaaaaaaaaaaa",
            out_dir=stored_out,
            checks=(
                StoredEvidenceCheck(
                    check_id="stored.graph",
                    status=stored_status,
                    detail="canonical graph",
                ),
            ),
        )

    monkeypatch.setattr(core_module, "verify_stored_evidence", verify_stored)

    def run_eval(config_path: Path, eval_out: Path) -> SimpleNamespace:
        assert os.environ["UV_OFFLINE"] == "1"
        eval_out.mkdir(parents=True)
        return SimpleNamespace(
            eval_suite_id="eval_suite_test",
            out_dir=eval_out,
            config=config,
            policy_runs=(SimpleNamespace(attempts=(object(),)),),
            replay_runs=(object(),),
        )

    monkeypatch.setattr(core_module, "run_eval_config_all_policies", run_eval)
    monkeypatch.setattr(
        core_module,
        "requires_operational_verification",
        lambda observed_config: True,
    )
    monkeypatch.setattr(
        core_module,
        "verify_eval_suite_operational_expectations",
        lambda eval_out: EvalSuiteOperationalVerification(
            eval_suite_id="eval_suite_test",
            checks=(
                EvalSuiteOperationalCheck(
                    check_id="control.oracle",
                    status="PASS",
                    detail="observed expected outcome",
                ),
            ),
        ),
    )

    def write_report(artifact_dir: Path, out_path: Path) -> Path:
        out_path.write_text("deterministic report\n")
        return out_path

    monkeypatch.setattr(core_module, "write_markdown_report", write_report)

    result = run_core_reproduction(
        out_dir,
        repo_root=repo_root,
    )

    assert result.status == stored_status
    assert "UV_OFFLINE" not in os.environ
    assert result.level_status(1) == stored_status
    assert result.level_status(2) == "PASS"
    assert len(result.checks) == 4
    report = result.report_path.read_text()
    assert f"- Overall: {stored_status}" in report
    assert "| 3 | Live model inference | SKIP |" in report
    assert "Failure injection is not rerun by this command" in report
    assert (out_dir / "stored_evidence/stored_evidence_verification.md").is_file()
    assert (out_dir / "eval_report.md").read_bytes() == (
        out_dir / "eval_report_regenerated.md"
    ).read_bytes()


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    (("PASS", 0), ("FAIL", 1)),
)
def test_core_reproduction_cli_uses_combined_status_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: Literal["PASS", "FAIL"],
    expected_exit: Literal[0, 1],
) -> None:
    out_dir = tmp_path / status.lower()
    result = _result(out_dir, status)
    monkeypatch.setattr(cli_module, "run_core_reproduction", lambda *args, **kwargs: result)

    invocation = CliRunner().invoke(
        app,
        ["reproduce", "core", "--out", str(out_dir)],
    )

    assert invocation.exit_code == expected_exit, invocation.output
    assert f"{status} core reproduction checks=" in invocation.output
    assert str(result.report_path) in invocation.output


def _plan() -> StoredEvidencePlan:
    return StoredEvidencePlan.model_validate(
        {
            "name": "canonical_result",
            "task_pack": "data/task_pack",
            "training_artifacts": [
                {
                    "name": "sft",
                    "kind": "positive_sft_lora",
                    "artifact_dir": "experiments/models/sft",
                    "expected_manifest_hash": "xxh64:1111111111111111",
                }
            ],
            "comparisons": [
                {
                    "name": "selection",
                    "eval_suite_dir": "experiments/runs/selection",
                    "expected_suite_manifest_hash": "xxh64:2222222222222222",
                    "canonical_report": "experiments/reports/selection.md",
                    "expected_report_hash": "xxh64:3333333333333333",
                    "expected_selection": {
                        "status": "abstained",
                        "branch": "complete_tie",
                        "selected_policy": None,
                    },
                }
            ],
        }
    )


def _runtime() -> HarnessRuntimeProvenance:
    harness_source_hash = "xxh64:1111111111111111"
    pyproject_hash = "xxh64:2222222222222222"
    lock_hash = "xxh64:3333333333333333"
    return HarnessRuntimeProvenance(
        schema_version=HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
        harness_source_root="src/agentenv",
        harness_source_hash=harness_source_hash,
        root_pyproject_path="pyproject.toml",
        root_pyproject_hash=pyproject_hash,
        root_uv_lock_path="uv.lock",
        root_uv_lock_hash=lock_hash,
        python_implementation="cpython",
        python_version="3.11.14",
        sys_platform="linux",
        platform_machine="x86_64",
        harness_runtime_hash=derive_harness_runtime_hash(
            harness_source_hash=harness_source_hash,
            root_pyproject_hash=pyproject_hash,
            root_uv_lock_hash=lock_hash,
            python_implementation="cpython",
            python_version="3.11.14",
            sys_platform="linux",
            platform_machine="x86_64",
        ),
    )


def _result(
    out_dir: Path,
    status: Literal["PASS", "FAIL"],
) -> CoreReproductionResult:
    return CoreReproductionResult(
        out_dir=out_dir,
        command="uv run --offline --frozen agentenv reproduce core --out output",
        plan_name="canonical_result",
        plan_hash="xxh64:aaaaaaaaaaaaaaaa",
        git_sha="abc123",
        git_worktree_dirty=False,
        git_diff_hash="xxh64:9999999999999999",
        runtime_provenance=_runtime(),
        checks=(
            CoreReproductionCheck(
                level=1,
                check_id="stored.graph",
                status=status,
                detail="canonical graph",
            ),
        ),
        canonical_artifacts=(
            CanonicalArtifactIdentity(
                kind="eval_suite",
                name="selection",
                path="experiments/runs/selection/manifest.json",
                expected_hash="xxh64:2222222222222222",
            ),
        ),
        portability_blockers=(),
    )
