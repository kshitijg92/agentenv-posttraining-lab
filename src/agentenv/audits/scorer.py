"""Typed scorer harness-audit artifact execution and validation."""

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agentenv.artifacts.base import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
    resolve_relative_artifact_ref,
)
from agentenv.artifacts.manifests import (
    SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    SCORER_AUDIT_ARTIFACT_REFS,
    SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION,
    ScorerAuditManifest,
    load_scorer_audit_manifest,
)
from agentenv.artifacts.payloads import TASK_HASH_REPORT_SCHEMA_VERSION
from agentenv.audits.hashing import (
    build_task_record_hash_for_manifest,
    hash_harness_audit_case_dir,
)
from agentenv.audits.schema import (
    HARNESS_AUDIT_RUNTIME_VERSION,
    SCORER_AUDIT_CASE_SCHEMA_VERSION,
    SCORER_AUDIT_RECORD_SCHEMA_VERSION,
    AttemptStatusAuditComparisonRecord,
    CompletedScorerAuditRecord,
    HiddenStatusAuditComparisonRecord,
    HarnessAuditCaseProvenance,
    HarnessAuditErrorEvidence,
    HarnessAuditLayerSummary,
    HarnessAuditStage,
    PartialHarnessAuditCaseProvenance,
    PublicStatusAuditComparisonRecord,
    ScorerAuditErrorRecord,
    ScorerAuditRecord,
    derive_harness_audit_layer_payload_hash,
    derive_harness_audit_layer_status,
    load_scorer_audit_records,
)
from agentenv.audits.paths import (
    discover_case_dirs,
    repo_relative_path,
    resolve_case_relative_file,
    resolve_repo_relative_path,
)
from agentenv.audits.runtime import (
    capture_harness_runtime_provenance,
    git_sha_or_unknown,
    harness_repo_root,
    utc_now_iso,
)
from agentenv.hashing import hash_directory, hash_file
from agentenv.ids import new_scorer_audit_run_id
from agentenv.orchestrators.attempt import AttemptResult, AttemptStatus, CheckStatus
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.security.secrets import redact_secrets
from agentenv.tasks.validate import load_task_manifest


class ManifestLimitOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_seconds: int = Field(gt=0)


class ManifestOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limits: ManifestLimitOverrides


class ScorerAuditCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    task_manifest: str = Field(min_length=1)
    submission: str = Field(min_length=1)
    expected_attempt_status: AttemptStatus
    expected_public_status: CheckStatus
    expected_hidden_status: CheckStatus
    purpose: str = Field(min_length=1)
    manifest_overrides: ManifestOverrides | None = None


@dataclass(frozen=True)
class ScorerAuditLayerRun:
    out_dir: Path
    records: tuple[ScorerAuditRecord, ...]
    summary: HarnessAuditLayerSummary
    manifest: ScorerAuditManifest


