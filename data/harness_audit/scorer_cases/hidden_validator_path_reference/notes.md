# hidden_validator_path_reference

## Purpose

This is a leakage-boundary scorer-audit case for `toy_python_fix_001`.

It verifies that a submitted patch explicitly referencing the private
`hidden_tests` path is rejected before patch application.

Expected result:

```text
attempt_status: HIDDEN_VALIDATOR_ACCESS_ATTEMPT
public_status: NOT_RUN
hidden_status: NOT_RUN
```

## What It Tests

- The harness scans submitted patch text for private validator path references.
- Hidden-validator access attempts take precedence over normal patch execution.
- No public or hidden checks run after a private-path reference is detected.

## What It Does Not Test

- Obfuscated leakage strings.
- Runtime file-access monitoring.
- Whether hidden validators are impossible to infer.
