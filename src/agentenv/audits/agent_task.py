"""Typed agent-task harness-audit artifact execution and validation."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.agents.schema import PromptLoopStatus
from agentenv.artifacts.base import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
    resolve_relative_artifact_ref,
)
from agentenv.artifacts.manifests import (
    AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    AGENT_TASK_AUDIT_ARTIFACT_REFS,
    AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION,
    AgentTaskAuditManifest,
    load_agent_task_audit_manifest,
)
from agentenv.artifacts.payloads import TASK_HASH_REPORT_SCHEMA_VERSION
from agentenv.audits.hashing import (
    build_task_record_hash_for_manifest,
    hash_harness_audit_case_dir,
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
from agentenv.audits.schema import (
    AGENT_TASK_AUDIT_CASE_SCHEMA_VERSION,
    AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
    HARNESS_AUDIT_RUNTIME_VERSION,
    AgentAuditComparisonRecord,
    AgentTaskAuditErrorRecord,
    AgentTaskAuditRecord,
    CompletedAgentTaskAuditRecord,
    HarnessAuditCaseProvenance,
    HarnessAuditErrorEvidence,
    HarnessAuditLayerSummary,
    HarnessAuditStage,
    PartialHarnessAuditCaseProvenance,
    derive_harness_audit_layer_payload_hash,
    derive_harness_audit_layer_status,
    load_agent_task_audit_records,
)
from agentenv.audits.types import AgentAuditField
from agentenv.controls.agent_control_scripts import (
    AgentControlScriptCase,
    ExpectedAgentControlToolResult,
    load_agent_control_script_case,
)
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.models.schema import ModelFinishReason
from agentenv.hashing import hash_directory, hash_file
from agentenv.ids import new_agent_task_audit_run_id
from agentenv.orchestrators.agent_task_schema import AgentTaskRunStatus
from agentenv.orchestrators.agent_task_run import (
    AgentTaskRun,
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.attempt import AttemptStatus, CheckStatus
from agentenv.security.secrets import redact_secrets
from agentenv.tasks.validate import load_task_manifest


AgentAuditValue = str | None | list[str] | list[dict[str, object]]

_EXPECTATION_FIELDS = {
    "expected_agent_run_status",
    "expected_agent_error_class",
    "expected_prompt_loop_status",
    "expected_prompt_loop_error_class",
    "expected_model_finish_reasons",
    "expected_tool_results",
    "expected_attempt_status",
    "expected_public_status",
    "expected_hidden_status",
}


class AgentTaskAuditCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    task_manifest: str = Field(min_length=1)
    agent_control_script: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    expected_agent_run_status: AgentTaskRunStatus | None = None
    expected_agent_error_class: str | None = Field(default=None, min_length=1)
    expected_prompt_loop_status: PromptLoopStatus | None = None
    expected_prompt_loop_error_class: str | None = Field(default=None, min_length=1)
    expected_model_finish_reasons: list[ModelFinishReason] | None = None
    expected_tool_results: list[ExpectedAgentControlToolResult] | None = None
    expected_attempt_status: AttemptStatus | None = None
    expected_public_status: CheckStatus | None = None
    expected_hidden_status: CheckStatus | None = None

    @model_validator(mode="after")
    def validate_expectations(self) -> "AgentTaskAuditCase":
        if not (_EXPECTATION_FIELDS & self.model_fields_set):
            raise ValueError("agent task audit cases require at least one expectation")
        return self


@dataclass(frozen=True)
class AgentTaskAuditLayerRun:
    out_dir: Path
    records: tuple[AgentTaskAuditRecord, ...]
    summary: HarnessAuditLayerSummary
    manifest: AgentTaskAuditManifest


def run_agent_task_audit_layer(
    case_root: Path,
    out_dir: Path,
    *,
    repo_root: Path | None = None,
    overwrite: bool = False,
) -> AgentTaskAuditLayerRun:
    """Run every discovered agent-task case and persist a standalone artifact."""
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    case_root = case_root.resolve()
    out_dir = out_dir.resolve()
    case_root_ref = repo_relative_path(case_root, root)
    case_dirs = discover_case_dirs(case_root, layer_name="agent-task audit")
    if not case_dirs:
        raise ValueError(
            f"No agent-task audit case directories found under {case_root}"
        )
    case_root_hash = hash_directory(case_root)
    runtime_root = harness_repo_root()
    runtime_provenance = capture_harness_runtime_provenance(runtime_root)
    agent_task_audit_run_id = new_agent_task_audit_run_id()
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
            _run_typed_agent_task_audit_case(
                case_dir,
                case_artifact_dir=cases_out_dir / f"{index:04d}",
                layer_out_dir=prepared_out_dir,
                repo_root=root,
            )
            for index, case_dir in enumerate(case_dirs, start=1)
        )

        results_path = prepared_out_dir / AGENT_TASK_AUDIT_ARTIFACT_REFS["results"]
        _write_typed_records(records, results_path)
        loaded_records = load_agent_task_audit_records(results_path)
        if loaded_records != records:
            raise ValueError("Persisted agent-task audit records failed exact readback")
        if capture_harness_runtime_provenance(runtime_root) != runtime_provenance:
            raise ValueError(
                "Harness runtime changed during agent-task audit execution"
            )

        completed_records = tuple(
            record
            for record in records
            if isinstance(record, CompletedAgentTaskAuditRecord)
        )
        matched_count = sum(record.overall_match for record in completed_records)
        mismatched_count = len(completed_records) - matched_count
        audit_error_count = sum(
            isinstance(record, AgentTaskAuditErrorRecord) for record in records
        )
        results_jsonl_hash = hash_file(results_path)
        case_artifacts_hash = hash_directory(cases_out_dir)
        summary = HarnessAuditLayerSummary(
            audit_layer="agent",
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
                results_jsonl=AGENT_TASK_AUDIT_ARTIFACT_REFS["results"],
                results_jsonl_hash=results_jsonl_hash,
                case_artifacts=AGENT_TASK_AUDIT_ARTIFACT_REFS["case_artifacts"],
                case_artifacts_hash=case_artifacts_hash,
            ),
            results_jsonl=AGENT_TASK_AUDIT_ARTIFACT_REFS["results"],
            results_jsonl_hash=results_jsonl_hash,
            case_artifacts=AGENT_TASK_AUDIT_ARTIFACT_REFS["case_artifacts"],
            case_artifacts_hash=case_artifacts_hash,
        )
        manifest = AgentTaskAuditManifest(
            artifact_type=ArtifactType.AGENT_TASK_AUDIT,
            artifact_schema_version=AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION,
            agent_task_audit_run_id=agent_task_audit_run_id,
            created_at=created_at,
            git_sha_or_unknown=git_sha,
            runtime_version=HARNESS_AUDIT_RUNTIME_VERSION,
            runtime_provenance=runtime_provenance,
            agent_task_audit_case_schema_version=(AGENT_TASK_AUDIT_CASE_SCHEMA_VERSION),
            agent_task_audit_record_schema_version=(
                AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION
            ),
            task_hash_report_schema_version=TASK_HASH_REPORT_SCHEMA_VERSION,
            agent_attempt_artifact_schema_version=(
                AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION
            ),
            summary=summary,
            artifacts=dict(AGENT_TASK_AUDIT_ARTIFACT_REFS),
        )
        manifest_path = prepared_out_dir / MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n"
        )
        loaded_layer = load_agent_task_audit_layer(prepared_out_dir)
        if loaded_layer.manifest != manifest or loaded_layer.records != records:
            raise ValueError(
                "Persisted agent-task audit manifest failed exact readback"
            )
        return loaded_layer
    except Exception:
        if prepared_out_dir is not None and prepared_out_dir.exists():
            shutil.rmtree(prepared_out_dir)
        raise


def load_agent_task_audit_layer(out_dir: Path) -> AgentTaskAuditLayerRun:
    out_dir = out_dir.resolve()
    manifest = load_agent_task_audit_manifest(out_dir / MANIFEST_FILENAME)
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
        label="agent-task audit results",
    )
    _require_hash(
        cases_dir,
        observed=hash_directory(cases_dir),
        expected=manifest.summary.case_artifacts_hash,
        label="agent-task audit case artifacts",
    )
    records = load_agent_task_audit_records(results_path)
    _validate_loaded_agent_summary(records, manifest.summary)
    for record in records:
        if not isinstance(record, CompletedAgentTaskAuditRecord):
            continue
        artifact_dir = resolve_relative_artifact_ref(
            out_dir,
            record.case_artifact.path,
        )
        if not artifact_dir.is_relative_to(cases_dir):
            raise ValueError(
                "Agent-task audit case artifact must be inside the declared cases "
                f"dir: {artifact_dir}"
            )
        _require_hash(
            artifact_dir,
            observed=hash_directory(artifact_dir),
            expected=record.case_artifact.content_hash,
            label=f"agent-task audit case artifact {record.provenance.case_id}",
        )
    return AgentTaskAuditLayerRun(
        out_dir=out_dir,
        records=records,
        summary=manifest.summary,
        manifest=manifest,
    )


def _validate_loaded_agent_summary(
    records: tuple[AgentTaskAuditRecord, ...],
    summary: HarnessAuditLayerSummary,
) -> None:
    completed = tuple(
        record
        for record in records
        if isinstance(record, CompletedAgentTaskAuditRecord)
    )
    matched_count = sum(record.overall_match for record in completed)
    observed = (
        len(records),
        len(completed),
        matched_count,
        len(completed) - matched_count,
        sum(isinstance(record, AgentTaskAuditErrorRecord) for record in records),
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
            f"Agent-task audit summary does not match loaded records: {observed!r} "
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


def _execute_agent_task_audit_case(
    control_case: AgentControlScriptCase,
    *,
    task_manifest_path: Path,
    artifact_dir: Path,
) -> AgentTaskRun:
    model_client = _model_client(control_case)
    decoding_config = model_client.default_decoding_config()
    return run_and_persist_agent_task_attempt_to_dir(
        task_manifest_path,
        model_client,
        decoding_config,
        artifact_dir,
        agent_control_script=control_case,
    )


def _run_typed_agent_task_audit_case(
    case_dir: Path,
    *,
    case_artifact_dir: Path,
    layer_out_dir: Path,
    repo_root: Path,
) -> AgentTaskAuditRecord:
    source_case_path = repo_relative_path(case_dir, repo_root)
    case_source_hash: str | None = None
    case_id: str | None = None
    task_id: str | None = None
    task_manifest_ref: str | None = None
    task_manifest_hash: str | None = None
    task_record_hash: str | None = None

    try:
        case_source_hash = hash_harness_audit_case_dir(case_dir)
        case = load_agent_task_audit_case(case_dir / "case.yaml")
        case_id = case.id
        task_manifest_path = resolve_repo_relative_path(
            case.task_manifest,
            repo_root=repo_root,
            layer_name="Agent-task audit",
        )
        task_manifest_ref = repo_relative_path(task_manifest_path, repo_root)
        task_manifest_hash = hash_file(task_manifest_path)
        task_manifest = load_task_manifest(task_manifest_path)
        task_id = task_manifest.id
        task_record_hash = build_task_record_hash_for_manifest(
            task_manifest_path,
            task_id=task_id,
        )
        control_script_path = resolve_case_relative_file(
            case_dir,
            case.agent_control_script,
            layer_name="Agent-task audit",
            file_label="agent control script",
        )
        control_case = load_agent_control_script_case(control_script_path)
    except Exception as exc:
        return _agent_task_audit_error_record(
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
        agent_task_run = _execute_agent_task_audit_case(
            control_case,
            task_manifest_path=task_manifest_path,
            artifact_dir=case_artifact_dir,
        )
    except Exception as exc:
        return _agent_task_audit_error_record_from_provenance(
            provenance,
            audit_stage="HARNESS_EXECUTION",
            exc=exc,
        )

    try:
        comparisons = _comparisons(case, agent_task_run)
    except Exception as exc:
        return _agent_task_audit_error_record_from_provenance(
            provenance,
            audit_stage="EXPECTATION_COMPARISON",
            exc=exc,
        )

    try:
        run_result = agent_task_run.result
        attempt_result = run_result.attempt_result
        scorer_result = (
            {
                "scorer_attempt_id": attempt_result.scorer_attempt_id,
                "attempt_status": attempt_result.status,
                "public_status": attempt_result.public_status,
                "hidden_status": attempt_result.hidden_status,
                "error_class": attempt_result.error_class,
            }
            if attempt_result is not None
            else None
        )
        return CompletedAgentTaskAuditRecord.model_validate(
            {
                "schema_version": AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
                "record_status": "COMPLETED",
                "audit_layer": "agent",
                "provenance": provenance,
                "purpose": case.purpose,
                "agent_control_script": case.agent_control_script,
                "case_artifact": {
                    "path": case_artifact_dir.relative_to(layer_out_dir).as_posix(),
                    "content_hash": hash_directory(case_artifact_dir),
                },
                "agent_attempt_id": run_result.agent_attempt_id,
                "agent_run_status": run_result.status,
                "prompt_loop_status": run_result.prompt_loop_status,
                "error_class": run_result.error_class,
                "scorer_result": scorer_result,
                "comparisons": [
                    {
                        "field": comparison.field,
                        "expected": comparison.expected,
                        "actual": comparison.actual,
                        "match": comparison.match,
                    }
                    for comparison in comparisons
                ],
                "overall_match": all(comparison.match for comparison in comparisons),
            }
        )
    except Exception as exc:
        return _agent_task_audit_error_record_from_provenance(
            provenance,
            audit_stage="RESULT_PERSISTENCE",
            exc=exc,
        )


def _agent_task_audit_error_record_from_provenance(
    provenance: HarnessAuditCaseProvenance,
    *,
    audit_stage: HarnessAuditStage,
    exc: Exception,
) -> AgentTaskAuditErrorRecord:
    return _agent_task_audit_error_record(
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


def _agent_task_audit_error_record(
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
) -> AgentTaskAuditErrorRecord:
    error_class = type(exc).__name__
    error_message = redact_secrets(str(exc)) or error_class
    return AgentTaskAuditErrorRecord.model_validate(
        {
            "schema_version": AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
            "record_status": "AUDIT_ERROR",
            "audit_layer": "agent",
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
    records: tuple[AgentTaskAuditRecord, ...],
    path: Path,
) -> None:
    lines = [
        json.dumps(record.model_dump(mode="json"), sort_keys=True) for record in records
    ]
    path.write_text("\n".join(lines) + "\n")


def load_agent_task_audit_case(path: Path) -> AgentTaskAuditCase:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected agent task audit case object at {path}")
    return AgentTaskAuditCase.model_validate(raw)


def _model_client(control_case: AgentControlScriptCase) -> ScriptedFakeModelClient:
    return ScriptedFakeModelClient(
        model_id="agent-audit-scripted-v0",
        script=control_case.script.steps,
    )


def _comparisons(
    case: AgentTaskAuditCase,
    agent_task_run: AgentTaskRun,
) -> tuple[AgentAuditComparisonRecord, ...]:
    comparisons: list[AgentAuditComparisonRecord] = []
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_agent_run_status",
        comparison_field="agent_run_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_agent_error_class",
        comparison_field="agent_error_class",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_prompt_loop_status",
        comparison_field="prompt_loop_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_prompt_loop_error_class",
        comparison_field="prompt_loop_error_class",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_model_finish_reasons",
        comparison_field="model_finish_reasons",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_tool_results",
        comparison_field="tool_results",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_attempt_status",
        comparison_field="attempt_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_public_status",
        comparison_field="public_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_hidden_status",
        comparison_field="hidden_status",
    )
    return tuple(comparisons)


def _append_comparison(
    comparisons: list[AgentAuditComparisonRecord],
    case: AgentTaskAuditCase,
    agent_task_run: AgentTaskRun,
    *,
    expected_field: str,
    comparison_field: AgentAuditField,
) -> None:
    if expected_field not in case.model_fields_set:
        return
    expected = _expected_value(case, expected_field)
    actual = _actual_value(agent_task_run, comparison_field)
    comparisons.append(
        AgentAuditComparisonRecord.model_validate(
            {
                "field": comparison_field,
                "expected": expected,
                "actual": actual,
                "match": expected == actual,
            }
        )
    )


def _expected_value(
    case: AgentTaskAuditCase,
    expected_field: str,
) -> AgentAuditValue:
    if expected_field == "expected_model_finish_reasons":
        if case.expected_model_finish_reasons is None:
            return None
        return list(case.expected_model_finish_reasons)
    if expected_field == "expected_tool_results":
        tool_results = case.expected_tool_results
        if tool_results is None:
            return None
        return [
            {
                "tool_name": tool_result.tool_name,
                "status": tool_result.status,
                "error_class": tool_result.error_class,
            }
            for tool_result in tool_results
        ]
    value = getattr(case, expected_field)
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"Unsupported expectation value for {expected_field}")


def _actual_value(
    agent_task_run: AgentTaskRun,
    field: AgentAuditField,
) -> AgentAuditValue:
    result = agent_task_run.result
    attempt_result = result.attempt_result
    if field == "agent_run_status":
        return result.status
    if field == "agent_error_class":
        return result.error_class
    if field == "prompt_loop_status":
        return result.prompt_loop_status
    if field == "prompt_loop_error_class":
        prompt_loop_result = agent_task_run.prompt_loop_result
        return (
            prompt_loop_result.error_class if prompt_loop_result is not None else None
        )
    if field == "model_finish_reasons":
        prompt_loop_result = agent_task_run.prompt_loop_result
        if prompt_loop_result is None:
            return []
        return [
            str(model_response.finish_reason)
            for model_response in prompt_loop_result.model_responses
        ]
    if field == "tool_results":
        return _actual_tool_results(agent_task_run)
    if field == "attempt_status":
        return attempt_result.status if attempt_result is not None else None
    if field == "public_status":
        return attempt_result.public_status if attempt_result is not None else None
    if field == "hidden_status":
        return attempt_result.hidden_status if attempt_result is not None else None


def _actual_tool_results(agent_task_run: AgentTaskRun) -> list[dict[str, object]]:
    if agent_task_run.prompt_loop_result is None:
        return []
    return [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in agent_task_run.prompt_loop_result.tool_results
    ]
