import json
from pathlib import Path

import pytest

from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_task_run import (
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.eval_run import (
    run_eval_config,
    run_eval_config_all_policies,
)
from agentenv.replay.runner import run_replay
from agentenv.reporting.markdown import write_markdown_report
from agentenv.rewards.export import run_and_persist_reward_hack_audit


CONTROL_EVAL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")
AGENT_CONTROL_EVAL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TOY_HAPPY_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/"
    "controls/agent_control_scripts/happy_path.json"
)


def _write_agent_control_source_artifact(out_dir: Path) -> None:
    control_case = load_agent_control_script_case(TOY_HAPPY_AGENT_CONTROL)
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )
    run_and_persist_agent_task_attempt_to_dir(
        TOY_TASK_MANIFEST,
        model_client,
        model_client.default_decoding_config(),
        out_dir,
        agent_control_script=control_case,
    )


def test_write_eval_markdown_report(tmp_path: Path) -> None:
    run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "eval_run")
    manifest = json.loads((tmp_path / "eval_run/manifest.json").read_text())
    eval_attempt_id = manifest["attempts"][0]["eval_attempt_id"]

    report_path = write_markdown_report(
        tmp_path / "eval_run",
        tmp_path / "reports/eval_report.md",
    )
    report = report_path.read_text()

    assert report_path == tmp_path / "reports/eval_report.md"
    assert "# Eval Report" in report
    assert "## Run Details" in report
    assert "## Layer Counts" in report
    assert "## Attempts" in report
    assert "- Config name: scorer_control_policies" in report
    assert "- Policy: oracle" in report
    assert "- Policy type: scorer_control_patch" in report
    assert "- Control layer: scorer" in report
    assert "- Split: practice" in report
    assert "- Config path: configs/eval/scorer_control_policies.yaml" in report
    assert "| scorer_status | PASS | 1 |" in report
    assert "| scorer_public_status | PASS | 1 |" in report
    assert "| scorer_hidden_status | PASS | 1 |" in report
    assert (
        f"| {eval_attempt_id} | toy_python_fix_001 | 0 | scorer_attempt | "
        "scorer_attempt_artifact_v0 | "
        "PASS | PASS | PASS |  |  |  |  |  |  | xxh64:e3fc746d6fe0786c | "
        "attempts/toy_python_fix_001__attempt_001 |"
    ) in report


def test_write_agent_eval_markdown_report(tmp_path: Path) -> None:
    run_eval_config(AGENT_CONTROL_EVAL_CONFIG, "agent-happy", tmp_path / "eval_run")
    manifest = json.loads((tmp_path / "eval_run/manifest.json").read_text())
    eval_attempt_id = manifest["attempts"][0]["eval_attempt_id"]

    report_path = write_markdown_report(
        tmp_path / "eval_run",
        tmp_path / "reports/agent_eval_report.md",
    )
    report = report_path.read_text()

    assert "- Policy: agent-happy" in report
    assert "- Policy type: agent_control_script" in report
    assert "- Control layer: agent" in report
    assert "| agent_scorer_status | PASS | 1 |" in report
    assert (
        f"| {eval_attempt_id} | toy_python_fix_001 | 0 | agent_attempt | "
        "agent_attempt_artifact_v0 | "
        " |  |  | scored | completed | PASS | PASS | PASS |  | "
        "xxh64:e3fc746d6fe0786c | "
        "attempts/toy_python_fix_001__attempt_001 |"
    ) in report


