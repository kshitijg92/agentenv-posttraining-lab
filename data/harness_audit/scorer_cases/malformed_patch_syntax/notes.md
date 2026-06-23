# malformed_patch_syntax

## Purpose

This is a patch-application scorer-audit case for `toy_python_fix_001`.

It verifies that syntactically malformed patch text reaches patch application
and is classified as `PATCH_APPLY_ERROR`.

Expected result:

```text
attempt_status: PATCH_APPLY_ERROR
public_status: NOT_RUN
hidden_status: NOT_RUN
```

## What It Tests

- Raw patch screening does not classify this benign malformed patch as leakage
  or shortcut behavior.
- Patch syntax errors are attempt failures, not orchestrator crashes.
- Public checks and hidden validators do not run after patch application fails.

## What It Does Not Test

- Nonexistent source file handling.
- Public-test tampering detection.
- Hidden-validator leakage detection.
