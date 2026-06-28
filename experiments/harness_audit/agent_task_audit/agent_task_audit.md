# Agent Task Audit

## Summary

| case | overall | agent_run_status | prompt_loop_status | agent_task_artifact_dir |
| --- | --- | --- | --- | --- |
| happy_path | PASS | scored | completed | agent_task_runs/happy_path |
| malformed_json | PASS | agent_loop_failed | invalid_model_output | agent_task_runs/malformed_json |
| max_turns_exceeded | PASS | agent_loop_failed | max_turns_exceeded | agent_task_runs/max_turns_exceeded |
| model_error | PASS | agent_loop_failed | model_error | agent_task_runs/model_error |
| tool_recovery | PASS | scored | completed | agent_task_runs/tool_recovery |

## Field Comparisons

| case | field | expected | actual | match |
| --- | --- | --- | --- | --- |
| happy_path | agent_run_status | scored | scored | PASS |
| happy_path | prompt_loop_status | completed | completed | PASS |
| happy_path | prompt_loop_error_class |  |  | PASS |
| happy_path | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| happy_path | attempt_status | PASS | PASS | PASS |
| happy_path | public_status | PASS | PASS | PASS |
| happy_path | hidden_status | PASS | PASS | PASS |
|  |  |  |  |  |
| malformed_json | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| malformed_json | prompt_loop_status | invalid_model_output | invalid_model_output | PASS |
| malformed_json | prompt_loop_error_class | MalformedModelOutput | MalformedModelOutput | PASS |
| malformed_json | tool_results | [] | [] | PASS |
| malformed_json | attempt_status |  |  | PASS |
| malformed_json | public_status |  |  | PASS |
| malformed_json | hidden_status |  |  | PASS |
|  |  |  |  |  |
| max_turns_exceeded | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| max_turns_exceeded | prompt_loop_status | max_turns_exceeded | max_turns_exceeded | PASS |
| max_turns_exceeded | prompt_loop_error_class | MaxTurnsExceeded | MaxTurnsExceeded | PASS |
| max_turns_exceeded | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}] | PASS |
| max_turns_exceeded | attempt_status |  |  | PASS |
| max_turns_exceeded | public_status |  |  | PASS |
| max_turns_exceeded | hidden_status |  |  | PASS |
|  |  |  |  |  |
| model_error | agent_run_status | agent_loop_failed | agent_loop_failed | PASS |
| model_error | prompt_loop_status | model_error | model_error | PASS |
| model_error | prompt_loop_error_class | ScriptedProviderError | ScriptedProviderError | PASS |
| model_error | tool_results | [] | [] | PASS |
| model_error | attempt_status |  |  | PASS |
| model_error | public_status |  |  | PASS |
| model_error | hidden_status |  |  | PASS |
|  |  |  |  |  |
| tool_recovery | agent_run_status | scored | scored | PASS |
| tool_recovery | prompt_loop_status | completed | completed | PASS |
| tool_recovery | prompt_loop_error_class |  |  | PASS |
| tool_recovery | tool_results | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| tool_recovery | attempt_status | PASS | PASS | PASS |
| tool_recovery | public_status | PASS | PASS | PASS |
| tool_recovery | hidden_status | PASS | PASS | PASS |
