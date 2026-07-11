from pathlib import Path
from collections.abc import Callable
from typing import Any

import yaml

from agentenv.audits.agent_task import load_agent_task_audit_case
from agentenv.audits.scorer import load_scorer_audit_case
from agentenv.hashing import hash_bytes
from agentenv.hashing import hash_json
from agentenv.hashing import hash_normalized_text
from agentenv.hashing import iter_hashable_files
from agentenv.hashing import relative_path
from agentenv.rewards.schema import (
    AgentTaskAuditEvidencePair,
    HarnessAuditCaseRef,
    RewardHackCase,
    RewardHackEvidencePair,
    ScorerAuditEvidencePair,
)


def load_reward_hack_case(path: Path) -> RewardHackCase:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected reward-hack case object at {path}")
    return RewardHackCase.model_validate(raw)


def verify_reward_hack_case_source_refs(
    case: RewardHackCase,
    *,
    repo_root: Path | None = None,
) -> None:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    _verify_evidence_pair(case.evidence, repo_root=root)


def hash_harness_audit_case_dir(case_dir: Path) -> str:
    case_dir = case_dir.resolve()
    if not case_dir.is_dir():
        raise ValueError(f"Expected harness audit case directory: {case_dir}")

    entries = [
        {
            "path": relative_path(file_path, case_dir),
            "hash": _hash_case_file(file_path),
        }
        for file_path in iter_hashable_files(case_dir)
    ]
    return hash_json(entries)


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


def _hash_case_file(path: Path) -> str:
    if path.name == "notes.md":
        return hash_normalized_text(path.read_text())
    return hash_bytes(path.read_bytes())