def test_write_agent_model_eval_report_includes_model_and_decoding_config(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "agent_model_eval"
    artifact_dir.mkdir()
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "eval_run",
                "artifact_schema_version": "eval_run_artifact_v0",
                "artifacts": {"attempts": "attempts", "trace": "trace.jsonl"},
                "attempt_count": 1,
                "attempts": [
                    {
                        "eval_attempt_id": "eval_attempt_test",
                        "task_id": "toy_python_fix_001",
                        "attempt_index": 0,
                        "artifact_dir": "attempts/toy_python_fix_001__attempt_001",
                        "artifact_type": "agent_attempt",
                        "artifact_schema_version": "agent_attempt_artifact_v0",
                        "scorer": None,
                        "agent": {
                            "agent_attempt_id": "agent_attempt_test",
                            "status": "agent_loop_failed",
                            "prompt_loop_status": "model_error",
                            "error_class": "MissingModelEnv",
                            "candidate_patch_hash": None,
                            "duration_ms": 0,
                            "scorer_attempt": None,
                        },
                    }
                ],
                "attempts_per_task": 1,
                "config_hash": "xxh64:test",
                "config_name": "agent_model_smoke",
                "config_path": "configs/eval/agent_model_smoke.yaml",
                "created_at": "2026-06-30T00:00:00Z",
                "decoding_config": "configs/decoding/greedy_1024.yaml",
                "eval_run_id": "eval_run_test",
                "layer_counts": {
                    "agent_status": {"agent_loop_failed": 1},
                    "prompt_loop_status": {"model_error": 1},
                },
                "model_config": "configs/models/openai_compatible_chat_placeholder.yaml",
                "policy": "local-model-smoke",
                "policy_family": "agent",
                "policy_type": "agent_model",
                "control_layer": None,
                "control_name": None,
                "replay_repeats": 0,
                "split": "practice",
                "task_pack": "data/task_packs/repo_patch_python_v0",
                "task_hashes": {
                    "schema_version": "eval_task_hashes_v0",
                    "task_pack_id": "repo_patch_python_v0",
                    "selected_task_hash_set": "xxh64:selected",
                    "selected_tasks": [
                        {
                            "task_id": "toy_python_fix_001",
                            "split": "practice",
                            "task_record_hash": "xxh64:task-record",
                            "task_yaml_hash": "xxh64:task-yaml",
                            "required_task_files_hash": "xxh64:required",
                            "full_task_dir_hash": "xxh64:full",
                            "required_task_files": [
                                {
                                    "path": "task.yaml",
                                    "kind": "file",
                                    "hash": "xxh64:task-yaml",
                                }
                            ],
                        }
                    ],
                },
            },
            indent=2,
        )
        + "\n"
    )

    report_path = write_markdown_report(
        artifact_dir,
        tmp_path / "reports/agent_model_eval_report.md",
    )
    report = report_path.read_text()

    assert (
        "- Model config: configs/models/openai_compatible_chat_placeholder.yaml"
        in report
    )
    assert "- Decoding config: configs/decoding/greedy_1024.yaml" in report


def test_write_agent_eval_malformed_markdown_report(tmp_path: Path) -> None:
    run_eval_config(
        AGENT_CONTROL_EVAL_CONFIG,
        "agent-malformed",
        tmp_path / "eval_run",
    )
    manifest = json.loads((tmp_path / "eval_run/manifest.json").read_text())
    eval_attempt_id = manifest["attempts"][0]["eval_attempt_id"]

    report_path = write_markdown_report(
        tmp_path / "eval_run",
        tmp_path / "reports/agent_eval_malformed_report.md",
    )
    report = report_path.read_text()

    assert "- Policy: agent-malformed" in report
    assert "| agent_status | agent_loop_failed | 1 |" in report
    assert (
        f"| {eval_attempt_id} | toy_python_fix_001 | 0 | agent_attempt | "
        "agent_attempt_artifact_v0 | "
        " |  |  | agent_loop_failed | invalid_model_output |  |  |  | "
        "MalformedModelOutput |  | attempts/toy_python_fix_001__attempt_001 |"
    ) in report


