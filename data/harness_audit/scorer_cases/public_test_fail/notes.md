# public_test_fail

## Purpose

This scorer-audit case verifies the public-check failure boundary.

The submitted patch applies cleanly but returns the wrong value for the public
test input.

Expected result:

```text
attempt_status: PUBLIC_TEST_FAIL
public_status: FAIL
hidden_status: NOT_RUN
```

## What It Tests

- Public-check failure is distinct from patch-application failure.
- Hidden validators do not run after public checks fail.
- The audit suite covers the normal public failure path separately from timeout
  and hidden-validation failure paths.
