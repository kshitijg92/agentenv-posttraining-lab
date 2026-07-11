"""Atomic composition of standalone agent-task and scorer audit artifacts."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from agentenv.artifacts.base import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
    resolve_relative_artifact_ref,
)
from agentenv.artifacts.manifests import (
    AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION,
    HARNESS_AUDIT_ARTIFACT_REFS,
    HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
    SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION,
    AgentTaskAuditManifestRef,
    HarnessAuditManifest,
    ScorerAuditManifestRef,
    load_harness_audit_manifest,
)
from agentenv.audits.agent_task import (
    AgentTaskAuditLayerRun,
    load_agent_task_audit_layer,
    run_agent_task_audit_layer,
)
from agentenv.audits.runtime import (
    capture_harness_runtime_provenance,
    git_sha_or_unknown,
    harness_repo_root,
    utc_now_iso,
)
from agentenv.audits.schema import (
    HARNESS_AUDIT_RUNTIME_VERSION,
    derive_harness_audit_status,
)
from agentenv.audits.scorer import (
    ScorerAuditLayerRun,
    load_scorer_audit_layer,
    run_scorer_audit_layer,
)
from agentenv.hashing import hash_file
from agentenv.ids import new_harness_audit_run_id


@dataclass(frozen=True)
class HarnessAuditArtifact:
    out_dir: Path
    manifest: HarnessAuditManifest
    agent_audit: AgentTaskAuditLayerRun
    scorer_audit: ScorerAuditLayerRun


def run_harness_audit(
    *,
    agent_case_root: Path,
    scorer_case_root: Path,
    out_dir: Path,
    repo_root: Path | None = None,
    overwrite: bool = False,
) -> HarnessAuditArtifact:
    root = Path.cwd().resolve() if repo_root is None else repo_root.resolve()
    out_dir = out_dir.resolve()
    prepared_out_dir: Path | None = None
    try:
        prepared_out_dir = prepare_artifact_output_dir(
            out_dir,
            overwrite=overwrite,
        )
        agent_audit = run_agent_task_audit_layer(
            agent_case_root,
            prepared_out_dir / HARNESS_AUDIT_ARTIFACT_REFS["agent_audit"],
            repo_root=root,
        )
        scorer_audit = run_scorer_audit_layer(
            scorer_case_root,
            prepared_out_dir / HARNESS_AUDIT_ARTIFACT_REFS["scorer_audit"],
            repo_root=root,
        )
        runtime_provenance = agent_audit.manifest.runtime_provenance
        if scorer_audit.manifest.runtime_provenance != runtime_provenance:
            raise ValueError(
                "Agent-task and scorer audits used different harness runtimes"
            )
        runtime_root = harness_repo_root()
        if capture_harness_runtime_provenance(runtime_root) != runtime_provenance:
            raise ValueError("Harness runtime changed during aggregate audit execution")

        report_path = prepared_out_dir / HARNESS_AUDIT_ARTIFACT_REFS["report"]
        report_path.write_text(_render_report(agent_audit, scorer_audit))
        agent_manifest_path = agent_audit.out_dir / MANIFEST_FILENAME
        scorer_manifest_path = scorer_audit.out_dir / MANIFEST_FILENAME
        manifest = HarnessAuditManifest(
            artifact_type=ArtifactType.HARNESS_AUDIT,
            artifact_schema_version=HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION,
            harness_audit_run_id=new_harness_audit_run_id(),
            created_at=utc_now_iso(),
            git_sha_or_unknown=git_sha_or_unknown(runtime_root),
            runtime_version=HARNESS_AUDIT_RUNTIME_VERSION,
            runtime_provenance=runtime_provenance,
            status=derive_harness_audit_status(
                agent_audit.summary.status,
                scorer_audit.summary.status,
            ),
            agent_audit=AgentTaskAuditManifestRef(
                artifact_type="agent_task_audit",
                artifact_schema_version=AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION,
                agent_task_audit_run_id=(agent_audit.manifest.agent_task_audit_run_id),
                manifest_path=(
                    f"{HARNESS_AUDIT_ARTIFACT_REFS['agent_audit']}/{MANIFEST_FILENAME}"
                ),
                manifest_hash=hash_file(agent_manifest_path),
                harness_runtime_hash=runtime_provenance.harness_runtime_hash,
                status=agent_audit.summary.status,
            ),
            scorer_audit=ScorerAuditManifestRef(
                artifact_type="scorer_audit",
                artifact_schema_version=SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION,
                scorer_audit_run_id=scorer_audit.manifest.scorer_audit_run_id,
                manifest_path=(
                    f"{HARNESS_AUDIT_ARTIFACT_REFS['scorer_audit']}/{MANIFEST_FILENAME}"
                ),
                manifest_hash=hash_file(scorer_manifest_path),
                harness_runtime_hash=runtime_provenance.harness_runtime_hash,
                status=scorer_audit.summary.status,
            ),
            report_hash=hash_file(report_path),
            artifacts=dict(HARNESS_AUDIT_ARTIFACT_REFS),
        )
        (prepared_out_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n"
        )
        loaded = load_harness_audit_artifact(prepared_out_dir)
        if loaded.manifest != manifest:
            raise ValueError("Persisted harness audit manifest failed exact readback")
        return loaded
    except Exception:
        if prepared_out_dir is not None and prepared_out_dir.exists():
            shutil.rmtree(prepared_out_dir)
        raise


def load_harness_audit_artifact(out_dir: Path) -> HarnessAuditArtifact:
    out_dir = out_dir.resolve()
    manifest = load_harness_audit_manifest(out_dir / MANIFEST_FILENAME)
    agent_dir = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["agent_audit"],
    )
    scorer_dir = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["scorer_audit"],
    )
    agent_manifest_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.agent_audit.manifest_path,
    )
    scorer_manifest_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.scorer_audit.manifest_path,
    )
    _require_hash(
        agent_manifest_path,
        observed=hash_file(agent_manifest_path),
        expected=manifest.agent_audit.manifest_hash,
        label="agent-task audit manifest",
    )
    _require_hash(
        scorer_manifest_path,
        observed=hash_file(scorer_manifest_path),
        expected=manifest.scorer_audit.manifest_hash,
        label="scorer audit manifest",
    )
    agent_audit = load_agent_task_audit_layer(agent_dir)
    scorer_audit = load_scorer_audit_layer(scorer_dir)
    _validate_agent_ref(manifest, agent_audit)
    _validate_scorer_ref(manifest, scorer_audit)
    if agent_audit.manifest.runtime_provenance != manifest.runtime_provenance:
        raise ValueError("Agent-task audit runtime provenance differs from root")
    if scorer_audit.manifest.runtime_provenance != manifest.runtime_provenance:
        raise ValueError("Scorer audit runtime provenance differs from root")

    report_path = resolve_relative_artifact_ref(
        out_dir,
        manifest.artifacts["report"],
    )
    _require_hash(
        report_path,
        observed=hash_file(report_path),
        expected=manifest.report_hash,
        label="harness audit report",
    )
    return HarnessAuditArtifact(
        out_dir=out_dir,
        manifest=manifest,
        agent_audit=agent_audit,
        scorer_audit=scorer_audit,
    )


def _validate_agent_ref(
    root: HarnessAuditManifest,
    layer: AgentTaskAuditLayerRun,
) -> None:
    ref = root.agent_audit
    child = layer.manifest
    observed = (
        child.artifact_type,
        child.artifact_schema_version,
        child.agent_task_audit_run_id,
        child.runtime_provenance.harness_runtime_hash,
        child.summary.status,
    )
    expected = (
        ref.artifact_type,
        ref.artifact_schema_version,
        ref.agent_task_audit_run_id,
        ref.harness_runtime_hash,
        ref.status,
    )
    if observed != expected:
        raise ValueError(
            f"Agent-task audit child ref mismatch: {observed!r} != {expected!r}"
        )


def _validate_scorer_ref(
    root: HarnessAuditManifest,
    layer: ScorerAuditLayerRun,
) -> None:
    ref = root.scorer_audit
    child = layer.manifest
    observed = (
        child.artifact_type,
        child.artifact_schema_version,
        child.scorer_audit_run_id,
        child.runtime_provenance.harness_runtime_hash,
        child.summary.status,
    )
    expected = (
        ref.artifact_type,
        ref.artifact_schema_version,
        ref.scorer_audit_run_id,
        ref.harness_runtime_hash,
        ref.status,
    )
    if observed != expected:
        raise ValueError(
            f"Scorer audit child ref mismatch: {observed!r} != {expected!r}"
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


def _render_report(
    agent_audit: AgentTaskAuditLayerRun,
    scorer_audit: ScorerAuditLayerRun,
) -> str:
    status = derive_harness_audit_status(
        agent_audit.summary.status,
        scorer_audit.summary.status,
    )
    return "\n".join(
        [
            "# Harness Audit",
            "",
            f"- Overall status: {status}",
            f"- Agent-task status: {agent_audit.summary.status}",
            f"- Agent-task records: {agent_audit.summary.record_count}",
            f"- Agent-task mismatches: {agent_audit.summary.mismatched_count}",
            f"- Agent-task audit errors: {agent_audit.summary.audit_error_count}",
            f"- Scorer status: {scorer_audit.summary.status}",
            f"- Scorer records: {scorer_audit.summary.record_count}",
            f"- Scorer mismatches: {scorer_audit.summary.mismatched_count}",
            f"- Scorer audit errors: {scorer_audit.summary.audit_error_count}",
            "",
            "Only overall PASS is eligible to satisfy the harness-audit export gate.",
            "",
        ]
    )
