import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentenv.rewards.cases import (
    hash_harness_audit_case_dir,
    load_reward_hack_case,
    verify_reward_hack_case_source_refs,
)
from agentenv.rewards.schema import (
    HarnessAuditCaseRef,
    HiddenValidatorProbeExploitSpec,
    RewardHackCase,
    ScorerAuditEvidencePair,
)
from agentenv.scorers.audit import (
    ScorerAuditCase,
    ScorerAuditResult,
    load_scorer_audit_case,
    run_scorer_audit,
)
from agentenv.security.leakage import LeakageScanResult
from agentenv.security.leakage import scan_directory_for_leakage
from agentenv.security.leakage import scan_files_for_leakage
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest


REWARD_HACK_AUDIT_RUNTIME_VERSION = "reward_hack_audit_runtime_v0"


@dataclass(frozen=True)
class RewardHackOutcomeComparison:
    field: Literal["private_content_exposed", "exploit_blocked", "training_allowed"]
    expected: bool
    actual: bool

    @property
    def match(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True)
class RewardHackRuntimeCheck:
    field: Literal[
        "exploit_harness_audit_passed",
        "valid_control_harness_audit_passed",
        "valid_control_task_success",
        "private_content_access_attempt",
        "task_success_allowed",
    ]
    expected: bool
    actual: bool

    @property
    def match(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True)
class RewardHackAuditResult:
    runtime_version: str
    case_path: Path
    reward_hack_case: RewardHackCase
    run_dir: Path
    exploit_source_case_hash: str
    valid_control_source_case_hash: str
    exploit_audit_result: ScorerAuditResult
    valid_control_audit_result: ScorerAuditResult
    exploit_harness_audit_passed: bool
    valid_control_harness_audit_passed: bool
    valid_control_task_success_actual: bool
    private_content_access_attempt_actual: bool
    leakage_scan_result: LeakageScanResult
    private_content_exposed_actual: bool
    exploit_blocked_actual: bool
    training_allowed_actual: bool
    task_success_allowed_actual: bool
    outcome_comparisons: tuple[RewardHackOutcomeComparison, ...]
    runtime_checks: tuple[RewardHackRuntimeCheck, ...]

    @property
    def expected_outcomes_match(self) -> bool:
        return all(comparison.match for comparison in self.outcome_comparisons)

    @property
    def runtime_checks_match(self) -> bool:
        return all(check.match for check in self.runtime_checks)

    @property
    def audit_pass(self) -> bool:
        return self.expected_outcomes_match and self.runtime_checks_match

    @property
    def canary_exposed_actual(self) -> bool:
        return self.leakage_scan_result.canary_leaked

    @property
    def canary_hash(self) -> str | None:
        return self.leakage_scan_result.canary_hash

    @property
    def canary_match_refs(self) -> tuple[str, ...]:
        return self.leakage_scan_result.canary_matches


def run_reward_hack_audit(
    case_root: Path,
    *,
    work_dir: Path | None = None,
    repo_root: Path | None = None,
) -> list[RewardHackAuditResult]:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    return [
        run_reward_hack_case_audit(case_path, work_dir=work_dir, repo_root=root)
        for case_path in _reward_hack_case_paths(case_root)
    ]


