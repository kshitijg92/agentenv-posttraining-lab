import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from agentenv.artifacts.manifests import (
    HARNESS_AUDIT_ARTIFACT_REFS,
    HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
    HarnessAuditManifest,
    load_harness_audit_manifest,
)
from agentenv.audits.schema import (
    AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
    HARNESS_AUDIT_RUNTIME_VERSION,
    HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
    SCORER_AUDIT_RECORD_SCHEMA_VERSION,
    AgentTaskAuditErrorRecord,
    AgentTaskAuditRecord,
    CompletedAgentTaskAuditRecord,
    CompletedScorerAuditRecord,
    HarnessAuditLayerSummary,
    HarnessRuntimeProvenance,
    ScorerAuditRecord,
    derive_harness_audit_layer_status,
    derive_harness_audit_layer_payload_hash,
    derive_harness_audit_status,
    derive_harness_runtime_hash,
    load_agent_task_audit_records,
    load_scorer_audit_records,
)


HASH_A = "xxh64:aaaaaaaaaaaaaaaa"
HASH_B = "xxh64:bbbbbbbbbbbbbbbb"
HASH_C = "xxh64:cccccccccccccccc"
HASH_D = "xxh64:dddddddddddddddd"


def _runtime_provenance() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
        "harness_source_root": "src/agentenv",
        "harness_source_hash": HASH_A,
        "root_pyproject_path": "pyproject.toml",
        "root_pyproject_hash": HASH_B,
        "root_uv_lock_path": "uv.lock",
        "root_uv_lock_hash": HASH_C,
        "python_implementation": "cpython",
        "python_version": "3.12.11",
        "sys_platform": "linux",
        "platform_machine": "x86_64",
    }
    payload["harness_runtime_hash"] = derive_harness_runtime_hash(
        harness_source_hash=HASH_A,
        root_pyproject_hash=HASH_B,
        root_uv_lock_hash=HASH_C,
        python_implementation="cpython",
        python_version="3.12.11",
        sys_platform="linux",
        platform_machine="x86_64",
    )
    return payload


def _complete_provenance() -> dict[str, object]:
    return {
        "source_case_path": "data/harness_audit/agent_task_cases/happy_path",
        "case_id": "happy_path",
        "case_source_hash": HASH_A,
        "task_id": "toy_python_fix_001",
        "task_manifest_path": (
            "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
        ),
        "task_manifest_hash": HASH_B,
        "task_record_hash": HASH_C,
    }


def _partial_provenance() -> dict[str, object]:
    return {
        "source_case_path": "data/harness_audit/agent_task_cases/broken",
        "case_source_hash": HASH_A,
        "case_id": None,
        "task_id": None,
        "task_manifest_path": None,
        "task_manifest_hash": None,
        "task_record_hash": None,
    }


def _completed_agent_record(*, match: bool = True) -> dict[str, object]:
    actual = "scored" if match else "agent_loop_failed"
    return {
        "schema_version": AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
        "record_status": "COMPLETED",
        "audit_layer": "agent",
        "provenance": _complete_provenance(),
        "purpose": "Prove that the happy path reaches authoritative scoring.",
        "agent_control_script": "agent_control_script.json",
        "case_artifact": {
            "path": "cases/happy_path",
            "content_hash": HASH_D,
        },
        "agent_attempt_id": "agent_attempt_001",
        "agent_run_status": actual,
        "prompt_loop_status": "completed" if match else "invalid_model_output",
        "error_class": None if match else "MalformedModelOutput",
        "scorer_result": (
            {
                "scorer_attempt_id": "scorer_attempt_001",
                "attempt_status": "PASS",
                "public_status": "PASS",
                "hidden_status": "PASS",
                "error_class": None,
            }
            if match
            else None
        ),
        "comparisons": [
            {
                "field": "agent_run_status",
                "expected": "scored",
                "actual": actual,
                "match": match,
            }
        ],
        "overall_match": match,
    }


def _agent_error_record() -> dict[str, object]:
    return {
        "schema_version": AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
        "record_status": "AUDIT_ERROR",
        "audit_layer": "agent",
        "provenance": _partial_provenance(),
        "error": {
            "audit_stage": "CASE_PREPARATION",
            "error_class": "ValidationError",
            "error_message": "case.yaml could not be validated",
        },
    }


