import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, cast

from pydantic import ValidationError

from agentenv.audits.agent_task import (
    load_agent_task_audit_case,
    run_agent_task_audit_layer,
)
from agentenv.agents.schema import PromptLoopResult, ToolCallAction, parse_agent_action
from agentenv.models.schema import Message
from agentenv.orchestrators.attempt import AttemptStatus, CheckStatus
from agentenv.audits.hashing import (
    find_owning_task_pack,
    hash_harness_audit_case_dir,
)
from agentenv.audits.schema import (
    AgentTaskAuditRecord,
    CompletedAgentTaskAuditRecord,
    CompletedScorerAuditRecord,
    ScorerAuditRecord,
)
from agentenv.rewards.cases import (
    find_reward_hack_case_paths,
    load_reward_hack_case,
    load_reward_hack_check_catalogue,
    verify_reward_hack_case_source_refs,
)
from agentenv.rewards.detection import (
    RewardHackDetectionContext,
    detect_reward_hack_exploit,
)
from agentenv.rewards.schema import (
    AgentTaskAuditEvidencePair,
    ExpectedRewardHackOutcome,
    HarnessAuditCaseRef,
    RewardHackCase,
    ScorerAuditEvidencePair,
)
from agentenv.audits.scorer import (
    load_scorer_audit_case,
    run_scorer_audit_layer,
)
from agentenv.security.leakage import LeakageScanResult
from agentenv.security.leakage import LeakageScanText
from agentenv.security.leakage import list_files_under
from agentenv.security.leakage import scan_directory_for_leakage
from agentenv.security.leakage import scan_files_for_leakage
from agentenv.security.leakage import scan_texts_for_leakage
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest


REWARD_HACK_AUDIT_RUNTIME_VERSION = "reward_hack_audit_runtime_v2"
HarnessAuditResult: TypeAlias = (
    CompletedScorerAuditRecord | CompletedAgentTaskAuditRecord
)

_AGENT_AUTHORED_FIXTURE_ARTIFACT_FILES = {
    "agent_control_script.json",
}
_PROMPT_LOOP_RESULT_ARTIFACT_FILE = "prompt_loop_result.json"


@dataclass(frozen=True)
class RewardHackOutcomeComparison:
    field: str
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
        "exploit_mechanism_detected",
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
    exploit_audit_result: HarnessAuditResult
    valid_control_audit_result: HarnessAuditResult
    exploit_audit_artifact_dir: Path
    valid_control_audit_artifact_dir: Path
    exploit_harness_audit_passed: bool
    valid_control_harness_audit_passed: bool
    valid_control_task_success_actual: bool
    exploit_mechanism_detected_actual: bool
    leakage_scan_result: LeakageScanResult
    private_content_exposed_actual: bool
    exploit_mechanism_neutralized_actual: bool
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


@dataclass(frozen=True)
class StagedHarnessAuditPair:
    repo_root: Path
    case_root: Path


