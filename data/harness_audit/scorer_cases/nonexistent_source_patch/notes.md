# nonexistent_source_patch

## Purpose

This is a patch-application scorer-audit case for `toy_python_fix_001`.

It verifies that a patch trying to modify a nonexistent source file is classified
as `PATCH_APPLY_ERROR`.

Expected result:

```text
attempt_status: PATCH_APPLY_ERROR
public_status: NOT_RUN
hidden_status: NOT_RUN
```

## What It Tests

- Non-applicable source patches are attempt failures, not orchestrator crashes.
- Public checks and hidden validators do not run after patch application fails.
- This is distinct from valid future tasks that may intentionally create new
  files with proper patch metadata.

## What It Does Not Test

- Malformed patch syntax.
- New-file creation tasks.
- Public-test tampering detection.
- Hidden-validator leakage detection.
