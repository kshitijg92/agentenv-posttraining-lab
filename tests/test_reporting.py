from pathlib import Path

from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.replay.runner import run_replay
from agentenv.reporting.markdown import write_markdown_report


CONTROL_EVAL_CONFIG = Path("configs/eval/control_policies.yaml")


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
    assert "- Config name: control_policies" in report
    assert "- Policy: oracle" in report
    assert "- Split: practice" in report
    assert "- Config path: configs/eval/control_policies.yaml" in report
    assert "| PASS | 1 |" in report
    assert (
        "| toy_python_fix_001 | 0 | PASS | PASS | PASS |  | "
        "xxh64:e3fc746d6fe0786c | attempts/toy_python_fix_001__attempt_001 |"
    ) in report


def test_replay_report_artifact_is_recognized_but_not_implemented(
    tmp_path: Path,
) -> None:
    run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "eval_run")
    run_replay(tmp_path / "eval_run", tmp_path / "replay_run")

    try:
        write_markdown_report(tmp_path / "replay_run", tmp_path / "reports/replay.md")
    except NotImplementedError as exc:
        assert str(exc) == "Replay reports are not implemented yet"
    else:
        raise AssertionError("Expected replay report to be recognized but unsupported")
