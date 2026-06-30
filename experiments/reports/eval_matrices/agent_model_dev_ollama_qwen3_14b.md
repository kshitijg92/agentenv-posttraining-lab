# Eval Matrix Report

## Run Details

- Artifact directory: experiments/runs/agent_model_dev_ollama_qwen3_14b
- Eval matrix manifest: eval_matrix_manifest.json
- Eval matrix id: eval_matrix_bd70dbdacd8248829d1eb18602425b5e
- Config name: agent_model_dev_ollama_qwen3_14b
- Config path: configs/eval/agent_model_dev_ollama_qwen3_14b.yaml
- Config hash: xxh64:7bcc52485e45ef59
- Split: dev
- Task pack: data/task_packs/repo_patch_python_v0
- Task count: 3
- Policy count: 7
- Attempt count: 21
- Hidden-validator version/hash: not captured in eval_matrix_v0; current substitute is config hash xxh64:7bcc52485e45ef59
- Replay policy count: 0
- Replay run count: 0
- Replay run success summary: 0/0
- Replay match rate: not run

## Tasks

- repair_jsonl_deduper
- preserve_cli_error_codes
- repair_config_precedence

## Control Calibration

### Scorer Control Summary

| policy | control | attempts | final_pass_rate | public_pass_rate | hidden_pass_rate | public_pass_hidden_fail | env_or_harness_failures | scorer_or_orchestrator_failures | median_duration_ms | trace |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| oracle | oracle | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | 0 | 0 | 470 | policies/oracle/trace.jsonl |
| noop | bad.noop | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 459 | policies/noop/trace.jsonl |
| public-tests-only | bad.public_only | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 459 | policies/public-tests-only/trace.jsonl |

### Scorer Control Expectations

| policy | control | expected final | observed final | expected public | observed public | expected hidden | observed hidden | result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| oracle | oracle | PASS | 3/3 (100%) | PASS | 3/3 (100%) | PASS | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| noop | bad.noop | HIDDEN_TEST_FAIL | 3/3 (100%) | PASS | 3/3 (100%) | FAIL | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| public-tests-only | bad.public_only | HIDDEN_TEST_FAIL | 3/3 (100%) | PASS | 3/3 (100%) | FAIL | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |

### Scorer Aggregate Rates

- Oracle pass rate: 3/3 (100%)
- Known-bad final PASS rate: 0/6 (0%)
- Known-bad public-pass/hidden-fail rate: 6/6 (100%)
- Environment/harness failure rate: 0/9 (0%)
- Scorer/orchestrator failure rate: 0/9 (0%)

### Agent Control Summary

| policy | control | attempts | agent_scored_rate | prompt_loop_completed_rate | agent_loop_failed | nested_scorer_run_rate | nested_scorer_pass_rate | nested_public_pass_rate | nested_hidden_pass_rate | median_duration_ms | trace |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| agent-happy | happy | 3 | 3/3 (100%) | 3/3 (100%) | 0 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 824 | policies/agent-happy/trace.jsonl |
| agent-malformed | malformed | 3 | 0/3 (0%) | 0/3 (0%) | 3 | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) | 3 | policies/agent-malformed/trace.jsonl |
| agent-recoverable | recoverable | 3 | 3/3 (100%) | 3/3 (100%) | 0 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 755 | policies/agent-recoverable/trace.jsonl |

### Agent Control Budget Summary

| policy | model_ids | strategy | temperature | max_new_tokens | model_timeout_seconds | max_turns | prompt_tokens | completion_tokens | total_tokens | cost | invalid_tool_calls | tool_errors |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| agent-happy | agent-control-scripted-v0 | greedy | 0.0 | 512 | 30 | 10 | not_recorded | not_recorded | not_recorded | not_recorded | 0 | 0 |
| agent-malformed | agent-control-scripted-v0 | greedy | 0.0 | 512 | 30 | 10 | not_recorded | not_recorded | not_recorded | not_recorded | 0 | 0 |
| agent-recoverable | agent-control-scripted-v0 | greedy | 0.0 | 512 | 30 | 10 | not_recorded | not_recorded | not_recorded | not_recorded | 3 | 3 |

### Agent Control Expectations

| policy | control | expected agent_status | observed agent_status | expected prompt_loop | observed prompt_loop | expected nested_scorer | observed nested_scorer | result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| agent-happy | happy | scored | 3/3 (100%) | completed | 3/3 (100%) | PASS | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| agent-malformed | malformed | agent_loop_failed | 3/3 (100%) | invalid_model_output | 3/3 (100%) | not_run | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| agent-recoverable | recoverable | scored | 3/3 (100%) | completed | 3/3 (100%) | PASS | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |

### Agent Control Aggregate Rates

- Agent control expectation pass rate: 3/3 (100%)

### Control Per-Task Outcomes

