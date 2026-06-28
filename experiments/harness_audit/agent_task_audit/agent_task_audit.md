# Agent Task Audit

## Summary

| case | overall | agent_run_status | prompt_loop_status | agent_task_artifact_dir |
| --- | --- | --- | --- | --- |
| completed_hidden_fail | PASS | scored | completed | agent_task_runs/completed_hidden_fail |
| completed_invalid_shortcut | PASS | scored | completed | agent_task_runs/completed_invalid_shortcut |
| completed_public_fail | PASS | scored | completed | agent_task_runs/completed_public_fail |
| happy_path | PASS | scored | completed | agent_task_runs/happy_path |
| malformed_json | PASS | agent_loop_failed | invalid_model_output | agent_task_runs/malformed_json |
| max_new_tokens_reached | PASS | agent_loop_failed | model_error | agent_task_runs/max_new_tokens_reached |
| max_turns_exceeded | PASS | agent_loop_failed | max_turns_exceeded | agent_task_runs/max_turns_exceeded |
| model_error | PASS | agent_loop_failed | model_error | agent_task_runs/model_error |
| model_timeout | PASS | agent_loop_failed | model_error | agent_task_runs/model_timeout |
| orchestrator_error_after_completed_prompt | PASS | orchestrator_error | completed | agent_task_runs/orchestrator_error_after_completed_prompt |
| terminal_tool_error | PASS | agent_loop_failed | terminal_tool_error | agent_task_runs/terminal_tool_error |
| tool_recovery | PASS | scored | completed | agent_task_runs/tool_recovery |

## Field Comparisons