def _completed_scorer_record(*, match: bool = True) -> dict[str, object]:
    actual_hidden = "PASS" if match else "FAIL"
    provenance = _complete_provenance()
    provenance["source_case_path"] = "data/harness_audit/scorer_cases/correct_oracle"
    provenance["case_id"] = "correct_oracle"
    return {
        "schema_version": SCORER_AUDIT_RECORD_SCHEMA_VERSION,
        "record_status": "COMPLETED",
        "audit_layer": "scorer",
        "provenance": provenance,
        "purpose": "Prove that the oracle passes public and hidden checks.",
        "submission": "oracle.patch",
        "case_artifact": {
            "path": "cases/correct_oracle",
            "content_hash": HASH_D,
        },
        "scorer_attempt_id": "scorer_attempt_001",
        "error_class": None,
        "manifest_override": None,
        "comparisons": [
            {
                "field": "attempt_status",
                "expected": "PASS",
                "actual": "PASS",
                "match": True,
            },
            {
                "field": "public_status",
                "expected": "PASS",
                "actual": "PASS",
                "match": True,
            },
            {
                "field": "hidden_status",
                "expected": "PASS",
                "actual": actual_hidden,
                "match": match,
            },
        ],
        "overall_match": match,
    }


def _layer_summary(
    layer: str,
    *,
    matched_count: int = 1,
    mismatched_count: int = 0,
    audit_error_count: int = 0,
) -> dict[str, object]:
    completed_count = matched_count + mismatched_count
    record_count = completed_count + audit_error_count
    if mismatched_count:
        status = "FAIL"
    elif audit_error_count:
        status = "INCONCLUSIVE"
    else:
        status = "PASS"
    summary = {
        "audit_layer": layer,
        "status": status,
        "case_root": f"data/harness_audit/{layer}_cases",
        "case_root_hash": HASH_A,
        "discovered_case_count": record_count,
        "record_count": record_count,
        "completed_count": completed_count,
        "matched_count": matched_count,
        "mismatched_count": mismatched_count,
        "audit_error_count": audit_error_count,
        "results_jsonl": "results.jsonl",
        "results_jsonl_hash": HASH_C,
        "case_artifacts": "cases",
        "case_artifacts_hash": HASH_D,
    }
    summary["artifact_payload_hash"] = derive_harness_audit_layer_payload_hash(
        results_jsonl="results.jsonl",
        results_jsonl_hash=HASH_C,
        case_artifacts="cases",
        case_artifacts_hash=HASH_D,
    )
    return summary


def _manifest() -> dict[str, object]:
    runtime = _runtime_provenance()
    runtime_hash = runtime["harness_runtime_hash"]
    return {
        "artifact_type": "harness_audit",
        "artifact_schema_version": HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
        "harness_audit_run_id": "harness_audit_001",
        "created_at": "2026-07-10T00:00:00Z",
        "git_sha_or_unknown": "deadbeef",
        "runtime_version": HARNESS_AUDIT_RUNTIME_VERSION,
        "runtime_provenance": runtime,
        "status": "PASS",
        "agent_audit": {
            "artifact_type": "agent_task_audit",
            "artifact_schema_version": "agent_task_audit_artifact_v0",
            "agent_task_audit_run_id": "agent_task_audit_001",
            "manifest_path": "agent/manifest.json",
            "manifest_hash": HASH_A,
            "harness_runtime_hash": runtime_hash,
            "status": "PASS",
        },
        "scorer_audit": {
            "artifact_type": "scorer_audit",
            "artifact_schema_version": "scorer_audit_artifact_v0",
            "scorer_audit_run_id": "scorer_audit_001",
            "manifest_path": "scorer/manifest.json",
            "manifest_hash": HASH_B,
            "harness_runtime_hash": runtime_hash,
            "status": "PASS",
        },
        "report_hash": HASH_C,
        "artifacts": dict(HARNESS_AUDIT_ARTIFACT_REFS),
    }


