from pathlib import Path

from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig
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
TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TOY_HAPPY_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/"
    "controls/agent_control_scripts/happy_path.json"
)


def _decoding_config() -> DecodingConfig:
    return DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=512,
        timeout_seconds=30,
    )


def _write_agent_control_source_artifact(out_dir: Path) -> None:
    control_case = load_agent_control_script_case(TOY_HAPPY_AGENT_CONTROL)
    decoding_config = _decoding_config()
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )
    run_and_persist_agent_task_attempt_to_dir(
        TOY_TASK_MANIFEST,
        model_client,
        decoding_config,
        out_dir,
    )
    (out_dir / "decoding_config.json").write_text(
        decoding_config.model_dump_json(indent=2) + "\n"
    )
    (out_dir / "agent_control_script.json").write_text(
        control_case.model_dump_json(indent=2) + "\n"
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
    assert "## Status Counts" in report
    assert "## Attempts" in report
    assert "- Config name: scorer_control_policies" in report
    assert "- Policy: oracle" in report
    assert "- Split: practice" in report
    assert "- Config path: configs/eval/scorer_control_policies.yaml" in report
    assert "| PASS | 1 |" in report
    assert (
        "| toy_python_fix_001 | 0 | PASS | PASS | PASS |  | "
        "xxh64:e3fc746d6fe0786c | attempts/toy_python_fix_001__attempt_001 |"
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
    assert "## Policy Summary" in report
    assert "## Calibration Checks" in report
    assert "### Control Expectations" in report
    assert "## Per-Task Outcomes" in report
    assert "- Config name: scorer_control_policies" in report
    assert "- Task count: 1" in report
    assert "- Policy count: 3" in report
    assert "- Replay scope: control_policies" in report
    assert "- Replay repeats: 1" in report
    assert "- Replay match rate: 3/3 (100%)" in report
    assert "- Oracle pass rate: 1/1 (100%)" in report
    assert "- Known-bad final PASS rate: 0/2 (0%)" in report
    assert "- Known-bad public-pass/hidden-fail rate: 2/2 (100%)" in report
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
        "| oracle | PASS | 1/1 (100%) | PASS | 1/1 (100%) | PASS | 1/1 (100%) | "
        '<span style="color: green">ON_TRACK</span> |'
    ) in report
    assert (
        "| bad-noop | HIDDEN_TEST_FAIL | 1/1 (100%) | PASS | 1/1 (100%) | "
        'FAIL | 1/1 (100%) | <span style="color: green">ON_TRACK</span> |'
    ) in report
    assert "| oracle | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0 | 0 | 0 |" in report
    assert ("| bad-noop | 1 | 0/1 (0%) | 1/1 (100%) | 0/1 (0%) | 1 | 0 | 0 |") in report
    assert (
        "| toy_python_fix_001 | bad-public-only | HIDDEN_TEST_FAIL | PASS | FAIL |"
    ) in report
