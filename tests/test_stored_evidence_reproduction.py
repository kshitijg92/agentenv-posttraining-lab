from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
from typer.testing import CliRunner

import agentenv.cli as cli_module
import agentenv.reproduction.stored_evidence as stored_evidence_module
from agentenv.cli import app
from agentenv.hashing import hash_file
from agentenv.reproduction.stored_evidence import (
    StoredEvidenceCheck,
    StoredEvidenceVerification,
    VerificationStatus,
    render_stored_evidence_verification,
    verify_stored_evidence,
)


CANONICAL_PLAN = Path("configs/reproduction/posttraining_result.yaml")
CANONICAL_EVIDENCE_MANIFEST = Path(
    "experiments/models/week_10_positive_sft_raw_lora/manifest.json"
)


@pytest.mark.skipif(
    not CANONICAL_EVIDENCE_MANIFEST.is_file(),
    reason="local canonical stored-evidence graph is unavailable",
)
def test_designated_stored_evidence_verifies(tmp_path: Path) -> None:
    verification = verify_stored_evidence(
        CANONICAL_PLAN,
        tmp_path / "verification",
    )

    assert verification.status == "PASS"
    assert len(verification.checks) == 11
    assert all(check.status == "PASS" for check in verification.checks)
    assert (
        tmp_path
        / "verification/reports/positive_sft_policy_selection.md"
    ).is_file()
    assert (
        tmp_path
        / "verification/reports/exploratory_dpo_policy_selection.md"
    ).is_file()
    summary = render_stored_evidence_verification(verification)
    assert "- Overall: PASS" in summary
    assert "cells=24; decision=abstained; branch=complete_tie" in summary
    assert "cells=18; decision=abstained; branch=complete_tie" in summary


@pytest.mark.parametrize(
    ("regenerated_report", "expected_status"),
    (("canonical report\n", "PASS"), ("renderer drift\n", "FAIL")),
)
def test_stored_evidence_verification_enforces_report_byte_equality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    regenerated_report: str,
    expected_status: str,
) -> None:
    repo_root = tmp_path / "repo"
    plan_path = repo_root / "configs/reproduction/posttraining_result.yaml"
    task_pack = repo_root / "data/task_pack"
    training_dir = repo_root / "experiments/models/positive_sft"
    suite_dir = repo_root / "experiments/runs/policy_selection"
    canonical_report = repo_root / "experiments/reports/policy_selection.md"
    for directory in (
        plan_path.parent,
        task_pack,
        training_dir,
        suite_dir,
        canonical_report.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    (training_dir / "manifest.json").write_text("training manifest\n")
    (suite_dir / "manifest.json").write_text("suite manifest\n")
    canonical_report.write_text("canonical report\n")
    plan_path.write_text(
        "\n".join(
            (
                "name: posttraining_result",
                "task_pack: data/task_pack",
                "training_artifacts:",
                "  - name: positive_sft",
                "    kind: positive_sft_lora",
                "    artifact_dir: experiments/models/positive_sft",
                "    expected_manifest_hash: "
                f"{hash_file(training_dir / 'manifest.json')}",
                "comparisons:",
                "  - name: policy_selection",
                "    eval_suite_dir: experiments/runs/policy_selection",
                "    expected_suite_manifest_hash: "
                f"{hash_file(suite_dir / 'manifest.json')}",
                "    canonical_report: experiments/reports/policy_selection.md",
                f"    expected_report_hash: {hash_file(canonical_report)}",
                "    expected_selection:",
                "      status: abstained",
                "      branch: complete_tie",
                "      selected_policy: null",
                "",
            )
        )
    )

    monkeypatch.setattr(
        stored_evidence_module,
        "validate_task_pack",
        lambda path: SimpleNamespace(task_pack_id="task_pack", task_count=1),
    )
    monkeypatch.setattr(
        stored_evidence_module,
        "load_task_pack_manifest",
        lambda path: SimpleNamespace(split_lock="splits.lock.json"),
    )
    monkeypatch.setattr(
        stored_evidence_module,
        "check_splits_lock",
        lambda path: SimpleNamespace(
            task_pack_id="task_pack",
            task_count=1,
            split_counts={"practice": 1},
        ),
    )
    monkeypatch.setattr(
        stored_evidence_module,
        "load_positive_sft_lora_training_artifact",
        lambda path: SimpleNamespace(
            result=SimpleNamespace(status="completed", completed_step_count=1)
        ),
    )
    monkeypatch.setattr(
        stored_evidence_module,
        "load_positive_sft_lora_training_task_ids",
        lambda path: frozenset({"task_a"}),
    )
    monkeypatch.setattr(
        stored_evidence_module,
        "build_policy_selection_analysis_from_eval_suite",
        lambda path: SimpleNamespace(
            cells=(object(), object()),
            decision=SimpleNamespace(
                status="abstained",
                branch="complete_tie",
                selected_policy=None,
            ),
        ),
    )

    def write_report(artifact_dir: Path, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(regenerated_report)
        return out_path

    monkeypatch.setattr(
        stored_evidence_module,
        "write_markdown_report",
        write_report,
    )

    verification = verify_stored_evidence(
        plan_path,
        tmp_path / f"verification-{expected_status.lower()}",
        repo_root=repo_root,
    )

    assert verification.status == expected_status
    report_check = next(
        check
        for check in verification.checks
        if check.check_id == "comparison.policy_selection.regenerated_report"
    )
    assert report_check.status == expected_status
    if expected_status == "FAIL":
        assert "differs from canonical report" in report_check.detail


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    (("PASS", 0), ("FAIL", 1)),
)
def test_stored_evidence_cli_writes_summary_and_uses_status_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: VerificationStatus,
    expected_exit: Literal[0, 1],
) -> None:
    out_dir = tmp_path / f"cli-{status.lower()}"

    def fake_verify(plan: Path, out: Path) -> StoredEvidenceVerification:
        assert plan == CANONICAL_PLAN
        assert out == out_dir
        out.mkdir(parents=True)
        return StoredEvidenceVerification(
            plan_name="posttraining_result",
            plan_hash="xxh64:aaaaaaaaaaaaaaaa",
            out_dir=out,
            checks=(
                StoredEvidenceCheck(
                    check_id="task_pack.structure",
                    status=status,
                    detail=("tasks=1" if status == "PASS" else "missing task pack"),
                ),
            ),
        )

    monkeypatch.setattr(cli_module, "verify_stored_evidence", fake_verify)

    result = CliRunner().invoke(
        app,
        ["reproduce", "stored-evidence", "--out", str(out_dir)],
    )

    assert result.exit_code == expected_exit, result.output
    assert f"{status} stored-evidence checks=" in result.output
    summary_path = out_dir / "stored_evidence_verification.md"
    assert summary_path.is_file()
    assert f"- Overall: {status}" in summary_path.read_text()
