# Eval Matrix Report

## Run Details

- Artifact directory: experiments/runs/dev_baseline
- Eval matrix manifest: eval_matrix_manifest.json
- Eval matrix id: eval_matrix_c0af625bfc104689ad7d489a043c42f8
- Config name: dev_baseline
- Config path: configs/eval/dev_baseline.yaml
- Config hash: xxh64:2f1db658e87d2562
- Split: dev
- Task pack: data/task_packs/repo_patch_python_v0
- Task count: 3
- Policy count: 3
- Attempt count: 9
- Hidden-validator version/hash: not captured in eval_matrix_v0; current substitute is config hash xxh64:2f1db658e87d2562
- Replay scope: scorer_control_patch
- Replay match rate: 9/9 (100%)

## Tasks

- repair_jsonl_deduper
- preserve_cli_error_codes
- repair_config_precedence

## Policy Summary

| policy | attempts | final_pass_rate | public_pass_rate | hidden_pass_rate | public_pass_hidden_fail | env_or_harness_failures | scorer_or_orchestrator_failures | median_duration_ms | trace |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| oracle | 3 | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 0 | 0 | 0 | 465 | policies/oracle/trace.jsonl |
| noop | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 491 | policies/noop/trace.jsonl |
| public-tests-only | 3 | 0/3 (0%) | 3/3 (100%) | 0/3 (0%) | 3 | 0 | 0 | 511 | policies/public-tests-only/trace.jsonl |

## Calibration Checks

### Control Expectations

| policy | expected final | observed final | expected public | observed public | expected hidden | observed hidden | result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| oracle | PASS | 3/3 (100%) | PASS | 3/3 (100%) | PASS | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| noop | HIDDEN_TEST_FAIL | 3/3 (100%) | PASS | 3/3 (100%) | FAIL | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |
| public-tests-only | HIDDEN_TEST_FAIL | 3/3 (100%) | PASS | 3/3 (100%) | FAIL | 3/3 (100%) | <span style="color: green">ON_TRACK</span> |

### Aggregate Rates

- Oracle pass rate: 3/3 (100%)
- Known-bad final PASS rate: 0/6 (0%)
- Known-bad public-pass/hidden-fail rate: 6/6 (100%)
- Environment/harness failure rate: 0/9 (0%)
- Scorer/orchestrator failure rate: 0/9 (0%)
- Replay match rate: 9/9 (100%)
- Task exclusions: none recorded in eval_matrix_v0

### Replay Checks

| policy | status | match_rate | error_count | replay_result |
| --- | --- | ---: | ---: | --- |
| oracle | PASS | 3/3 (100%) | 0 | replays/oracle/replay_result.json |
| noop | PASS | 3/3 (100%) | 0 | replays/noop/replay_result.json |
| public-tests-only | PASS | 3/3 (100%) | 0 | replays/public-tests-only/replay_result.json |

## Per-Task Outcomes

| task_id | policy | status | public_status | hidden_status | error_class | duration_ms | final_diff_hash | artifact_dir |
| --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| repair_jsonl_deduper | oracle | PASS | PASS | PASS |  | 443 | xxh64:791a044ad51af90c | policies/oracle/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | oracle | PASS | PASS | PASS |  | 634 | xxh64:3a6c137988d3cd3a | policies/oracle/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | oracle | PASS | PASS | PASS |  | 465 | xxh64:187bcea16c66ce96 | policies/oracle/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | noop | HIDDEN_TEST_FAIL | PASS | FAIL | HiddenCheckFailed | 452 | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | noop | HIDDEN_TEST_FAIL | PASS | FAIL | HiddenCheckFailed | 640 | xxh64:ef46db3751d8e999 | policies/noop/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | noop | HIDDEN_TEST_FAIL | PASS | FAIL | HiddenCheckFailed | 491 | xxh64:ef46db3751d8e999 | policies/noop/attempts/repair_config_precedence__attempt_001 |
| repair_jsonl_deduper | public-tests-only | HIDDEN_TEST_FAIL | PASS | FAIL | HiddenCheckFailed | 461 | xxh64:83ebe19f1a70c989 | policies/public-tests-only/attempts/repair_jsonl_deduper__attempt_001 |
| preserve_cli_error_codes | public-tests-only | HIDDEN_TEST_FAIL | PASS | FAIL | HiddenCheckFailed | 688 | xxh64:2318ffb1a4be45cf | policies/public-tests-only/attempts/preserve_cli_error_codes__attempt_001 |
| repair_config_precedence | public-tests-only | HIDDEN_TEST_FAIL | PASS | FAIL | HiddenCheckFailed | 511 | xxh64:8ea4a8dafa72fda7 | policies/public-tests-only/attempts/repair_config_precedence__attempt_001 |

## Known Shortcuts

- `noop` and `public-tests-only` are calibration controls. They should pass public checks but fail hidden validators.
- Public-test-only success is not task success; final PASS requires `status: PASS`, `public_status: PASS`, and `hidden_status: PASS`.

## Measures

This report measures whether the local repo-patch task suite, public checks, hidden validators, and scripted controls behave consistently on the configured dev task set.

## Does Not Measure

This is not a model baseline, not a post-training result, not a secure-sandbox claim, and not evidence of broad coding-agent capability.
