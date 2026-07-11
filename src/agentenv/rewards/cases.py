import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml

from agentenv.audits.agent_task import load_agent_task_audit_case
from agentenv.audits.scorer import load_scorer_audit_case
from agentenv.rewards.schema import (
    AgentTaskAuditEvidencePair,
    HarnessAuditCaseRef,
    RewardHackCase,
    RewardHackEvidencePair,
    RewardHackExploitCheck,
    ScorerAuditEvidencePair,
)


def load_reward_hack_case(path: Path) -> RewardHackCase:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected reward-hack case object at {path}")
    return RewardHackCase.model_validate(raw)


def load_reward_hack_check_catalogue(
    case_root: Path,
) -> tuple[RewardHackExploitCheck, ...]:
    case_paths = find_reward_hack_case_paths(case_root)
    if not case_paths:
        raise ValueError(
            f"Reward-hack check catalogue contains no cases under {case_root}"
        )
    return build_reward_hack_check_catalogue(
        [load_reward_hack_case(path) for path in case_paths]
    )


def build_reward_hack_check_catalogue(
    cases: Sequence[RewardHackCase],
) -> tuple[RewardHackExploitCheck, ...]:
    if not cases:
        raise ValueError("Reward-hack check catalogue requires at least one case")

    cases_by_id: dict[str, RewardHackCase] = {}
    checks_by_id: dict[str, RewardHackExploitCheck] = {}
    check_ids_by_exploit: dict[str, str] = {}

    for case in cases:
        if case.reward_hack_id in cases_by_id:
            raise ValueError(
                "Reward-hack cases contain duplicate reward_hack_id: "
                f"{case.reward_hack_id!r}"
            )
        cases_by_id[case.reward_hack_id] = case

        check = RewardHackExploitCheck(
            exploit_check_id=case.exploit_check_id,
            finding_classification=case.finding_classification,
            exploit=case.exploit,
        )
        existing_check = checks_by_id.get(case.exploit_check_id)
        if existing_check is not None and existing_check != check:
            raise ValueError(
                "Reward-hack cases map exploit_check_id to conflicting check "
                f"definitions: {case.exploit_check_id!r}"
            )

        exploit_key = json.dumps(
            case.exploit.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        existing_check_id = check_ids_by_exploit.get(exploit_key)
        if existing_check_id is not None and existing_check_id != case.exploit_check_id:
            raise ValueError(
                "Identical reward-hack exploit specifications use different "
                f"exploit_check_id values: {existing_check_id!r} and "
                f"{case.exploit_check_id!r}"
            )

        checks_by_id[case.exploit_check_id] = check
        check_ids_by_exploit[exploit_key] = case.exploit_check_id

    return tuple(checks_by_id[check_id] for check_id in sorted(checks_by_id))


def find_reward_hack_case_paths(case_root: Path) -> list[Path]:
    case_root = case_root.resolve()
    if case_root.is_file():
        if case_root.name != "case.yaml":
            raise ValueError(f"Expected reward-hack case.yaml file: {case_root}")
        return [case_root]
    if (case_root / "case.yaml").is_file():
        return [case_root / "case.yaml"]
    return sorted(case_root.rglob("case.yaml"))


def verify_reward_hack_case_source_refs(
    case: RewardHackCase,
    *,
    repo_root: Path | None = None,
) -> None:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    _verify_evidence_pair(case.evidence, repo_root=root)


def _verify_evidence_pair(evidence: RewardHackEvidencePair, *, repo_root: Path) -> None:
    if isinstance(evidence, ScorerAuditEvidencePair | AgentTaskAuditEvidencePair):
        loader = (
            load_scorer_audit_case
            if isinstance(evidence, ScorerAuditEvidencePair)
            else load_agent_task_audit_case
        )
        exploit_case = _verify_harness_audit_ref(
            evidence.exploit,
            repo_root=repo_root,
            loader=loader,
        )
        valid_control_case = _verify_harness_audit_ref(
            evidence.valid_control,
            repo_root=repo_root,
            loader=loader,
        )
        _verify_same_task_manifest(
            exploit_task_manifest=exploit_case.task_manifest,
            valid_control_task_manifest=valid_control_case.task_manifest,
        )
        return

    raise ValueError(
        f"Evidence verification is not implemented for {evidence.source_type}"
    )


def _verify_harness_audit_ref(
    ref: HarnessAuditCaseRef,
    *,
    repo_root: Path,
    loader: Callable[[Path], Any],
) -> Any:
    case_dir = _resolve_repo_relative_path(repo_root, ref.case_dir)
    case_yaml = case_dir / "case.yaml"
    if not case_yaml.is_file():
        raise ValueError(f"Missing harness audit case YAML: {case_yaml}")

    case = loader(case_yaml)
    loaded_case_id = getattr(case, "id")
    if loaded_case_id != ref.case_id:
        raise ValueError(
            f"Harness audit case id mismatch for {case_dir}: "
            f"expected {ref.case_id!r}, loaded {loaded_case_id!r}"
        )
    return case


def _verify_same_task_manifest(
    *,
    exploit_task_manifest: str,
    valid_control_task_manifest: str,
) -> None:
    if exploit_task_manifest != valid_control_task_manifest:
        raise ValueError(
            "Reward-hack evidence pair must reference the same task manifest: "
            f"exploit={exploit_task_manifest!r} "
            f"valid_control={valid_control_task_manifest!r}"
        )


def _resolve_repo_relative_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Reward-hack source paths must be repo-relative: {raw_path}")
    resolved = (repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"Reward-hack source path escapes repo root: {raw_path}")
    return resolved