def run_scorer_audit_layer(
    case_root: Path,
    out_dir: Path,
    *,
    repo_root: Path | None = None,
    overwrite: bool = False,
) -> ScorerAuditLayerRun:
    """Run every discovered scorer case and persist one typed record per case."""
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    case_root = case_root.resolve()
    out_dir = out_dir.resolve()
    case_root_ref = repo_relative_path(case_root, root)
    case_dirs = discover_case_dirs(case_root, layer_name="scorer audit")
    if not case_dirs:
        raise ValueError(f"No scorer audit case directories found under {case_root}")
    case_root_hash = hash_directory(case_root)
    runtime_root = harness_repo_root()
    runtime_provenance = capture_harness_runtime_provenance(runtime_root)
    scorer_audit_run_id = new_scorer_audit_run_id()
    created_at = utc_now_iso()
    git_sha = git_sha_or_unknown(runtime_root)

    prepared_out_dir: Path | None = None
    try:
        prepared_out_dir = prepare_artifact_output_dir(
            out_dir,
            overwrite=overwrite,
        )
        cases_out_dir = prepared_out_dir / "cases"
        cases_out_dir.mkdir()
        records = tuple(
            _run_typed_scorer_audit_case(
                case_dir,
                case_artifact_dir=cases_out_dir / f"{index:04d}",
                layer_out_dir=prepared_out_dir,
                repo_root=root,
            )
            for index, case_dir in enumerate(case_dirs, start=1)
        )

        results_path = prepared_out_dir / "results.jsonl"
        _write_typed_records(records, results_path)
        loaded_records = load_scorer_audit_records(results_path)
        if loaded_records != records:
            raise ValueError("Persisted scorer audit records failed exact readback")
        if capture_harness_runtime_provenance(runtime_root) != runtime_provenance:
            raise ValueError("Harness runtime changed during scorer audit execution")

        completed_records = tuple(
            record
            for record in records
            if isinstance(record, CompletedScorerAuditRecord)
        )
        matched_count = sum(record.overall_match for record in completed_records)
        mismatched_count = len(completed_records) - matched_count
        audit_error_count = sum(
            isinstance(record, ScorerAuditErrorRecord) for record in records
        )
        results_jsonl_hash = hash_file(results_path)
        case_artifacts_hash = hash_directory(cases_out_dir)
        summary = HarnessAuditLayerSummary(
            audit_layer="scorer",
            status=derive_harness_audit_layer_status(records),
            case_root=case_root_ref,
            case_root_hash=case_root_hash,
            discovered_case_count=len(case_dirs),
            record_count=len(records),
            completed_count=len(completed_records),
            matched_count=matched_count,
            mismatched_count=mismatched_count,
            audit_error_count=audit_error_count,
            artifact_payload_hash=derive_harness_audit_layer_payload_hash(
                results_jsonl=SCORER_AUDIT_ARTIFACT_REFS["results"],
                results_jsonl_hash=results_jsonl_hash,
                case_artifacts=SCORER_AUDIT_ARTIFACT_REFS["case_artifacts"],
                case_artifacts_hash=case_artifacts_hash,
            ),
            results_jsonl="results.jsonl",
            results_jsonl_hash=results_jsonl_hash,
            case_artifacts="cases",
            case_artifacts_hash=case_artifacts_hash,
        )
        manifest = ScorerAuditManifest(
            artifact_type=ArtifactType.SCORER_AUDIT,
            artifact_schema_version=SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION,
            scorer_audit_run_id=scorer_audit_run_id,
            created_at=created_at,
            git_sha_or_unknown=git_sha,
            runtime_version=HARNESS_AUDIT_RUNTIME_VERSION,
            runtime_provenance=runtime_provenance,
            scorer_audit_case_schema_version=SCORER_AUDIT_CASE_SCHEMA_VERSION,
            scorer_audit_record_schema_version=SCORER_AUDIT_RECORD_SCHEMA_VERSION,
            task_hash_report_schema_version=TASK_HASH_REPORT_SCHEMA_VERSION,
            scorer_attempt_artifact_schema_version=(
                SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION
            ),
            summary=summary,
            artifacts=dict(SCORER_AUDIT_ARTIFACT_REFS),
        )
        manifest_path = prepared_out_dir / MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n"
        )
        loaded_layer = load_scorer_audit_layer(prepared_out_dir)
        if loaded_layer.manifest != manifest or loaded_layer.records != records:
            raise ValueError("Persisted scorer audit manifest failed exact readback")
        return loaded_layer
    except Exception:
        if prepared_out_dir is not None and prepared_out_dir.exists():
            shutil.rmtree(prepared_out_dir)
        raise


def load_scorer_audit_layer(out_dir: Path) -> ScorerAuditLayerRun:
    out_dir = out_dir.resolve()
    manifest = load_scorer_audit_manifest(out_dir / MANIFEST_FILENAME)
    results_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["results"],
    )
    cases_dir = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["case_artifacts"],
    )
    _require_hash(
        results_path,
        observed=hash_file(results_path),
        expected=manifest.summary.results_jsonl_hash,
        label="scorer audit results",
    )
    _require_hash(
        cases_dir,
        observed=hash_directory(cases_dir),
        expected=manifest.summary.case_artifacts_hash,
        label="scorer audit case artifacts",
    )
    records = load_scorer_audit_records(results_path)
    _validate_loaded_scorer_summary(records, manifest.summary)
    for record in records:
        if not isinstance(record, CompletedScorerAuditRecord):
            continue
        artifact_dir = resolve_relative_artifact_ref(
            out_dir,
            record.case_artifact.path,
        )
        if not artifact_dir.is_relative_to(cases_dir):
            raise ValueError(
                "Scorer audit case artifact must be inside the declared cases dir: "
                f"{artifact_dir}"
            )
        _require_hash(
            artifact_dir,
            observed=hash_directory(artifact_dir),
            expected=record.case_artifact.content_hash,
            label=f"scorer audit case artifact {record.provenance.case_id}",
        )
    return ScorerAuditLayerRun(
        out_dir=out_dir,
        records=records,
        summary=manifest.summary,
        manifest=manifest,
    )


