from types import SimpleNamespace

from typer.testing import CliRunner

import agentenv.cli as cli_module
from agentenv.cli import app


def test_positive_sft_cli_uses_one_combined_review_surface() -> None:
    result = CliRunner().invoke(app, ["training", "positive-sft", "--help"])

    assert result.exit_code == 0, result.output
    assert "review-init" in result.output
    assert "review-validate" in result.output
    assert "efficiency-review-init" not in result.output
    assert "efficiency-review-validate" not in result.output


def test_positive_sft_review_validation_reports_dimension_specific_labels(
    monkeypatch,
) -> None:
    unresolved_prefix = SimpleNamespace(
        review_status="reviewed",
        review_decision="needs_followup",
        efficiency_judgment=None,
    )
    efficiency_abstention = SimpleNamespace(
        review_status="reviewed",
        review_decision="accepted",
        efficiency_judgment=SimpleNamespace(review_decision="needs_followup"),
    )
    validation = SimpleNamespace(
        review_artifact=SimpleNamespace(
            reviews=(unresolved_prefix, efficiency_abstention)
        )
    )
    monkeypatch.setattr(
        cli_module,
        "validate_positive_sft_review_artifact",
        lambda _path: validation,
    )

    result = CliRunner().invoke(
        app,
        [
            "training",
            "positive-sft",
            "review-validate",
            "--reviews",
            "unused",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "prefix_unresolved=1" in result.output
    assert "efficiency_abstained=1" in result.output
    assert "prefix_needs_followup" not in result.output
    assert "efficiency_needs_followup" not in result.output
