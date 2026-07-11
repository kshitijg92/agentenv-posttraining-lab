from pathlib import Path

import pytest

import agentenv.audits.runner as harness_runner_module
from agentenv.artifacts.base import MANIFEST_FILENAME
from agentenv.audits.runner import (
    load_harness_audit_artifact,
    run_harness_audit,
)
from agentenv.hashing import hash_file


AGENT_CASE_ROOT = Path("data/harness_audit/agent_task_cases")
SCORER_CASE_ROOT = Path("data/harness_audit/scorer_cases")


def test_run_harness_audit_composes_hash_pinned_child_artifacts(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "harness_audit"

    artifact = run_harness_audit(
        agent_case_root=AGENT_CASE_ROOT,
        scorer_case_root=SCORER_CASE_ROOT,
        out_dir=out_dir,
    )

    assert artifact.out_dir == out_dir.resolve()
    assert artifact.manifest.status == "PASS"
    assert artifact.agent_audit.summary.status == "PASS"
    assert artifact.agent_audit.summary.record_count == 21
    assert artifact.scorer_audit.summary.status == "PASS"
    assert artifact.scorer_audit.summary.record_count == 12
    assert artifact.agent_audit.manifest.runtime_provenance == (
        artifact.manifest.runtime_provenance
    )
    assert artifact.scorer_audit.manifest.runtime_provenance == (
        artifact.manifest.runtime_provenance
    )
    assert artifact.manifest.agent_audit.manifest_hash == hash_file(
        out_dir / "agent/manifest.json"
    )
    assert artifact.manifest.scorer_audit.manifest_hash == hash_file(
        out_dir / "scorer/manifest.json"
    )
    assert (out_dir / MANIFEST_FILENAME).is_file()
    assert (out_dir / "harness_audit.md").is_file()
    assert load_harness_audit_artifact(out_dir) == artifact

    child_manifest = out_dir / "agent/manifest.json"
    child_manifest.write_text(child_manifest.read_text() + "\n")
    with pytest.raises(ValueError, match="agent-task audit manifest hash mismatch"):
        load_harness_audit_artifact(out_dir)


def test_run_harness_audit_removes_partial_root_on_global_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "harness_audit"

    def stage_agent_output(*args: object, **kwargs: object) -> object:
        agent_out = args[1]
        assert isinstance(agent_out, Path)
        agent_out.mkdir()
        (agent_out / "partial.txt").write_text("partial\n")
        return object()

    def fail_scorer_output(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic scorer-layer failure")

    monkeypatch.setattr(
        harness_runner_module,
        "run_agent_task_audit_layer",
        stage_agent_output,
    )
    monkeypatch.setattr(
        harness_runner_module,
        "run_scorer_audit_layer",
        fail_scorer_output,
    )

    with pytest.raises(RuntimeError, match="synthetic scorer-layer failure"):
        run_harness_audit(
            agent_case_root=AGENT_CASE_ROOT,
            scorer_case_root=SCORER_CASE_ROOT,
            out_dir=out_dir,
        )

    assert not out_dir.exists()
