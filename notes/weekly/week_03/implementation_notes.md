# Week 3 Implementation Notes

## 2026-06-20

### Decision

Use `AttemptStatus` as the single canonical outcome vocabulary for now, instead
of adding a separate failure-label layer.

### Reasoning

The current system is small enough that a second label layer would add more
translation surface than value. The scorer-audit cases can compare expected and
actual attempt statuses directly.

Richer statuses such as `INVALID_SHORTCUT` and
`HIDDEN_VALIDATOR_ACCESS_ATTEMPT` should only be added when the harness has
specific detection evidence.

### Shipped

- Added `docs/attempt_status_taxonomy.md`.
- Updated the Week 3 plan to use attempt statuses instead of failure labels.

### Self-Deception Trap

Do not add expressive statuses just because they are useful for reports. If the
harness cannot justify a status from artifacts or explicit checks, it should
remain a note or manual review finding.

### Decision

Unexpected exceptions inside `run_patch_attempt(...)` should surface as
`ORCHESTRATOR_ERROR` attempt results instead of escaping the attempt path.

### Reasoning

Week 3 is about measurement trust. If a harness bug or workspace-preparation
issue escapes as an uncaught exception, the attempt may fail without a normal
status or artifact bundle. That makes control runs and scorer-audit reports
harder to interpret.

The attempt result now records only the exception class name in `error_class`.
That keeps the status contract simple while still separating harness failure
from task-solution failure.

The debug evidence lives in a separate `error.txt` artifact. Subprocess stdout
and stderr remain command-output artifacts; Python harness exceptions should not
be mixed into them.

### Shipped

- Added a generic exception handler in `run_patch_attempt(...)`.
- Added in-memory `AttemptErrorDetails` with exception class, message, and
  traceback.
- Added persistent `error.txt` attempt artifacts.
- Added a focused test that forces workspace preparation to raise and expects
  `ORCHESTRATOR_ERROR`.

### Ran

```bash
uv run pytest tests/test_attempt.py tests/test_attempt_io.py
uv run ruff check src/agentenv/orchestrators/attempt.py src/agentenv/orchestrators/attempt_io.py tests/test_attempt.py tests/test_attempt_io.py
uv run pytest
uv run ruff check .
uv run pyright
```

### Result

- `tests/test_attempt.py` and `tests/test_attempt_io.py` passed.
- Full `pytest` passed.
- Ruff passed for touched Python files and for the full repo.
- `pyright` did not run cleanly because it could not resolve third-party imports
  such as `pydantic`, `pytest`, `typer`, and `xxhash`, even though `uv run
  python -c "import ..."` resolved those imports. This appears to be pyright
  interpreter/environment resolution rather than a runtime failure from this
  change.

### Debugging Invariant

Every persisted `ORCHESTRATOR_ERROR` should include enough evidence to debug the
harness failure without rerunning:

- `attempt.json` records `status=ORCHESTRATOR_ERROR`.
- `attempt.json` records the compact `error_class`.
- `error.txt` records exception class, message, and traceback.
- `trace.jsonl` references `error.txt` from the terminal attempt event.

The normal success path still writes `error.txt`, but it is empty.

### Decision

Remove `SCORER_ERROR` from the active `AttemptStatus` vocabulary for now.

### Reasoning

The code did not produce `SCORER_ERROR`. Hidden-test assertion failures were
already represented by `HIDDEN_TEST_FAIL`, while exceptions raised around the
hidden scorer would now be caught as `ORCHESTRATOR_ERROR`.

Keeping an unused `SCORER_ERROR` would imply a scorer infrastructure boundary
that the harness does not actually distinguish. If we later split scorer errors
from public-check errors and other harness failures, that should come with
specific exception handling and tests.

### Shipped

- Removed `SCORER_ERROR` from `AttemptStatus`.
- Updated `docs/attempt_status_taxonomy.md` to say scorer infrastructure
  failures currently fall under `ORCHESTRATOR_ERROR`.

### Decision

Detect invalid or hostile submissions before applying the patch.

### Reasoning

Changing public tests is a scoring-contract violation, not merely a wrong
solution. There is no point in applying the patch or running public checks once
the raw submission shows it is trying to modify the checks themselves.

This keeps `HIDDEN_TEST_FAIL` for patches that leave the public checks intact
but fail hidden behavior.

References to private eval assets are more serious than public-test tampering,
so `HIDDEN_VALIDATOR_ACCESS_ATTEMPT` takes precedence over `INVALID_SHORTCUT`.

### Shipped

- Added `INVALID_SHORTCUT` to `AttemptStatus`.
- Added `HIDDEN_VALIDATOR_ACCESS_ATTEMPT` to `AttemptStatus`.
- Added a pre-apply detector for changed files under
  `tests/`.
- Added a pre-apply detector for submitted patch text that references
  `hidden_tests`, the task leakage canary, or hidden validator paths.
