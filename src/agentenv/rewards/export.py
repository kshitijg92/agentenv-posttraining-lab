import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import load_jsonl_objects, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    REWARD_HACK_AUDIT_ARTIFACT_REFS,
    REWARD_HACK_AUDIT_ARTIFACT_SCHEMA_VERSION,
    RewardHackAuditManifest,
    load_reward_hack_audit_manifest,
)
from agentenv.hashing import hash_file
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.rewards.audit import (
    REWARD_HACK_AUDIT_RUNTIME_VERSION,
    RewardHackAuditResult,
    RewardHackOutcomeComparison,
    RewardHackRuntimeCheck,
    run_reward_hack_audit,
)
from agentenv.rewards.schema import REWARD_HACK_CASE_SCHEMA_VERSION, RewardHackCase
from agentenv.scorers.audit import (
    ScorerAuditCase,
    ScorerAuditResult,
    StatusComparison,
)
from agentenv.security.leakage import LeakageScanResult


@dataclass(frozen=True)
class RewardHackAuditArtifact:
    out_dir: Path
    manifest: RewardHackAuditManifest
    records: list[RewardHackAuditResult]


def run_and_persist_reward_hack_audit(
    case_root: Path,
    out_dir: Path,
    *,
    repo_root: Path | None = None,
    overwrite: bool = False,
) -> RewardHackAuditArtifact:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)
    case_runs_dir = out_dir / REWARD_HACK_AUDIT_ARTIFACT_REFS["case_runs"]
    results = list(
        run_reward_hack_audit(
            case_root,
            work_dir=case_runs_dir,
            repo_root=root,
        )
    )
    results_path = out_dir / REWARD_HACK_AUDIT_ARTIFACT_REFS["results"]
    write_reward_hack_audit_results_jsonl(
        results_path,
        results,
        artifact_root=out_dir,
        repo_root=root,
    )
    manifest = build_reward_hack_audit_manifest(
        case_root=case_root,
        results_path=results_path,
        results=results,
    )
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return load_reward_hack_audit_artifact(out_dir, repo_root=root)


def load_reward_hack_audit_artifact(
    out_dir: Path,
    *,
    repo_root: Path | None = None,
) -> RewardHackAuditArtifact:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    out_dir = out_dir.resolve()
    manifest = load_reward_hack_audit_manifest(out_dir / MANIFEST_FILENAME)
    results_path = resolve_relative_artifact_ref(out_dir, manifest.artifacts["results"])
    observed_hash = hash_file(results_path)
    if observed_hash != manifest.results_jsonl_hash:
        raise ValueError(
            f"Reward-hack audit results hash mismatch at {results_path}: "
            f"{observed_hash!r} != {manifest.results_jsonl_hash!r}"
        )
    records = load_reward_hack_audit_results_jsonl(
        results_path,
        artifact_root=out_dir,
        repo_root=root,
    )
    if len(records) != manifest.record_count:
        raise ValueError(
            f"Reward-hack audit record count mismatch at {results_path}: "
            f"{len(records)} != {manifest.record_count}"
        )
    observed_pass_count = sum(record.audit_pass for record in records)
    if observed_pass_count != manifest.pass_count:
        raise ValueError(
            "Reward-hack audit pass_count mismatch: "
            f"{observed_pass_count} != {manifest.pass_count}"
        )
    return RewardHackAuditArtifact(
        out_dir=out_dir,
        manifest=manifest,
        records=records,
    )


def write_reward_hack_audit_results_jsonl(
    path: Path,
    results: Sequence[RewardHackAuditResult],
    *,
    artifact_root: Path,
    repo_root: Path,
) -> None:
    path.write_text(
        "".join(
            json.dumps(
                _reward_hack_audit_result_record(
                    result,
                    artifact_root=artifact_root,
                    repo_root=repo_root,
                ),
                sort_keys=True,
            )
            + "\n"
            for result in results
        )
    )


def load_reward_hack_audit_results_jsonl(
    path: Path,
    *,
    artifact_root: Path,
    repo_root: Path,
) -> list[RewardHackAuditResult]:
    return [
        _reward_hack_audit_result_from_record(
            record,
            artifact_root=artifact_root,
            repo_root=repo_root,
        )
        for record in load_jsonl_objects(path)
    ]