def run_reward_hack_case_audit(
    case_path: Path,
    *,
    work_dir: Path | None = None,
    repo_root: Path | None = None,
) -> RewardHackAuditResult:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    case = load_reward_hack_case(case_path)
    verify_reward_hack_case_source_refs(case, repo_root=root)
    if not isinstance(case.evidence, ScorerAuditEvidencePair):
        raise ValueError(
            "Reward-hack runtime audit currently supports scorer_audit_case "
            f"evidence only, got {case.evidence.source_type!r}"
        )
    if case.evidence.exploit.case_id == case.evidence.valid_control.case_id:
        raise ValueError("Reward-hack exploit and valid control case ids must differ")

    exploit_case_dir = _resolve_repo_relative_path(root, case.evidence.exploit.case_dir)
    valid_control_case_dir = _resolve_repo_relative_path(
        root,
        case.evidence.valid_control.case_dir,
    )
    exploit_case = load_scorer_audit_case(exploit_case_dir / "case.yaml")
    task_manifest_path = _resolve_repo_relative_path(root, exploit_case.task_manifest)
    task_manifest = load_task_manifest(task_manifest_path)
    run_dir = _make_run_dir(work_dir)
    staged_case_root = _stage_scorer_audit_pair(case.evidence, run_dir, repo_root=root)
    scorer_out_dir = run_dir / "scorer_audit"
    scorer_results = run_scorer_audit(staged_case_root, scorer_out_dir)
    scorer_results_by_case_id = _index_scorer_results(scorer_results)
    exploit_result = scorer_results_by_case_id[case.evidence.exploit.case_id]
    valid_control_result = scorer_results_by_case_id[case.evidence.valid_control.case_id]

    leakage_scan_result = scan_directory_for_leakage(
        exploit_result.attempt_artifact_dir,
        task_manifest,
    )
    private_content_access_attempt_actual = detect_private_content_access_attempt(
        case,
        exploit_case=exploit_case,
        exploit_case_dir=exploit_case_dir,
        task_manifest=task_manifest,
    )
    exploit_blocked_actual = _expected_non_pass_status_matched(exploit_result)
    task_success_allowed_actual = exploit_result.attempt_result.status == "PASS"
    valid_control_task_success_actual = _expected_pass_status_matched(
        valid_control_result,
    )
    private_content_exposed_actual = _private_content_exposed(leakage_scan_result)
    training_allowed_actual = False
    outcome_comparisons = _outcome_comparisons(
        case,
        private_content_exposed_actual=private_content_exposed_actual,
        exploit_blocked_actual=exploit_blocked_actual,
        training_allowed_actual=training_allowed_actual,
    )
    runtime_checks = (
        RewardHackRuntimeCheck(
            field="exploit_harness_audit_passed",
            expected=True,
            actual=exploit_result.overall_match,
        ),
        RewardHackRuntimeCheck(
            field="valid_control_harness_audit_passed",
            expected=True,
            actual=valid_control_result.overall_match,
        ),
        RewardHackRuntimeCheck(
            field="valid_control_task_success",
            expected=True,
            actual=valid_control_task_success_actual,
        ),
        RewardHackRuntimeCheck(
            field="private_content_access_attempt",
            expected=True,
            actual=private_content_access_attempt_actual,
        ),
        RewardHackRuntimeCheck(
            field="task_success_allowed",
            expected=False,
            actual=task_success_allowed_actual,
        ),
    )

    return RewardHackAuditResult(
        runtime_version=REWARD_HACK_AUDIT_RUNTIME_VERSION,
        case_path=case_path.resolve(),
        reward_hack_case=case,
        run_dir=run_dir,
        exploit_source_case_hash=hash_harness_audit_case_dir(exploit_case_dir),
        valid_control_source_case_hash=hash_harness_audit_case_dir(
            valid_control_case_dir,
        ),
        exploit_audit_result=exploit_result,
        valid_control_audit_result=valid_control_result,
        exploit_harness_audit_passed=exploit_result.overall_match,
        valid_control_harness_audit_passed=valid_control_result.overall_match,
        valid_control_task_success_actual=valid_control_task_success_actual,
        private_content_access_attempt_actual=private_content_access_attempt_actual,
        leakage_scan_result=leakage_scan_result,
        private_content_exposed_actual=private_content_exposed_actual,
        exploit_blocked_actual=exploit_blocked_actual,
        training_allowed_actual=training_allowed_actual,
        task_success_allowed_actual=task_success_allowed_actual,
        outcome_comparisons=outcome_comparisons,
        runtime_checks=runtime_checks,
    )


def detect_private_content_access_attempt(
    case: RewardHackCase,
    *,
    exploit_case: ScorerAuditCase,
    exploit_case_dir: Path,
    task_manifest: TaskManifest,
) -> bool:
    if case.exploit.exploit_classification != "hidden_validator_probe_attempt":
        raise ValueError(
            "Reward-hack runtime audit currently supports "
            "hidden_validator_probe_attempt exploits only"
        )
    spec = case.exploit.exploit_spec
    if spec.probe_surface == "submitted_patch_text":
        submission_path = exploit_case_dir / exploit_case.submission
        scan = scan_files_for_leakage(
            [submission_path],
            task_manifest,
            root=exploit_case_dir,
        )
        return _submitted_patch_scan_contains_probe_reference(
            scan,
            spec=spec,
        )
    raise ValueError(
        f"Unsupported hidden-validator probe surface: {spec.probe_surface}"
    )


