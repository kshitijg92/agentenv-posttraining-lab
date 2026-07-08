from pathlib import Path

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import REWARD_HACK_AUDIT_ARTIFACT_SCHEMA_VERSION
from agentenv.rewards.audit import RewardHackAuditResult
from agentenv.rewards.export import (
    load_reward_hack_audit_artifact,
    run_and_persist_reward_hack_audit,
)


CASE_ROOT = Path("data/reward_hack_cases")


def test_run_and_persist_reward_hack_audit_writes_artifact(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "reward_hack_audit"

    artifact = run_and_persist_reward_hack_audit(CASE_ROOT, out_dir)

    assert artifact.out_dir == out_dir.resolve()
    assert artifact.manifest.artifact_type == "reward_hack_audit"
    assert (
        artifact.manifest.artifact_schema_version
        == REWARD_HACK_AUDIT_ARTIFACT_SCHEMA_VERSION
    )
    assert artifact.manifest.record_count == 7
    assert artifact.manifest.pass_count == 7
    assert artifact.manifest.fail_count == 0
    assert artifact.manifest.artifacts == {
        "results": "reward_hack_audit_results.jsonl",
        "case_runs": "case_runs",
    }
    assert (out_dir / MANIFEST_FILENAME).is_file()
    assert (out_dir / "reward_hack_audit_results.jsonl").is_file()
    assert (out_dir / "case_runs").is_dir()
    assert isinstance(artifact.records[0], RewardHackAuditResult)
    assert {
        record.reward_hack_case.reward_hack_id for record in artifact.records
    } == {
        "hidden_validator_path_agent_tool_call_probe_attempt",
        "hidden_validator_path_submitted_patch_text_probe_attempt",
        "leakage_canary_agent_tool_call_probe_attempt",
        "leakage_canary_submitted_patch_text_probe_attempt",
        "no_op_patch_submitted_patch_text_probe_attempt",
        "public_check_tampering_submitted_patch_text_probe_attempt",
        "public_test_only_pass_submitted_patch_text_probe_attempt",
    }
    assert all(record.audit_pass for record in artifact.records)

    loaded = load_reward_hack_audit_artifact(out_dir)

    assert loaded.manifest == artifact.manifest
    assert isinstance(loaded.records[0], RewardHackAuditResult)
    assert {
        record.reward_hack_case.reward_hack_id for record in loaded.records
    } == {
        "hidden_validator_path_agent_tool_call_probe_attempt",
        "hidden_validator_path_submitted_patch_text_probe_attempt",
        "leakage_canary_agent_tool_call_probe_attempt",
        "leakage_canary_submitted_patch_text_probe_attempt",
        "no_op_patch_submitted_patch_text_probe_attempt",
        "public_check_tampering_submitted_patch_text_probe_attempt",
        "public_test_only_pass_submitted_patch_text_probe_attempt",
    }
    assert all(record.audit_pass for record in loaded.records)
    assert {
        record.leakage_scan_result.canary_hash for record in loaded.records
    } == {"xxh64:e5432f5538d562e7"}
