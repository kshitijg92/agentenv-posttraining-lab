# Control Calibration

## Summary

- Control run ID: controls_570cd32938a5418794c3591418fb93e8
- Task pack: /home/kshitij/agentenv-posttraining-lab/data/task_packs/repo_patch_python_v0
- Repeats: 1
- Records: 24
- Overall: PASS

## Scorer Control Overview

| control | tasks | records | matches | failures | status |
| --- | ---: | ---: | ---: | ---: | --- |
| all controls | 4 | 12 | 12/12 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |
| bad.noop | 4 | 4 | 4/4 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |
| bad.public_only | 4 | 4 | 4/4 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |
| oracle | 4 | 4 | 4/4 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |

## Agent Control Overview

| control | tasks | records | matches | failures | status |
| --- | ---: | ---: | ---: | ---: | --- |
| all controls | 4 | 12 | 12/12 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |
| happy | 4 | 4 | 4/4 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |
| malformed | 4 | 4 | 4/4 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |
| recoverable | 4 | 4 | 4/4 | 0 | <span style="background-color: #dcfce7; color: #166534; font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span> |

## Scorer Control Summary

| task_id | control | repeats | matches | expected_attempt | expected_public | expected_hidden |
| --- | --- | ---: | ---: | --- | --- | --- |
| preserve_cli_error_codes | bad.noop | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| preserve_cli_error_codes | bad.public_only | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| preserve_cli_error_codes | oracle | 1 | 1/1 | PASS | PASS | PASS |
| repair_config_precedence | bad.noop | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| repair_config_precedence | bad.public_only | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| repair_config_precedence | oracle | 1 | 1/1 | PASS | PASS | PASS |
| repair_jsonl_deduper | bad.noop | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| repair_jsonl_deduper | bad.public_only | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| repair_jsonl_deduper | oracle | 1 | 1/1 | PASS | PASS | PASS |
| toy_python_fix_001 | bad.noop | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| toy_python_fix_001 | bad.public_only | 1 | 1/1 | HIDDEN_TEST_FAIL | PASS | FAIL |
| toy_python_fix_001 | oracle | 1 | 1/1 | PASS | PASS | PASS |

## Agent Control Summary

| task_id | control | repeats | matches | expected_prompt_loop | expected_tool_results |
| --- | --- | ---: | ---: | --- | --- |
| preserve_cli_error_codes | happy | 1 | 1/1 | completed |  |
| preserve_cli_error_codes | malformed | 1 | 1/1 | invalid_model_output |  |
| preserve_cli_error_codes | recoverable | 1 | 1/1 | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] |
| repair_config_precedence | happy | 1 | 1/1 | completed |  |
| repair_config_precedence | malformed | 1 | 1/1 | invalid_model_output |  |
| repair_config_precedence | recoverable | 1 | 1/1 | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] |
| repair_jsonl_deduper | happy | 1 | 1/1 | completed |  |
| repair_jsonl_deduper | malformed | 1 | 1/1 | invalid_model_output |  |
| repair_jsonl_deduper | recoverable | 1 | 1/1 | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] |
| toy_python_fix_001 | happy | 1 | 1/1 | completed |  |
| toy_python_fix_001 | malformed | 1 | 1/1 | invalid_model_output |  |
| toy_python_fix_001 | recoverable | 1 | 1/1 | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] |

## Scorer Record Details