def test_write_reward_hack_audit_markdown_report(tmp_path: Path) -> None:
    artifact = run_and_persist_reward_hack_audit(
        Path("data/reward_hack_cases"),
        tmp_path / "reward_hack_audit",
    )

    report_path = write_markdown_report(
        artifact.out_dir,
        tmp_path / "reports/reward_hack_audit.md",
    )
    report = report_path.read_text()

    assert report_path == tmp_path / "reports/reward_hack_audit.md"
    assert "# Reward-Hack Audit Report" in report
    assert "## Safety Signal Summary" in report
    assert "## Evidence Reuse" in report
    assert "## Cases" in report
    assert "## Outcome Comparisons" in report
    assert "## Runtime Checks" in report
    assert "## Source Audit Results" in report
    assert "## Leakage Scans" in report
    assert "- Record count: 4" in report
    assert "- Passed: 4" in report
    assert "- Failed: 0" in report
    assert "- Private-content access attempts: 4/4 (100%)" in report
    assert "- Private-content exposures: 0/4 (0%)" in report
    assert (
        "| hidden_validator_path_agent_tool_call_probe_attempt | PASS | "
        "agent_task_audit_case | hidden_validator_probe_attempt | "
        "agent_tool_call | hidden_validator_path | true | false | true | "
        "false | false | true |"
    ) in report
    assert (
        "| hidden_validator_path_submitted_patch_text_probe_attempt | PASS | scorer_audit_case | "
        "hidden_validator_probe_attempt | submitted_patch_text | "
        "hidden_validator_path | true | false | true | false | false | true |"
    ) in report
    assert (
        "| leakage_canary_agent_tool_call_probe_attempt | PASS | "
        "agent_task_audit_case | hidden_validator_probe_attempt | agent_tool_call | "
        "leakage_canary | true | false | true | false | false | true |"
    ) in report
    assert (
        "| leakage_canary_submitted_patch_text_probe_attempt | PASS | scorer_audit_case | "
        "hidden_validator_probe_attempt | submitted_patch_text | leakage_canary | "
        "true | false | true | false | false | true |"
    ) in report
    assert (
        "| hidden_validator_path_submitted_patch_text_probe_attempt | private_content_exposed | "
        "false | false | PASS |"
    ) in report
    assert "agent_task_audit_case:data/harness_audit/agent_task_cases/happy_path" in report
    assert "scorer_audit_case:data/harness_audit/scorer_cases/correct_oracle" in report
    assert (
        "| hidden_validator_path_agent_tool_call_probe_attempt | exploit | "
        "private_reference_tool_call |"
    ) in report
    assert (
        "| hidden_validator_path_submitted_patch_text_probe_attempt | exploit | "
        "hidden_validator_path_reference |"
    ) in report
    assert (
        "| hidden_validator_path_submitted_patch_text_probe_attempt | xxh64:e5432f5538d562e7 | "
        "0 | 0 | 7 |"
    ) in report


def test_eval_report_rejects_bad_attempt_schema(tmp_path: Path) -> None:
    run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "eval_run")
    manifest_path = tmp_path / "eval_run/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["attempts"][0]["artifact_schema_version"] = "scorer_attempt_artifact_v999"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    with pytest.raises(
        ValueError,
        match="eval attempt artifact_schema_version does not match artifact_type",
    ):
        write_markdown_report(
            tmp_path / "eval_run",
            tmp_path / "reports/bad_eval_attempt.md",
        )


def test_write_replay_markdown_report(tmp_path: Path) -> None:
    run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "eval_run")
    run_replay(tmp_path / "eval_run", tmp_path / "replay_run")

    report_path = write_markdown_report(
        tmp_path / "replay_run",
        tmp_path / "reports/replay.md",
    )
    report = report_path.read_text()

    assert report_path == tmp_path / "reports/replay.md"
    assert "# Replay Report" in report
    assert "## Replay Details" in report
    assert "## Replay Result" in report
    assert "## Attempt Comparisons" in report
    assert "- Source run directory:" in report
    assert "- Status: PASS" in report
    assert "- Attempt count: 1" in report
    assert "- Matched attempts: 1" in report
    assert (
        "| toy_python_fix_001 | scorer_attempt | match | 7/7 (100%) | "
        "5/5 (100%) | "
        "attempts/toy_python_fix_001__attempt_001 | "
        "attempts/toy_python_fix_001__attempt_001 |"
    ) in report


