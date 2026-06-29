# Eval Matrix Report

## Run Details

- Artifact directory: experiments/runs/policy_owned_eval_smoke
- Eval matrix manifest: eval_matrix_manifest.json
- Eval matrix id: eval_matrix_024671bf1e9249428c03aa77e2b7b57b
- Config name: scorer_control_policies
- Config path: configs/eval/scorer_control_policies.yaml
- Config hash: xxh64:be1a25b6a52abf58
- Split: practice
- Task pack: data/task_packs/repo_patch_python_v0
- Task count: 1
- Policy count: 3
- Attempt count: 3
- Hidden-validator version/hash: not captured in eval_matrix_v0; current substitute is config hash xxh64:be1a25b6a52abf58
- Replay policy count: 3
- Replay run count: 3
- Replay run success summary: 3/3
- Replay match rate: 3/3 (100%)

## Tasks

- toy_python_fix_001

## Scorer Policy Summary

| policy | control | attempts | final_pass_rate | public_pass_rate | hidden_pass_rate | public_pass_hidden_fail | env_or_harness_failures | scorer_or_orchestrator_failures | median_duration_ms | trace |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| oracle | oracle | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0 | 0 | 0 | 424 | policies/oracle/trace.jsonl |
| bad-noop | bad.noop | 1 | 0/1 (0%) | 1/1 (100%) | 0/1 (0%) | 1 | 0 | 0 | 455 | policies/bad-noop/trace.jsonl |
| bad-public-only | bad.public_only | 1 | 0/1 (0%) | 1/1 (100%) | 0/1 (0%) | 1 | 0 | 0 | 439 | policies/bad-public-only/trace.jsonl |

## Agent Policy Summary

No agent policies in this eval matrix.

## Agent Model And Budget Summary

No agent model or budget metadata in this eval matrix.

## Calibration Checks

### Scorer Control Expectations

| policy | control | expected final | observed final | expected public | observed public | expected hidden | observed hidden | result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| oracle | oracle | PASS | 1/1 (100%) | PASS | 1/1 (100%) | PASS | 1/1 (100%) | <span style="color: green">ON_TRACK</span> |
| bad-noop | bad.noop | HIDDEN_TEST_FAIL | 1/1 (100%) | PASS | 1/1 (100%) | FAIL | 1/1 (100%) | <span style="color: green">ON_TRACK</span> |
| bad-public-only | bad.public_only | HIDDEN_TEST_FAIL | 1/1 (100%) | PASS | 1/1 (100%) | FAIL | 1/1 (100%) | <span style="color: green">ON_TRACK</span> |

### Scorer Aggregate Rates

- Oracle pass rate: 1/1 (100%)
- Known-bad final PASS rate: 0/2 (0%)
- Known-bad public-pass/hidden-fail rate: 2/2 (100%)
- Environment/harness failure rate: 0/3 (0%)
- Scorer/orchestrator failure rate: 0/3 (0%)

### Agent Control Expectations

No agent control policies in this eval matrix.

### Agent Aggregate Rates

No agent aggregate rates for this eval matrix.

### Replay Checks

- Replay match rate: 3/3 (100%)
- Task exclusions: none recorded in eval_matrix_v0

| policy | status | match_rate | error_count | replay_result |
| --- | --- | ---: | ---: | --- |
| oracle | PASS | 1/1 (100%) | 0 | replays/oracle__replay_001/replay_result.json |
| bad-noop | PASS | 1/1 (100%) | 0 | replays/bad-noop__replay_001/replay_result.json |
| bad-public-only | PASS | 1/1 (100%) | 0 | replays/bad-public-only__replay_001/replay_result.json |

## Per-Task Outcomes

| task_id | policy | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | agent_scorer_status | agent_scorer_public_status | agent_scorer_hidden_status | error_class | duration_ms | final_diff_hash | artifact_dir |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| toy_python_fix_001 | oracle | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | 424 | xxh64:e3fc746d6fe0786c | policies/oracle/attempts/toy_python_fix_001__attempt_001 |
| toy_python_fix_001 | bad-noop | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 455 | xxh64:ef46db3751d8e999 | policies/bad-noop/attempts/toy_python_fix_001__attempt_001 |
| toy_python_fix_001 | bad-public-only | run_artifacts_v0 | HIDDEN_TEST_FAIL | PASS | FAIL |  |  |  |  |  | HiddenCheckFailed | 439 | xxh64:963c30a755bee9ee | policies/bad-public-only/attempts/toy_python_fix_001__attempt_001 |

## Known Shortcuts

- `noop` and `public-tests-only` are calibration controls. They should pass public checks but fail hidden validators.
- Public-test-only success is not task success; final PASS requires `status: PASS`, `public_status: PASS`, and `hidden_status: PASS`.

## Measures

This report measures whether the local repo-patch task suite, public checks, hidden validators, and scripted controls behave consistently on the configured dev task set.

## Does Not Measure

This is not a model baseline, not a post-training result, not a secure-sandbox claim, and not evidence of broad coding-agent capability.
