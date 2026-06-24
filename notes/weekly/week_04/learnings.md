# Week 4 Learnings

## Summary

Week 4 moved the project from one calibrated toy task to a small dev suite with
a consolidated environment baseline report.

The useful result is not that there are three new tasks. The useful result is
that the suite now has:

- task-pack metadata and split lock,
- three non-practice dev tasks,
- task cards for shortcut and limitation analysis,
- oracle/no-op/public-only controls per task,
- repeated control calibration,
- a full eval matrix over all scripted policies,
- control-policy replay for reproducibility,
- a consolidated report with explicit control expectations.

## Main Design Lesson

Task difficulty should come from the behavioral contract, not from incidental
implementation size.

The strongest tasks this week were small:

```text
repair_jsonl_deduper: honor caller-supplied identity and validation semantics
preserve_cli_error_codes: preserve distinct expected failure modes
repair_config_precedence: merge sources with explicit precedence and validation
```

Each one had a public-only shortcut that was easy to state before writing hidden
tests. That made calibration much cleaner.

## Hidden Validators

Hidden validators should verify visible semantics, not introduce surprise
requirements.

Two concrete fixes improved task quality:

- `repair_jsonl_deduper` made first-seen retention and `ValueError` behavior
  visible in the seed docstring.
- hidden tests stopped matching exact `ValueError` message text when message
  wording was not part of the visible contract.

This is the right direction: hidden validators should catch shortcuts and edge
cases, but the agent-visible task should still be solvable without reading
private tests.

## Controls

Control policies are calibration evidence, not submitted-patch success.

The clean expected pattern is:

```text
oracle: PASS / PASS / PASS
noop: HIDDEN_TEST_FAIL / PASS / FAIL
public-tests-only: HIDDEN_TEST_FAIL / PASS / FAIL
```

The consolidated report now makes those expectations explicit. That matters
because a bad control failure is only useful if it failed for the expected
reason. A public-only patch failing to apply would not prove hidden validators
are doing their job.

## Replay

Replay belongs in the trust story.

Running a full eval matrix shows the controls behaved correctly once. Replaying
the control-policy runs shows that the recorded outcomes are reproducible.

For this stage, replay is intentionally scoped to `control_patch` policies.
That avoids making premature claims about future model-agent replay semantics.

Current durable result:

```text
control-policy replay match rate: 9/9
```

## Eval Matrix

The eval config is now treated as a policy matrix over one task set:

```text
dev_baseline x {oracle, noop, public-tests-only}
```

This is better than treating each policy run as an unrelated artifact. The
parent matrix manifest gives the report a stable unit:

```text
one config
one split
one task list
multiple scripted policies
optional replay summaries
```

The report path convention should follow artifact type:

```text
experiments/reports/eval_matrices/dev_baseline.md
```

## Suite Limitations

The current suite is still narrow:

- three dev tasks,
- all self-authored and inspected,
- no heldout-private tasks,
- no model-agent policy,
- no training data generation,
- no hidden-validator file hashes in the matrix report,
- no structured task-exclusion records.

These are real limitations, but they are acceptable for the Week 4 goal. Adding
more plumbing now would be less useful than moving into the Week 5 model/agent
interface with a calibrated environment baseline.

## What To Preserve Going Forward

Do not weaken these invariants:

- final task success means `AttemptStatus: PASS`,
- public checks are diagnostic only,
- hidden validators remain private,
- oracle controls must pass,
- known-bad controls must fail hidden scoring,
- replay evidence must be separated from one-shot eval evidence,
- reports must state non-claims explicitly.

## Open Follow-Ups

Good follow-ups, but not blockers for Week 4 closeout:

- capture hidden-validator file hashes in `eval_matrix_v0`,
- represent task exclusions as structured report data,
- define model-agent replay semantics separately from patch-control replay,
- preserve the artifact-type report convention for future eval matrix reports.
