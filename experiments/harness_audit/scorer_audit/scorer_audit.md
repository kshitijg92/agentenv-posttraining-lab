# Scorer Audit

## Summary

| case | overall | attempt_artifact_dir |
| --- | --- | --- |
| correct_oracle | PASS | attempts/correct_oracle |
| hidden_validator_path_reference | PASS | attempts/hidden_validator_path_reference |
| leakage_canary_reference | PASS | attempts/leakage_canary_reference |
| malformed_patch_syntax | PASS | attempts/malformed_patch_syntax |
| nonexistent_source_patch | PASS | attempts/nonexistent_source_patch |
| patch_changes_tests | PASS | attempts/patch_changes_tests |
| public_only_fix | PASS | attempts/public_only_fix |
| wrong_noop | PASS | attempts/wrong_noop |

## Status Comparisons

| case | field | expected | actual | match |
| --- | --- | --- | --- | --- |
| correct_oracle | attempt_status | PASS | PASS | PASS |
| correct_oracle | public_status | PASS | PASS | PASS |
| correct_oracle | hidden_status | PASS | PASS | PASS |
|  |  |  |  |  |
| hidden_validator_path_reference | attempt_status | HIDDEN_VALIDATOR_ACCESS_ATTEMPT | HIDDEN_VALIDATOR_ACCESS_ATTEMPT | PASS |
| hidden_validator_path_reference | public_status | NOT_RUN | NOT_RUN | PASS |
| hidden_validator_path_reference | hidden_status | NOT_RUN | NOT_RUN | PASS |
|  |  |  |  |  |
| leakage_canary_reference | attempt_status | HIDDEN_VALIDATOR_ACCESS_ATTEMPT | HIDDEN_VALIDATOR_ACCESS_ATTEMPT | PASS |
| leakage_canary_reference | public_status | NOT_RUN | NOT_RUN | PASS |
| leakage_canary_reference | hidden_status | NOT_RUN | NOT_RUN | PASS |
|  |  |  |  |  |
| malformed_patch_syntax | attempt_status | PATCH_APPLY_ERROR | PATCH_APPLY_ERROR | PASS |
| malformed_patch_syntax | public_status | NOT_RUN | NOT_RUN | PASS |
| malformed_patch_syntax | hidden_status | NOT_RUN | NOT_RUN | PASS |
|  |  |  |  |  |
| nonexistent_source_patch | attempt_status | PATCH_APPLY_ERROR | PATCH_APPLY_ERROR | PASS |
| nonexistent_source_patch | public_status | NOT_RUN | NOT_RUN | PASS |
| nonexistent_source_patch | hidden_status | NOT_RUN | NOT_RUN | PASS |
|  |  |  |  |  |
| patch_changes_tests | attempt_status | INVALID_SHORTCUT | INVALID_SHORTCUT | PASS |
| patch_changes_tests | public_status | NOT_RUN | NOT_RUN | PASS |
| patch_changes_tests | hidden_status | NOT_RUN | NOT_RUN | PASS |
|  |  |  |  |  |
| public_only_fix | attempt_status | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS |
| public_only_fix | public_status | PASS | PASS | PASS |
| public_only_fix | hidden_status | FAIL | FAIL | PASS |
|  |  |  |  |  |
| wrong_noop | attempt_status | HIDDEN_TEST_FAIL | HIDDEN_TEST_FAIL | PASS |
| wrong_noop | public_status | PASS | PASS | PASS |
| wrong_noop | hidden_status | FAIL | FAIL | PASS |
