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
RECOVERY_TOOL_RESULTS = [
    {
        "tool_name": "read_file",
        "status": "error",
        "error_class": "InvalidToolInput",
    },
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
    "malformed_json": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        (
            "prompt_loop_status",
            "invalid_model_output",
            "invalid_model_output",
            True,
        ),
        ("tool_results", [], [], True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "tool_recovery": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("tool_results", RECOVERY_TOOL_RESULTS, RECOVERY_TOOL_RESULTS, True),
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

    malformed_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "malformed_json/case.yaml"
    )

    assert malformed_case.id == "malformed_json"
    assert malformed_case.expected_agent_run_status == "agent_loop_failed"
    assert malformed_case.expected_prompt_loop_status == "invalid_model_output"
    assert malformed_case.expected_tool_results == []
    assert malformed_case.expected_attempt_status is None
    assert malformed_case.expected_public_status is None
    assert malformed_case.expected_hidden_status is None

    recovery_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "tool_recovery/case.yaml"
    )

    assert recovery_case.id == "tool_recovery"
    assert recovery_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in recovery_case.expected_tool_results
    ] == RECOVERY_TOOL_RESULTS


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

    assert jsonl_path.is_file()
    assert markdown_path.is_file()
    for case_id in EXPECTED_COMPARISONS:
        artifact_dir = out_dir / f"agent_task_runs/{case_id}"
        assert (artifact_dir / "run_manifest.json").is_file()
        assert (artifact_dir / "agent_task_run.json").is_file()
        assert (artifact_dir / "agent_task_view.json").is_file()
        assert (artifact_dir / "prompt_loop_result.json").is_file()
        assert (artifact_dir / "decoding_config.json").is_file()
        assert (artifact_dir / "agent_control_script.json").is_file()

    malformed_artifact_dir = out_dir / "agent_task_runs/malformed_json"
    assert not (malformed_artifact_dir / "candidate.patch").exists()
    assert not (malformed_artifact_dir / "attempt").exists()

    for case_id in ("happy_path", "tool_recovery"):
        artifact_dir = out_dir / f"agent_task_runs/{case_id}"
        assert (artifact_dir / "candidate.patch").is_file()
        assert (artifact_dir / "attempt/attempt.json").is_file()
        assert (artifact_dir / "attempt/trace.jsonl").is_file()
        assert (artifact_dir / "attempt/final.diff").is_file()

    records = [
        json.loads(line)
        for line in jsonl_path.read_text().splitlines()
        if line.strip()
    ]
    assert {record["case_id"] for record in records} == set(EXPECTED_COMPARISONS)
    records_by_case = {record["case_id"]: record for record in records}
    for case_id, expected_comparisons in EXPECTED_COMPARISONS.items():
        record = records_by_case[case_id]
        assert record["agent_control_script"] == "agent_control_script.json"
        assert record["agent_task_artifact_dir"] == f"agent_task_runs/{case_id}"
        assert record["comparisons"] == [
            {
                "field": field,
                "expected": expected,
                "actual": actual,
                "match": match,
            }
            for field, expected, actual, match in expected_comparisons
        ]
        assert record["overall_match"] is True
        assert record["task_manifest"] == (
            "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
        )

    assert records_by_case["happy_path"] == {
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
    assert records_by_case["malformed_json"] == {
        "agent_control_script": "agent_control_script.json",
        "agent_run_id": results[1].agent_task_run.result.run_id,
        "agent_run_status": "agent_loop_failed",
        "agent_task_artifact_dir": "agent_task_runs/malformed_json",
        "case_id": "malformed_json",
        "comparisons": [
            {
                "field": field,
                "expected": expected,
                "actual": actual,
                "match": match,
            }
            for field, expected, actual, match in EXPECTED_COMPARISONS[
                "malformed_json"
            ]
        ],
        "error_class": "MalformedModelOutput",
        "overall_match": True,
        "prompt_loop_status": "invalid_model_output",
        "purpose": (
            "Verify malformed model JSON fails the agent loop without running "
            "the nested scorer."
        ),
        "task_manifest": (
            "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
        ),
    }
    assert records_by_case["tool_recovery"] == {
        "agent_control_script": "agent_control_script.json",
        "agent_run_id": results[2].agent_task_run.result.run_id,
        "agent_run_status": "scored",
        "agent_task_artifact_dir": "agent_task_runs/tool_recovery",
        "case_id": "tool_recovery",
        "comparisons": [
            {
                "field": field,
                "expected": expected,
                "actual": actual,
                "match": match,
            }
            for field, expected, actual, match in EXPECTED_COMPARISONS[
                "tool_recovery"
            ]
        ],
        "error_class": None,
        "overall_match": True,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a recoverable bad tool input is recorded and the agent "
            "can continue to a PASS scorer result."
        ),
        "task_manifest": (
            "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
        ),
    }

    markdown = markdown_path.read_text()
    assert "# Agent Task Audit" in markdown
    assert "| happy_path | PASS | scored | completed | agent_task_runs/happy_path |" in markdown
    assert "| happy_path | agent_run_status | scored | scored | PASS |" in markdown
    assert "| happy_path | prompt_loop_status | completed | completed | PASS |" in markdown
    assert "| happy_path | attempt_status | PASS | PASS | PASS |" in markdown
    assert (
        "| malformed_json | PASS | agent_loop_failed | invalid_model_output "
        "| agent_task_runs/malformed_json |"
    ) in markdown
    assert "| malformed_json | attempt_status |  |  | PASS |" in markdown
    assert (
        "| tool_recovery | PASS | scored | completed "
        "| agent_task_runs/tool_recovery |"
    ) in markdown
    assert (
        "| tool_recovery | agent_run_status | scored | scored | PASS |"
    ) in markdown