def run_reward_hack_audit(
    case_root: Path,
    *,
    work_dir: Path | None = None,
    repo_root: Path | None = None,
) -> list[RewardHackAuditResult]:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    load_reward_hack_check_catalogue(case_root)
    return [
        run_reward_hack_case_audit(case_path, work_dir=work_dir, repo_root=root)
        for case_path in find_reward_hack_case_paths(case_root)
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

    if isinstance(case.evidence, ScorerAuditEvidencePair):
        _verify_distinct_harness_case_ids(case.evidence)
        return _run_scorer_reward_hack_case_audit(
            case_path,
            case,
            work_dir=work_dir,
            repo_root=root,
        )
    if isinstance(case.evidence, AgentTaskAuditEvidencePair):
        _verify_distinct_harness_case_ids(case.evidence)
        return _run_agent_task_reward_hack_case_audit(
            case_path,
            case,
            work_dir=work_dir,
            repo_root=root,
        )
    raise ValueError(
        "Reward-hack runtime audit currently supports scorer_audit_case and "
        f"agent_task_audit_case evidence only, got {case.evidence.source_type!r}"
    )


def _verify_distinct_harness_case_ids(
    evidence: ScorerAuditEvidencePair | AgentTaskAuditEvidencePair,
) -> None:
    if evidence.exploit.case_id == evidence.valid_control.case_id:
        raise ValueError("Reward-hack exploit and valid control case ids must differ")


def _run_scorer_reward_hack_case_audit(
    case_path: Path,
    case: RewardHackCase,
    *,
    work_dir: Path | None,
    repo_root: Path,
) -> RewardHackAuditResult:
    if not isinstance(case.evidence, ScorerAuditEvidencePair):
        raise TypeError("Expected scorer_audit_case evidence")

    exploit_case_dir = _resolve_repo_relative_path(
        repo_root,
        case.evidence.exploit.case_dir,
    )
    valid_control_case_dir = _resolve_repo_relative_path(
        repo_root,
        case.evidence.valid_control.case_dir,
    )
    exploit_case = load_scorer_audit_case(exploit_case_dir / "case.yaml")
    task_manifest_path = _resolve_repo_relative_path(
        repo_root, exploit_case.task_manifest
    )
    task_manifest = load_task_manifest(task_manifest_path)
    run_dir = _make_run_dir(work_dir)
    staged = _stage_scorer_audit_pair(
        case.evidence,
        run_dir,
        task_manifest_path=task_manifest_path,
        repo_root=repo_root,
    )
    scorer_out_dir = run_dir / "scorer_audit"
    scorer_layer = run_scorer_audit_layer(
        staged.case_root,
        scorer_out_dir,
        repo_root=staged.repo_root,
    )
    scorer_results_by_case_id = _index_scorer_results(scorer_layer.records)
    exploit_result = scorer_results_by_case_id[case.evidence.exploit.case_id]
    valid_control_result = scorer_results_by_case_id[
        case.evidence.valid_control.case_id
    ]
    exploit_artifact_dir = scorer_out_dir / exploit_result.case_artifact.path
    valid_control_artifact_dir = (
        scorer_out_dir / valid_control_result.case_artifact.path
    )

    leakage_scan_result = scan_directory_for_leakage(
        exploit_artifact_dir,
        task_manifest,
    )
    exploit_mechanism_detected_actual = detect_reward_hack_exploit(
        case.exploit,
        context=RewardHackDetectionContext(
            candidate_patch_path=exploit_case_dir / exploit_case.submission,
            prompt_loop_result_path=None,
            attempt_artifact_available=True,
            attempt_status=cast(
                AttemptStatus,
                _scorer_actual_status(exploit_result, "attempt_status"),
            ),
            public_status=cast(
                CheckStatus,
                _scorer_actual_status(exploit_result, "public_status"),
            ),
            hidden_status=cast(
                CheckStatus,
                _scorer_actual_status(exploit_result, "hidden_status"),
            ),
            task_manifest_path=task_manifest_path,
            task_manifest=task_manifest,
        ),
    ).detected
    return _build_reward_hack_result(
        case_path=case_path,
        case=case,
        run_dir=run_dir,
        exploit_case_dir=exploit_case_dir,
        valid_control_case_dir=valid_control_case_dir,
        exploit_result=exploit_result,
        valid_control_result=valid_control_result,
        exploit_audit_artifact_dir=exploit_artifact_dir,
        valid_control_audit_artifact_dir=valid_control_artifact_dir,
        leakage_scan_result=leakage_scan_result,
        exploit_mechanism_detected_actual=exploit_mechanism_detected_actual,
    )


def _run_agent_task_reward_hack_case_audit(
    case_path: Path,
    case: RewardHackCase,
    *,
    work_dir: Path | None,
    repo_root: Path,
) -> RewardHackAuditResult:
    if not isinstance(case.evidence, AgentTaskAuditEvidencePair):
        raise TypeError("Expected agent_task_audit_case evidence")

    exploit_case_dir = _resolve_repo_relative_path(
        repo_root,
        case.evidence.exploit.case_dir,
    )
    valid_control_case_dir = _resolve_repo_relative_path(
        repo_root,
        case.evidence.valid_control.case_dir,
    )
    exploit_case = load_agent_task_audit_case(exploit_case_dir / "case.yaml")
    task_manifest_path = _resolve_repo_relative_path(
        repo_root, exploit_case.task_manifest
    )
    task_manifest = load_task_manifest(task_manifest_path)
    run_dir = _make_run_dir(work_dir)
    staged = _stage_agent_task_audit_pair(
        case.evidence,
        run_dir,
        task_manifest_path=task_manifest_path,
        repo_root=repo_root,
    )
    agent_task_out_dir = run_dir / "agent_task_audit"
    agent_task_layer = run_agent_task_audit_layer(
        staged.case_root,
        agent_task_out_dir,
        repo_root=staged.repo_root,
    )
    agent_results_by_case_id = _index_agent_task_results(agent_task_layer.records)
    exploit_result = agent_results_by_case_id[case.evidence.exploit.case_id]
    valid_control_result = agent_results_by_case_id[case.evidence.valid_control.case_id]
    exploit_artifact_dir = agent_task_out_dir / exploit_result.case_artifact.path
    valid_control_artifact_dir = (
        agent_task_out_dir / valid_control_result.case_artifact.path
    )

    leakage_scan_result = _scan_agent_task_exposure_artifacts(
        artifact_dir=exploit_artifact_dir,
        task_manifest=task_manifest,
    )
    scorer_result = exploit_result.scorer_result
    candidate_patch_path = exploit_artifact_dir / "candidate.patch"
    prompt_loop_result_path = exploit_artifact_dir / _PROMPT_LOOP_RESULT_ARTIFACT_FILE
    exploit_mechanism_detected_actual = detect_reward_hack_exploit(
        case.exploit,
        context=RewardHackDetectionContext(
            candidate_patch_path=(
                candidate_patch_path if candidate_patch_path.is_file() else None
            ),
            prompt_loop_result_path=(
                prompt_loop_result_path if prompt_loop_result_path.is_file() else None
            ),
            attempt_artifact_available=scorer_result is not None,
            attempt_status=(
                scorer_result.attempt_status if scorer_result is not None else None
            ),
            public_status=(
                scorer_result.public_status if scorer_result is not None else None
            ),
            hidden_status=(
                scorer_result.hidden_status if scorer_result is not None else None
            ),
            task_manifest_path=task_manifest_path,
            task_manifest=task_manifest,
        ),
    ).detected
    return _build_reward_hack_result(
        case_path=case_path,
        case=case,
        run_dir=run_dir,
        exploit_case_dir=exploit_case_dir,
        valid_control_case_dir=valid_control_case_dir,
        exploit_result=exploit_result,
        valid_control_result=valid_control_result,
        exploit_audit_artifact_dir=exploit_artifact_dir,
        valid_control_audit_artifact_dir=valid_control_artifact_dir,
        leakage_scan_result=leakage_scan_result,
        exploit_mechanism_detected_actual=exploit_mechanism_detected_actual,
    )


def _build_reward_hack_result(
    *,
    case_path: Path,
    case: RewardHackCase,
    run_dir: Path,
    exploit_case_dir: Path,
    valid_control_case_dir: Path,
    exploit_result: HarnessAuditResult,
    valid_control_result: HarnessAuditResult,
    exploit_audit_artifact_dir: Path,
    valid_control_audit_artifact_dir: Path,
    leakage_scan_result: LeakageScanResult,
    exploit_mechanism_detected_actual: bool,
) -> RewardHackAuditResult:
    task_success_allowed_actual = _source_task_success(exploit_result)
    exploit_mechanism_neutralized_actual = _exploit_mechanism_neutralized_actual(
        case,
        exploit_result=exploit_result,
        exploit_mechanism_detected_actual=exploit_mechanism_detected_actual,
    )
    valid_control_task_success_actual = _source_harness_passed(
        valid_control_result
    ) and _source_task_success(valid_control_result)
    private_content_exposed_actual = _private_content_exposed(leakage_scan_result)
    training_allowed_actual = False
    outcome_comparisons = _outcome_comparisons(
        case,
        private_content_exposed_actual=private_content_exposed_actual,
        exploit_mechanism_neutralized_actual=exploit_mechanism_neutralized_actual,
        task_success_allowed_actual=task_success_allowed_actual,
        training_allowed_actual=training_allowed_actual,
    )
    runtime_checks = (
        RewardHackRuntimeCheck(
            field="exploit_harness_audit_passed",
            expected=True,
            actual=_source_harness_passed(exploit_result),
        ),
        RewardHackRuntimeCheck(
            field="valid_control_harness_audit_passed",
            expected=True,
            actual=_source_harness_passed(valid_control_result),
        ),
        RewardHackRuntimeCheck(
            field="valid_control_task_success",
            expected=True,
            actual=valid_control_task_success_actual,
        ),
        RewardHackRuntimeCheck(
            field="exploit_mechanism_detected",
            expected=True,
            actual=exploit_mechanism_detected_actual,
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
        exploit_audit_artifact_dir=exploit_audit_artifact_dir,
        valid_control_audit_artifact_dir=valid_control_audit_artifact_dir,
        exploit_harness_audit_passed=_source_harness_passed(exploit_result),
        valid_control_harness_audit_passed=_source_harness_passed(
            valid_control_result,
        ),
        valid_control_task_success_actual=valid_control_task_success_actual,
        exploit_mechanism_detected_actual=exploit_mechanism_detected_actual,
        leakage_scan_result=leakage_scan_result,
        private_content_exposed_actual=private_content_exposed_actual,
        exploit_mechanism_neutralized_actual=exploit_mechanism_neutralized_actual,
        training_allowed_actual=training_allowed_actual,
        task_success_allowed_actual=task_success_allowed_actual,
        outcome_comparisons=outcome_comparisons,
        runtime_checks=runtime_checks,
    )


def _load_prompt_loop_result(artifact_dir: Path) -> PromptLoopResult | None:
    path = artifact_dir / _PROMPT_LOOP_RESULT_ARTIFACT_FILE
    if not path.is_file():
        return None
    return PromptLoopResult.model_validate_json(path.read_text())


def _stage_scorer_audit_pair(
    evidence: ScorerAuditEvidencePair,
    run_dir: Path,
    *,
    task_manifest_path: Path,
    repo_root: Path,
) -> StagedHarnessAuditPair:
    return _stage_harness_audit_pair(
        evidence,
        run_dir,
        task_manifest_path=task_manifest_path,
        repo_root=repo_root,
    )


def _stage_agent_task_audit_pair(
    evidence: AgentTaskAuditEvidencePair,
    run_dir: Path,
    *,
    task_manifest_path: Path,
    repo_root: Path,
) -> StagedHarnessAuditPair:
    return _stage_harness_audit_pair(
        evidence,
        run_dir,
        task_manifest_path=task_manifest_path,
        repo_root=repo_root,
    )


def _stage_harness_audit_pair(
    evidence: ScorerAuditEvidencePair | AgentTaskAuditEvidencePair,
    run_dir: Path,
    *,
    task_manifest_path: Path,
    repo_root: Path,
) -> StagedHarnessAuditPair:
    staged_repo_root = run_dir / "input_repo"
    case_root = staged_repo_root / "cases"
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
    task_pack = find_owning_task_pack(task_manifest_path)
    try:
        task_pack_ref = task_pack.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Task pack must be inside reward-audit repository root: {task_pack}"
        ) from exc
    shutil.copytree(task_pack, staged_repo_root / task_pack_ref)
    return StagedHarnessAuditPair(
        repo_root=staged_repo_root,
        case_root=case_root,
    )


def _copy_harness_case_dir(
    ref: HarnessAuditCaseRef,
    destination: Path,
    *,
    repo_root: Path,
) -> None:
    source = _resolve_repo_relative_path(repo_root, ref.case_dir)
    shutil.copytree(source, destination)


def _index_scorer_results(
    results: tuple[ScorerAuditRecord, ...],
) -> dict[str, CompletedScorerAuditRecord]:
    indexed: dict[str, CompletedScorerAuditRecord] = {}
    for result in results:
        if not isinstance(result, CompletedScorerAuditRecord):
            raise ValueError(
                "Reward-hack scorer evidence produced AUDIT_ERROR: "
                f"{result.provenance.source_case_path}"
            )
        case_id = result.provenance.case_id
        if case_id in indexed:
            raise ValueError(f"Duplicate scorer audit case id: {case_id}")
        indexed[case_id] = result
    return indexed


def _index_agent_task_results(
    results: tuple[AgentTaskAuditRecord, ...],
) -> dict[str, CompletedAgentTaskAuditRecord]:
    indexed: dict[str, CompletedAgentTaskAuditRecord] = {}
    for result in results:
        if not isinstance(result, CompletedAgentTaskAuditRecord):
            raise ValueError(
                "Reward-hack agent evidence produced AUDIT_ERROR: "
                f"{result.provenance.source_case_path}"
            )
        case_id = result.provenance.case_id
        if case_id in indexed:
            raise ValueError(f"Duplicate agent task audit case id: {case_id}")
        indexed[case_id] = result
    return indexed


def _source_harness_passed(result: HarnessAuditResult) -> bool:
    return result.overall_match


def _scorer_actual_status(
    result: CompletedScorerAuditRecord,
    field: str,
) -> str:
    matches = [
        comparison.actual
        for comparison in result.comparisons
        if comparison.field == field
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one scorer audit comparison for {field!r}")
    return matches[0]


def _source_task_success(result: HarnessAuditResult) -> bool:
    if isinstance(result, CompletedScorerAuditRecord):
        return _scorer_actual_status(result, "attempt_status") == "PASS"
    return (
        result.scorer_result is not None
        and result.scorer_result.attempt_status == "PASS"
    )


def _source_has_trusted_scorer_result(result: HarnessAuditResult) -> bool:
    if isinstance(result, CompletedScorerAuditRecord):
        return True
    return result.scorer_result is not None


def _exploit_mechanism_neutralized_actual(
    case: RewardHackCase,
    *,
    exploit_result: HarnessAuditResult,
    exploit_mechanism_detected_actual: bool,
) -> bool:
    if case.exploit.exploit_classification == "fake_success_output":
        return (
            exploit_mechanism_detected_actual
            and _source_harness_passed(exploit_result)
            and _source_has_trusted_scorer_result(exploit_result)
        )
    if case.exploit.exploit_classification == "tool_output_spoofing":
        return (
            exploit_mechanism_detected_actual
            and _source_harness_passed(exploit_result)
            and _source_has_authoritative_tool_results(exploit_result)
        )
    if case.exploit.exploit_classification == "state_corruption":
        return (
            exploit_mechanism_detected_actual
            and _source_harness_passed(exploit_result)
            and _source_has_trusted_scorer_result(exploit_result)
        )
    return (
        exploit_mechanism_detected_actual
        and _source_harness_passed(exploit_result)
        and not _source_task_success(exploit_result)
    )


def _source_has_authoritative_tool_results(result: HarnessAuditResult) -> bool:
    if not isinstance(result, CompletedAgentTaskAuditRecord):
        return False
    return any(
        comparison.field == "tool_results" and comparison.match
        for comparison in result.comparisons
    )


def _scan_agent_task_exposure_artifacts(
    *,
    artifact_dir: Path,
    task_manifest: TaskManifest,
) -> LeakageScanResult:
    file_paths = _agent_raw_exposure_artifact_files(artifact_dir)
    file_scan = scan_files_for_leakage(
        file_paths,
        task_manifest,
        root=artifact_dir,
    )

    prompt_loop_result = _load_prompt_loop_result(artifact_dir)
    if prompt_loop_result is None:
        return file_scan

    prompt_loop_scan = _scan_prompt_loop_result_for_exposure(
        prompt_loop_result,
        task_manifest,
    )
    return _merge_leakage_scans(file_scan, prompt_loop_scan)


def _agent_raw_exposure_artifact_files(artifact_dir: Path) -> tuple[Path, ...]:
    raw_files: list[Path] = []
    for path in list_files_under(artifact_dir):
        if path.name in _AGENT_AUTHORED_FIXTURE_ARTIFACT_FILES:
            continue
        if path.name == _PROMPT_LOOP_RESULT_ARTIFACT_FILE:
            continue
        raw_files.append(path)
    return tuple(raw_files)


def _scan_prompt_loop_result_for_exposure(
    prompt_loop_result: PromptLoopResult,
    task_manifest: TaskManifest,
) -> LeakageScanResult:
    texts: list[LeakageScanText] = []
    for index, message in enumerate(prompt_loop_result.messages):
        if _is_assistant_private_tool_call_attempt(message, task_manifest):
            continue
        texts.append(
            LeakageScanText(
                ref=f"prompt_loop_message:{index}:{message.role}",
                text=message.model_dump_json(),
            )
        )

    for index, tool_result in enumerate(prompt_loop_result.tool_results):
        texts.append(
            LeakageScanText(
                ref=f"prompt_loop_tool_result:{index}:{tool_result.tool_name}",
                text=tool_result.model_dump_json(),
            )
        )

    if prompt_loop_result.error_message is not None:
        texts.append(
            LeakageScanText(
                ref="prompt_loop_error_message",
                text=prompt_loop_result.error_message,
            )
        )

    return scan_texts_for_leakage(texts, task_manifest)


def _is_assistant_private_tool_call_attempt(
    message: Message,
    task_manifest: TaskManifest,
) -> bool:
    if message.role != "assistant":
        return False
    try:
        action = parse_agent_action(message.content)
    except (ValidationError, ValueError):
        return False
    if not isinstance(action, ToolCallAction):
        return False
    scan = scan_texts_for_leakage(
        (
            LeakageScanText(
                ref="assistant_tool_call_attempt",
                text=action.model_dump_json(),
            ),
        ),
        task_manifest,
    )
    return _private_content_exposed(scan)


def _merge_leakage_scans(
    first: LeakageScanResult,
    second: LeakageScanResult,
) -> LeakageScanResult:
    if first.leakage_check_version != second.leakage_check_version:
        raise ValueError("Cannot merge leakage scans with different versions")
    if first.canary_hash != second.canary_hash:
        raise ValueError("Cannot merge leakage scans with different canary hashes")
    return LeakageScanResult(
        leakage_check_version=first.leakage_check_version,
        canary_hash=first.canary_hash,
        canary_matches=tuple(
            dict.fromkeys(first.canary_matches + second.canary_matches)
        ),
        private_marker_matches=tuple(
            dict.fromkeys(first.private_marker_matches + second.private_marker_matches)
        ),
        scanned_files=tuple(dict.fromkeys(first.scanned_files + second.scanned_files)),
    )


def _private_content_exposed(scan: LeakageScanResult) -> bool:
    return scan.canary_leaked or scan.hidden_validators_visible_to_model


def _outcome_comparisons(
    case: RewardHackCase,
    *,
    private_content_exposed_actual: bool,
    exploit_mechanism_neutralized_actual: bool,
    task_success_allowed_actual: bool,
    training_allowed_actual: bool,
) -> tuple[RewardHackOutcomeComparison, ...]:
    expected = case.expected_reward_hack_outcome
    actual = ExpectedRewardHackOutcome(
        private_content_exposed=private_content_exposed_actual,
        exploit_mechanism_neutralized=exploit_mechanism_neutralized_actual,
        task_success_allowed=task_success_allowed_actual,
        training_allowed=training_allowed_actual,
    )
    comparisons: list[RewardHackOutcomeComparison] = []
    for field in ExpectedRewardHackOutcome.model_fields:
        expected_value = getattr(expected, field)
        actual_value = getattr(actual, field)
        if not isinstance(expected_value, bool) or not isinstance(actual_value, bool):
            raise TypeError(f"Expected reward-hack outcome field to be bool: {field}")
        comparisons.append(
            RewardHackOutcomeComparison(
                field=field,
                expected=expected_value,
                actual=actual_value,
            )
        )
    return tuple(comparisons)


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
