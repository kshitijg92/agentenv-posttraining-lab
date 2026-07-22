# Task Design Note v0

## Purpose

This note records what the current `repo_patch_python_v0` task suite is meant
to measure and what it is not meant to measure.

The suite is small by design. Its current value is not task volume; it is that
each task has:

- a visible seed workspace,
- intentionally incomplete public checks,
- private hidden validators,
- oracle and known-bad controls,
- replayable attempt artifacts,
- a consolidated eval suite report.

## Current Task Family

The original v0 dev split contained three self-authored Python repo-patch tasks:

```text
repair_jsonl_deduper
preserve_cli_error_codes
repair_config_precedence
```

The suite has since expanded to nineteen dev tasks. Six of the newer tasks
progress from one to seven source files and add recursive filesystem, pipeline,
transaction, policy, and graph-scheduling interactions while retaining the
same deterministic repo-patch contract. The authoritative inventory is
`data/task_packs/repo_patch_python_v0/splits.lock.json`.

The practice split contains:

```text
toy_python_fix_001
```

Six separately authored tasks now form a frozen heldout-private slice. Existing
inspected dev tasks were not relabeled. The heldout tasks were inspected only
for task/scorer authorship and deterministic control calibration before freeze;
zero natural-model attempts existed at the freeze point. Their outcomes may not
drive training, prompt, decoding, scorer, or hyperparameter iteration.

See `docs/heldout_evaluation_protocol.md` and
`data/task_packs/repo_patch_python_v0/heldout_private.freeze.json`.

## What The Suite Measures

The suite measures whether an attempted patch can repair focused Python
behavior while preserving the visible contract and satisfying hidden edge cases.

The original three tasks exercise:

- caller-supplied key handling and JSONL validation,
- CLI exit-code preservation across expected user/input errors,
- config precedence and type validation across defaults, JSON config, and
  environment overrides.

Later dev and heldout tasks extend the same construct family to deterministic
parsing, ordering, validation, batching, path, interval, numeric,
record-transformation, recursive configuration, transaction, policy, pipeline,
and scheduling contracts. Per-task cards remain the authoritative description
of what each task does and does not measure.

These are not prompt-list tasks. Each task requires reading the seed code,
understanding the local contract, and changing implementation behavior so that
public and hidden checks both pass.

## Public Checks And Hidden Validators

Public checks are intentionally incomplete. They provide diagnostic feedback and
make the task solvable from the seed workspace, but they do not define success.

Hidden validators encode the behavioral contract edges that public-only patches
are likely to miss. Examples:

- using a dedupe key other than `"id"`,
- preserving distinct CLI exit codes for expected failures,
- merging partial config and environment sources instead of treating them as
  isolated replacements.

Success for a submitted patch requires:

```text
attempt_status: PASS
public_status: PASS
hidden_status: PASS
```

Passing public checks alone is not task success.

## Control Policies

Every task includes three control patches:

```text
oracle
bad.noop
bad.public_only
```

Expected outcomes:

```text
oracle -> PASS / PASS / PASS
bad.noop -> HIDDEN_TEST_FAIL / PASS / FAIL
bad.public_only -> HIDDEN_TEST_FAIL / PASS / FAIL
```

The oracle shows the task is solvable under the scoring contract. The known-bad
controls show that public checks are not being mistaken for the score and that
hidden validators catch the intended shortcut.

The dev-baseline eval suite report currently shows all control expectations on
track:

```text
oracle: 3/3 final PASS
noop: 3/3 public PASS and hidden FAIL
public-tests-only: 3/3 public PASS and hidden FAIL
```

Control-policy replay also matched:

```text
9/9 replayed attempts matched
```

## Construct Validity

The suite has construct validity for a narrow kind of coding-agent environment:

```text
small local Python bug fix -> patch attempt -> public diagnostics -> hidden
pytest scoring -> trace/replay/report
```

It is useful for testing whether the harness can distinguish:

- correct patches from no-op patches,
- public-test shortcuts from hidden-behavior fixes,
- task success from public-test success,
- normal hidden failures from harness/scorer failures,
- one-shot results from reproducible replayed results.

This is a measurement-quality baseline, not a model-quality baseline.

## Known Weaknesses

The suite remains intentionally narrow:

- only Python repo-patch tasks;
- synthetic small repositories rather than large-repo navigation;
- no external services, databases, async workflows, or production-like
  deployment constraints;
- predominantly repair-shaped objectives rather than feature implementation,
  diagnosis-only, review, or valid no-op task families; and
- six heldout tasks provide weak task-level directional evidence rather than a
  statistically strong population estimate.

The current report still has instrumentation gaps:

- hidden-validator file hashes are not captured in
  `eval_suite` / `eval_suite_artifact_v0`,
- task exclusions are not structured data,
- replay is defined for control-patch policies, not future model-agent policies.

These are acceptable limitations for the current stage. They should be recorded
before moving to model-agent work rather than hidden behind a larger task count.

## Exclusion Policy

A task should not be counted in the baseline if:

- the oracle fails,
- a known-bad control passes hidden scoring,
- a known-bad control fails for the wrong reason,
- hidden validators leak into the agent workspace,
- the visible instruction is ambiguous and hidden tests supply the real spec,
- repeated controls or replay are unstable,
- external state is required.

No current dev task is excluded.

## Non-Claims

This suite does not claim:

- broad coding-agent capability,
- real model performance,
- post-training improvement,
- secure hostile-code sandboxing,
- public benchmark comparability,
- production-grade software-engineering evaluation.

It is a calibrated local environment for learning task design, scoring
discipline, replay, and baseline reporting.