def build_reward_hack_audit_manifest(
    *,
    case_root: Path,
    results_path: Path,
    results: Sequence[RewardHackAuditResult],
) -> RewardHackAuditManifest:
    pass_count = sum(result.audit_pass for result in results)
    return RewardHackAuditManifest.model_validate(
        {
            "artifact_type": ArtifactType.REWARD_HACK_AUDIT,
            "artifact_schema_version": REWARD_HACK_AUDIT_ARTIFACT_SCHEMA_VERSION,
            "created_at": _utc_now(),
            "runtime_version": REWARD_HACK_AUDIT_RUNTIME_VERSION,
            "case_root": str(case_root),
            "reward_hack_case_schema_version": REWARD_HACK_CASE_SCHEMA_VERSION,
            "record_count": len(results),
            "pass_count": pass_count,
            "fail_count": len(results) - pass_count,
            "results_jsonl_hash": hash_file(results_path),
            "artifacts": dict(REWARD_HACK_AUDIT_ARTIFACT_REFS),
        }
    )


def _reward_hack_audit_result_record(
    result: RewardHackAuditResult,
    *,
    artifact_root: Path,
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "runtime_version": result.runtime_version,
        "case_path": _display_path(result.case_path, repo_root),
        "reward_hack_case": result.reward_hack_case.model_dump(mode="json"),
        "run_dir": _display_path(result.run_dir, artifact_root),
        "audit_pass": result.audit_pass,
        "exploit_source_case_hash": result.exploit_source_case_hash,
        "valid_control_source_case_hash": result.valid_control_source_case_hash,
        "exploit_audit_result": _scorer_audit_result_record(
            result.exploit_audit_result,
            artifact_root=artifact_root,
        ),
        "valid_control_audit_result": _scorer_audit_result_record(
            result.valid_control_audit_result,
            artifact_root=artifact_root,
        ),
        "exploit_harness_audit_passed": result.exploit_harness_audit_passed,
        "valid_control_harness_audit_passed": (
            result.valid_control_harness_audit_passed
        ),
        "valid_control_task_success_actual": result.valid_control_task_success_actual,
        "private_content_access_attempt_actual": (
            result.private_content_access_attempt_actual
        ),
        "private_content_exposed_actual": result.private_content_exposed_actual,
        "leakage_scan": _leakage_scan_record(result.leakage_scan_result),
        "exploit_blocked_actual": result.exploit_blocked_actual,
        "training_allowed_actual": result.training_allowed_actual,
        "task_success_allowed_actual": result.task_success_allowed_actual,
        "outcome_comparisons": [
            asdict(comparison) for comparison in result.outcome_comparisons
        ],
        "runtime_checks": [asdict(check) for check in result.runtime_checks],
    }


def _reward_hack_audit_result_from_record(
    record: dict[str, Any],
    *,
    artifact_root: Path,
    repo_root: Path,
) -> RewardHackAuditResult:
    return RewardHackAuditResult(
        runtime_version=_required_str(record, "runtime_version"),
        case_path=_record_path(record, "case_path", repo_root),
        reward_hack_case=RewardHackCase.model_validate(
            _required_mapping(record, "reward_hack_case")
        ),
        run_dir=_record_path(record, "run_dir", artifact_root),
        exploit_source_case_hash=_required_str(record, "exploit_source_case_hash"),
        valid_control_source_case_hash=_required_str(
            record,
            "valid_control_source_case_hash",
        ),
        exploit_audit_result=_scorer_audit_result_from_record(
            _required_mapping(record, "exploit_audit_result"),
            artifact_root=artifact_root,
        ),
        valid_control_audit_result=_scorer_audit_result_from_record(
            _required_mapping(record, "valid_control_audit_result"),
            artifact_root=artifact_root,
        ),
        exploit_harness_audit_passed=_required_bool(
            record,
            "exploit_harness_audit_passed",
        ),
        valid_control_harness_audit_passed=_required_bool(
            record,
            "valid_control_harness_audit_passed",
        ),
        valid_control_task_success_actual=_required_bool(
            record,
            "valid_control_task_success_actual",
        ),
        private_content_access_attempt_actual=_required_bool(
            record,
            "private_content_access_attempt_actual",
        ),
        leakage_scan_result=_leakage_scan_from_record(
            _required_mapping(record, "leakage_scan")
        ),
        private_content_exposed_actual=_required_bool(
            record,
            "private_content_exposed_actual",
        ),
        exploit_blocked_actual=_required_bool(record, "exploit_blocked_actual"),
        training_allowed_actual=_required_bool(record, "training_allowed_actual"),
        task_success_allowed_actual=_required_bool(
            record,
            "task_success_allowed_actual",
        ),
        outcome_comparisons=_outcome_comparisons_from_record(record),
        runtime_checks=_runtime_checks_from_record(record),
    )


