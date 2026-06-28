# Agent Task Audit

## Summary

| case | overall | agent_run_status | prompt_loop_status | agent_task_artifact_dir |
| --- | --- | --- | --- | --- |
| happy_path | PASS | scored | completed | agent_task_runs/happy_path |

## Field Comparisons

| case | field | expected | actual | match |
| --- | --- | --- | --- | --- |
| happy_path | agent_run_status | scored | scored | PASS |
| happy_path | prompt_loop_status | completed | completed | PASS |
| happy_path | tool_results | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS |
| happy_path | attempt_status | PASS | PASS | PASS |
| happy_path | public_status | PASS | PASS | PASS |
| happy_path | hidden_status | PASS | PASS | PASS |
