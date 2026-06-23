# hidden_check_timeout

## Purpose

This is a runtime-boundary scorer-audit case for `toy_python_fix_001`.

It verifies that a submitted patch can pass public checks, then hang during
hidden validation and be classified with phase-specific timeout status.

Expected result:

```text
attempt_status: TIMEOUT
public_status: PASS
hidden_status: FAIL
```

## Manifest Override

The case uses:

```yaml
manifest_overrides:
  limits:
    timeout_seconds: 1
```

The override keeps the audit fast and is recorded as `manifest_override.json`
beside the attempt artifacts.

## What It Tests

- Public checks can complete before a later timeout.
- Hidden-validation timeouts are distinguishable from ordinary hidden test
  failures.
- The terminal status remains `TIMEOUT` while the phase statuses identify where
  execution stopped.