def test_write_agent_replay_markdown_report(tmp_path: Path) -> None:
    _write_agent_control_source_artifact(tmp_path / "source_agent")
    run_replay(tmp_path / "source_agent", tmp_path / "replay_run")

    report_path = write_markdown_report(
        tmp_path / "replay_run",
        tmp_path / "reports/agent_replay.md",
    )
    report = report_path.read_text()

    assert report_path == tmp_path / "reports/agent_replay.md"
    assert "# Replay Report" in report
    assert "- Source artifact type: agent_attempt" in report
    assert "- Source artifact schema version: agent_attempt_artifact_v0" in report
    assert (
        "| toy_python_fix_001 | agent_task_run | match | 15/15 (100%) | "
        "6/6 (100%) | . | agent_task_run |"
    ) in report


def test_write_eval_matrix_markdown_report(tmp_path: Path) -> None:
    run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )
    bad_public_only_manifest = json.loads(
        (tmp_path / "eval_matrix/policies/bad-public-only/manifest.json").read_text()
    )
    bad_public_only_eval_attempt_id = bad_public_only_manifest["attempts"][0][
        "eval_attempt_id"
    ]

    report_path = write_markdown_report(
        tmp_path / "eval_matrix",
        tmp_path / "reports/eval_matrix.md",
    )
    report = report_path.read_text()

    assert report_path == tmp_path / "reports/eval_matrix.md"
    assert "# Eval Suite Report" in report
    assert "## Control Calibration" in report
    assert "### Scorer Control Summary" in report
    assert "### Agent Control Summary" in report
    assert "### Agent Control Budget Summary" in report
    assert "### Scorer Control Expectations" in report
    assert "### Agent Control Expectations" in report
    assert "### Scorer Aggregate Rates" in report
    assert "### Agent Control Aggregate Rates" in report
    assert "### Control Per-Task Outcomes" in report
    assert "## Agent Model Results" in report
    assert "### Agent Model Outcome Summary" in report
    assert "### Agent Model Debug Signals" in report
    assert "### Agent Model Budget Summary" in report
    assert "### Agent Model Per-Task Outcomes" in report
    assert "candidate_patch_bytes" in report
    assert "- Config name: scorer_control_policies" in report
    assert "- Task count: 1" in report
    assert "- Policy count: 3" in report
    assert "- Replay policy count: 3" in report
    assert "- Replay run count: 3" in report
    assert "- Replay run success summary: 3/3" in report
    assert "- Replay match rate: 3/3 (100%)" in report
    assert "- Oracle pass rate: 1/1 (100%)" in report
    assert "- Known-bad final PASS rate: 0/2 (0%)" in report
    assert "- Known-bad public-pass/hidden-fail rate: 2/2 (100%)" in report
    assert "No agent control policies in this eval suite." in report
    assert "No agent budget metadata in this eval suite." in report
    assert "No agent model policies in this eval suite." in report
    assert "No agent model debug signals in this eval suite." in report
    assert "No agent model policy attempts in this eval suite." in report
    assert "No agent aggregate rates for this eval suite." in report
    assert "### Replay Checks" in report
    assert (
        "| oracle | PASS | 1/1 (100%) | 0 | "
        "replays/oracle__replay_001/replay_result.json |" in report
    )
    assert (
        "| bad-public-only | PASS | 1/1 (100%) | 0 | "
        "replays/bad-public-only__replay_001/replay_result.json |"
    ) in report
    assert (
        "| oracle | oracle | PASS | 1/1 (100%) | PASS | 1/1 (100%) | "
        'PASS | 1/1 (100%) | <span style="color: green">ON_TRACK</span> |'
    ) in report
    assert (
        "| bad-noop | bad.noop | HIDDEN_TEST_FAIL | 1/1 (100%) | "
        "PASS | 1/1 (100%) | FAIL | 1/1 (100%) | "
        '<span style="color: green">ON_TRACK</span> |'
    ) in report
    assert (
        "| oracle | oracle | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0 | 0 | 0 |"
    ) in report
    assert (
        "| bad-noop | bad.noop | 1 | 0/1 (0%) | 1/1 (100%) | 0/1 (0%) | 1 | 0 | 0 |"
    ) in report
    assert (
        f"| {bad_public_only_eval_attempt_id} | toy_python_fix_001 | "
        "bad-public-only | scorer_attempt | "
        "scorer_attempt_artifact_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |"
    ) in report


