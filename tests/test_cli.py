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


def test_eval_cli_rejects_non_empty_out_without_overwrite(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_run"
    out_dir.mkdir()
    stale_file = out_dir / "stale.txt"
    stale_file.write_text("stale\n")

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
        ],
    )

    assert result.exit_code != 0
    assert "Output directory is not empty" in result.output
    assert stale_file.read_text() == "stale\n"


def test_eval_cli_overwrite_clears_non_empty_out(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval_run"
    out_dir.mkdir()
    stale_file = out_dir / "stale.txt"
    stale_file.write_text("stale\n")

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
            "--overwrite",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not stale_file.exists()
    assert (out_dir / "run_manifest.json").is_file()


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