def test_runtime_provenance_requires_derived_hash() -> None:
    provenance = HarnessRuntimeProvenance.model_validate(_runtime_provenance())

    assert provenance.harness_source_root == "src/agentenv"
    assert provenance.harness_runtime_hash.startswith("xxh64:")

    payload = _runtime_provenance()
    payload["harness_runtime_hash"] = HASH_D
    with pytest.raises(ValidationError, match="harness_runtime_hash must reflect"):
        HarnessRuntimeProvenance.model_validate(payload)


def test_completed_agent_record_requires_comparison_derived_match() -> None:
    record = TypeAdapter(AgentTaskAuditRecord).validate_python(
        _completed_agent_record()
    )

    assert isinstance(record, CompletedAgentTaskAuditRecord)
    assert record.overall_match is True
    assert record.scorer_result is not None
    assert record.scorer_result.attempt_status == "PASS"
    assert {comparison.field for comparison in record.comparisons} == {
        "agent_run_status"
    }

    payload = _completed_agent_record()
    payload["overall_match"] = False
    with pytest.raises(ValidationError, match="overall_match must reflect"):
        TypeAdapter(AgentTaskAuditRecord).validate_python(payload)


def test_agent_record_requires_scorer_result_exactly_when_scored() -> None:
    scored_payload = _completed_agent_record()
    scored_payload["scorer_result"] = None
    with pytest.raises(ValidationError, match="require scorer_result"):
        TypeAdapter(AgentTaskAuditRecord).validate_python(scored_payload)

    unscored_payload = _completed_agent_record(match=False)
    unscored_payload["scorer_result"] = {
        "scorer_attempt_id": "scorer_attempt_001",
        "attempt_status": "PASS",
        "public_status": "PASS",
        "hidden_status": "PASS",
        "error_class": None,
    }
    with pytest.raises(ValidationError, match="cannot include scorer_result"):
        TypeAdapter(AgentTaskAuditRecord).validate_python(unscored_payload)


def test_nested_scorer_result_enforces_attempt_terminal_state() -> None:
    payload = _completed_agent_record()
    scorer_result = payload["scorer_result"]
    assert isinstance(scorer_result, dict)
    scorer_result["hidden_status"] = "FAIL"

    with pytest.raises(ValidationError, match="PASS attempts require"):
        TypeAdapter(AgentTaskAuditRecord).validate_python(payload)


def test_audit_error_record_allows_unparsed_case_and_task_identity() -> None:
    record = TypeAdapter(AgentTaskAuditRecord).validate_python(_agent_error_record())

    assert isinstance(record, AgentTaskAuditErrorRecord)
    assert record.provenance.case_id is None
    assert record.provenance.task_record_hash is None
    assert record.error.audit_stage == "CASE_PREPARATION"


def test_partial_provenance_rejects_authoritative_hash_without_task_identity() -> None:
    payload = _agent_error_record()
    provenance = payload["provenance"]
    assert isinstance(provenance, dict)
    provenance["task_record_hash"] = HASH_D

    with pytest.raises(
        ValidationError,
        match="task_record_hash requires complete parsed task identity",
    ):
        TypeAdapter(AgentTaskAuditRecord).validate_python(payload)


def test_scorer_record_uses_field_discriminated_comparisons() -> None:
    record = TypeAdapter(ScorerAuditRecord).validate_python(_completed_scorer_record())

    assert isinstance(record, CompletedScorerAuditRecord)
    assert [comparison.field for comparison in record.comparisons] == [
        "attempt_status",
        "public_status",
        "hidden_status",
    ]

    payload = _completed_scorer_record()
    comparisons = payload["comparisons"]
    assert isinstance(comparisons, list)
    assert isinstance(comparisons[1], dict)
    comparisons[1]["actual"] = "TIMEOUT"
    with pytest.raises(ValidationError):
        TypeAdapter(ScorerAuditRecord).validate_python(payload)


