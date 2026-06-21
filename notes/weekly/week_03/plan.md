# Week 3 Plan

## Theme

Week 3 is about measurement trust.

Weeks 1 and 2 proved that the lab can run one repo-patch task through the
orchestrator, hidden scorer, eval runner, replay runner, traces, and reports.
Week 3 should not broaden into model agents, training, or a larger task suite
yet. The useful question now is:

```text
Can I trust the scorer, attempt statuses, and environment boundaries enough to
build more tasks on top of them?
```

## What Was Missing After Week 2

Week 2 closed with working eval/replay/report plumbing, but several measurement
trust gaps remained:

- Control policies were runnable one at a time, but there was no first-class
  repeated control audit that checks expected outcomes across all controls.
- Attempt statuses existed, but there was no reusable failure-label taxonomy for
  scorer audits, later reward components, or training eligibility.
- The hidden scorer distinguished the current oracle/no-op/public-only controls,
  but there was no broader audit fixture set for false positives, false
  negatives, malformed patches, timeouts, hidden-test probing, or invalid
  shortcuts.
- Local workspace preparation checked that hidden tests and controls were absent,
  but those checks were not yet documented as sandbox invariants.
- Docker was not part of the verified path yet, so no network-disabled sandbox
  smoke check or image digest logging existed.
- Reports summarized eval and replay artifacts, but there was no scorer-audit
  report comparing expected and actual status outcomes.

## Planned Artifacts

Code and config:

```text
data/harness_audit/scorer_cases/
src/agentenv/scorers/audit.py
src/agentenv/sandbox/docker_env.py
configs/sandbox/docker_none.yaml
tests/sandbox/test_invariants.py
```

`tests/scorers/test_audit.py` should be created when the audit runner code
exists. Do not create a test file before there is audit code to exercise.

CLI surface:

```text
agentenv controls run --task-pack <pack> --repeats <n> --out <run-dir>
agentenv scorers audit --cases <case-dir> --out <report.md>
agentenv sandbox smoke --config <config.yaml> --task <task.yaml>
```

Docs and notes:

```text
docs/attempt_status_taxonomy.md
docs/sandbox_invariants_v0.md
notes/failures/scorer_false_positive_001.md
notes/weekly/week_03/implementation_notes.md
notes/weekly/week_03/learnings.md
```

Generated evidence:

```text
experiments/runs/week03_controls/
experiments/harness_audit/scorer_audit/
```

## Execution Plan

1. Define the attempt status taxonomy first.
   Keep one canonical outcome vocabulary instead of a separate failure-label
   layer. Existing statuses such as `PASS`, `PATCH_APPLY_ERROR`,
   `PUBLIC_TEST_FAIL`, `HIDDEN_TEST_FAIL`, and `TIMEOUT` remain valid, and Week
   3 can add richer statuses only where the harness has concrete detection
   evidence.

2. Build the scorer-audit fixture shape.
   Each case under `data/harness_audit/scorer_cases/` should have `case.yaml`,
   `submission.patch`, expected status, and short notes.

3. Implement scorer audit.
   The audit should run each fixture through the existing attempt path, compare
   expected vs actual status, and write a Markdown report with false positive
   and false negative flags.

4. Implement repeated control calibration.
   `controls run` should reuse the existing attempt/eval machinery where
   possible, but add expectation checking:

   ```text
   oracle: expected PASS
   bad_noop: expected non-PASS
   bad_public_only: expected non-PASS
   ```

5. Add sandbox invariant checks.
   Start with local invariants that already matter: hidden tests absent during
   agent phase, controls absent during agent phase, canary absent from
   agent-visible trace, workspace reset between attempts, and timeout
   classification.

6. Add Docker smoke.
   Docker is a smoke path only. It should check network-disabled execution and
   record image digest if available. It should not be presented as production
   hostile-code sandboxing.

7. Run the Week 3 commands and write notes.
   The week should end with reports, tests, and explicit limitations.

## Done Criteria

- Oracle passes `3/3`.
- Every known-bad control fails `3/3`.
- Scorer audit has zero unexpected passes.
- Attempt statuses are documented and used by audit output.
- Hidden validator text does not appear in agent-visible traces.
- Leakage canary does not appear in agent-visible traces.
- Sandbox invariants are documented.
- Docker smoke passes, or a blocker note records the exact command and error.
- `pytest` and `ruff` pass.

## Self-Deception Traps

- Do not treat a single oracle pass as evidence that the scorer is reliable.
- Do not treat public-test success as task success.
- Do not count a bad control failure without checking why it failed.
- Do not call Docker smoke a secure sandbox.
- Do not add model agents or training before the scorer-audit layer is usable.
- Do not broaden to new task families; stay in local Python repo-patch tasks.

## First Small Step

Create `docs/attempt_status_taxonomy.md`. The taxonomy should be written before
the audit runner so that the runner has a clear contract to satisfy.
