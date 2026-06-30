import json
from pathlib import Path

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
        "| toy_python_fix_001 | 0 | run_artifacts_v0 | PASS | PASS | PASS |  |  | "
        " |  |  |  | xxh64:e3fc746d6fe0786c | "
        "attempts/toy_python_fix_001__attempt_001 |"
    ) in report


def test_write_agent_eval_markdown_report(tmp_path: Path) -> None:
    run_eval_config(AGENT_CONTROL_EVAL_CONFIG, "agent-happy", tmp_path / "eval_run")

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
        "| toy_python_fix_001 | 0 | agent_task_run_artifacts_v0 |  |  |  | scored | "
        "completed | PASS | PASS | PASS |  | xxh64:e3fc746d6fe0786c | "
        "attempts/toy_python_fix_001__attempt_001 |"
    ) in report


def test_write_agent_model_eval_report_includes_model_and_decoding_config(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "agent_model_eval"
    artifact_dir.mkdir()
    (artifact_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "artifact_version": "eval_run_v0",
                "artifacts": {"attempts": "attempts", "trace": "trace.jsonl"},
                "attempt_count": 0,
                "attempts": [],
                "attempts_per_task": 1,
                "config_hash": "xxh64:test",
                "config_name": "agent_model_smoke",
                "config_path": "configs/eval/agent_model_smoke.yaml",
                "created_at": "2026-06-30T00:00:00Z",
                "decoding_config": "configs/decoding/greedy_1024.yaml",
                "eval_run_id": "eval_test",
                "layer_counts": {},
                "model_config": "configs/models/openai_compatible_chat_placeholder.yaml",
                "policy": "local-model-smoke",
                "policy_family": "agent",
                "policy_type": "agent_model",
                "replay_repeats": 0,
                "split": "practice",
                "task_pack": "data/task_packs/repo_patch_python_v0",
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

    assert "- Model config: configs/models/openai_compatible_chat_placeholder.yaml" in report
    assert "- Decoding config: configs/decoding/greedy_1024.yaml" in report


def test_write_agent_eval_malformed_markdown_report(tmp_path: Path) -> None:
    run_eval_config(
        AGENT_CONTROL_EVAL_CONFIG,
        "agent-malformed",
        tmp_path / "eval_run",
    )

    report_path = write_markdown_report(
        tmp_path / "eval_run",
        tmp_path / "reports/agent_eval_malformed_report.md",
    )
    report = report_path.read_text()

    assert "- Policy: agent-malformed" in report
    assert "| agent_status | agent_loop_failed | 1 |" in report
    assert (
        "| toy_python_fix_001 | 0 | agent_task_run_artifacts_v0 |  |  |  | "
        "agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput | "
        " | attempts/toy_python_fix_001__attempt_001 |"
    ) in report


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
    assert "- Source artifact version: agent_task_run_artifacts_v0" in report
    assert (
        "| toy_python_fix_001 | agent_task_run | match | 15/15 (100%) | "
        "6/6 (100%) | . | agent_task_run |"
    ) in report


def test_write_eval_matrix_markdown_report(tmp_path: Path) -> None:
    run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )

    report_path = write_markdown_report(
        tmp_path / "eval_matrix",
        tmp_path / "reports/eval_matrix.md",
    )
    report = report_path.read_text()

    assert report_path == tmp_path / "reports/eval_matrix.md"
    assert "# Eval Matrix Report" in report
    assert "## Scorer Policy Summary" in report
    assert "## Agent Policy Summary" in report
    assert "## Agent Model And Budget Summary" in report
    assert "## Calibration Checks" in report
    assert "### Scorer Control Expectations" in report
    assert "### Agent Control Expectations" in report
    assert "### Scorer Aggregate Rates" in report
    assert "### Agent Aggregate Rates" in report
    assert "## Per-Task Outcomes" in report
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
    assert "No agent policies in this eval matrix." in report
    assert "No agent model or budget metadata in this eval matrix." in report
    assert "No agent control policies in this eval matrix." in report
    assert "No agent aggregate rates for this eval matrix." in report
    assert "### Replay Checks" in report
    assert (
        "| oracle | PASS | 1/1 (100%) | 0 | "
        "replays/oracle__replay_001/replay_result.json |"
        in report
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
        "| oracle | oracle | 1 | 1/1 (100%) | 1/1 (100%) | "
        "1/1 (100%) | 0 | 0 | 0 |"
    ) in report
    assert (
        "| bad-noop | bad.noop | 1 | 0/1 (0%) | 1/1 (100%) | "
        "0/1 (0%) | 1 | 0 | 0 |"
    ) in report
    assert (
        "| toy_python_fix_001 | bad-public-only | run_artifacts_v0 | "
        "HIDDEN_TEST_FAIL | PASS | FAIL |"
    ) in report


def test_write_agent_eval_matrix_markdown_report(tmp_path: Path) -> None:
    run_eval_config_all_policies(
        AGENT_CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )

    report_path = write_markdown_report(
        tmp_path / "eval_matrix",
        tmp_path / "reports/agent_eval_matrix.md",
    )
    report = report_path.read_text()

    assert "- Config name: agent_control_policies" in report
    assert "- Policy count: 3" in report
    assert "- Replay match rate: 3/3 (100%)" in report
    assert "## Scorer Policy Summary" in report
    assert "## Agent Policy Summary" in report
    assert "## Agent Model And Budget Summary" in report
    assert "### Scorer Control Expectations" in report
    assert "### Agent Control Expectations" in report
    assert "No scorer policies in this eval matrix." in report
    assert "No scorer control policies in this eval matrix." in report
    assert "No scorer aggregate rates for this eval matrix." in report
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
        "| toy_python_fix_001 | agent-happy | agent_task_run_artifacts_v0 | "
        " |  |  | scored | completed | PASS | PASS | PASS |"
    ) in report
    assert (
        "| toy_python_fix_001 | agent-malformed | agent_task_run_artifacts_v0 | "
        " |  |  | agent_loop_failed | invalid_model_output |  |  |  | "
        "MalformedModelOutput |"
    ) in report
