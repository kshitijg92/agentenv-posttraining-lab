# Eval Matrix Report

## Run Details

- Artifact directory: experiments/runs/dev_baseline
- Eval matrix manifest: eval_matrix_manifest.json
- Eval matrix id: eval_matrix_f8631e165a47473c969302cb5bd81695
- Config name: dev_baseline
- Config path: configs/eval/dev_baseline.yaml
- Config hash: xxh64:00db51e25e3a97e4
- Split: dev
- Task pack: data/task_packs/repo_patch_python_v0
- Task count: 3
- Policy count: 6
- Attempt count: 18
- Hidden-validator version/hash: not captured in eval_matrix_v0; current substitute is config hash xxh64:00db51e25e3a97e4
- Replay policy count: 6
- Replay run count: 6
- Replay run success summary: 6/6
- Replay match rate: 18/18 (100%)

## Tasks

- repair_jsonl_deduper
- preserve_cli_error_codes
- repair_config_precedence

## Control Calibration

### Scorer Control Summary

| policy | control | attempts | final_pass_rate | public_pass_rate | hidden_pass_rate | public_pass_hidden_fail | env_or_harness_failures | scorer_or_orchestrator_failures | median_duration_ms | trace |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| oracle | oracle | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | 0 | 0 | 597 | policies/oracle/trace.jsonl |
| noop | bad.noop | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 468 | policies/noop/trace.jsonl |
| public-tests-only | bad.public_only | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 457 | policies/public-tests-only/trace.jsonl |

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
| agent-happy | happy | 3 | 3/3 (100%) | 3/3 (100%) | 0 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 749 | policies/agent-happy/trace.jsonl |
| agent-malformed | malformed | 3 | 0/3 (0%) | 0/3 (0%) | 3 | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) | 3 | policies/agent-malformed/trace.jsonl |
| agent-recoverable | recoverable | 3 | 3/3 (100%) | 3/3 (100%) | 0 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 753 | policies/agent-recoverable/trace.jsonl |

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
| repair_jsonl_deduper | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | 597 |  | xxh64:791a044ad51af90c | policies/oracle/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | 997 |  | xxh64:3a6c137988d3cd3a | policies/oracle/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | 442 |  | xxh64:187bcea16c66ce96 | policies/oracle/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 440 |  | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 612 |  | xxh64:ef46db3751d8e999 | policies/noop/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 468 |  | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 440 |  | xxh64:83ebe19f1a70c989 | policies/public-tests-only/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 623 |  | xxh64:2318ffb1a4be45cf | policies/public-tests-only/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 457 |  | xxh64:8ea4a8dafa72fda7 | policies/public-tests-only/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-happy | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 715 | 1241 | xxh64:791a044ad51af90c | policies/agent-happy/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-happy | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 921 | 2111 | xxh64:3a6c137988d3cd3a | policies/agent-happy/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-happy | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 749 | 1611 | xxh64:187bcea16c66ce96 | policies/agent-happy/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput | 3 |  |  | policies/agent-malformed/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput | 3 |  |  | policies/agent-malformed/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput | 3 |  |  | policies/agent-malformed/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-recoverable | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 720 | 1241 | xxh64:791a044ad51af90c | policies/agent-recoverable/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-recoverable | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 932 | 2111 | xxh64:3a6c137988d3cd3a | policies/agent-recoverable/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-recoverable | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | 753 | 1611 | xxh64:187bcea16c66ce96 | policies/agent-recoverable/attempts/repair_config_precedence__attempt_001 |

### Replay Checks

- Replay match rate: 18/18 (100%)
- Task exclusions: none recorded in eval_matrix_v0

| policy | status | match_rate | error_count | replay_result |
| --- | --- | ---: | ---: | --- |
| oracle | PASS | 3/3 (100%) | 0 | replays/oracle__replay_001/replay_result.json |
| noop | PASS | 3/3 (100%) | 0 | replays/noop__replay_001/replay_result.json |
| public-tests-only | PASS | 3/3 (100%) | 0 | replays/public-tests-only__replay_001/replay_result.json |
| agent-happy | PASS | 3/3 (100%) | 0 | replays/agent-happy__replay_001/replay_result.json |
| agent-malformed | PASS | 3/3 (100%) | 0 | replays/agent-malformed__replay_001/replay_result.json |
| agent-recoverable | PASS | 3/3 (100%) | 0 | replays/agent-recoverable__replay_001/replay_result.json |

## Agent Model Results

### Agent Model Outcome Summary

No agent model policies in this eval matrix.

### Agent Model Debug Signals

No agent model debug signals in this eval matrix.

### Agent Model Budget Summary

No agent budget metadata in this eval matrix.

### Agent Model Per-Task Outcomes

No agent model policy attempts in this eval matrix.

## Known Shortcuts

- `noop` and `public-tests-only` are calibration controls. They should pass public checks but fail hidden validators.
- Public-test-only success is not task success; final PASS requires `status: PASS`, `public_status: PASS`, and `hidden_status: PASS`.

## Measures

This report measures whether the local repo-patch task suite, public checks, hidden validators, and scripted controls behave consistently on the configured dev task set.

## Does Not Measure

This is not a model baseline, not a post-training result, not a secure-sandbox claim, and not evidence of broad coding-agent capability.