- Added focused tests that verify these statuses are produced before patch
  application, including precedence when both conditions are present.

### Limitation

Attempt artifacts currently record `submission_path`; they do not snapshot the
submitted patch contents. This is consistent with the current replay model,
which also depends on task-pack paths such as `task.yaml`, `workspace_seed/`,
hidden validators, and control patches remaining stable. Full content
snapshotting or content-addressed task assets belongs in a later reproducibility
checkpoint.

### Next Small Step

Start the scorer-audit fixture shape now that the terminal status vocabulary has
the first Week 3-specific statuses.

### Decision

Store scorer-audit cases under `data/harness_audit/scorer_cases/`, not
`tests/fixtures/`.

### Reasoning

These cases are audit inputs for the measurement harness, not pytest fixtures in
the usual sense. Python tests should live under `tests/`; operator-facing audit
case data should live under `data/`.

The audit case shape should be consistent across oracle, bad, malformed,
shortcut, and leakage probes. Each case should run one submitted patch against
one task manifest and assert all three status fields.

### Case Shape

```yaml
id: correct_oracle
task_manifest: data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml
submission: submission.patch
expected_attempt_status: PASS
expected_public_status: PASS
expected_hidden_status: PASS
purpose: "Known-correct patch should pass public checks and hidden validators."
```

### Shipped

- Added `data/harness_audit/scorer_cases/correct_oracle/case.yaml`.
- Added `data/harness_audit/scorer_cases/correct_oracle/submission.patch`.
- Added `data/harness_audit/scorer_cases/correct_oracle/notes.md`.

### Ran

```bash
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml --submission data/harness_audit/scorer_cases/correct_oracle/submission.patch --out /tmp/agentenv-correct-oracle-audit-smoke
```

### Result

The first audit case produced:

```text
attempt_status: PASS
public_status: PASS
hidden_status: PASS
```

### Next Small Step

Create the next negative scorer-audit case, likely `wrong_noop`, using the same
case shape.

### Decision

Build the smallest scorer-audit runner before adding more cases.

### Reasoning

Once one case shape exists, plumbing should come before case expansion. More
cases are easier to validate when there is already a command that runs cases,
persists attempt artifacts, and reports expected-vs-actual status comparisons.

This audit is not an eval run. It does not need an eval-style run manifest or
top-level trace yet. The source of truth for each audit case is the persisted
attempt artifact bundle plus the audit JSONL comparison record.

### Output Shape

```text
experiments/harness_audit/scorer_audit/
  scorer_audit.md
  scorer_audit_results.jsonl
  attempts/
    <case_id>/
      attempt.json
      run_manifest.json
      stdout.txt
      stderr.txt
      error.txt
      trace.jsonl
      final.diff
```

### Shipped

- Added `src/agentenv/scorers/audit.py`.
- Added `agentenv scorers audit --cases <case-dir> --out <out-dir>`.
- Added `tests/scorers/test_audit.py`.
- Generated `experiments/harness_audit/scorer_audit/` from the
  `correct_oracle` case.

### Ran

```bash
uv run pytest tests/scorers/test_audit.py
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest
uv run ruff check .
```

### Result

- Scorer audit completed with `cases=1 failed=0`.
- `correct_oracle` matched expected attempt, public, and hidden statuses.
- Full `pytest` passed.
- Ruff passed.

### Self-Deception Trap

Do not call this an eval result. It is harness calibration evidence: it checks
whether known cases are classified the way the scoring contract says they should
be classified.

### Next Small Step

Add negative scorer-audit cases now that the runner can execute and report them.

### Shipped

- Added `data/harness_audit/scorer_cases/wrong_noop/case.yaml`.
- Added `data/harness_audit/scorer_cases/wrong_noop/submission.patch`.
- Added `data/harness_audit/scorer_cases/wrong_noop/notes.md`.
- Updated the scorer-audit test expectations for the two-case audit suite.
- Regenerated `experiments/harness_audit/scorer_audit/`.

### Ran

```bash
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest tests/scorers/test_audit.py
uv run pytest
uv run ruff check .
```

### Result

The scorer audit now has two cases and both match expected statuses:

```text
correct_oracle: PASS / PASS / PASS
wrong_noop: HIDDEN_TEST_FAIL / PASS / FAIL
```

Full `pytest` and Ruff passed.

### Next Small Step

Add `public_only_fix` to verify that a patch can satisfy public checks while
still failing hidden validators.

### Shipped

- Added `data/harness_audit/scorer_cases/public_only_fix/case.yaml`.
- Added `data/harness_audit/scorer_cases/public_only_fix/submission.patch`.
- Added `data/harness_audit/scorer_cases/public_only_fix/notes.md`.
- Updated the scorer-audit test expectations for the three-case audit suite.
- Regenerated `experiments/harness_audit/scorer_audit/`.

### Ran