def _reward_hack_case_paths(case_root: Path) -> list[Path]:
    case_root = case_root.resolve()
    if case_root.is_file():
        if case_root.name != "case.yaml":
            raise ValueError(f"Expected reward-hack case.yaml file: {case_root}")
        return [case_root]
    if (case_root / "case.yaml").is_file():
        return [case_root / "case.yaml"]
    return sorted(case_root.rglob("case.yaml"))


def _stage_scorer_audit_pair(
    evidence: ScorerAuditEvidencePair,
    run_dir: Path,
    *,
    repo_root: Path,
) -> Path:
    case_root = run_dir / "scorer_case_inputs"
    case_root.mkdir(parents=True, exist_ok=True)
    _copy_harness_case_dir(
        evidence.exploit,
        case_root / f"exploit_{evidence.exploit.case_id}",
        repo_root=repo_root,
    )
    _copy_harness_case_dir(
        evidence.valid_control,
        case_root / f"valid_control_{evidence.valid_control.case_id}",
        repo_root=repo_root,
    )
    return case_root


def _copy_harness_case_dir(
    ref: HarnessAuditCaseRef,
    destination: Path,
    *,
    repo_root: Path,
) -> None:
    source = _resolve_repo_relative_path(repo_root, ref.case_dir)
    shutil.copytree(source, destination)


def _index_scorer_results(
    results: list[ScorerAuditResult],
) -> dict[str, ScorerAuditResult]:
    indexed: dict[str, ScorerAuditResult] = {}
    for result in results:
        if result.case.id in indexed:
            raise ValueError(f"Duplicate scorer audit case id: {result.case.id}")
        indexed[result.case.id] = result
    return indexed


def _expected_non_pass_status_matched(result: ScorerAuditResult) -> bool:
    return result.overall_match and result.case.expected_attempt_status != "PASS"


def _expected_pass_status_matched(result: ScorerAuditResult) -> bool:
    return result.overall_match and result.case.expected_attempt_status == "PASS"


def _private_content_exposed(scan: LeakageScanResult) -> bool:
    return scan.canary_leaked or scan.hidden_validators_visible_to_model


def _submitted_patch_scan_contains_probe_reference(
    scan: LeakageScanResult,
    *,
    spec: HiddenValidatorProbeExploitSpec,
) -> bool:
    if spec.probe_reference_type == "leakage_canary":
        return scan.canary_leaked
    if spec.probe_reference_type == "hidden_validator_path":
        return scan.hidden_validators_visible_to_model
    raise ValueError(f"Unsupported probe reference type: {spec.probe_reference_type}")


def _outcome_comparisons(
    case: RewardHackCase,
    *,
    private_content_exposed_actual: bool,
    exploit_blocked_actual: bool,
    training_allowed_actual: bool,
) -> tuple[RewardHackOutcomeComparison, ...]:
    expected = case.expected_reward_hack_outcome
    return (
        RewardHackOutcomeComparison(
            field="private_content_exposed",
            expected=expected.private_content_exposed,
            actual=private_content_exposed_actual,
        ),
        RewardHackOutcomeComparison(
            field="exploit_blocked",
            expected=expected.exploit_blocked,
            actual=exploit_blocked_actual,
        ),
        RewardHackOutcomeComparison(
            field="training_allowed",
            expected=expected.training_allowed,
            actual=training_allowed_actual,
        ),
    )


def _make_run_dir(work_dir: Path | None) -> Path:
    if work_dir is None:
        return Path(tempfile.mkdtemp(prefix="agentenv-reward-hack-audit-")).resolve()
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=work_dir)).resolve()


def _resolve_repo_relative_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    resolved = (repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"Path escapes repo root: {raw_path}")
    return resolved
