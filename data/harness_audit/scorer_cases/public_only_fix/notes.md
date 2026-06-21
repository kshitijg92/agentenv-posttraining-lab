# public_only_fix

## Purpose

This is a negative scorer-audit case for `toy_python_fix_001`.

It verifies that a patch can satisfy the visible public check while still being
rejected by hidden validators.

Expected result:

```text
attempt_status: HIDDEN_TEST_FAIL
public_status: PASS
hidden_status: FAIL
```

## What It Tests

- Public-test success is not the scoring criterion.
- Hidden validators catch behavior not covered by the shallow public test.
- A plausible but incomplete patch is classified as task-behavior failure.

## What It Does Not Test

- No-op rejection.
- Malformed patch handling.
- Public-test tampering detection.
- Hidden-validator leakage detection.
