from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

import agentenv.orchestrators.eval_run as eval_run_module
from agentenv.agents.schema import PromptLoopResult, TokenUsage
from agentenv.artifacts.manifests import load_eval_suite_manifest
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.orchestrators.eval_run import run_eval_config_all_policies
from agentenv.reporting.policy_selection import (
    PolicyCellOutcome,
    PolicyTaskCell,
    analyze_policy_cells,
    build_policy_selection_analysis_from_eval_suite,
    policy_task_cell_from_attempt_evidence,
    render_policy_selection_analysis,
    select_policy,
    summarize_policy_cells,
)
from agentenv.tasks.hashing import build_eval_task_hashes


POLICIES = ("base", "raw-sft", "efficiency-filtered-sft")
TASKS = ("task_a", "task_b", "task_c")
TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
POLICY_SELECTION_TASK = "toy_python_fix_001"


def _cells(
    outcomes: Mapping[str, Sequence[str]],
    *,
    total_tokens: Mapping[str, Sequence[int | None]] | None = None,
    action_counts: Mapping[str, Sequence[int | None]] | None = None,
) -> tuple[PolicyTaskCell, ...]:
    records: list[PolicyTaskCell] = []
    for policy_id in POLICIES:
        for index, task_id in enumerate(TASKS):
            outcome = cast(PolicyCellOutcome, outcomes[policy_id][index])
            tokens = total_tokens[policy_id][index] if total_tokens else 100 + index
            actions = action_counts[policy_id][index] if action_counts else 4 + index
            records.append(
                PolicyTaskCell(
                    policy_id=policy_id,
                    task_id=task_id,
                    outcome=outcome,
                    outcome_detail=outcome,
                    prompt_tokens=tokens,
                    completion_tokens=(0 if tokens is not None else None),
                    total_tokens=tokens,
                    action_count=actions,
                )
            )
    return tuple(records)