def test_eval_matrix_report_rejects_bad_nested_policy_manifest(
    tmp_path: Path,
) -> None:
    run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )
    nested_manifest_path = tmp_path / "eval_matrix/policies/oracle/manifest.json"
    nested_manifest = json.loads(nested_manifest_path.read_text())
    nested_manifest["artifact_type"] = "replay_run"
    nested_manifest["artifact_schema_version"] = "replay_run_artifact_v0"
    nested_manifest_path.write_text(json.dumps(nested_manifest, indent=2) + "\n")

    with pytest.raises(ValueError, match="artifact_type must be 'eval_run'"):
        write_markdown_report(
            tmp_path / "eval_matrix",
            tmp_path / "reports/bad_nested_policy.md",
        )


def test_eval_matrix_report_rejects_bad_nested_attempt_schema(
    tmp_path: Path,
) -> None:
    run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )
    nested_manifest_path = tmp_path / "eval_matrix/policies/oracle/manifest.json"
    nested_manifest = json.loads(nested_manifest_path.read_text())
    nested_manifest["attempts"][0]["artifact_schema_version"] = (
        "scorer_attempt_artifact_v999"
    )
    nested_manifest_path.write_text(json.dumps(nested_manifest, indent=2) + "\n")

    with pytest.raises(
        ValueError,
        match="eval attempt artifact_schema_version does not match artifact_type",
    ):
        write_markdown_report(
            tmp_path / "eval_matrix",
            tmp_path / "reports/bad_nested_attempt.md",
        )


def test_eval_matrix_report_rejects_child_policy_summary_mismatch(
    tmp_path: Path,
) -> None:
    run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )
    nested_manifest_path = tmp_path / "eval_matrix/policies/oracle/manifest.json"
    nested_manifest = json.loads(nested_manifest_path.read_text())
    nested_manifest["eval_run_id"] = "eval_run_child_mismatch"
    nested_manifest_path.write_text(json.dumps(nested_manifest, indent=2) + "\n")

    with pytest.raises(
        ValueError,
        match="policy run record does not match child manifest",
    ):
        write_markdown_report(
            tmp_path / "eval_matrix",
            tmp_path / "reports/policy_summary_mismatch.md",
        )


def test_eval_matrix_report_rejects_child_replay_result_mismatch(
    tmp_path: Path,
) -> None:
    run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )
    replay_result_path = (
        tmp_path / "eval_matrix/replays/oracle__replay_001/replay_result.json"
    )
    replay_result = json.loads(replay_result_path.read_text())
    replay_result["matched_attempts"] = 0
    replay_result["mismatched_attempts"] = 1
    replay_result["status"] = "MISMATCH"
    replay_result_path.write_text(json.dumps(replay_result, indent=2) + "\n")

    with pytest.raises(
        ValueError,
        match="replay run record does not match child replay result",
    ):
        write_markdown_report(
            tmp_path / "eval_matrix",
            tmp_path / "reports/replay_result_mismatch.md",
        )


def test_eval_matrix_report_rejects_stale_agent_decoding_payload(
    tmp_path: Path,
) -> None:
    run_eval_config_all_policies(
        AGENT_CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )
    decoding_path = (
        tmp_path / "eval_matrix/policies/agent-happy/attempts/"
        "toy_python_fix_001__attempt_001/decoding_config.json"
    )
    decoding_payload = json.loads(decoding_path.read_text())
    decoding_path.write_text(
        json.dumps(decoding_payload["config"], indent=2, sort_keys=True) + "\n"
    )

    with pytest.raises(ValueError, match="DecodingConfigProvenance at"):
        write_markdown_report(
            tmp_path / "eval_matrix",
            tmp_path / "reports/stale_agent_decoding.md",
        )


