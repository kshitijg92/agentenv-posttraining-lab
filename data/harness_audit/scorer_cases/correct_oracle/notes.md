# correct_oracle

## Purpose

This is the positive-control scorer-audit case for `toy_python_fix_001`.

It verifies that the attempt path accepts a known-correct patch and produces:

```text
attempt_status: PASS
public_status: PASS
hidden_status: PASS
```

## What It Tests

- The patch can be applied to the task workspace.
- Public checks still pass.
- Hidden validators accept the implementation behavior.

## What It Does Not Test

- Whether bad solutions are rejected.
- Whether shortcuts are detected.
- Whether hidden-validator leakage is detected.
- Whether the task is realistic or broadly representative.