def _write_policy_selection_eval_config(path: Path) -> None:
    selected_task_hash_set = build_eval_task_hashes(
        TASK_PACK,
        [POLICY_SELECTION_TASK],
    ).selected_task_hash_set
    path.write_text(
        "\n".join(
            [
                "name: policy_selection_artifact_test",
                "task_pack: data/task_packs/repo_patch_python_v0",
                "tasks:",
                f"  - {POLICY_SELECTION_TASK}",
                f"expected_task_hash_set: {selected_task_hash_set}",
                "policy_selection_rule: nested_pass_then_success_tokens_then_actions",
                "split: practice",
                "policies:",
                "  policy-a:",
                "    type: agent_model",
                "    model_config: configs/models/openai_compatible_chat_placeholder.yaml",
                "    decoding_config: configs/decoding/greedy_1024.yaml",
                "    attempts: 1",
                "    replay:",
                "      repeats: 0",
                "  policy-b:",
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


def _run_policy_selection_eval_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    config_path = tmp_path / "policy_selection.yaml"
    suite_dir = tmp_path / "eval_suite"
    _write_policy_selection_eval_config(config_path)

    def fake_build_model_client(
        *args: object, **kwargs: object
    ) -> ScriptedFakeModelClient:
        del args
        del kwargs
        return ScriptedFakeModelClient(
            model_id="placeholder-model",
            script=[FakeModelScriptStep(output_text="not-json")],
        )

    monkeypatch.setattr(
        eval_run_module,
        "build_model_client",
        fake_build_model_client,
    )
    run_eval_config_all_policies(config_path, suite_dir)
    return config_path, suite_dir


def test_more_nested_passes_selects_policy_before_efficiency() -> None:
    cells = _cells(
        {
            "base": ("pass", "policy_failure", "policy_failure"),
            "raw-sft": ("pass", "pass", "policy_failure"),
            "efficiency-filtered-sft": ("policy_failure", "policy_failure", "pass"),
        },
        total_tokens={
            "base": (10, 10, 10),
            "raw-sft": (1000, 1000, 1000),
            "efficiency-filtered-sft": (1, 1, 1),
        },
    )

    decision = select_policy(cells, policy_order=POLICIES, task_order=TASKS)

    assert decision.status == "selected"
    assert decision.selected_policy == "raw-sft"
    assert decision.branch == "task_success"


def test_equal_pass_counts_on_different_tasks_abstains() -> None:
    cells = _cells(
        {
            "base": ("pass", "pass", "policy_failure"),
            "raw-sft": ("pass", "policy_failure", "pass"),
            "efficiency-filtered-sft": ("policy_failure", "pass", "pass"),
        }
    )

    decision = select_policy(cells, policy_order=POLICIES, task_order=TASKS)

    assert decision.status == "abstained"
    assert decision.selected_policy is None
    assert decision.branch == "different_success_vectors"


def test_identical_success_vector_uses_tokens_then_actions() -> None:
    outcomes = {
        policy: ("pass", "pass", "policy_failure") for policy in POLICIES
    }
    token_winner = select_policy(
        _cells(
            outcomes,
            total_tokens={
                "base": (100, 100, 20),
                "raw-sft": (90, 90, 20),
                "efficiency-filtered-sft": (95, 95, 20),
            },
        ),
        policy_order=POLICIES,
        task_order=TASKS,
    )
    action_winner = select_policy(
        _cells(
            outcomes,
            total_tokens={policy: (100, 100, 20) for policy in POLICIES},
            action_counts={
                "base": (5, 5, 1),
                "raw-sft": (4, 4, 1),
                "efficiency-filtered-sft": (6, 3, 1),
            },
        ),
        policy_order=POLICIES,
        task_order=TASKS,
    )

    assert token_winner.selected_policy == "raw-sft"
    assert token_winner.branch == "successful_total_tokens"
    assert action_winner.selected_policy == "raw-sft"
    assert action_winner.branch == "successful_action_count"


def test_invalid_cell_or_missing_tiebreak_metric_abstains() -> None:
    invalid = _cells(
        {
            "base": ("pass", "pass", "policy_failure"),
            "raw-sft": ("pass", "invalid", "policy_failure"),
            "efficiency-filtered-sft": ("pass", "pass", "policy_failure"),
        }
    )
    tied_outcomes = {
        policy: ("pass", "pass", "policy_failure") for policy in POLICIES
    }
    missing_tokens = _cells(
        tied_outcomes,
        total_tokens={
            "base": (100, 100, 20),
            "raw-sft": (100, None, 20),
            "efficiency-filtered-sft": (100, 100, 20),
        },
    )

    invalid_decision = select_policy(
        invalid,
        policy_order=POLICIES,
        task_order=TASKS,
    )
    missing_decision = select_policy(
        missing_tokens,
        policy_order=POLICIES,
        task_order=TASKS,
    )

    assert invalid_decision.branch == "invalid_comparison_cells"
    assert missing_decision.branch == "missing_success_token_counts"


def test_complete_tie_abstains_and_summary_reports_all_task_metrics() -> None:
    outcomes = {
        policy: ("pass", "policy_failure", "pass") for policy in POLICIES
    }
    cells = _cells(outcomes)

    decision = select_policy(cells, policy_order=POLICIES, task_order=TASKS)
    summaries = summarize_policy_cells(
        cells,
        policy_order=POLICIES,
        task_order=TASKS,
    )

    assert decision.status == "abstained"
    assert decision.branch == "complete_tie"
    assert summaries[0].pass_task_ids == ("task_a", "task_c")
    assert summaries[0].policy_failure_task_ids == ("task_b",)
    assert summaries[0].observed_total_tokens == 303
    assert summaries[0].token_observed_task_count == 3
    assert summaries[0].observed_actions == 15
    assert summaries[0].action_observed_task_count == 3


def test_policy_selection_requires_exact_frozen_matrix() -> None:
    cells = _cells({policy: ("pass", "pass", "pass") for policy in POLICIES})

    with pytest.raises(ValueError, match="policy-task matrix"):
        select_policy(
            cells[:-1],
            policy_order=POLICIES,
            task_order=TASKS,
        )


def test_attempt_evidence_maps_status_tokens_and_actions_mechanically() -> None:
    prompt_loop = PromptLoopResult(
        task_id="task_a",
        prompt_builder_version="test",
        prompt_builder_code_hash="xxh64:cccccccccccccccc",
        status="completed",
        turns_executed=4,
        duration_ms=15,
        token_usage=TokenUsage(
            prompt_tokens=90,
            completion_tokens=10,
            total_tokens=100,
        ),
        messages=[],
        model_responses=[],
        tool_results=[],
    )

    cell = policy_task_cell_from_attempt_evidence(
        policy_id="base",
        task_id="task_a",
        agent_status="scored",
        prompt_loop_status="completed",
        scorer_status="PASS",
        prompt_loop=prompt_loop,
    )
    disqualified = policy_task_cell_from_attempt_evidence(
        policy_id="base",
        task_id="task_a",
        agent_status="scored",
        prompt_loop_status="completed",
        scorer_status="PASS",
        prompt_loop=prompt_loop,
        confirmed_reward_hack=True,
    )

    assert cell.outcome == "pass"
    assert cell.outcome_detail == "nested_scorer:PASS"
    assert cell.prompt_tokens == 90
    assert cell.completion_tokens == 10
    assert cell.total_tokens == 100
    assert cell.action_count == 4
    assert disqualified.outcome == "policy_failure"
    assert disqualified.outcome_detail == "reward_hack:confirmed"


def test_analysis_reports_all_pairs_and_renders_decision() -> None:
    cells = _cells(
        {
            "base": ("pass", "policy_failure", "pass"),
            "raw-sft": ("pass", "pass", "policy_failure"),
            "efficiency-filtered-sft": ("pass", "policy_failure", "pass"),
        }
    )

    analysis = analyze_policy_cells(
        cells,
        policy_order=POLICIES,
        task_order=TASKS,
    )
    report = render_policy_selection_analysis(analysis)

    base_to_raw = analysis.pairwise_comparisons[0]
    assert base_to_raw.reference_policy == "base"
    assert base_to_raw.candidate_policy == "raw-sft"
    assert base_to_raw.gain_task_ids == ("task_b",)
    assert base_to_raw.regression_task_ids == ("task_c",)
    assert len(analysis.pairwise_comparisons) == 3
    assert analysis.decision.branch == "different_success_vectors"
    assert "## Policy Selection" in report
    assert "| base | raw-sft | task_b | task_c | task_a | none | none |" in report
    assert "- Status: abstained" in report


def test_policy_selection_analysis_reconstructs_from_eval_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, suite_dir = _run_policy_selection_eval_suite(tmp_path, monkeypatch)

    analysis = build_policy_selection_analysis_from_eval_suite(suite_dir)

    assert tuple(cell.policy_id for cell in analysis.cells) == (
        "policy-a",
        "policy-b",
    )
    assert tuple(cell.task_id for cell in analysis.cells) == (
        POLICY_SELECTION_TASK,
        POLICY_SELECTION_TASK,
    )
    assert tuple(cell.outcome for cell in analysis.cells) == (
        "policy_failure",
        "policy_failure",
    )
    assert analysis.decision.status == "abstained"
    assert analysis.decision.selected_policy is None
    assert analysis.decision.branch == "complete_tie"


def test_policy_selection_analysis_rejects_live_config_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path, suite_dir = _run_policy_selection_eval_suite(tmp_path, monkeypatch)
    config_path.write_text(config_path.read_text() + "# drift\n")

    with pytest.raises(ValueError, match="config hash"):
        build_policy_selection_analysis_from_eval_suite(suite_dir)


def test_policy_selection_analysis_rejects_missing_attempt_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, suite_dir = _run_policy_selection_eval_suite(tmp_path, monkeypatch)
    suite_manifest = load_eval_suite_manifest(suite_dir / "manifest.json")
    first_policy_run = suite_manifest.policy_runs[0]
    prompt_loop_path = (
        suite_dir
        / first_policy_run.artifact_dir
        / "attempts"
        / f"{POLICY_SELECTION_TASK}__attempt_001"
        / "prompt_loop_result.json"
    )
    prompt_loop_path.unlink()

    with pytest.raises(FileNotFoundError, match="prompt_loop_result.json"):
        build_policy_selection_analysis_from_eval_suite(suite_dir)
