import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from agentenv.artifacts.manifests import (
    AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    AGENT_TASK_AUDIT_ARTIFACT_REFS,
    AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION,
    SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    SCORER_AUDIT_ARTIFACT_REFS,
    SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION,
    AgentTaskAuditManifest,
    ScorerAuditManifest,
    load_agent_task_audit_manifest,
    load_scorer_audit_manifest,
)
from agentenv.artifacts.payloads import TASK_HASH_REPORT_SCHEMA_VERSION
from agentenv.audits.schema import (
    AGENT_TASK_AUDIT_CASE_SCHEMA_VERSION,
    AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
    HARNESS_AUDIT_RUNTIME_VERSION,
    HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
    SCORER_AUDIT_CASE_SCHEMA_VERSION,
    SCORER_AUDIT_RECORD_SCHEMA_VERSION,
    derive_harness_audit_layer_payload_hash,
    derive_harness_runtime_hash,
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
        "python_version": "3.11.14",
        "sys_platform": "linux",
        "platform_machine": "x86_64",
    }
    payload["harness_runtime_hash"] = derive_harness_runtime_hash(
        harness_source_hash=HASH_A,
        root_pyproject_hash=HASH_B,
        root_uv_lock_hash=HASH_C,
        python_implementation="cpython",
        python_version="3.11.14",
        sys_platform="linux",
        platform_machine="x86_64",
    )
    return payload


def _summary(layer: str) -> dict[str, object]:
    results_ref = "results.jsonl"
    cases_ref = "cases"
    return {
        "audit_layer": layer,
        "status": "PASS",
        "case_root": f"data/harness_audit/{layer}_cases",
        "case_root_hash": HASH_A,
        "discovered_case_count": 1,
        "record_count": 1,
        "completed_count": 1,
        "matched_count": 1,
        "mismatched_count": 0,
        "audit_error_count": 0,
        "artifact_payload_hash": derive_harness_audit_layer_payload_hash(
            results_jsonl=results_ref,
            results_jsonl_hash=HASH_C,
            case_artifacts=cases_ref,
            case_artifacts_hash=HASH_D,
        ),
        "results_jsonl": results_ref,
        "results_jsonl_hash": HASH_C,
        "case_artifacts": cases_ref,
        "case_artifacts_hash": HASH_D,
    }


def _scorer_manifest() -> dict[str, object]:
    return {
        "artifact_type": "scorer_audit",
        "artifact_schema_version": SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION,
        "scorer_audit_run_id": "scorer_audit_001",
        "created_at": "2026-07-10T00:00:00Z",
        "git_sha_or_unknown": "deadbeef",
        "runtime_version": HARNESS_AUDIT_RUNTIME_VERSION,
        "runtime_provenance": _runtime_provenance(),
        "scorer_audit_case_schema_version": SCORER_AUDIT_CASE_SCHEMA_VERSION,
        "scorer_audit_record_schema_version": SCORER_AUDIT_RECORD_SCHEMA_VERSION,
        "task_hash_report_schema_version": TASK_HASH_REPORT_SCHEMA_VERSION,
        "scorer_attempt_artifact_schema_version": (
            SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION
        ),
        "summary": _summary("scorer"),
        "artifacts": dict(SCORER_AUDIT_ARTIFACT_REFS),
    }


def _agent_manifest() -> dict[str, object]:
    return {
        "artifact_type": "agent_task_audit",
        "artifact_schema_version": AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION,
        "agent_task_audit_run_id": "agent_task_audit_001",
        "created_at": "2026-07-10T00:00:00Z",
        "git_sha_or_unknown": "deadbeef",
        "runtime_version": HARNESS_AUDIT_RUNTIME_VERSION,
        "runtime_provenance": _runtime_provenance(),
        "agent_task_audit_case_schema_version": (AGENT_TASK_AUDIT_CASE_SCHEMA_VERSION),
        "agent_task_audit_record_schema_version": (
            AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION
        ),
        "task_hash_report_schema_version": TASK_HASH_REPORT_SCHEMA_VERSION,
        "agent_attempt_artifact_schema_version": (
            AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION
        ),
        "summary": _summary("agent"),
        "artifacts": dict(AGENT_TASK_AUDIT_ARTIFACT_REFS),
    }


def test_standalone_layer_manifests_accept_current_contracts() -> None:
    scorer = ScorerAuditManifest.model_validate(_scorer_manifest())
    agent = AgentTaskAuditManifest.model_validate(_agent_manifest())

    assert scorer.summary.audit_layer == "scorer"
    assert agent.summary.audit_layer == "agent"
    assert scorer.summary.artifact_payload_hash.startswith("xxh64:")
    assert agent.summary.artifact_payload_hash.startswith("xxh64:")


@pytest.mark.parametrize(
    ("manifest_factory", "model", "wrong_layer"),
    [
        (_scorer_manifest, ScorerAuditManifest, "agent"),
        (_agent_manifest, AgentTaskAuditManifest, "scorer"),
    ],
)
def test_standalone_layer_manifests_reject_cross_layer_summaries(
    manifest_factory: Callable[[], dict[str, object]],
    model: type[BaseModel],
    wrong_layer: str,
) -> None:
    payload = manifest_factory()
    summary = payload["summary"]
    assert isinstance(summary, dict)
    summary["audit_layer"] = wrong_layer

    with pytest.raises(ValidationError, match="summary must describe"):
        model.model_validate(payload)


def test_standalone_layer_manifests_require_exact_payload_refs() -> None:
    payload = _scorer_manifest()
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, dict)
    artifacts["results"] = "other.jsonl"

    with pytest.raises(ValidationError, match="artifact refs must be canonical"):
        ScorerAuditManifest.model_validate(payload)


def test_standalone_layer_manifest_loaders_accept_current_contracts(
    tmp_path: Path,
) -> None:
    scorer_path = tmp_path / "scorer.json"
    agent_path = tmp_path / "agent.json"
    scorer_path.write_text(json.dumps(_scorer_manifest()))
    agent_path.write_text(json.dumps(_agent_manifest()))

    assert isinstance(load_scorer_audit_manifest(scorer_path), ScorerAuditManifest)
    assert isinstance(
        load_agent_task_audit_manifest(agent_path),
        AgentTaskAuditManifest,
    )