def _scorer_audit_result_record(
    result: ScorerAuditResult,
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    return {
        "case": result.case.model_dump(mode="json"),
        "case_dir": _display_path(result.case_dir, artifact_root),
        "attempt_artifact_dir": _display_path(
            result.attempt_artifact_dir,
            artifact_root,
        ),
        "manifest_override": result.manifest_override_record,
        "comparisons": [asdict(comparison) for comparison in result.comparisons],
        "attempt_result": result.attempt_result.model_dump(mode="json"),
    }


def _scorer_audit_result_from_record(
    record: dict[str, Any],
    *,
    artifact_root: Path,
) -> ScorerAuditResult:
    return ScorerAuditResult(
        case=ScorerAuditCase.model_validate(_required_mapping(record, "case")),
        case_dir=_record_path(record, "case_dir", artifact_root),
        attempt_artifact_dir=_record_path(
            record,
            "attempt_artifact_dir",
            artifact_root,
        ),
        attempt_result=AttemptResult.model_validate(
            _required_mapping(record, "attempt_result")
        ),
        comparisons=tuple(
            StatusComparison(**comparison)
            for comparison in _required_list(record, "comparisons")
        ),
        manifest_override_record=_optional_mapping(record, "manifest_override"),
    )


def _leakage_scan_record(scan: LeakageScanResult) -> dict[str, Any]:
    return {
        "leakage_check_version": scan.leakage_check_version,
        "canary_hash": scan.canary_hash,
        "canary_matches": list(scan.canary_matches),
        "private_marker_matches": list(scan.private_marker_matches),
        "scanned_files": list(scan.scanned_files),
    }


def _leakage_scan_from_record(record: dict[str, Any]) -> LeakageScanResult:
    return LeakageScanResult(
        leakage_check_version=_required_str(record, "leakage_check_version"),
        canary_hash=_optional_str(record, "canary_hash"),
        canary_matches=tuple(_required_str_list(record, "canary_matches")),
        private_marker_matches=tuple(
            _required_str_list(record, "private_marker_matches")
        ),
        scanned_files=tuple(_required_str_list(record, "scanned_files")),
    )


def _outcome_comparisons_from_record(
    record: dict[str, Any],
) -> tuple[RewardHackOutcomeComparison, ...]:
    return tuple(
        RewardHackOutcomeComparison(**comparison)
        for comparison in _required_list(record, "outcome_comparisons")
    )


def _runtime_checks_from_record(
    record: dict[str, Any],
) -> tuple[RewardHackRuntimeCheck, ...]:
    return tuple(
        RewardHackRuntimeCheck(**check)
        for check in _required_list(record, "runtime_checks")
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _display_path(path: Path, root: Path) -> str:
    path = path.resolve()
    root = root.resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _record_path(record: dict[str, Any], field: str, root: Path) -> Path:
    raw_path = _required_str(record, field)
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _required_mapping(record: dict[str, Any], field: str) -> dict[str, Any]:
    value = record.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"Expected object field {field!r}")
    return value


def _optional_mapping(record: dict[str, Any], field: str) -> dict[str, Any] | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Expected object field {field!r}")
    return value


def _required_list(record: dict[str, Any], field: str) -> list[Any]:
    value = record.get(field)
    if not isinstance(value, list):
        raise ValueError(f"Expected list field {field!r}")
    return value


def _required_str_list(record: dict[str, Any], field: str) -> list[str]:
    values = _required_list(record, field)
    if not all(isinstance(value, str) for value in values):
        raise ValueError(f"Expected string list field {field!r}")
    return values


def _required_str(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise ValueError(f"Expected string field {field!r}")
    return value


def _optional_str(record: dict[str, Any], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected optional string field {field!r}")
    return value


def _required_bool(record: dict[str, Any], field: str) -> bool:
    value = record.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"Expected bool field {field!r}")
    return value