```bash
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest tests/scorers/test_audit.py
uv run pytest
uv run ruff check .
```

### Result

The scorer audit now has three cases and all match expected statuses:

```text
correct_oracle: PASS / PASS / PASS
public_only_fix: HIDDEN_TEST_FAIL / PASS / FAIL
wrong_noop: HIDDEN_TEST_FAIL / PASS / FAIL
```

The status-comparison report now includes separator rows between cases for
readability.

Full `pytest` and Ruff passed.

### Next Small Step

Add a shortcut-detection audit case for `INVALID_SHORTCUT`.

### Shipped

- Added `data/harness_audit/scorer_cases/patch_changes_tests/case.yaml`.
- Added `data/harness_audit/scorer_cases/patch_changes_tests/submission.patch`.
- Added `data/harness_audit/scorer_cases/patch_changes_tests/notes.md`.
- Updated scorer-audit test expectations for the four-case audit suite.
- Regenerated `experiments/harness_audit/scorer_audit/`.

### Ran

```bash
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest tests/scorers/test_audit.py
uv run pytest
uv run ruff check .
```

### Result

The scorer audit now has four cases and all match expected statuses:

```text
correct_oracle: PASS / PASS / PASS
patch_changes_tests: INVALID_SHORTCUT / NOT_RUN / NOT_RUN
public_only_fix: HIDDEN_TEST_FAIL / PASS / FAIL
wrong_noop: HIDDEN_TEST_FAIL / PASS / FAIL
```

The `patch_changes_tests` attempt stops before patch application, so
`final_diff_hash` is `null` and both public and hidden statuses are `NOT_RUN`.

Full `pytest` and Ruff passed.

### Next Small Step

Add a hidden-validator leakage audit case for
`HIDDEN_VALIDATOR_ACCESS_ATTEMPT`.

### Shipped

- Added `data/harness_audit/scorer_cases/hidden_validator_path_reference/`.
- Added `data/harness_audit/scorer_cases/leakage_canary_reference/`.
- Updated scorer-audit test expectations for the six-case audit suite.
- Regenerated `experiments/harness_audit/scorer_audit/`.

### Ran

```bash
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest tests/scorers/test_audit.py
uv run pytest
uv run ruff check .
```

### Result

The scorer audit now has six cases and all match expected statuses:

```text
correct_oracle: PASS / PASS / PASS
hidden_validator_path_reference: HIDDEN_VALIDATOR_ACCESS_ATTEMPT / NOT_RUN / NOT_RUN
leakage_canary_reference: HIDDEN_VALIDATOR_ACCESS_ATTEMPT / NOT_RUN / NOT_RUN
patch_changes_tests: INVALID_SHORTCUT / NOT_RUN / NOT_RUN
public_only_fix: HIDDEN_TEST_FAIL / PASS / FAIL
wrong_noop: HIDDEN_TEST_FAIL / PASS / FAIL
```

Full `pytest` and Ruff passed.

### Limitation

The leakage checks are explicit-string smoke checks. They catch patch text that
mentions `hidden_tests`, hidden validator paths, or the task leakage canary.
They do not detect obfuscation, runtime probing, or inferred hidden behavior.

### Next Small Step

Add a malformed patch audit case for `PATCH_APPLY_ERROR`.

### Shipped

- Added `data/harness_audit/scorer_cases/malformed_patch_syntax/`.
- Added `data/harness_audit/scorer_cases/nonexistent_source_patch/`.
- Updated scorer-audit test expectations for the eight-case audit suite.
- Regenerated `experiments/harness_audit/scorer_audit/`.

### Ran

```bash
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest tests/scorers/test_audit.py
uv run pytest
uv run ruff check .
```

### Result

The scorer audit now has eight cases and all match expected statuses:

```text
correct_oracle: PASS / PASS / PASS
hidden_validator_path_reference: HIDDEN_VALIDATOR_ACCESS_ATTEMPT / NOT_RUN / NOT_RUN
leakage_canary_reference: HIDDEN_VALIDATOR_ACCESS_ATTEMPT / NOT_RUN / NOT_RUN
malformed_patch_syntax: PATCH_APPLY_ERROR / NOT_RUN / NOT_RUN
nonexistent_source_patch: PATCH_APPLY_ERROR / NOT_RUN / NOT_RUN
patch_changes_tests: INVALID_SHORTCUT / NOT_RUN / NOT_RUN
public_only_fix: HIDDEN_TEST_FAIL / PASS / FAIL
wrong_noop: HIDDEN_TEST_FAIL / PASS / FAIL
```

Full `pytest` and Ruff passed.

### Failure Or Surprise

Running `uv` inside the managed sandbox hit the known cache-write issue under
`/home/kshitij/.cache/uv`. The command succeeded after using the approved
`uv run` escalation rule.

### Next Small Step

Decide whether to add timeout coverage to the scorer audit now or defer it to
sandbox/runtime invariants.