| task_id | control | repeat | expected_attempt | actual_attempt | expected_public | actual_public | expected_hidden | actual_hidden | error_class | final_diff_hash | match | artifact_dir |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| preserve_cli_error_codes | oracle | 1 | PASS | PASS | PASS | PASS | PASS | PASS |  | xxh64:3a6c137988d3cd3a | PASS | scorer_control_patches/preserve_cli_error_codes__oracle__repeat_001 |
| preserve_cli_error_codes | bad.noop | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:ef46db3751d8e999 | PASS | scorer_control_patches/preserve_cli_error_codes__bad_noop__repeat_001 |
| preserve_cli_error_codes | bad.public_only | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:2318ffb1a4be45cf | PASS | scorer_control_patches/preserve_cli_error_codes__bad_public_only__repeat_001 |
| repair_config_precedence | oracle | 1 | PASS | PASS | PASS | PASS | PASS | PASS |  | xxh64:187bcea16c66ce96 | PASS | scorer_control_patches/repair_config_precedence__oracle__repeat_001 |
| repair_config_precedence | bad.noop | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:ef46db3751d8e999 | PASS | scorer_control_patches/repair_config_precedence__bad_noop__repeat_001 |
| repair_config_precedence | bad.public_only | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:8ea4a8dafa72fda7 | PASS | scorer_control_patches/repair_config_precedence__bad_public_only__repeat_001 |
| repair_jsonl_deduper | oracle | 1 | PASS | PASS | PASS | PASS | PASS | PASS |  | xxh64:791a044ad51af90c | PASS | scorer_control_patches/repair_jsonl_deduper__oracle__repeat_001 |
| repair_jsonl_deduper | bad.noop | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:ef46db3751d8e999 | PASS | scorer_control_patches/repair_jsonl_deduper__bad_noop__repeat_001 |
| repair_jsonl_deduper | bad.public_only | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:83ebe19f1a70c989 | PASS | scorer_control_patches/repair_jsonl_deduper__bad_public_only__repeat_001 |
| toy_python_fix_001 | oracle | 1 | PASS | PASS | PASS | PASS | PASS | PASS |  | xxh64:e3fc746d6fe0786c | PASS | scorer_control_patches/toy_python_fix_001__oracle__repeat_001 |
| toy_python_fix_001 | bad.noop | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:ef46db3751d8e999 | PASS | scorer_control_patches/toy_python_fix_001__bad_noop__repeat_001 |
| toy_python_fix_001 | bad.public_only | 1 | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS | PASS | FAIL | FAIL | HiddenCheckFailed | xxh64:963c30a755bee9ee | PASS | scorer_control_patches/toy_python_fix_001__bad_public_only__repeat_001 |

## Agent Record Details

| task_id | control | repeat | expected_prompt_loop | actual_agent_run | actual_prompt_loop | expected_tool_results | actual_tool_results | nested_attempt | nested_public | nested_hidden | error_class | match | artifact_dir |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| preserve_cli_error_codes | happy | 1 | completed | scored | completed |  | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/preserve_cli_error_codes__happy__repeat_001 |
| preserve_cli_error_codes | malformed | 1 | invalid_model_output | agent_loop_failed | invalid_model_output |  | [] |  |  |  | MalformedModelOutput | PASS | agent_control_scripts/preserve_cli_error_codes__malformed__repeat_001 |
| preserve_cli_error_codes | recoverable | 1 | completed | scored | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/preserve_cli_error_codes__recoverable__repeat_001 |
| repair_config_precedence | happy | 1 | completed | scored | completed |  | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/repair_config_precedence__happy__repeat_001 |
| repair_config_precedence | malformed | 1 | invalid_model_output | agent_loop_failed | invalid_model_output |  | [] |  |  |  | MalformedModelOutput | PASS | agent_control_scripts/repair_config_precedence__malformed__repeat_001 |
| repair_config_precedence | recoverable | 1 | completed | scored | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/repair_config_precedence__recoverable__repeat_001 |
| repair_jsonl_deduper | happy | 1 | completed | scored | completed |  | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/repair_jsonl_deduper__happy__repeat_001 |
| repair_jsonl_deduper | malformed | 1 | invalid_model_output | agent_loop_failed | invalid_model_output |  | [] |  |  |  | MalformedModelOutput | PASS | agent_control_scripts/repair_jsonl_deduper__malformed__repeat_001 |
| repair_jsonl_deduper | recoverable | 1 | completed | scored | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/repair_jsonl_deduper__recoverable__repeat_001 |
| toy_python_fix_001 | happy | 1 | completed | scored | completed |  | [{"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/toy_python_fix_001__happy__repeat_001 |
| toy_python_fix_001 | malformed | 1 | invalid_model_output | agent_loop_failed | invalid_model_output |  | [] |  |  |  | MalformedModelOutput | PASS | agent_control_scripts/toy_python_fix_001__malformed__repeat_001 |
| toy_python_fix_001 | recoverable | 1 | completed | scored | completed | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | [{"error_class": "InvalidToolInput", "status": "error", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "read_file"}, {"error_class": null, "status": "ok", "tool_name": "write_file"}, {"error_class": null, "status": "ok", "tool_name": "run_tests"}] | PASS | PASS | PASS |  | PASS | agent_control_scripts/toy_python_fix_001__recoverable__repeat_001 |
