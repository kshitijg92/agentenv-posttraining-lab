# Attempt Status Taxonomy

## Purpose

`AttemptStatus` is the canonical terminal outcome for one patch attempt.

It should answer:

```text
What happened to this attempt, and what evidence does the harness have for that
classification?
```

Week 3 intentionally keeps one status vocabulary instead of adding a separate
failure-label layer. This keeps reports, scorer-audit cases, and later filtering
rules easier to inspect.

## Boundary

An attempt status is about one submitted patch attempt.

It is not:

- a model-capability claim,
- a task-suite quality label,
- a training-eligibility decision,
- a production sandbox security finding.

Those later decisions may use `AttemptStatus`, but they should not be collapsed
into it.

## Current Statuses

### `PASS`

The patch applied, public checks passed, and hidden validators passed.

Evidence:

- patch application command returned zero,
- all public check commands returned zero,
- all hidden scorer commands returned zero.

### `PATCH_APPLY_ERROR`

The submitted patch could not be applied to the prepared workspace.

Evidence:

- patch application command returned nonzero.

### `PUBLIC_TEST_FAIL`

The patch applied, but at least one public check failed.

Evidence:

- patch application command returned zero,
- at least one configured public check command returned nonzero,
- hidden validators were not run.

### `HIDDEN_TEST_FAIL`

The patch applied and public checks passed, but at least one hidden validator
failed.

Evidence:

- patch application command returned zero,
- all public checks returned zero,
- at least one hidden scorer command returned nonzero.

### `TIMEOUT`

The attempt exceeded an enforced timeout.

Evidence:

- the runner raised or recorded a timeout while executing a controlled command.

The status remains `TIMEOUT` for now rather than `SANDBOX_TIMEOUT`, because the
current local runner is not yet a full sandbox abstraction. Sandbox-specific
details can be recorded in artifacts or later status refinements.

### `SCORER_ERROR`

The hidden scorer could not produce a trustworthy score because of scorer-side
failure rather than task-solution failure.

Evidence:

- hidden validation could not be invoked,
- hidden validator assets were missing or malformed,
- scorer execution crashed in a way that is not attributable to the submitted
  patch's behavior.

Current limitation:

- this status exists in the schema but is not yet strongly distinguished from
  other runtime failures in all paths.

### `ORCHESTRATOR_ERROR`

The attempt lifecycle failed outside patch behavior, public checks, or hidden
scoring.

Evidence:

- workspace preparation failed,
- manifest resolution failed after validation should have caught it,
- artifact writing failed,
- another harness bug prevented a normal terminal outcome,
- `error.txt` records exception class, message, and traceback when the attempt
  can still be persisted.

Current limitation:

- this status exists in the schema but is not yet strongly distinguished from
  all runner failures.

## Week 3 Candidate Statuses

These should only be added if the harness has concrete detection rules.

### `INVALID_SHORTCUT`

The attempt used a detected shortcut that violates the task or scoring contract.

Narrow Week 3 detection target:

- submitted patch modifies public test files under `tests/`.

Important limitation:

- not every shortcut is detectable. This status should only be used for
  explicitly checked shortcut classes.

### `HIDDEN_VALIDATOR_ACCESS_ATTEMPT`

The attempt appears to access or depend on private evaluation assets.

Narrow Week 3 detection targets:

- submitted patch text contains `hidden_tests`,
- submitted patch text contains the task leakage canary,
- submitted patch text contains known private validator paths.

Important limitation:

- this is a leakage-smoke check, not a complete malicious-code detector.

## Not Attempt Statuses Yet

### `AMBIGUOUS_TASK`

Ambiguity is primarily a task-design finding, not a terminal result of one patch
attempt. It belongs in task review, scorer-audit notes, or task exclusion
records unless the harness later gets a concrete rule for detecting it.

### `TASK_FLAKE`

Flakiness requires repeated runs and statistical evidence. Week 3 can document
flake risks, but real flake detection belongs to the later eval-quality gate.

## Invariants

- Every completed attempt has exactly one `AttemptStatus`.
- A status must be justified by recorded artifacts, command results, or explicit
  audit evidence.
- Public-test success is not task success.
- Hidden-validation failure is not automatically scorer failure.
- Scorer or orchestrator failures should not be counted as model failures.
- Richer statuses should not be added just because they are useful for reports;
  they need detection evidence.
