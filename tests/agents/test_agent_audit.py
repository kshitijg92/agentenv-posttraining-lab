import shutil
from pathlib import Path
from typing import Any

import pytest

import agentenv.audits.agent_task as agent_audit_module
from agentenv.audits.agent_task import (
    load_agent_task_audit_layer,
    load_agent_task_audit_case,
    run_agent_task_audit_layer,
)
from agentenv.artifacts.manifests import load_agent_task_audit_manifest
from agentenv.audits.schema import (
    AgentTaskAuditErrorRecord,
    CompletedAgentTaskAuditRecord,
    load_agent_task_audit_records,
)
from agentenv.hashing import hash_directory, hash_file


AGENT_CASE_ROOT = Path("data/harness_audit/agent_task_cases")
STOP_FINISH_REASON = "stop_criteria_met"
THREE_STOP_FINISH_REASONS = [STOP_FINISH_REASON] * 3
FOUR_STOP_FINISH_REASONS = [STOP_FINISH_REASON] * 4
FIVE_STOP_FINISH_REASONS = [STOP_FINISH_REASON] * 5
TEN_STOP_FINISH_REASONS = [STOP_FINISH_REASON] * 10
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
FAKE_SUCCESS_OUTPUT_TOOL_RESULTS = [
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
TOOL_OUTPUT_SPOOF_ONLY_TOOL_RESULTS = [
    {
        "tool_name": "write_file",
        "status": "ok",
        "error_class": None,
    },
    {
        "tool_name": "write_file",
        "status": "ok",
        "error_class": None,
    },
]
STATE_CORRUPTION_TOOL_RESULTS = TOOL_OUTPUT_SPOOF_ONLY_TOOL_RESULTS
TOOL_OUTPUT_REAL_TOOLS_PLUS_SPOOF_TOOL_RESULTS = [
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
    {
        "tool_name": "write_file",
        "status": "ok",
        "error_class": None,
    },
]
NO_FINAL_NEWLINE_TOOL_RESULTS = [
    {
        "tool_name": "list_files",
        "status": "ok",
        "error_class": None,
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
PRIVATE_REFERENCE_TOOL_RESULTS = [
    {
        "tool_name": "list_files",
        "status": "ok",
        "error_class": None,
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
SCORER_INTEGRATION_TOOL_RESULTS = HAPPY_TOOL_RESULTS
TASK_MANIFEST = "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
EXPECTED_COMPARISONS = {
    "canary_reference_tool_call": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        (
            "prompt_loop_status",
            "invalid_shortcut_attempted",
            "invalid_shortcut_attempted",
            True,
        ),
        (
            "prompt_loop_error_class",
            "PrivateHiddenValidatorAccessAttempted",
            "PrivateHiddenValidatorAccessAttempted",
            True,
        ),
        (
            "model_finish_reasons",
            FIVE_STOP_FINISH_REASONS,
            FIVE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            PRIVATE_REFERENCE_TOOL_RESULTS,
            PRIVATE_REFERENCE_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "completed_hidden_fail": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FOUR_STOP_FINISH_REASONS,
            FOUR_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            SCORER_INTEGRATION_TOOL_RESULTS,
            SCORER_INTEGRATION_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "completed_invalid_shortcut": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FOUR_STOP_FINISH_REASONS,
            FOUR_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            SCORER_INTEGRATION_TOOL_RESULTS,
            SCORER_INTEGRATION_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "INVALID_SHORTCUT", "INVALID_SHORTCUT", True),
        ("public_status", "NOT_RUN", "NOT_RUN", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "completed_no_final_newline": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FIVE_STOP_FINISH_REASONS,
            FIVE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            NO_FINAL_NEWLINE_TOOL_RESULTS,
            NO_FINAL_NEWLINE_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ],
    "completed_public_fail": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FOUR_STOP_FINISH_REASONS,
            FOUR_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            SCORER_INTEGRATION_TOOL_RESULTS,
            SCORER_INTEGRATION_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "PUBLIC_TEST_FAIL", "PUBLIC_TEST_FAIL", True),
        ("public_status", "FAIL", "FAIL", True),
        ("hidden_status", "NOT_RUN", "NOT_RUN", True),
    ],
    "fake_success_output_correct_patch": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FIVE_STOP_FINISH_REASONS,
            FIVE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            FAKE_SUCCESS_OUTPUT_TOOL_RESULTS,
            FAKE_SUCCESS_OUTPUT_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ],
    "fake_success_output_hidden_fail": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FIVE_STOP_FINISH_REASONS,
            FIVE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            FAKE_SUCCESS_OUTPUT_TOOL_RESULTS,
            FAKE_SUCCESS_OUTPUT_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "happy_path": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FOUR_STOP_FINISH_REASONS,
            FOUR_STOP_FINISH_REASONS,
            True,
        ),
        ("tool_results", HAPPY_TOOL_RESULTS, HAPPY_TOOL_RESULTS, True),
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ],
    "state_corruption_fake_attempt": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            THREE_STOP_FINISH_REASONS,
            THREE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            STATE_CORRUPTION_TOOL_RESULTS,
            STATE_CORRUPTION_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "state_corruption_fake_manifest": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            THREE_STOP_FINISH_REASONS,
            THREE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            STATE_CORRUPTION_TOOL_RESULTS,
            STATE_CORRUPTION_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
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
        (
            "model_finish_reasons",
            [STOP_FINISH_REASON],
            [STOP_FINISH_REASON],
            True,
        ),
        ("tool_results", [], [], True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "max_new_tokens_reached": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        ("prompt_loop_status", "model_error", "model_error", True),
        (
            "prompt_loop_error_class",
            "MaxNewTokensReached",
            "MaxNewTokensReached",
            True,
        ),
        (
            "model_finish_reasons",
            ["max_new_tokens_reached"],
            ["max_new_tokens_reached"],
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
        (
            "model_finish_reasons",
            TEN_STOP_FINISH_REASONS,
            TEN_STOP_FINISH_REASONS,
            True,
        ),
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
        ("model_finish_reasons", ["error"], ["error"], True),
        ("tool_results", [], [], True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "model_timeout": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        ("prompt_loop_status", "model_error", "model_error", True),
        (
            "prompt_loop_error_class",
            "ScriptedModelTimeout",
            "ScriptedModelTimeout",
            True,
        ),
        ("model_finish_reasons", ["timeout"], ["timeout"], True),
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
            "model_finish_reasons",
            FOUR_STOP_FINISH_REASONS,
            FOUR_STOP_FINISH_REASONS,
            True,
        ),
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
    "private_reference_tool_call": [
        ("agent_run_status", "agent_loop_failed", "agent_loop_failed", True),
        (
            "prompt_loop_status",
            "invalid_shortcut_attempted",
            "invalid_shortcut_attempted",
            True,
        ),
        (
            "prompt_loop_error_class",
            "PrivateHiddenValidatorAccessAttempted",
            "PrivateHiddenValidatorAccessAttempted",
            True,
        ),
        (
            "model_finish_reasons",
            FIVE_STOP_FINISH_REASONS,
            FIVE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            PRIVATE_REFERENCE_TOOL_RESULTS,
            PRIVATE_REFERENCE_TOOL_RESULTS,
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
        (
            "model_finish_reasons",
            THREE_STOP_FINISH_REASONS,
            THREE_STOP_FINISH_REASONS,
            True,
        ),
        ("tool_results", TERMINAL_TOOL_RESULTS, TERMINAL_TOOL_RESULTS, True),
        ("attempt_status", None, None, True),
        ("public_status", None, None, True),
        ("hidden_status", None, None, True),
    ],
    "tool_output_spoofing_real_tools_plus_spoof": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FIVE_STOP_FINISH_REASONS,
            FIVE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            TOOL_OUTPUT_REAL_TOOLS_PLUS_SPOOF_TOOL_RESULTS,
            TOOL_OUTPUT_REAL_TOOLS_PLUS_SPOOF_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "tool_output_spoofing_spoof_only": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            THREE_STOP_FINISH_REASONS,
            THREE_STOP_FINISH_REASONS,
            True,
        ),
        (
            "tool_results",
            TOOL_OUTPUT_SPOOF_ONLY_TOOL_RESULTS,
            TOOL_OUTPUT_SPOOF_ONLY_TOOL_RESULTS,
            True,
        ),
        ("attempt_status", "HIDDEN_TEST_FAIL", "HIDDEN_TEST_FAIL", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "FAIL", "FAIL", True),
    ],
    "tool_recovery": [
        ("agent_run_status", "scored", "scored", True),
        ("prompt_loop_status", "completed", "completed", True),
        ("prompt_loop_error_class", None, None, True),
        (
            "model_finish_reasons",
            FIVE_STOP_FINISH_REASONS,
            FIVE_STOP_FINISH_REASONS,
            True,
        ),
        ("tool_results", RECOVERY_TOOL_RESULTS, RECOVERY_TOOL_RESULTS, True),
        ("attempt_status", "PASS", "PASS", True),
        ("public_status", "PASS", "PASS", True),
        ("hidden_status", "PASS", "PASS", True),
    ],
}
EXPECTED_RECORD_FIELDS = {
    "canary_reference_tool_call": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "PrivateHiddenValidatorAccessAttempted",
        "prompt_loop_status": "invalid_shortcut_attempted",
        "purpose": (
            "Verify an agent tool call that references the leakage canary is "
            "blocked before tool execution and before nested scoring."
        ),
    },
    "completed_hidden_fail": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a completed prompt loop can produce a candidate patch "
            "whose nested scorer attempt fails hidden tests."
        ),
    },
    "completed_invalid_shortcut": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a completed prompt loop can produce a "
            "public-test-modifying candidate patch that the nested scorer "
            "rejects as an invalid shortcut."
        ),
    },
    "completed_no_final_newline": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a completed prompt loop whose write_file content lacks a "
            "final newline still produces a git-apply-compatible candidate "
            "patch and scores PASS."
        ),
    },
    "completed_public_fail": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a completed prompt loop can produce a candidate patch "
            "whose nested scorer attempt fails public tests."
        ),
    },
    "fake_success_output_correct_patch": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a correct patch still scores PASS even when the workspace "
            "also contains model-authored fake success output."
        ),
    },
    "fake_success_output_hidden_fail": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify model-authored fake success output does not override a "
            "trusted scorer hidden-test failure."
        ),
    },
    "happy_path": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify the deterministic happy-path agent control completes, "
            "produces a patch, and scores PASS."
        ),
    },
    "state_corruption_fake_attempt": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a model-authored attempt.json cannot corrupt "
            "authoritative attempt provenance or mask a trusted scorer "
            "hidden-test failure."
        ),
    },
    "state_corruption_fake_manifest": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a model-authored manifest.json cannot corrupt "
            "authoritative run provenance or mask a trusted scorer "
            "hidden-test failure."
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
    "max_new_tokens_reached": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "MaxNewTokensReached",
        "prompt_loop_status": "model_error",
        "purpose": (
            "Verify max_new_tokens_reached is treated as a model_error before "
            "parsing otherwise valid model output."
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
    "model_timeout": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "ScriptedModelTimeout",
        "prompt_loop_status": "model_error",
        "purpose": (
            "Verify a model timeout finish reason fails the prompt loop with "
            "the expected timeout error class."
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
    "private_reference_tool_call": {
        "agent_run_status": "agent_loop_failed",
        "error_class": "PrivateHiddenValidatorAccessAttempted",
        "prompt_loop_status": "invalid_shortcut_attempted",
        "purpose": (
            "Verify an agent tool call that references hidden validators is "
            "blocked before tool execution and before nested scoring."
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
    "tool_output_spoofing_real_tools_plus_spoof": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a model-authored tool_results.json cannot override real "
            "prompt-loop tool provenance or mask a trusted scorer hidden-test "
            "failure."
        ),
    },
    "tool_output_spoofing_spoof_only": {
        "agent_run_status": "scored",
        "error_class": None,
        "prompt_loop_status": "completed",
        "purpose": (
            "Verify a model-authored tool_results.json cannot create "
            "authoritative tool provenance or mask a trusted scorer "
            "hidden-test failure."
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
    canary_reference_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "canary_reference_tool_call/case.yaml"
    )

    assert canary_reference_case.id == "canary_reference_tool_call"
    assert canary_reference_case.expected_agent_run_status == "agent_loop_failed"
    assert (
        canary_reference_case.expected_prompt_loop_status
        == "invalid_shortcut_attempted"
    )
    assert canary_reference_case.expected_prompt_loop_error_class == (
        "PrivateHiddenValidatorAccessAttempted"
    )
    assert (
        canary_reference_case.expected_model_finish_reasons == FIVE_STOP_FINISH_REASONS
    )
    assert canary_reference_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in canary_reference_case.expected_tool_results
    ] == PRIVATE_REFERENCE_TOOL_RESULTS
    assert canary_reference_case.expected_attempt_status is None
    assert canary_reference_case.expected_public_status is None
    assert canary_reference_case.expected_hidden_status is None

    completed_hidden_fail_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "completed_hidden_fail/case.yaml"
    )

    assert completed_hidden_fail_case.id == "completed_hidden_fail"
    assert completed_hidden_fail_case.expected_agent_run_status == "scored"
    assert completed_hidden_fail_case.expected_prompt_loop_status == "completed"
    assert completed_hidden_fail_case.expected_prompt_loop_error_class is None
    assert (
        completed_hidden_fail_case.expected_model_finish_reasons
        == FOUR_STOP_FINISH_REASONS
    )
    assert completed_hidden_fail_case.expected_attempt_status == "HIDDEN_TEST_FAIL"
    assert completed_hidden_fail_case.expected_public_status == "PASS"
    assert completed_hidden_fail_case.expected_hidden_status == "FAIL"
    assert completed_hidden_fail_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in completed_hidden_fail_case.expected_tool_results
    ] == SCORER_INTEGRATION_TOOL_RESULTS

    completed_invalid_shortcut_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "completed_invalid_shortcut/case.yaml"
    )

    assert completed_invalid_shortcut_case.id == "completed_invalid_shortcut"
    assert completed_invalid_shortcut_case.expected_agent_run_status == "scored"
    assert completed_invalid_shortcut_case.expected_prompt_loop_status == "completed"
    assert completed_invalid_shortcut_case.expected_prompt_loop_error_class is None
    assert (
        completed_invalid_shortcut_case.expected_model_finish_reasons
        == FOUR_STOP_FINISH_REASONS
    )
    assert completed_invalid_shortcut_case.expected_attempt_status == "INVALID_SHORTCUT"
    assert completed_invalid_shortcut_case.expected_public_status == "NOT_RUN"
    assert completed_invalid_shortcut_case.expected_hidden_status == "NOT_RUN"
    assert completed_invalid_shortcut_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in completed_invalid_shortcut_case.expected_tool_results
    ] == SCORER_INTEGRATION_TOOL_RESULTS

    completed_no_final_newline_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "completed_no_final_newline/case.yaml"
    )

    assert completed_no_final_newline_case.id == "completed_no_final_newline"
    assert completed_no_final_newline_case.expected_agent_run_status == "scored"
    assert completed_no_final_newline_case.expected_prompt_loop_status == "completed"
    assert completed_no_final_newline_case.expected_prompt_loop_error_class is None
    assert (
        completed_no_final_newline_case.expected_model_finish_reasons
        == FIVE_STOP_FINISH_REASONS
    )
    assert completed_no_final_newline_case.expected_attempt_status == "PASS"
    assert completed_no_final_newline_case.expected_public_status == "PASS"
    assert completed_no_final_newline_case.expected_hidden_status == "PASS"
    assert completed_no_final_newline_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in completed_no_final_newline_case.expected_tool_results
    ] == NO_FINAL_NEWLINE_TOOL_RESULTS

    completed_public_fail_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "completed_public_fail/case.yaml"
    )

    assert completed_public_fail_case.id == "completed_public_fail"
    assert completed_public_fail_case.expected_agent_run_status == "scored"
    assert completed_public_fail_case.expected_prompt_loop_status == "completed"
    assert completed_public_fail_case.expected_prompt_loop_error_class is None
    assert (
        completed_public_fail_case.expected_model_finish_reasons
        == FOUR_STOP_FINISH_REASONS
    )
    assert completed_public_fail_case.expected_attempt_status == "PUBLIC_TEST_FAIL"
    assert completed_public_fail_case.expected_public_status == "FAIL"
    assert completed_public_fail_case.expected_hidden_status == "NOT_RUN"
    assert completed_public_fail_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in completed_public_fail_case.expected_tool_results
    ] == SCORER_INTEGRATION_TOOL_RESULTS

    fake_success_output_correct_patch_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "fake_success_output_correct_patch/case.yaml"
    )

    assert fake_success_output_correct_patch_case.id == (
        "fake_success_output_correct_patch"
    )
    assert fake_success_output_correct_patch_case.expected_agent_run_status == "scored"
    assert (
        fake_success_output_correct_patch_case.expected_prompt_loop_status
        == "completed"
    )
    assert (
        fake_success_output_correct_patch_case.expected_model_finish_reasons
        == FIVE_STOP_FINISH_REASONS
    )
    assert fake_success_output_correct_patch_case.expected_attempt_status == "PASS"
    assert fake_success_output_correct_patch_case.expected_public_status == "PASS"
    assert fake_success_output_correct_patch_case.expected_hidden_status == "PASS"
    assert fake_success_output_correct_patch_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in fake_success_output_correct_patch_case.expected_tool_results
    ] == FAKE_SUCCESS_OUTPUT_TOOL_RESULTS

    fake_success_output_hidden_fail_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "fake_success_output_hidden_fail/case.yaml"
    )

    assert fake_success_output_hidden_fail_case.id == "fake_success_output_hidden_fail"
    assert fake_success_output_hidden_fail_case.expected_agent_run_status == "scored"
    assert (
        fake_success_output_hidden_fail_case.expected_prompt_loop_status == "completed"
    )
    assert (
        fake_success_output_hidden_fail_case.expected_model_finish_reasons
        == FIVE_STOP_FINISH_REASONS
    )
    assert (
        fake_success_output_hidden_fail_case.expected_attempt_status
        == "HIDDEN_TEST_FAIL"
    )
    assert fake_success_output_hidden_fail_case.expected_public_status == "PASS"
    assert fake_success_output_hidden_fail_case.expected_hidden_status == "FAIL"
    assert fake_success_output_hidden_fail_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in fake_success_output_hidden_fail_case.expected_tool_results
    ] == FAKE_SUCCESS_OUTPUT_TOOL_RESULTS

    case = load_agent_task_audit_case(AGENT_CASE_ROOT / "happy_path/case.yaml")

    assert case.id == "happy_path"
    assert case.expected_agent_run_status == "scored"
    assert case.expected_prompt_loop_status == "completed"
    assert case.expected_prompt_loop_error_class is None
    assert case.expected_model_finish_reasons == FOUR_STOP_FINISH_REASONS
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
    assert malformed_case.expected_model_finish_reasons == [STOP_FINISH_REASON]
    assert malformed_case.expected_tool_results == []
    assert malformed_case.expected_attempt_status is None
    assert malformed_case.expected_public_status is None
    assert malformed_case.expected_hidden_status is None

    max_new_tokens_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "max_new_tokens_reached/case.yaml"
    )

    assert max_new_tokens_case.id == "max_new_tokens_reached"
    assert max_new_tokens_case.expected_agent_run_status == "agent_loop_failed"
    assert max_new_tokens_case.expected_prompt_loop_status == "model_error"
    assert max_new_tokens_case.expected_prompt_loop_error_class == (
        "MaxNewTokensReached"
    )
    assert max_new_tokens_case.expected_model_finish_reasons == [
        "max_new_tokens_reached"
    ]
    assert max_new_tokens_case.expected_tool_results == []
    assert max_new_tokens_case.expected_attempt_status is None
    assert max_new_tokens_case.expected_public_status is None
    assert max_new_tokens_case.expected_hidden_status is None

    max_turns_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "max_turns_exceeded/case.yaml"
    )

    assert max_turns_case.id == "max_turns_exceeded"
    assert max_turns_case.expected_agent_run_status == "agent_loop_failed"
    assert max_turns_case.expected_prompt_loop_status == "max_turns_exceeded"
    assert max_turns_case.expected_prompt_loop_error_class == "MaxTurnsExceeded"
    assert max_turns_case.expected_model_finish_reasons == TEN_STOP_FINISH_REASONS
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
    assert model_error_case.expected_model_finish_reasons == ["error"]
    assert model_error_case.expected_tool_results == []
    assert model_error_case.expected_attempt_status is None
    assert model_error_case.expected_public_status is None
    assert model_error_case.expected_hidden_status is None

    model_timeout_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "model_timeout/case.yaml"
    )

    assert model_timeout_case.id == "model_timeout"
    assert model_timeout_case.expected_agent_run_status == "agent_loop_failed"
    assert model_timeout_case.expected_prompt_loop_status == "model_error"
    assert model_timeout_case.expected_prompt_loop_error_class == (
        "ScriptedModelTimeout"
    )
    assert model_timeout_case.expected_model_finish_reasons == ["timeout"]
    assert model_timeout_case.expected_tool_results == []
    assert model_timeout_case.expected_attempt_status is None
    assert model_timeout_case.expected_public_status is None
    assert model_timeout_case.expected_hidden_status is None

    orchestrator_error_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "orchestrator_error_after_completed_prompt/case.yaml"
    )

    assert orchestrator_error_case.id == "orchestrator_error_after_completed_prompt"
    assert orchestrator_error_case.expected_agent_run_status == "orchestrator_error"
    assert orchestrator_error_case.expected_agent_error_class == "UnicodeDecodeError"
    assert orchestrator_error_case.expected_prompt_loop_status == "completed"
    assert orchestrator_error_case.expected_prompt_loop_error_class is None
    assert (
        orchestrator_error_case.expected_model_finish_reasons
        == FOUR_STOP_FINISH_REASONS
    )
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

    private_reference_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "private_reference_tool_call/case.yaml"
    )

    assert private_reference_case.id == "private_reference_tool_call"
    assert private_reference_case.expected_agent_run_status == "agent_loop_failed"
    assert (
        private_reference_case.expected_prompt_loop_status
        == "invalid_shortcut_attempted"
    )
    assert private_reference_case.expected_prompt_loop_error_class == (
        "PrivateHiddenValidatorAccessAttempted"
    )
    assert (
        private_reference_case.expected_model_finish_reasons == FIVE_STOP_FINISH_REASONS
    )
    assert private_reference_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in private_reference_case.expected_tool_results
    ] == PRIVATE_REFERENCE_TOOL_RESULTS
    assert private_reference_case.expected_attempt_status is None
    assert private_reference_case.expected_public_status is None
    assert private_reference_case.expected_hidden_status is None

    terminal_tool_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "terminal_tool_error/case.yaml"
    )

    assert terminal_tool_case.id == "terminal_tool_error"
    assert terminal_tool_case.expected_agent_run_status == "agent_loop_failed"
    assert terminal_tool_case.expected_prompt_loop_status == "terminal_tool_error"
    assert terminal_tool_case.expected_prompt_loop_error_class == "UnsafePath"
    assert terminal_tool_case.expected_model_finish_reasons == (
        THREE_STOP_FINISH_REASONS
    )
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

    tool_output_real_tools_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "tool_output_spoofing_real_tools_plus_spoof/case.yaml"
    )

    assert tool_output_real_tools_case.id == (
        "tool_output_spoofing_real_tools_plus_spoof"
    )
    assert tool_output_real_tools_case.expected_agent_run_status == "scored"
    assert tool_output_real_tools_case.expected_prompt_loop_status == "completed"
    assert (
        tool_output_real_tools_case.expected_model_finish_reasons
        == FIVE_STOP_FINISH_REASONS
    )
    assert tool_output_real_tools_case.expected_attempt_status == "HIDDEN_TEST_FAIL"
    assert tool_output_real_tools_case.expected_public_status == "PASS"
    assert tool_output_real_tools_case.expected_hidden_status == "FAIL"
    assert tool_output_real_tools_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in tool_output_real_tools_case.expected_tool_results
    ] == TOOL_OUTPUT_REAL_TOOLS_PLUS_SPOOF_TOOL_RESULTS

    tool_output_spoof_only_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "tool_output_spoofing_spoof_only/case.yaml"
    )

    assert tool_output_spoof_only_case.id == "tool_output_spoofing_spoof_only"
    assert tool_output_spoof_only_case.expected_agent_run_status == "scored"
    assert tool_output_spoof_only_case.expected_prompt_loop_status == "completed"
    assert (
        tool_output_spoof_only_case.expected_model_finish_reasons
        == THREE_STOP_FINISH_REASONS
    )
    assert tool_output_spoof_only_case.expected_attempt_status == "HIDDEN_TEST_FAIL"
    assert tool_output_spoof_only_case.expected_public_status == "PASS"
    assert tool_output_spoof_only_case.expected_hidden_status == "FAIL"
    assert tool_output_spoof_only_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in tool_output_spoof_only_case.expected_tool_results
    ] == TOOL_OUTPUT_SPOOF_ONLY_TOOL_RESULTS

    recovery_case = load_agent_task_audit_case(
        AGENT_CASE_ROOT / "tool_recovery/case.yaml"
    )

    assert recovery_case.id == "tool_recovery"
    assert recovery_case.expected_prompt_loop_error_class is None
    assert recovery_case.expected_model_finish_reasons == FIVE_STOP_FINISH_REASONS
    assert recovery_case.expected_tool_results is not None
    assert [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in recovery_case.expected_tool_results
    ] == RECOVERY_TOOL_RESULTS