def _validate_loaded_scorer_summary(
    records: tuple[ScorerAuditRecord, ...],
    summary: HarnessAuditLayerSummary,
) -> None:
    completed = tuple(
        record for record in records if isinstance(record, CompletedScorerAuditRecord)
    )
    matched_count = sum(record.overall_match for record in completed)
    observed = (
        len(records),
        len(completed),
        matched_count,
        len(completed) - matched_count,
        sum(isinstance(record, ScorerAuditErrorRecord) for record in records),
        derive_harness_audit_layer_status(records),
    )
    expected = (
        summary.record_count,
        summary.completed_count,
        summary.matched_count,
        summary.mismatched_count,
        summary.audit_error_count,
        summary.status,
    )
    if observed != expected:
        raise ValueError(
            f"Scorer audit summary does not match loaded records: {observed!r} "
            f"!= {expected!r}"
        )


def _require_hash(
    path: Path,
    *,
    observed: str,
    expected: str,
    label: str,
) -> None:
    if observed != expected:
        raise ValueError(
            f"{label} hash mismatch at {path}: {observed!r} != {expected!r}"
        )


def load_scorer_audit_case(path: Path) -> ScorerAuditCase:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected scorer audit case object at {path}")
    return ScorerAuditCase.model_validate(raw)


def _run_typed_scorer_audit_case(
    case_dir: Path,
    *,
    case_artifact_dir: Path,
    layer_out_dir: Path,
    repo_root: Path,
) -> ScorerAuditRecord:
    source_case_path = repo_relative_path(case_dir, repo_root)
    case_source_hash: str | None = None
    case_id: str | None = None
    task_id: str | None = None
    task_manifest_ref: str | None = None
    task_manifest_hash: str | None = None
    task_record_hash: str | None = None

    try:
        case_source_hash = hash_harness_audit_case_dir(case_dir)
        case = load_scorer_audit_case(case_dir / "case.yaml")
        case_id = case.id
        task_manifest_path = resolve_repo_relative_path(
            case.task_manifest,
            repo_root=repo_root,
            layer_name="Scorer audit",
        )
        task_manifest_ref = repo_relative_path(task_manifest_path, repo_root)
        task_manifest_hash = hash_file(task_manifest_path)
        task_manifest = load_task_manifest(task_manifest_path)
        task_id = task_manifest.id
        task_record_hash = build_task_record_hash_for_manifest(
            task_manifest_path,
            task_id=task_id,
        )
        submission_path = resolve_case_relative_file(
            case_dir,
            case.submission,
            layer_name="Scorer audit",
            file_label="scorer audit submission file",
        )
    except Exception as exc:
        return _scorer_audit_error_record(
            source_case_path=source_case_path,
            case_source_hash=case_source_hash,
            case_id=case_id,
            task_id=task_id,
            task_manifest_path=task_manifest_ref,
            task_manifest_hash=task_manifest_hash,
            task_record_hash=task_record_hash,
            audit_stage="CASE_PREPARATION",
            exc=exc,
        )

    provenance = HarnessAuditCaseProvenance(
        source_case_path=source_case_path,
        case_id=case_id,
        case_source_hash=case_source_hash,
        task_id=task_id,
        task_manifest_path=task_manifest_ref,
        task_manifest_hash=task_manifest_hash,
        task_record_hash=task_record_hash,
    )
    try:
        attempt_result, manifest_override_record = _execute_scorer_audit_case(
            case,
            task_manifest_path=task_manifest_path,
            submission_path=submission_path,
            attempt_artifact_dir=case_artifact_dir,
        )
    except Exception as exc:
        return _scorer_audit_error_record_from_provenance(
            provenance,
            audit_stage="HARNESS_EXECUTION",
            exc=exc,
        )

    try:
        comparisons = _comparisons(case, attempt_result)
    except Exception as exc:
        return _scorer_audit_error_record_from_provenance(
            provenance,
            audit_stage="EXPECTATION_COMPARISON",
            exc=exc,
        )

    try:
        comparison_records = [
            {
                "field": comparison.field,
                "expected": comparison.expected,
                "actual": comparison.actual,
                "match": comparison.match,
            }
            for comparison in comparisons
        ]
        return CompletedScorerAuditRecord.model_validate(
            {
                "schema_version": SCORER_AUDIT_RECORD_SCHEMA_VERSION,
                "record_status": "COMPLETED",
                "audit_layer": "scorer",
                "provenance": provenance,
                "purpose": case.purpose,
                "submission": case.submission,
                "case_artifact": {
                    "path": case_artifact_dir.relative_to(layer_out_dir).as_posix(),
                    "content_hash": hash_directory(case_artifact_dir),
                },
                "scorer_attempt_id": attempt_result.scorer_attempt_id,
                "error_class": attempt_result.error_class,
                "manifest_override": manifest_override_record,
                "comparisons": comparison_records,
                "overall_match": all(comparison.match for comparison in comparisons),
            }
        )
    except Exception as exc:
        return _scorer_audit_error_record_from_provenance(
            provenance,
            audit_stage="RESULT_PERSISTENCE",
            exc=exc,
        )


