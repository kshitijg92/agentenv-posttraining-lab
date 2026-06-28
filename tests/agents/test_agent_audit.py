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
MAX_TURNS_TOOL_RESULTS = [
    {
        "tool_name": "read_file",
        "status": "ok",
        "error_class": None,
    }
    for _ in range(10)
]
TERMINAL_TOOL_RESULTS = [
    {
        "tool_name": "read_file",
        "status": "ok",
        "error_class": None,
    },
    {
        "tool_name": "read_file",
        "status": "ok",
        "error_class": None,
    },
    {
        "tool_name": "read_file",
        "status": "error",
        "error_class": "UnsafePath",
    },
]
ORCHESTRATOR_ERROR_TOOL_RESULTS = HAPPY_TOOL_RESULTS
TASK_MANIFEST = "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
EXPECTED_COMPARISONS = {
    "happy_path": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
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
        (
            "prompt_loop_error_class",
            "MalformedModelOutput",
            "MalformedModelOutput",
            True,
        ),
        ("tool_results", [], [], True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "max_turns_exceeded": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        ("prompt_loop_status", "max_turns_exceeded", "max_turns_exceeded", True),
        ("prompt_loop_error_class", "MaxTurnsExceeded", "MaxTurnsExceeded", True),
        ("tool_results", MAX_TURNS_TOOL_RESULTS, MAX_TURNS_TOOL_RESULTS, True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "model_error": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        ("prompt_loop_status", "model_error", "model_error", True),
        (
            "prompt_loop_error_class",
            "ScriptedProviderError",
            "ScriptedProviderError",
            True,
        ),
        ("tool_results", [], [], True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "orchestrator_error_after_completed_prompt": [
        ("agent_run_status", "orchestrator_error", "orchestrator_error", True),
        ("agent_error_class", "UnicodeDecodeError", "UnicodeDecodeError", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "tool_results",
            ORCHESTRATOR_ERROR_TOOL_RESULTS,
            ORCHESTRATOR_ERROR_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "terminal_tool_error": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        ("prompt_loop_status", "terminal_tool_error", "terminal_tool_error", True),
        ("prompt_loop_error_class", "UnsafePath", "UnsafePath", True),
        ("tool_results", TERMINAL_TOOL_RESULTS, TERMINAL_TOOL_RESULTS, True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "tool_recovery": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        ("tool_results", RECOVERY_TOOL_RESULTS, RECOVERY_TOOL_RESULTS, True),
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ],
}
EXPECTED_RECORD_FIELDS = {
    "happy_path": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify the deterministic happy-path agent control completes, "
            "produces a patch, and scores PASS."
        ),
    },
    "malformed_json": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "MalformedModelOutput",
        "prompt_loop_status": "invalid_model_output",
        "purpose": (
            "Verify malformed model JSON fails the agent loop without running "
            "the nested scorer."
        ),
    },
    "max_turns_exceeded": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "MaxTurnsExceeded",
        "prompt_loop_status": "max_turns_exceeded",
        "purpose": (
            "Verify an agent that never emits final_answer stops at max_turns "
            "without running the nested scorer."
        ),
    },
    "model_error": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "ScriptedProviderError",
        "prompt_loop_status": "model_error",
        "purpose": (
            "Verify a model finish_reason=error fails the agent loop without "
            "running tools or the nested scorer."
        ),
    },
    "orchestrator_error_after_completed_prompt": {
        "agent_run_status": "orchestrator_error",
        "error_class": "UnicodeDecodeError",
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a completed prompt loop can still fail at the agent "
            "orchestrator layer while materializing the candidate patch."
        ),
    },
    "terminal_tool_error": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "UnsafePath",
        "prompt_loop_status": "terminal_tool_error",
        "purpose": (
            "Verify a terminal tool error on the third tool call stops the "
            "agent loop without running the nested scorer."
        ),
    },
    "tool_recovery": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a recoverable bad tool input is recorded and the agent "
            "can continue to a PASS scorer result."
        ),
    },
}