def test_layer_status_precedence_keeps_observed_mismatch() -> None:
    mismatch = TypeAdapter(AgentTaskAuditRecord).validate_python(
        _completed_agent_record(match=False)
    )
    audit_error = TypeAdapter(AgentTaskAuditRecord).validate_python(
        _agent_error_record()
    )

    assert derive_harness_audit_layer_status([mismatch, audit_error]) == "FAIL"
    assert derive_harness_audit_layer_status([audit_error]) == "INCONCLUSIVE"
    with pytest.raises(ValueError, match="at least one record"):
        derive_harness_audit_layer_status([])


@pytest.mark.parametrize(
    ("agent_status", "scorer_status", "expected"),
    [
        ("PASS", "PASS", "PASS"),
        ("PASS", "INCONCLUSIVE", "INCONCLUSIVE"),
        ("INCONCLUSIVE", "INCONCLUSIVE", "INCONCLUSIVE"),
        ("FAIL", "PASS", "FAIL"),
        ("INCONCLUSIVE", "FAIL", "FAIL"),
    ],
)
def test_overall_status_is_three_valued_and(
    agent_status: Any,
    scorer_status: Any,
    expected: str,
) -> None:
    assert derive_harness_audit_status(agent_status, scorer_status) == expected


def test_layer_summary_validates_counts_and_status() -> None:
    summary = HarnessAuditLayerSummary.model_validate(
        _layer_summary("agent", audit_error_count=1)
    )
    assert summary.status == "INCONCLUSIVE"

    payload = _layer_summary("agent", audit_error_count=1)
    payload["status"] = "PASS"
    with pytest.raises(ValidationError, match="status must reflect"):
        HarnessAuditLayerSummary.model_validate(payload)

    payload = _layer_summary("agent")
    payload["artifact_payload_hash"] = HASH_A
    with pytest.raises(ValidationError, match="artifact_payload_hash must reflect"):
        HarnessAuditLayerSummary.model_validate(payload)


def test_harness_audit_manifest_derives_overall_status_and_child_identity() -> None:
    manifest = HarnessAuditManifest.model_validate(_manifest())
    assert manifest.status == "PASS"

    payload = _manifest()
    agent_audit = payload["agent_audit"]
    assert isinstance(agent_audit, dict)
    agent_audit["status"] = "INCONCLUSIVE"
    payload["status"] = "PASS"
    with pytest.raises(ValidationError, match="status must reflect"):
        HarnessAuditManifest.model_validate(payload)

    payload = _manifest()
    agent_audit = payload["agent_audit"]
    assert isinstance(agent_audit, dict)
    agent_audit["artifact_type"] = "scorer_audit"
    with pytest.raises(ValidationError):
        HarnessAuditManifest.model_validate(payload)

    payload = _manifest()
    agent_audit = payload["agent_audit"]
    assert isinstance(agent_audit, dict)
    agent_audit["harness_runtime_hash"] = HASH_D
    with pytest.raises(ValidationError, match="root harness runtime"):
        HarnessAuditManifest.model_validate(payload)


def test_harness_audit_manifest_requires_exact_artifact_refs() -> None:
    payload = _manifest()
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, dict)
    del artifacts["agent_audit"]

    with pytest.raises(ValidationError, match="harness audit manifests require"):
        HarnessAuditManifest.model_validate(payload)


def test_harness_audit_manifest_loaders_accept_current_contract(
    tmp_path: Path,
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest()))

    assert isinstance(load_harness_audit_manifest(path), HarnessAuditManifest)


def test_layer_specific_jsonl_loaders_reject_cross_layer_records(
    tmp_path: Path,
) -> None:
    agent_path = tmp_path / "agent.jsonl"
    scorer_path = tmp_path / "scorer.jsonl"
    agent_path.write_text(json.dumps(_completed_agent_record()) + "\n")
    scorer_path.write_text(json.dumps(_completed_scorer_record()) + "\n")

    assert isinstance(
        load_agent_task_audit_records(agent_path)[0],
        CompletedAgentTaskAuditRecord,
    )
    assert isinstance(
        load_scorer_audit_records(scorer_path)[0],
        CompletedScorerAuditRecord,
    )

    agent_path.write_text(json.dumps(_completed_scorer_record()) + "\n")
    with pytest.raises(ValidationError, match=str(agent_path)):
        load_agent_task_audit_records(agent_path)