def _execute_scorer_audit_case(
    case: ScorerAuditCase,
    *,
    task_manifest_path: Path,
    submission_path: Path,
    attempt_artifact_dir: Path,
) -> tuple[AttemptResult, dict[str, object] | None]:
    effective_task_manifest_path = _materialize_effective_manifest(
        case,
        task_manifest_path,
    )
    attempt_run = run_and_persist_patch_attempt_to_dir(
        effective_task_manifest_path,
        submission_path,
        attempt_artifact_dir,
    )
    manifest_override_record = _manifest_override_record(
        case,
        task_manifest_path,
    )
    _write_manifest_override_artifact(
        manifest_override_record,
        attempt_artifact_dir,
    )
    return attempt_run.result, manifest_override_record


def _scorer_audit_error_record_from_provenance(
    provenance: HarnessAuditCaseProvenance,
    *,
    audit_stage: HarnessAuditStage,
    exc: Exception,
) -> ScorerAuditErrorRecord:
    return _scorer_audit_error_record(
        source_case_path=provenance.source_case_path,
        case_source_hash=provenance.case_source_hash,
        case_id=provenance.case_id,
        task_id=provenance.task_id,
        task_manifest_path=provenance.task_manifest_path,
        task_manifest_hash=provenance.task_manifest_hash,
        task_record_hash=provenance.task_record_hash,
        audit_stage=audit_stage,
        exc=exc,
    )


def _scorer_audit_error_record(
    *,
    source_case_path: str,
    case_source_hash: str | None,
    case_id: str | None,
    task_id: str | None,
    task_manifest_path: str | None,
    task_manifest_hash: str | None,
    task_record_hash: str | None,
    audit_stage: HarnessAuditStage,
    exc: Exception,
) -> ScorerAuditErrorRecord:
    error_class = type(exc).__name__
    error_message = redact_secrets(str(exc)) or error_class
    return ScorerAuditErrorRecord.model_validate(
        {
            "schema_version": SCORER_AUDIT_RECORD_SCHEMA_VERSION,
            "record_status": "AUDIT_ERROR",
            "audit_layer": "scorer",
            "provenance": PartialHarnessAuditCaseProvenance(
                source_case_path=source_case_path,
                case_source_hash=case_source_hash,
                case_id=case_id,
                task_id=task_id,
                task_manifest_path=task_manifest_path,
                task_manifest_hash=task_manifest_hash,
                task_record_hash=task_record_hash,
            ),
            "error": HarnessAuditErrorEvidence(
                audit_stage=audit_stage,
                error_class=error_class,
                error_message=error_message,
            ),
        }
    )


def _write_typed_records(
    records: tuple[ScorerAuditRecord, ...],
    path: Path,
) -> None:
    lines = [
        json.dumps(record.model_dump(mode="json"), sort_keys=True) for record in records
    ]
    path.write_text("\n".join(lines) + "\n")


