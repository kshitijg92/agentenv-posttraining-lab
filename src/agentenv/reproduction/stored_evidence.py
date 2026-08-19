from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import (
    prepare_artifact_output_dir,
    resolve_relative_artifact_ref,
)
from agentenv.hashing import hash_file
from agentenv.reporting.markdown import write_markdown_report
from agentenv.reporting.policy_selection import (
    PolicySelectionAnalysis,
    build_policy_selection_analysis_from_eval_suite,
)
from agentenv.reproduction.schema import (
    StoredComparisonSpec,
    StoredEvidencePlan,
    StoredTrainingArtifactSpec,
    load_stored_evidence_plan,
)
from agentenv.tasks.splits import check_splits_lock
from agentenv.tasks.validate import load_task_pack_manifest, validate_task_pack
from agentenv.training.positive_sft.lora.workflow import (
    load_positive_sft_lora_training_artifact,
    load_positive_sft_lora_training_task_ids,
)
from agentenv.training.preferences.dpo.workflow import (
    load_dpo_lora_training_artifact,
    load_dpo_lora_training_task_ids,
)


VerificationStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class StoredEvidenceCheck:
    check_id: str
    status: VerificationStatus
    detail: str


@dataclass(frozen=True)
class StoredEvidenceVerification:
    plan_name: str
    plan_hash: str
    out_dir: Path
    checks: tuple[StoredEvidenceCheck, ...]

    @property
    def status(self) -> VerificationStatus:
        if all(check.status == "PASS" for check in self.checks):
            return "PASS"
        return "FAIL"


def verify_stored_evidence(
    plan_path: Path,
    out_dir: Path,
    *,
    repo_root: Path = Path("."),
) -> StoredEvidenceVerification:
    """Validate designated stored evidence and regenerate canonical reports."""

    repo_root = repo_root.resolve()
    plan_path = _resolve_input_path(repo_root, plan_path)
    plan = load_stored_evidence_plan(plan_path)
    out_dir = prepare_artifact_output_dir(out_dir)

    checks = [
        _capture_check(
            "task_pack.structure",
            lambda: _validate_task_pack(repo_root, plan),
        ),
        _capture_check(
            "task_pack.splits",
            lambda: _validate_splits(repo_root, plan),
        ),
    ]
    checks.extend(
        _capture_check(
            f"training.{artifact.name}",
            lambda artifact=artifact: _validate_training_artifact(
                repo_root,
                artifact,
            ),
        )
        for artifact in plan.training_artifacts
    )
    for comparison in plan.comparisons:
        checks.extend(
            (
                _capture_check(
                    f"comparison.{comparison.name}.evidence",
                    lambda comparison=comparison: _validate_comparison_evidence(
                        repo_root,
                        comparison,
                    ),
                ),
                _capture_check(
                    f"comparison.{comparison.name}.canonical_report",
                    lambda comparison=comparison: _validate_canonical_report(
                        repo_root,
                        comparison,
                    ),
                ),
                _capture_check(
                    f"comparison.{comparison.name}.regenerated_report",
                    lambda comparison=comparison: _regenerate_and_compare_report(
                        repo_root,
                        out_dir,
                        comparison,
                    ),
                ),
            )
        )

    return StoredEvidenceVerification(
        plan_name=plan.name,
        plan_hash=hash_file(plan_path),
        out_dir=out_dir,
        checks=tuple(checks),
    )


def render_stored_evidence_verification(
    verification: StoredEvidenceVerification,
) -> str:
    lines = [
        "# Stored Evidence Verification",
        "",
        f"- Plan: {verification.plan_name}",
        f"- Plan hash: {verification.plan_hash}",
        f"- Overall: {verification.status}",
        "",
        "| check | status | detail |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {check.check_id} | {check.status} | {_markdown_cell(check.detail)} |"
        for check in verification.checks
    )
    return "\n".join(lines) + "\n"


def _capture_check(check_id: str, operation: Callable[[], str]) -> StoredEvidenceCheck:
    try:
        detail = operation()
    except (OSError, ValueError) as exc:
        return StoredEvidenceCheck(
            check_id=check_id,
            status="FAIL",
            detail=f"{type(exc).__name__}: {exc}",
        )
    return StoredEvidenceCheck(check_id=check_id, status="PASS", detail=detail)


def _validate_task_pack(repo_root: Path, plan: StoredEvidencePlan) -> str:
    result = validate_task_pack(_repo_path(repo_root, plan.task_pack))
    return f"task_pack={result.task_pack_id}; tasks={result.task_count}"