def test_load_agent_task_audit_case() -> None:
    case = load_agent_task_audit_case(AGENT_CASE_ROOT / "happy_path/case.yaml")

    assert case.id == "happy_path"
    assert case.expected_agent_run_status == "scored"
    assert case.expected_prompt_loop_status == "completed"
    assert case.expected_prompt_loop_error_class is None
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
    assert malformed_case.expected_prompt_loop_error_class == "MalformedModelOutput"
    assert malformed_case.expected_tool_results == []
    assert malformed_case.expected_attempt_status is None
    assert malformed_case.expected_public_status is None
    assert malformed_case.expected_hidden_status is None

    max_turns_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "max_turns_exceeded/case.yaml"
    )

    assert max_turns_case.id == "max_turns_exceeded"
    assert max_turns_case.expected_agent_run_status == "agent_loop_failed"
    assert max_turns_case.expected_prompt_loop_status == "max_turns_exceeded"
    assert max_turns_case.expected_prompt_loop_error_class == "MaxTurnsExceeded"
    assert max_turns_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in max_turns_case.expected_tool_results
    ] == MAX_TURNS_TOOL_RESULTS
    assert max_turns_case.expected_attempt_status is None
    assert max_turns_case.expected_public_status is None
    assert max_turns_case.expected_hidden_status is None

    model_error_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "model_error/case.yaml"
    )

    assert model_error_case.id == "model_error"
    assert model_error_case.expected_agent_run_status == "agent_loop_failed"
    assert model_error_case.expected_prompt_loop_status == "model_error"
    assert model_error_case.expected_prompt_loop_error_class == (
        "ScriptedProviderError"
    )
    assert model_error_case.expected_tool_results == []
    assert model_error_case.expected_attempt_status is None
    assert model_error_case.expected_public_status is None
    assert model_error_case.expected_hidden_status is None

    orchestrator_error_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "orchestrator_error_after_completed_prompt/case.yaml"
    )

    assert orchestrator_error_case.id == "orchestrator_error_after_completed_prompt"
    assert orchestrator_error_case.expected_agent_run_status == "orchestrator_error"
    assert orchestrator_error_case.expected_agent_error_class == "UnicodeDecodeError"
    assert orchestrator_error_case.expected_prompt_loop_status == "completed"
    assert orchestrator_error_case.expected_prompt_loop_error_class is None
    assert orchestrator_error_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in orchestrator_error_case.expected_tool_results
    ] == ORCHESTRATOR_ERROR_TOOL_RESULTS
    assert orchestrator_error_case.expected_attempt_status is None
    assert orchestrator_error_case.expected_public_status is None
    assert orchestrator_error_case.expected_hidden_status is None

    terminal_tool_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "terminal_tool_error/case.yaml"
    )

    assert terminal_tool_case.id == "terminal_tool_error"
    assert terminal_tool_case.expected_agent_run_status == "agent_loop_failed"
    assert terminal_tool_case.expected_prompt_loop_status == "terminal_tool_error"
    assert terminal_tool_case.expected_prompt_loop_error_class == "UnsafePath"
    assert terminal_tool_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in terminal_tool_case.expected_tool_results
    ] == TERMINAL_TOOL_RESULTS
    assert terminal_tool_case.expected_attempt_status is None
    assert terminal_tool_case.expected_public_status is None
    assert terminal_tool_case.expected_hidden_status is None

    recovery_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "tool_recovery/case.yaml"
    )

    assert recovery_case.id == "tool_recovery"
    assert recovery_case.expected_prompt_loop_error_class is None
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
    results_by_case = {result.case.id: result for result in results}
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

    for case_id in (
        "malformed_json",
        "max_turns_exceeded",
        "model_error",
        "orchestrator_error_after_completed_prompt",
        "terminal_tool_error",
    ):
        artifact_dir = out_dir / f"agent_task_runs/{case_id}"
        assert not (artifact_dir / "candidate.patch").exists()
        assert not (artifact_dir / "attempt").exists()

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
        assert record["task_manifest"] == TASK_MANIFEST
        assert record["agent_run_id"] == (
            results_by_case[case_id].agent_task_run.result.run_id
        )
        for field, expected_value in EXPECTED_RECORD_FIELDS[case_id].items():
            assert record[field] == expected_value

    markdown = markdown_path.read_text()
    assert "# Agent Task Audit" in markdown
    assert "| happy_path | PASS | scored | completed | agent_task_runs/happy_path |" in markdown
    assert "| happy_path | agent_run_status | scored | scored | PASS |" in markdown
    assert "| happy_path | prompt_loop_status | completed | completed | PASS |" in markdown
    assert "| happy_path | prompt_loop_error_class |  |  | PASS |" in markdown
    assert "| happy_path | attempt_status | PASS | PASS | PASS |" in markdown
    assert (
        "| malformed_json | PASS | agent_loop_failed | invalid_model_output "
        "| agent_task_runs/malformed_json |"
    ) in markdown
    assert "| malformed_json | attempt_status |  |  | PASS |" in markdown
    assert (
        "| malformed_json | prompt_loop_error_class | MalformedModelOutput "
        "| MalformedModelOutput | PASS |"
    ) in markdown
    assert (
        "| max_turns_exceeded | PASS | agent_loop_failed | max_turns_exceeded "
        "| agent_task_runs/max_turns_exceeded |"
    ) in markdown
    assert "| max_turns_exceeded | attempt_status |  |  | PASS |" in markdown
    assert (
        "| max_turns_exceeded | prompt_loop_error_class | MaxTurnsExceeded "
        "| MaxTurnsExceeded | PASS |"
    ) in markdown
    assert (
        "| model_error | PASS | agent_loop_failed | model_error "
        "| agent_task_runs/model_error |"
    ) in markdown
    assert "| model_error | attempt_status |  |  | PASS |" in markdown
    assert (
        "| model_error | prompt_loop_error_class | ScriptedProviderError "
        "| ScriptedProviderError | PASS |"
    ) in markdown
    assert (
        "| orchestrator_error_after_completed_prompt | PASS | orchestrator_error "
        "| completed | agent_task_runs/orchestrator_error_after_completed_prompt |"
    ) in markdown
    assert (
        "| orchestrator_error_after_completed_prompt | agent_error_class "
        "| UnicodeDecodeError | UnicodeDecodeError | PASS |"
    ) in markdown
    assert (
        "| orchestrator_error_after_completed_prompt | prompt_loop_error_class "
        "|  |  | PASS |"
    ) in markdown
    assert (
        "| orchestrator_error_after_completed_prompt | attempt_status "
        "|  |  | PASS |"
    ) in markdown
    assert (
        "| terminal_tool_error | PASS | agent_loop_failed | terminal_tool_error "
        "| agent_task_runs/terminal_tool_error |"
    ) in markdown
    assert "| terminal_tool_error | attempt_status |  |  | PASS |" in markdown
    assert (
        "| terminal_tool_error | prompt_loop_error_class | UnsafePath "
        "| UnsafePath | PASS |"
    ) in markdown
    assert (
        "| tool_recovery | PASS | scored | completed "
        "| agent_task_runs/tool_recovery |"
    ) in markdown
    assert (
        "| tool_recovery | agent_run_status | scored | scored | PASS |"
    ) in markdown