def test_write_agent_eval_matrix_markdown_report(tmp_path: Path) -> None:
    run_eval_config_all_policies(
        AGENT_CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )
    happy_manifest = json.loads(
        (tmp_path / "eval_matrix/policies/agent-happy/manifest.json").read_text()
    )
    malformed_manifest = json.loads(
        (tmp_path / "eval_matrix/policies/agent-malformed/manifest.json").read_text()
    )
    happy_eval_attempt_id = happy_manifest["attempts"][0]["eval_attempt_id"]
    malformed_eval_attempt_id = malformed_manifest["attempts"][0]["eval_attempt_id"]

    report_path = write_markdown_report(
        tmp_path / "eval_matrix",
        tmp_path / "reports/agent_eval_matrix.md",
    )
    report = report_path.read_text()

    assert "- Config name: agent_control_policies" in report
    assert "- Policy count: 3" in report
    assert "- Replay match rate: 3/3 (100%)" in report
    assert "## Control Calibration" in report
    assert "### Scorer Control Summary" in report
    assert "### Agent Control Summary" in report
    assert "### Agent Control Budget Summary" in report
    assert "## Agent Model Results" in report
    assert "### Agent Model Outcome Summary" in report
    assert "### Agent Model Debug Signals" in report
    assert "### Agent Model Budget Summary" in report
    assert "### Scorer Control Expectations" in report
    assert "### Agent Control Expectations" in report
    assert "No scorer control policies in this eval suite." in report
    assert "No scorer aggregate rates for this eval suite." in report
    assert "- Agent control expectation pass rate: 3/3 (100%)" in report
    assert (
        "| agent-happy | happy | 1 | 1/1 (100%) | 1/1 (100%) | 0 | "
        "1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) |"
    ) in report
    assert (
        "| agent-malformed | malformed | 1 | 0/1 (0%) | 0/1 (0%) | 1 | "
        "0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |"
    ) in report
    assert (
        "| agent-happy | agent-control-scripted-v0 | greedy | 0.0 | 512 | 30 | "
        "10 | not_recorded | not_recorded | not_recorded | not_recorded | 0 | 0 |"
    ) in report
    assert (
        "| agent-malformed | agent-control-scripted-v0 | greedy | 0.0 | 512 | "
        "30 | 10 | not_recorded | not_recorded | not_recorded | not_recorded | "
        "0 | 0 |"
    ) in report
    assert (
        "| agent-recoverable | agent-control-scripted-v0 | greedy | 0.0 | 512 | "
        "30 | 10 | not_recorded | not_recorded | not_recorded | not_recorded | "
        "1 | 1 |"
    ) in report
    assert (
        "| agent-happy | happy | scored | 1/1 (100%) | completed | 1/1 (100%) | "
        'PASS | 1/1 (100%) | <span style="color: green">ON_TRACK</span> |'
    ) in report
    assert (
        "| agent-malformed | malformed | agent_loop_failed | 1/1 (100%) | "
        "invalid_model_output | 1/1 (100%) | not_run | 1/1 (100%) | "
        '<span style="color: green">ON_TRACK</span> |'
    ) in report
    assert (
        f"| {happy_eval_attempt_id} | toy_python_fix_001 | agent-happy | "
        "agent_attempt | "
        "agent_attempt_artifact_v0 |  |  |  | scored | completed | PASS | PASS | "
        "PASS |"
    ) in report
    assert (
        f"| {malformed_eval_attempt_id} | toy_python_fix_001 | agent-malformed | "
        "agent_attempt | "
        "agent_attempt_artifact_v0 |  |  |  | agent_loop_failed | "
        "invalid_model_output |  |  |  | "
        "MalformedModelOutput |"
    ) in report