| case | field | expected | actual | match |
| --- | --- | --- | --- | --- |
| completed_hidden_fail | agent_run_status | scored | scored | PASS |
| completed_hidden_fail | prompt_loop_status | completed | completed | PASS |
| completed_hidden_fail | prompt_loop_error_class |  |  | PASS |
| completed_hidden_fail | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| completed_hidden_fail | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| completed_hidden_fail | attempt_status | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS |
| completed_hidden_fail | public_status | PASS | PASS | PASS |
| completed_hidden_fail | hidden_status | FAIL | FAIL | PASS |
|  |  |  |  |  |
| completed_invalid_shortcut | agent_run_status | scored | scored | PASS |
| completed_invalid_shortcut | prompt_loop_status | completed | completed | PASS |
| completed_invalid_shortcut | prompt_loop_error_class |  |  | PASS |
| completed_invalid_shortcut | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| completed_invalid_shortcut | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| completed_invalid_shortcut | attempt_status | INVALID_SHORTCUT | INVALID_SHORTCUT | PASS |
| completed_invalid_shortcut | public_status | NOT_RUN | NOT_RUN | PASS |
| completed_invalid_shortcut | hidden_status | NOT_RUN | NOT_RUN | PASS |
|  |  |  |  |  |
| completed_public_fail | agent_run_status | scored | scored | PASS |
| completed_public_fail | prompt_loop_status | completed | completed | PASS |
| completed_public_fail | prompt_loop_error_class |  |  | PASS |
| completed_public_fail | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| completed_public_fail | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| completed_public_fail | attempt_status | PUBLIC_TEST_FAIL | PUBLIC_TEST_FAIL | PASS |
| completed_public_fail | public_status | FAIL | FAIL | PASS |
| completed_public_fail | hidden_status | NOT_RUN | NOT_RUN | PASS |
|  |  |  |  |  |
| happy_path | agent_run_status | scored | scored | PASS |
| happy_path | prompt_loop_status | completed | completed | PASS |
| happy_path | prompt_loop_error_class |  |  | PASS |
| happy_path | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| happy_path | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| happy_path | attempt_status | PASS | PASS | PASS |
| happy_path | public_status | PASS | PASS | PASS |
| happy_path | hidden_status | PASS | PASS | PASS |
|  |  |  |  |  |
| malformed_json | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| malformed_json | prompt_loop_status | invalid_model_output | invalid_model_output | PASS |
| malformed_json | prompt_loop_error_class | MalformedModelOutput | MalformedModelOutput | PASS |
| malformed_json | model_finish_reasons | ["stop_criteria_met"] | ["stop_criteria_met"] | PASS |
| malformed_json | tool_results | [] | [] | PASS |
| malformed_json | attempt_status |  |  | PASS |
| malformed_json | public_status |  |  | PASS |
| malformed_json | hidden_status |  |  | PASS |
|  |  |  |  |  |
| max_new_tokens_reached | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| max_new_tokens_reached | prompt_loop_status | model_error | model_error | PASS |
| max_new_tokens_reached | prompt_loop_error_class | MaxNewTokensReached | MaxNewTokensReached | PASS |
| max_new_tokens_reached | model_finish_reasons | ["max_new_tokens_reached"] | ["max_new_tokens_reached"] | PASS |
| max_new_tokens_reached | tool_results | [] | [] | PASS |
| max_new_tokens_reached | attempt_status |  |  | PASS |
| max_new_tokens_reached | public_status |  |  | PASS |
| max_new_tokens_reached | hidden_status |  |  | PASS |
|  |  |  |  |  |
| max_turns_exceeded | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| max_turns_exceeded | prompt_loop_status | max_turns_exceeded | max_turns_exceeded | PASS |
| max_turns_exceeded | prompt_loop_error_class | MaxTurnsExceeded | MaxTurnsExceeded | PASS |
| max_turns_exceeded | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| max_turns_exceeded | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}] | PASS |
| max_turns_exceeded | attempt_status |  |  | PASS |
| max_turns_exceeded | public_status |  |  | PASS |
| max_turns_exceeded | hidden_status |  |  | PASS |
|  |  |  |  |  |
| model_error | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| model_error | prompt_loop_status | model_error | model_error | PASS |
| model_error | prompt_loop_error_class | ScriptedProviderError | ScriptedProviderError | PASS |
| model_error | model_finish_reasons | ["error"] | ["error"] | PASS |
| model_error | tool_results | [] | [] | PASS |
| model_error | attempt_status |  |  | PASS |
| model_error | public_status |  |  | PASS |
| model_error | hidden_status |  |  | PASS |
|  |  |  |  |  |
| model_timeout | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| model_timeout | prompt_loop_status | model_error | model_error | PASS |
| model_timeout | prompt_loop_error_class | ScriptedModelTimeout | ScriptedModelTimeout | PASS |
| model_timeout | model_finish_reasons | ["timeout"] | ["timeout"] | PASS |
| model_timeout | tool_results | [] | [] | PASS |
| model_timeout | attempt_status |  |  | PASS |
| model_timeout | public_status |  |  | PASS |
| model_timeout | hidden_status |  |  | PASS |
|  |  |  |  |  |
| orchestrator_error_after_completed_prompt | agent_run_status | orchestrator_error | orchestrator_error | PASS |
| orchestrator_error_after_completed_prompt | agent_error_class | UnicodeDecodeError | UnicodeDecodeError | PASS |
| orchestrator_error_after_completed_prompt | prompt_loop_status | completed | completed | PASS |
| orchestrator_error_after_completed_prompt | prompt_loop_error_class |  |  | PASS |
| orchestrator_error_after_completed_prompt | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| orchestrator_error_after_completed_prompt | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| orchestrator_error_after_completed_prompt | attempt_status |  |  | PASS |
| orchestrator_error_after_completed_prompt | public_status |  |  | PASS |
| orchestrator_error_after_completed_prompt | hidden_status |  |  | PASS |
|  |  |  |  |  |
| terminal_tool_error | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| terminal_tool_error | prompt_loop_status | terminal_tool_error | terminal_tool_error | PASS |
| terminal_tool_error | prompt_loop_error_class | UnsafePath | UnsafePath | PASS |
| terminal_tool_error | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| terminal_tool_error | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": "UnsafePath", "status": "error", "tool_name": "read_file"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": "UnsafePath", "status": "error", "tool_name": "read_file"}] | PASS |
| terminal_tool_error | attempt_status |  |  | PASS |
| terminal_tool_error | public_status |  |  | PASS |
| terminal_tool_error | hidden_status |  |  | PASS |
|  |  |  |  |  |
| tool_recovery | agent_run_status | scored | scored | PASS |
| tool_recovery | prompt_loop_status | completed | completed | PASS |
| tool_recovery | prompt_loop_error_class |  |  | PASS |
| tool_recovery | model_finish_reasons | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | ["stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met", "stop_criteria_met"] | PASS |
| tool_recovery | tool_results | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| tool_recovery | attempt_status | PASS | PASS | PASS |
| tool_recovery | public_status | PASS | PASS | PASS |
| tool_recovery | hidden_status | PASS | PASS | PASS |
