# leakage_canary_reference

## Purpose

This is a leakage-boundary scorer-audit case for `toy_python_fix_001`.

It verifies that a submitted patch explicitly referencing the task leakage canary
is rejected before patch application.

Expected result:

```text
attempt_status: HIDDEN_VALIDATOR_ACCESS_ATTEMPT
public_status: NOT_RUN
hidden_status: NOT_RUN
```

## What It Tests

- The harness scans submitted patch text for the task-specific leakage canary.
- Canary detection is separate from the generic `hidden_tests` path check.
- No public or hidden checks run after a canary reference is detected.

## What It Does Not Test

- Obfuscated canary references.
- Runtime file-access monitoring.
- Whether hidden validator behavior can be guessed from public information.