def _validate_splits(repo_root: Path, plan: StoredEvidencePlan) -> str:
    task_pack_dir = _repo_path(repo_root, plan.task_pack)
    pack_manifest = load_task_pack_manifest(task_pack_dir / "manifest.yaml")
    split_lock_path = resolve_relative_artifact_ref(
        task_pack_dir,
        pack_manifest.split_lock,
    )
    result = check_splits_lock(split_lock_path)
    counts = ",".join(
        f"{split}={count}" for split, count in sorted(result.split_counts.items())
    )
    return f"task_pack={result.task_pack_id}; tasks={result.task_count}; {counts}"


def _validate_training_artifact(
    repo_root: Path,
    spec: StoredTrainingArtifactSpec,
) -> str:
    artifact_dir = _repo_path(repo_root, spec.artifact_dir)
    _require_hash(
        artifact_dir / MANIFEST_FILENAME,
        spec.expected_manifest_hash,
        label=f"training artifact {spec.name} manifest",
    )

    if spec.kind == "positive_sft_lora":
        artifact = load_positive_sft_lora_training_artifact(artifact_dir)
        if artifact.result.status != "completed":
            raise ValueError(f"training artifact {spec.name} is not completed")
        task_ids = load_positive_sft_lora_training_task_ids(artifact_dir)
        completed_steps = artifact.result.completed_step_count
    else:
        artifact = load_dpo_lora_training_artifact(artifact_dir)
        task_ids = load_dpo_lora_training_task_ids(artifact_dir)
        completed_steps = artifact.result.completed_step_count

    return (
        f"manifest_hash={spec.expected_manifest_hash}; status=completed; "
        f"steps={completed_steps}; training_tasks={len(task_ids)}"
    )


def _validate_comparison_evidence(
    repo_root: Path,
    spec: StoredComparisonSpec,
) -> str:
    eval_suite_dir = _repo_path(repo_root, spec.eval_suite_dir)
    _require_hash(
        eval_suite_dir / MANIFEST_FILENAME,
        spec.expected_suite_manifest_hash,
        label=f"comparison {spec.name} suite manifest",
    )
    analysis = build_policy_selection_analysis_from_eval_suite(eval_suite_dir)
    _require_expected_selection(spec, analysis)
    return (
        f"suite_manifest_hash={spec.expected_suite_manifest_hash}; "
        f"cells={len(analysis.cells)}; decision={analysis.decision.status}; "
        f"branch={analysis.decision.branch}; "
        f"selected_policy={analysis.decision.selected_policy or 'none'}"
    )


def _validate_canonical_report(
    repo_root: Path,
    spec: StoredComparisonSpec,
) -> str:
    canonical_report = _repo_path(repo_root, spec.canonical_report)
    _require_hash(
        canonical_report,
        spec.expected_report_hash,
        label=f"comparison {spec.name} canonical report",
    )
    return f"report_hash={spec.expected_report_hash}"


def _regenerate_and_compare_report(
    repo_root: Path,
    out_dir: Path,
    spec: StoredComparisonSpec,
) -> str:
    eval_suite_dir = _repo_path(repo_root, spec.eval_suite_dir)
    canonical_report = _repo_path(repo_root, spec.canonical_report)
    regenerated_report = out_dir / "reports" / f"{spec.name}.md"
    write_markdown_report(eval_suite_dir, regenerated_report)
    if regenerated_report.read_bytes() != canonical_report.read_bytes():
        raise ValueError(
            f"regenerated report differs from canonical report for {spec.name}"
        )
    return f"byte_match=true; output={regenerated_report.relative_to(out_dir)}"


def _require_expected_selection(
    spec: StoredComparisonSpec,
    analysis: PolicySelectionAnalysis,
) -> None:
    expected = spec.expected_selection
    decision = analysis.decision
    observed = (decision.status, decision.branch, decision.selected_policy)
    declared = (expected.status, expected.branch, expected.selected_policy)
    if observed != declared:
        raise ValueError(
            f"comparison {spec.name} decision mismatch: "
            f"observed={observed!r} expected={declared!r}"
        )


def _require_hash(path: Path, expected_hash: str, *, label: str) -> None:
    observed_hash = hash_file(path)
    if observed_hash != expected_hash:
        raise ValueError(
            f"{label} hash mismatch: {observed_hash!r} != {expected_hash!r}"
        )


def _resolve_input_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _repo_path(repo_root: Path, relative_path: str) -> Path:
    return resolve_relative_artifact_ref(repo_root, relative_path)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
