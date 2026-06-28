import json
from pathlib import Path

from agentenv.agents.audit import (
    load_agent_task_audit_case,
    run_agent_task_audit,
)


AGENT_CASE_ROOT = Path("data/harness_audit/agent_task_cases")
HAPPY_TOOL_RESULTS = [
    {
        "tool_name": "read_file",
        "status": "ok",
        "error_class": None,
    },
    {
        "tool_name": "write_file",
        "status": "ok",
        "error_class": None,
    },
    {
        "tool_name": "run_tests",
        "status": "ok",
        "error_class": None,
    },
]
EXPECTED_COMPARISONS = {
    "happy_path": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("tool_results", HAPPY_TOOL_RESULTS, HAPPY_TOOL_RESULTS, True),
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ],
}


def test_load_agent_task_audit_case() -> None:
    case = load_agent_task_audit_case(AGENT_CASE_ROOT / "happy_path/case.yaml")

    assert case.id == "happy_path"
    assert case.expected_agent_run_status == "scored"
    assert case.expected_prompt_loop_status == "completed"
    assert case.expected_attempt_status == "PASS"
    assert case.expected_public_status == "PASS"
    assert case.expected_hidden_status == "PASS"
    assert case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in case.expected_tool_results
    ] == HAPPY_TOOL_RESULTS


def test_run_agent_task_audit_writes_jsonl_markdown_and_artifacts(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "agent_task_audit"

    results = run_agent_task_audit(AGENT_CASE_ROOT, out_dir)

    assert {result.case.id for result in results} == set(EXPECTED_COMPARISONS)
    assert all(result.overall_match for result in results)
    comparisons_by_case = {
        result.case.id: [
            (comparison.field, comparison.expected, comparison.actual, comparison.match)
            for comparison in result.comparisons
        ]
        for result in results
    }
    assert comparisons_by_case == EXPECTED_COMPARISONS

    jsonl_path = out_dir / "agent_task_audit_results.jsonl"
    markdown_path = out_dir / "agent_task_audit.md"
    artifact_dir = out_dir / "agent_task_runs/happy_path"

    assert jsonl_path.is_file()
    assert markdown_path.is_file()
    assert (artifact_dir / "run_manifest.json").is_file()
    assert (artifact_dir / "agent_task_run.json").is_file()
    assert (artifact_dir / "agent_task_view.json").is_file()
    assert (artifact_dir / "prompt_loop_result.json").is_file()
    assert (artifact_dir / "candidate.patch").is_file()
    assert (artifact_dir / "decoding_config.json").is_file()
    assert (artifact_dir / "agent_control_script.json").is_file()
    assert (artifact_dir / "attempt/attempt.json").is_file()
    assert (artifact_dir / "attempt/trace.jsonl").is_file()
    assert (artifact_dir / "attempt/final.diff").is_file()

    records = [
        json.loads(line)
        for line in jsonl_path.read_text().splitlines()
        if line.strip()
    ]
    assert records == [
        {
            "agent_control_script": "agent_control_script.json",
            "agent_run_id": results[0].agent_task_run.result.run_id,
            "agent_run_status": "scored",
            "agent_task_artifact_dir": "agent_task_runs/happy_path",
            "case_id": "happy_path",
            "comparisons": [
                {
                    "field": field,
                    "expected": expected,
                    "actual": actual,
                    "match": match,
                }
                for field, expected, actual, match in EXPECTED_COMPARISONS[
                    "happy_path"
                ]
            ],
            "error_class": None,
            "overall_match": True,
            "prompt_loop_status": "completed",
            "purpose": (
                "Verify the deterministic happy-path agent control completes, "
                "produces a patch, and scores PASS."
            ),
            "task_manifest": (
                "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
            ),
        }
    ]

    markdown = markdown_path.read_text()
    assert "# Agent Task Audit" in markdown
    assert "| happy_path | PASS | scored | completed | agent_task_runs/happy_path |" in markdown
    assert "| happy_path | agent_run_status | scored | scored | PASS |" in markdown
    assert "| happy_path | prompt_loop_status | completed | completed | PASS |" in markdown
    assert "| happy_path | attempt_status | PASS | PASS | PASS |" in markdown