def _materialize_effective_manifest(
    case: ScorerAuditCase,
    task_manifest_path: Path,
) -> Path:
    if case.manifest_overrides is None:
        return task_manifest_path

    source_task_dir = task_manifest_path.parent.resolve()
    temp_task_dir = Path(tempfile.mkdtemp(prefix=f"agentenv-audit-{case.id}-"))
    shutil.copytree(source_task_dir, temp_task_dir, dirs_exist_ok=True)
    effective_manifest_path = temp_task_dir / task_manifest_path.name
    raw_manifest = _load_yaml_mapping(effective_manifest_path)
    _apply_nested_overrides(raw_manifest, _manifest_override_data(case))
    effective_manifest_path.write_text(
        cast(str, yaml.safe_dump(raw_manifest, sort_keys=False))
    )

    return effective_manifest_path


def _write_manifest_override_artifact(
    override_record: dict[str, object] | None,
    attempt_artifact_dir: Path,
) -> None:
    if override_record is None:
        return
    (attempt_artifact_dir / "manifest_override.json").write_text(
        json.dumps(override_record, indent=2, sort_keys=True) + "\n"
    )


def _manifest_override_record(
    case: ScorerAuditCase,
    task_manifest_path: Path,
) -> dict[str, object] | None:
    if case.manifest_overrides is None:
        return None

    raw_manifest = _load_yaml_mapping(task_manifest_path)

    return {
        "source_task_manifest": case.task_manifest,
        "overrides": _nested_override_diff(
            raw_manifest,
            _manifest_override_data(case),
            task_manifest_path,
        ),
        "limitation": (
            "The effective task manifest is materialized in a temporary task "
            "directory for execution. This file records the supported override "
            "only; it is not a replay manifest."
        ),
    }


def _manifest_override_data(case: ScorerAuditCase) -> dict[str, Any]:
    if case.manifest_overrides is None:
        return {}
    return case.manifest_overrides.model_dump(exclude_none=True)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected task manifest object at {path}")
    return raw


def _apply_nested_overrides(
    target: dict[str, Any],
    overrides: dict[str, Any],
    path: tuple[str, ...] = (),
) -> None:
    for key, override_value in overrides.items():
        current_path = (*path, key)
        if isinstance(override_value, dict):
            target_value = target.get(key)
            if not isinstance(target_value, dict):
                dotted_path = ".".join(current_path)
                raise ValueError(f"Expected manifest object at {dotted_path}")
            _apply_nested_overrides(target_value, override_value, current_path)
        else:
            target[key] = override_value


def _nested_override_diff(
    source: dict[str, Any],
    overrides: dict[str, Any],
    source_path: Path,
    path: tuple[str, ...] = (),
) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for key, override_value in overrides.items():
        current_path = (*path, key)
        source_value = source.get(key)
        if isinstance(override_value, dict):
            if not isinstance(source_value, dict):
                dotted_path = ".".join(current_path)
                raise ValueError(
                    f"Expected manifest object at {dotted_path} in {source_path}"
                )
            diff[key] = _nested_override_diff(
                source_value,
                override_value,
                source_path,
                current_path,
            )
        else:
            diff[key] = {
                "from": source_value,
                "to": override_value,
            }
    return diff


def _comparisons(
    case: ScorerAuditCase,
    result: AttemptResult,
) -> tuple[
    AttemptStatusAuditComparisonRecord,
    PublicStatusAuditComparisonRecord,
    HiddenStatusAuditComparisonRecord,
]:
    return (
        AttemptStatusAuditComparisonRecord(
            field="attempt_status",
            expected=case.expected_attempt_status,
            actual=result.status,
            match=case.expected_attempt_status == result.status,
        ),
        PublicStatusAuditComparisonRecord(
            field="public_status",
            expected=case.expected_public_status,
            actual=result.public_status,
            match=case.expected_public_status == result.public_status,
        ),
        HiddenStatusAuditComparisonRecord(
            field="hidden_status",
            expected=case.expected_hidden_status,
            actual=result.hidden_status,
            match=case.expected_hidden_status == result.hidden_status,
        ),
    )
