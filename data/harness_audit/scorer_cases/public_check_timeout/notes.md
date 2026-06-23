# public_check_timeout

## Purpose

This is a runtime-boundary scorer-audit case for `toy_python_fix_001`.

It verifies that a submitted patch that hangs during public checks is terminated
by the harness and classified with phase-specific timeout status.

Expected result:

```text
attempt_status: TIMEOUT
public_status: FAIL
hidden_status: NOT_RUN
```

## Manifest Override

The case uses:

```yaml
manifest_overrides:
  limits:
    timeout_seconds: 1
```

The audit runner records the override as `manifest_override.json` beside this
case's attempt artifacts. The override exists only to keep the audit fast; it is
not a task semantic change.

## What It Tests

- A hanging public check does not block the harness indefinitely.
- Public-check timeouts are distinguishable from hidden-validation failures.
- Hidden validators do not run after the public-check phase times out.

## What It Does Not Test

- Patch-application timeouts.
- Production sandbox resource isolation.
