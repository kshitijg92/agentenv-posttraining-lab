# wrong_noop

## Purpose

This is a negative scorer-audit case for `toy_python_fix_001`.

It verifies that doing nothing is not accepted as a task solution, even though
the shallow public check still passes.

Expected result:

```text
attempt_status: HIDDEN_TEST_FAIL
public_status: PASS
hidden_status: FAIL
```

## What It Tests

- Public checks alone are not the score.
- Hidden validators reject the original buggy implementation.
- A no-op submission is classified as task-behavior failure, not harness failure.

## What It Does Not Test

- Malformed patch handling.
- Public-test tampering detection.
- Hidden-validator leakage detection.
