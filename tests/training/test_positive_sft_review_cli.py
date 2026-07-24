from typer.testing import CliRunner

from agentenv.cli import app


def test_positive_sft_cli_uses_one_combined_review_surface() -> None:
    result = CliRunner().invoke(app, ["training", "positive-sft", "--help"])

    assert result.exit_code == 0, result.output
    assert "review-init" in result.output
    assert "review-validate" in result.output
    assert "efficiency-review-init" not in result.output
    assert "efficiency-review-validate" not in result.output
