# Eval Matrix Report

## Run Details

- Artifact directory: experiments/runs/cli_smoke_dev_baseline
- Eval matrix manifest: eval_matrix_manifest.json
- Eval matrix id: eval_matrix_baecd75e761840e2b77091e5653085a7
- Config name: dev_baseline
- Config path: configs/eval/dev_baseline.yaml
- Config hash: xxh64:7d0070161dcfb5d0
- Split: dev
- Task pack: data/task_packs/repo_patch_python_v0
- Task count: 3
- Policy count: 6
- Attempt count: 18
- Hidden-validator version/hash: not captured in eval_matrix_v0; current substitute is config hash xxh64:7d0070161dcfb5d0
- Replay scope: control_policies
- Replay repeats: 1
- Replay match rate: 18/18 (100%)

## Tasks

- repair_jsonl_deduper
- preserve_cli_error_codes
- repair_config_precedence

## Policy Summary

| policy | attempts | final_pass_rate | public_pass_rate | hidden_pass_rate | public_pass_hidden_fail | env_or_harness_failures | scorer_or_orchestrator_failures | median_duration_ms | trace |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| oracle | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | 0 | 0 | 537 | policies/oracle/trace.jsonl |
| noop | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 494 | policies/noop/trace.jsonl |
| public-tests-only | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 499 | policies/public-tests-only/trace.jsonl |
| agent-happy | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | 0 | 0 | 875 | policies/agent-happy/trace.jsonl |
| agent-malformed | 3 | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) | 0 | 0 | 0 | 3 | policies/agent-malformed/trace.jsonl |
| agent-recoverable | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | 0 | 0 | 793 | policies/agent-recoverable/trace.jsonl |

## Calibration Checks

### Control Expectations

| policy | expected final | observed final | expected public | observed public | expected hidden | observed hidden | result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| oracle | PASS | 3/3 (100%) | PASS | 3/3 (100%) | PASS | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| noop | HIDDEN_TEST_FAIL | 3/3 (100%) | PASS | 3/3 (100%) | FAIL | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| public-tests-only | HIDDEN_TEST_FAIL | 3/3 (100%) | PASS | 3/3 (100%) | FAIL | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| agent-happy |  |  |  |  |  |  | <span style="color: gray">NOT_CHECKED</span> |
| agent-malformed |  |  |  |  |  |  | <span style="color: gray">NOT_CHECKED</span> |
| agent-recoverable |  |  |  |  |  |  | <span style="color: gray">NOT_CHECKED</span> |

### Aggregate Rates

- Oracle pass rate: 3/3 (100%)
- Known-bad final PASS rate: 0/6 (0%)
- Known-bad public-pass/hidden-fail rate: 6/6 (100%)
- Environment/harness failure rate: 0/18 (0%)
- Scorer/orchestrator failure rate: 0/18 (0%)
- Replay match rate: 18/18 (100%)
- Task exclusions: none recorded in eval_matrix_v0

### Replay Checks

| policy | status | match_rate | error_count | replay_result |
| --- | --- | ---: | ---: | --- |
| oracle | PASS | 3/3 (100%) | 0 | replays/oracle__replay_001/replay_result.json |
| noop | PASS | 3/3 (100%) | 0 | replays/noop__replay_001/replay_result.json |
| public-tests-only | PASS | 3/3 (100%) | 0 | replays/public-tests-only__replay_001/replay_result.json |
| agent-happy | PASS | 3/3 (100%) | 0 | replays/agent-happy__replay_001/replay_result.json |
| agent-malformed | PASS | 3/3 (100%) | 0 | replays/agent-malformed__replay_001/replay_result.json |
| agent-recoverable | PASS | 3/3 (100%) | 0 | replays/agent-recoverable__replay_001/replay_result.json |

## Per-Task Outcomes

| task_id | policy | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | error_class | duration_ms | final_diff_hash | artifact_dir |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| repair_jsonl_deduper | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  | 537 | xxh64:791a044ad51af90c | policies/oracle/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  | 711 | xxh64:3a6c137988d3cd3a | policies/oracle/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  | 496 | xxh64:187bcea16c66ce96 | policies/oracle/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  | HiddenCheckFailed | 487 | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  | HiddenCheckFailed | 671 | xxh64:ef46db3751d8e999 | policies/noop/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  | HiddenCheckFailed | 494 | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  | HiddenCheckFailed | 485 | xxh64:83ebe19f1a70c989 | policies/public-tests-only/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  | HiddenCheckFailed | 795 | xxh64:2318ffb1a4be45cf | policies/public-tests-only/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | public-tests-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  | HiddenCheckFailed | 499 | xxh64:8ea4a8dafa72fda7 | policies/public-tests-only/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-happy | agent_task_run_artifacts_v0 | PASS | PASS | PASS | scored | completed |  | 756 | xxh64:791a044ad51af90c | policies/agent-happy/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-happy | agent_task_run_artifacts_v0 | PASS | PASS | PASS | scored | completed |  | 989 | xxh64:3a6c137988d3cd3a | policies/agent-happy/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-happy | agent_task_run_artifacts_v0 | PASS | PASS | PASS | scored | completed |  | 875 | xxh64:187bcea16c66ce96 | policies/agent-happy/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output | MalformedModelOutput | 3 |  | policies/agent-malformed/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output | MalformedModelOutput | 3 |  | policies/agent-malformed/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-malformed | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output | MalformedModelOutput | 4 |  | policies/agent-malformed/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | agent-recoverable | agent_task_run_artifacts_v0 | PASS | PASS | PASS | scored | completed |  | 792 | xxh64:791a044ad51af90c | policies/agent-recoverable/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | agent-recoverable | agent_task_run_artifacts_v0 | PASS | PASS | PASS | scored | completed |  | 991 | xxh64:3a6c137988d3cd3a | policies/agent-recoverable/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | agent-recoverable | agent_task_run_artifacts_v0 | PASS | PASS | PASS | scored | completed |  | 793 | xxh64:187bcea16c66ce96 | policies/agent-recoverable/attempts/repair_config_precedence__attempt_001 |

## Known Shortcuts

- `noop` and `public-tests-only` are calibration controls. They should pass public checks but fail hidden validators.
- Public-test-only success is not task success; final PASS requires `status: PASS`, `public_status: PASS`, and `hidden_status: PASS`.

## Measures

This report measures whether the local repo-patch task suite, public checks, hidden validators, and scripted controls behave consistently on the configured dev task set.

## Does Not Measure

This is not a model baseline, not a post-training result, not a secure-sandbox claim, and not evidence of broad coding-agent capability.