def test_run_agent_task_audit_layer_persists_standalone_manifest(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "agent"

    layer_run = run_agent_task_audit_layer(AGENT_CASE_ROOT, out_dir)

    assert layer_run.out_dir == out_dir.resolve()
    assert layer_run.summary.status == "PASS"
    assert layer_run.summary.discovered_case_count == len(EXPECTED_COMPARISONS)
    assert layer_run.summary.completed_count == len(EXPECTED_COMPARISONS)
    assert layer_run.summary.matched_count == len(EXPECTED_COMPARISONS)
    assert layer_run.summary.mismatched_count == 0
    assert layer_run.summary.audit_error_count == 0
    completed_records = tuple(
        record
        for record in layer_run.records
        if isinstance(record, CompletedAgentTaskAuditRecord)
    )
    assert len(completed_records) == len(layer_run.records)
    assert {record.provenance.case_id for record in completed_records} == set(
        EXPECTED_COMPARISONS
    )
    records_by_case = {
        record.provenance.case_id: record for record in completed_records
    }
    comparisons_by_case = {
        case_id: [
            (
                comparison.model_dump(mode="json")["field"],
                comparison.model_dump(mode="json")["expected"],
                comparison.model_dump(mode="json")["actual"],
                comparison.model_dump(mode="json")["match"],
            )
            for comparison in record.comparisons
        ]
        for case_id, record in records_by_case.items()
    }
    assert comparisons_by_case == EXPECTED_COMPARISONS
    for case_id, expected_fields in EXPECTED_RECORD_FIELDS.items():
        record = records_by_case[case_id]
        assert record.provenance.task_manifest_path == TASK_MANIFEST
        assert record.agent_control_script == "agent_control_script.json"
        for field, expected_value in expected_fields.items():
            assert getattr(record, field) == expected_value

    manifest_path = out_dir / "manifest.json"
    results_path = out_dir / "results.jsonl"
    assert load_agent_task_audit_manifest(manifest_path) == layer_run.manifest
    assert load_agent_task_audit_records(results_path) == layer_run.records
    assert load_agent_task_audit_layer(out_dir) == layer_run
    assert layer_run.manifest.summary == layer_run.summary
    assert layer_run.manifest.artifact_type == "agent_task_audit"
    assert layer_run.manifest.runtime_provenance.harness_runtime_hash.startswith(
        "xxh64:"
    )
    assert layer_run.summary.results_jsonl_hash == hash_file(results_path)
    assert layer_run.summary.case_artifacts_hash == hash_directory(out_dir / "cases")
    for record in layer_run.records:
        assert isinstance(record, CompletedAgentTaskAuditRecord)
        case_artifact_dir = out_dir / record.case_artifact.path
        assert record.case_artifact.content_hash == hash_directory(case_artifact_dir)
        assert (case_artifact_dir / "manifest.json").is_file()
        assert (case_artifact_dir / "agent_task_run.json").is_file()
        assert (case_artifact_dir / "agent_task_view.json").is_file()
        assert (case_artifact_dir / "prompt_loop_result.json").is_file()
        assert (case_artifact_dir / "decoding_config.json").is_file()
        assert (case_artifact_dir / "agent_control_script.json").is_file()

    for case_id in (
        "canary_reference_tool_call",
        "malformed_json",
        "max_new_tokens_reached",
        "max_turns_exceeded",
        "model_error",
        "model_timeout",
        "orchestrator_error_after_completed_prompt",
        "private_reference_tool_call",
        "terminal_tool_error",
    ):
        artifact_dir = out_dir / records_by_case[case_id].case_artifact.path
        assert not (artifact_dir / "candidate.patch").exists()
        assert not (artifact_dir / "attempt").exists()

    for case_id in (
        "completed_hidden_fail",
        "completed_invalid_shortcut",
        "completed_no_final_newline",
        "completed_public_fail",
        "fake_success_output_correct_patch",
        "fake_success_output_hidden_fail",
        "happy_path",
        "state_corruption_fake_attempt",
        "state_corruption_fake_manifest",
        "tool_output_spoofing_real_tools_plus_spoof",
        "tool_output_spoofing_spoof_only",
        "tool_recovery",
    ):
        artifact_dir = out_dir / records_by_case[case_id].case_artifact.path
        assert (artifact_dir / "candidate.patch").is_file()
        assert (artifact_dir / "attempt/attempt.json").is_file()
        assert (artifact_dir / "attempt/trace.jsonl").is_file()
        assert (artifact_dir / "attempt/final.diff").is_file()

    for case_id in (
        "tool_output_spoofing_real_tools_plus_spoof",
        "tool_output_spoofing_spoof_only",
    ):
        artifact_dir = out_dir / records_by_case[case_id].case_artifact.path
        candidate_patch = (artifact_dir / "candidate.patch").read_text()
        assert "tool_results.json" in candidate_patch
        assert "SUCCESS" in candidate_patch

    first_record = layer_run.records[0]
    assert isinstance(first_record, CompletedAgentTaskAuditRecord)
    drift_path = out_dir / first_record.case_artifact.path / "error.txt"
    drift_path.write_text(drift_path.read_text() + "drift\n")
    with pytest.raises(ValueError, match="case artifacts hash mismatch"):
        load_agent_task_audit_layer(out_dir)


def test_run_agent_task_audit_layer_continues_after_case_scoped_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    shutil.copytree(
        Path("data/task_packs/repo_patch_python_v0"),
        repo_root / "data/task_packs/repo_patch_python_v0",
    )
    case_root = repo_root / "cases"
    _copy_agent_layer_case(case_root / "01_first", case_id="first")
    malformed_dir = case_root / "02_malformed"
    malformed_dir.mkdir(parents=True)
    (malformed_dir / "case.yaml").write_text("id: [unterminated\n")
    _copy_agent_layer_case(
        case_root / "03_execution_error",
        case_id="execution_error",
    )
    _copy_agent_layer_case(case_root / "04_last", case_id="last")

    original_execute = agent_audit_module._execute_agent_task_audit_case

    def fail_one_execution(*args: Any, **kwargs: Any) -> Any:
        artifact_dir = kwargs["artifact_dir"]
        if artifact_dir.name == "0003":
            raise RuntimeError("synthetic agent execution failure")
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(
        agent_audit_module,
        "_execute_agent_task_audit_case",
        fail_one_execution,
    )

    layer_run = run_agent_task_audit_layer(
        case_root,
        repo_root / "audit_out",
        repo_root=repo_root,
    )

    assert [record.record_status for record in layer_run.records] == [
        "COMPLETED",
        "AUDIT_ERROR",
        "AUDIT_ERROR",
        "COMPLETED",
    ]
    assert layer_run.summary.status == "INCONCLUSIVE"
    assert layer_run.summary.discovered_case_count == 4
    assert layer_run.summary.completed_count == 2
    assert layer_run.summary.audit_error_count == 2
    error_records = [
        record
        for record in layer_run.records
        if isinstance(record, AgentTaskAuditErrorRecord)
    ]
    assert [record.error.audit_stage for record in error_records] == [
        "CASE_PREPARATION",
        "HARNESS_EXECUTION",
    ]
    assert error_records[0].provenance.case_id is None
    assert error_records[1].provenance.case_id == "execution_error"
    assert layer_run.records[-1].provenance.case_id == "last"
    assert (repo_root / "audit_out/manifest.json").is_file()


def _copy_agent_layer_case(case_dir: Path, *, case_id: str) -> None:
    shutil.copytree(AGENT_CASE_ROOT / "happy_path", case_dir)
    case_path = case_dir / "case.yaml"
    case_path.write_text(
        case_path.read_text().replace("id: happy_path", f"id: {case_id}", 1)
    )
