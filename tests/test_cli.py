from pathlib import Path

from typer.testing import CliRunner

from agentenv.cli import app


def test_eval_cli_writes_optional_eval_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_run"
    report_path = tmp_path / "reports/eval_report.md"

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--policy",
            "oracle",
            "--out",
            str(out_dir),
            "--report-out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "wrote" in result.output
    assert "run_manifest.json" in result.output
    assert "eval_report.md" in result.output
    assert (out_dir / "run_manifest.json").is_file()
    assert report_path.is_file()
    assert "# Eval Report" in report_path.read_text()


def test_eval_cli_writes_optional_eval_matrix_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_matrix"
    report_path = tmp_path / "reports/eval_matrix.md"

    result = CliRunner().invoke(
        app,
        [
            "eval",
            "--config",
            "configs/eval/scorer_control_policies.yaml",
            "--all-policies",
            "--out",
            str(out_dir),
            "--report-out",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "wrote" in result.output
    assert "eval_matrix_manifest.json" in result.output
    assert "eval_matrix.md" in result.output
    assert (out_dir / "eval_matrix_manifest.json").is_file()
    assert report_path.is_file()
    assert "# Eval Matrix Report" in report_path.read_text()
