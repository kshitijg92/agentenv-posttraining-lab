# Control Calibration

## Summary

- Control run ID: controls_782cd6a6a9384d968fa8d626117fd408
- Task pack: /home/kshitij/agentenv-posttraining-lab/data/task_packs/repo_patch_python_v0
- Repeats: 3
- Attempts: 27
- Overall: PASS

## Control Summary

| task_id | control | repeats | matches | expected |
| --- | --- | --- | --- | --- |
| preserve_cli_error_codes | bad.noop | 3 | 3/3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL |
| preserve_cli_error_codes | bad.public_only | 3 | 3/3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL |
| preserve_cli_error_codes | oracle | 3 | 3/3 | attempt_status: PASS; public_status: PASS; hidden_status: PASS |
| repair_jsonl_deduper | bad.noop | 3 | 3/3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL |
| repair_jsonl_deduper | bad.public_only | 3 | 3/3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL |
| repair_jsonl_deduper | oracle | 3 | 3/3 | attempt_status: PASS; public_status: PASS; hidden_status: PASS |
| toy_python_fix_001 | bad.noop | 3 | 3/3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL |
| toy_python_fix_001 | bad.public_only | 3 | 3/3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL |
| toy_python_fix_001 | oracle | 3 | 3/3 | attempt_status: PASS; public_status: PASS; hidden_status: PASS |

## Attempt Details

| task_id | control | repeat | expected | actual | match | artifact_dir |
| --- | --- | --- | --- | --- | --- | --- |
| preserve_cli_error_codes | oracle | 1 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/preserve_cli_error_codes__oracle__repeat_001 |
| preserve_cli_error_codes | oracle | 2 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/preserve_cli_error_codes__oracle__repeat_002 |
| preserve_cli_error_codes | oracle | 3 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/preserve_cli_error_codes__oracle__repeat_003 |
| preserve_cli_error_codes | bad.noop | 1 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/preserve_cli_error_codes__bad_noop__repeat_001 |
| preserve_cli_error_codes | bad.noop | 2 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/preserve_cli_error_codes__bad_noop__repeat_002 |
| preserve_cli_error_codes | bad.noop | 3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/preserve_cli_error_codes__bad_noop__repeat_003 |
| preserve_cli_error_codes | bad.public_only | 1 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/preserve_cli_error_codes__bad_public_only__repeat_001 |
| preserve_cli_error_codes | bad.public_only | 2 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/preserve_cli_error_codes__bad_public_only__repeat_002 |
| preserve_cli_error_codes | bad.public_only | 3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/preserve_cli_error_codes__bad_public_only__repeat_003 |
| repair_jsonl_deduper | oracle | 1 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/repair_jsonl_deduper__oracle__repeat_001 |
| repair_jsonl_deduper | oracle | 2 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/repair_jsonl_deduper__oracle__repeat_002 |
| repair_jsonl_deduper | oracle | 3 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/repair_jsonl_deduper__oracle__repeat_003 |
| repair_jsonl_deduper | bad.noop | 1 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/repair_jsonl_deduper__bad_noop__repeat_001 |
| repair_jsonl_deduper | bad.noop | 2 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/repair_jsonl_deduper__bad_noop__repeat_002 |
| repair_jsonl_deduper | bad.noop | 3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/repair_jsonl_deduper__bad_noop__repeat_003 |
| repair_jsonl_deduper | bad.public_only | 1 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/repair_jsonl_deduper__bad_public_only__repeat_001 |
| repair_jsonl_deduper | bad.public_only | 2 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/repair_jsonl_deduper__bad_public_only__repeat_002 |
| repair_jsonl_deduper | bad.public_only | 3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/repair_jsonl_deduper__bad_public_only__repeat_003 |
| toy_python_fix_001 | oracle | 1 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/toy_python_fix_001__oracle__repeat_001 |
| toy_python_fix_001 | oracle | 2 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/toy_python_fix_001__oracle__repeat_002 |
| toy_python_fix_001 | oracle | 3 | attempt_status: PASS; public_status: PASS; hidden_status: PASS | attempt_status: PASS; public_status: PASS; hidden_status: PASS | PASS | attempts/toy_python_fix_001__oracle__repeat_003 |
| toy_python_fix_001 | bad.noop | 1 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/toy_python_fix_001__bad_noop__repeat_001 |
| toy_python_fix_001 | bad.noop | 2 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/toy_python_fix_001__bad_noop__repeat_002 |
| toy_python_fix_001 | bad.noop | 3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/toy_python_fix_001__bad_noop__repeat_003 |
| toy_python_fix_001 | bad.public_only | 1 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/toy_python_fix_001__bad_public_only__repeat_001 |
| toy_python_fix_001 | bad.public_only | 2 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/toy_python_fix_001__bad_public_only__repeat_002 |
| toy_python_fix_001 | bad.public_only | 3 | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL | PASS | attempts/toy_python_fix_001__bad_public_only__repeat_003 |