| task_id | policy | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | agent_scorer_status | agent_scorer_public_status | agent_scorer_hidden_status | error_class | duration_ms | candidate_patch_bytes | final_diff_hash | artifact_dir |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| repair_jsonl_deduper | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | 470 |  | xxh64:791a044ad51af90c | policies/oracle/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | 1026 |  | xxh64:3a6c137988d3cd3a | policies/oracle/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | 447 |  | xxh64:187bcea16c66ce96 | policies/oracle/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 447 |  | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 605 |  | xxh64:ef46db3751d8e999 | policies/noop/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 459 |  | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 434 |  | xxh64:83ebe19f1a70c989 | policies/public-tests-only/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 612 |  | xxh64:2318ffb1a4be45cf | policies/public-tests-only/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 459 |  | xxh64:8ea4a8dafa72fda7 | policies/public-tests-only/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-happy | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 719 | 1241 | xxh64:791a044ad51af90c | policies/agent-happy/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-happy | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 969 | 2111 | xxh64:3a6c137988d3cd3a | policies/agent-happy/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-happy | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 824 | 1611 | xxh64:187bcea16c66ce96 | policies/agent-happy/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput | 3 |  |  | policies/agent-malformed/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput | 3 |  |  | policies/agent-malformed/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput | 4 |  |  | policies/agent-malformed/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-recoverable | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 732 | 1241 | xxh64:791a044ad51af90c | policies/agent-recoverable/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-recoverable | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 936 | 2111 | xxh64:3a6c137988d3cd3a | policies/agent-recoverable/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-recoverable | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 755 | 1611 | xxh64:187bcea16c66ce96 | policies/agent-recoverable/attempts/repair_config_precedence__attempt_001 |

### Replay Checks

- Replay match rate: not run
- Task exclusions: none recorded in eval_matrix_v0

Replay was not run for this eval matrix.

## Agent Model Results

### Agent Model Outcome Summary

| policy | attempts | agent_scored_rate | prompt_loop_completed_rate | agent_loop_failed | scorer_run_rate | final_pass_rate | public_pass_rate | hidden_pass_rate | median_duration_ms | trace |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| local-qwen-dev | 3 | 2/3 (67%) | 2/3 (67%) | 1 | 2/3 (67%) | 0/3 (0%) | 2/3 (67%) | 0/3 (0%) | 9922 | policies/local-qwen-dev/trace.jsonl |

### Agent Model Debug Signals

| policy | prompt_loop_statuses | agent_error_classes | nested_scorer_statuses | nested_scorer_error_classes | public_pass_hidden_fail | empty_patch | missing_patch | invalid_tool_calls | tool_errors |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| local-qwen-dev | completed=2, max_turns_exceeded=1 | MaxTurnsExceeded=1 | HIDDEN_TEST_FAIL=2 | HiddenCheckFailed=2 | 2 | 2 | 1 | 1 | 1 |

### Agent Model Budget Summary

| policy | model_ids | strategy | temperature | max_new_tokens | model_timeout_seconds | max_turns | prompt_tokens | completion_tokens | total_tokens | cost | invalid_tool_calls | tool_errors |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| local-qwen-dev | hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M | greedy | 0.0 | 1024 | 60 | 10 | 31244 | 1224 | 32468 | not_recorded | 1 | 1 |

### Agent Model Per-Task Outcomes

| task_id | policy | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | agent_scorer_status | agent_scorer_public_status | agent_scorer_hidden_status | error_class | duration_ms | candidate_patch_bytes | final_diff_hash | artifact_dir |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| repair_jsonl_deduper | local-qwen-dev | agent_task_run_artifacts_v0 |  |  |  | scored | completed | HIDDEN_TEST_FAIL | PASS | FAIL |  | 9922 | 0 | xxh64:ef46db3751d8e999 | policies/local-qwen-dev/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | local-qwen-dev | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | max_turns_exceeded |  |  |  | MaxTurnsExceeded | 31083 |  |  | policies/local-qwen-dev/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | local-qwen-dev | agent_task_run_artifacts_v0 |  |  |  | scored | completed | HIDDEN_TEST_FAIL | PASS | FAIL |  | 6681 | 0 | xxh64:ef46db3751d8e999 | policies/local-qwen-dev/attempts/repair_config_precedence__attempt_001 |

## Known Shortcuts

- `noop` and `public-tests-only` are calibration controls. They should pass public checks but fail hidden validators.
- Public-test-only success is not task success; final PASS requires `status: PASS`, `public_status: PASS`, and `hidden_status: PASS`.

## Measures

This report measures whether the local repo-patch task suite, public checks, hidden validators, and scripted controls behave consistently on the configured dev task set.

## Does Not Measure

This is not a model baseline, not a post-training result, not a secure-sandbox claim, and not evidence of broad coding-agent capability.