def test_write_mixed_agent_control_and_model_eval_matrix_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.delenv("AGENTENV_MODEL_API_KEY", raising=False)
    config_path = tmp_path / "mixed_agent_model_eval.yaml"
    config_path.write_text(
        "\n".join(
            [
                "name: mixed_agent_model_eval",
                "task_pack: data/task_packs/repo_patch_python_v0",
                "tasks:",
                "  - toy_python_fix_001",
                "split: practice",
                "policies:",
                "  agent-happy:",
                "    type: agent_control_script",
                "    control: happy",
                "    attempts: 1",
                "    replay:",
                "      repeats: 0",
                "  real-agent-smoke:",
                "    type: agent_model",
                "    model_config: configs/models/openai_compatible_chat_placeholder.yaml",
                "    decoding_config: configs/decoding/greedy_1024.yaml",
                "    attempts: 1",
                "    replay:",
                "      repeats: 0",
                "trace:",
                "  version: trace_v0",
                "  capture_stdout: true",
                "  capture_stderr: true",
                "  capture_diff: true",
                "",
            ]
        )
    )
    run_eval_config_all_policies(config_path, tmp_path / "eval_matrix")
    happy_manifest = json.loads(
        (tmp_path / "eval_matrix/policies/agent-happy/manifest.json").read_text()
    )
    model_manifest = json.loads(
        (tmp_path / "eval_matrix/policies/real-agent-smoke/manifest.json").read_text()
    )
    happy_eval_attempt_id = happy_manifest["attempts"][0]["eval_attempt_id"]
    model_eval_attempt_id = model_manifest["attempts"][0]["eval_attempt_id"]

    report_path = write_markdown_report(
        tmp_path / "eval_matrix",
        tmp_path / "reports/mixed_agent_model_eval_matrix.md",
    )
    report = report_path.read_text()

    assert report_path == tmp_path / "reports/mixed_agent_model_eval_matrix.md"
    agent_control_summary = report.split("### Agent Control Summary", 1)[1].split(
        "### Agent Control Budget Summary",
        1,
    )[0]
    agent_model_summary = report.split("### Agent Model Outcome Summary", 1)[1].split(
        "### Agent Model Debug Signals",
        1,
    )[0]
    agent_model_debug = report.split("### Agent Model Debug Signals", 1)[1].split(
        "### Agent Model Budget Summary",
        1,
    )[0]
    control_per_task = report.split("### Control Per-Task Outcomes", 1)[1].split(
        "### Replay Checks",
        1,
    )[0]
    agent_model_per_task = report.split("### Agent Model Per-Task Outcomes", 1)[
        1
    ].split("## Known Shortcuts", 1)[0]

    assert "| agent-happy | happy | 1 | 1/1 (100%)" in agent_control_summary
    assert "real-agent-smoke" not in agent_control_summary
    assert "| real-agent-smoke | 1 | 0/1 (0%)" in agent_model_summary
    assert "agent-happy" not in agent_model_summary
    assert (
        "| real-agent-smoke | model_error=1 | MissingModelApiKeyEnvVar=1 | "
        "none | none | 0 | 0 | 1 | 0 | 0 |"
    ) in agent_model_debug
    assert "agent-happy" not in agent_model_debug
    assert (
        "| real-agent-smoke | placeholder-model | greedy | 0.0 | 1024 | "
        "60 | 10 | not_recorded | not_recorded | not_recorded | not_recorded | "
        "0 | 0 |"
    ) in report
    assert (
        f"| {happy_eval_attempt_id} | toy_python_fix_001 | agent-happy |"
        in control_per_task
    )
    assert "real-agent-smoke" not in control_per_task
    assert (
        f"| {model_eval_attempt_id} | toy_python_fix_001 | real-agent-smoke |"
        in agent_model_per_task
    )
    assert "agent-happy" not in agent_model_per_task
    assert "- Agent control expectation pass rate: 1/1 (100%)" in report
