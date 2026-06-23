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

### Decision

Add timeout coverage to the scorer audit and make timeout statuses
phase-specific.

### Reasoning

Timeout handling is partly runtime behavior, but it affects trust in the eval
harness. A bad submission should not hang the audit or eval path indefinitely,
and the user should be able to tell which phase timed out without inspecting the
full trace first.

The terminal `AttemptStatus` remains `TIMEOUT`, while `public_status`,
`hidden_status`, and `error_class` identify the phase:

```text
patch apply timeout: TIMEOUT / NOT_RUN / NOT_RUN / PatchApplyTimeout
public check timeout: TIMEOUT / FAIL / NOT_RUN / PublicCheckTimeout
hidden validation timeout: TIMEOUT / PASS / FAIL / HiddenValidationTimeout
```

### Decision

Support a narrow scorer-audit manifest override for
`manifest_overrides.limits.timeout_seconds`.

### Reasoning

The core `run_patch_attempt(...)` API should remain tight: it consumes a task
manifest and a submission patch. Other task-manifest parameters are not passed
as generic function arguments, so timeout should not become a generic attempt
parameter either.

For the timeout audit case, the audit runner materializes a temporary task
directory with only `limits.timeout_seconds` changed. It records the narrow
override evidence as `manifest_override.json` beside the attempt artifacts.

This proves the audit case did not change task semantics to get the timeout
result. It does not make the audit attempt replayable through `agentenv replay`.

### Shipped

- Added phase-aware timeout status handling in `run_patch_attempt(...)`.
- Added focused timeout phase tests for patch apply, public checks, and hidden
  validation.
- Added `manifest_overrides.limits.timeout_seconds` to scorer-audit case schema.
- Added `data/harness_audit/scorer_cases/public_check_timeout/`.
- Regenerated `experiments/harness_audit/scorer_audit/`.

### Ran

```bash
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest tests/scorers/test_audit.py tests/test_attempt.py
uv run ruff check src/agentenv/scorers/audit.py src/agentenv/orchestrators/attempt.py tests/scorers/test_audit.py tests/test_attempt.py
uv run pytest
uv run ruff check .
uv run pyright
```

### Result

The scorer audit now has nine cases and all match expected statuses:

```text
correct_oracle: PASS / PASS / PASS
hidden_validator_path_reference: HIDDEN_VALIDATOR_ACCESS_ATTEMPT / NOT_RUN / NOT_RUN
leakage_canary_reference: HIDDEN_VALIDATOR_ACCESS_ATTEMPT / NOT_RUN / NOT_RUN
malformed_patch_syntax: PATCH_APPLY_ERROR / NOT_RUN / NOT_RUN
nonexistent_source_patch: PATCH_APPLY_ERROR / NOT_RUN / NOT_RUN
patch_changes_tests: INVALID_SHORTCUT / NOT_RUN / NOT_RUN
public_only_fix: HIDDEN_TEST_FAIL / PASS / FAIL
public_check_timeout: TIMEOUT / FAIL / NOT_RUN
wrong_noop: HIDDEN_TEST_FAIL / PASS / FAIL
```

Focused tests and Ruff passed. Full validation also passed:

```text
pytest: 52 passed
ruff: all checks passed
pyright: 0 errors
```

### Limitation

Scorer-audit artifacts are regenerable from case definitions, but they are not
currently replayable through `agentenv replay`. The timeout case records
`manifest_override.json` as evidence of the only supported override; the
effective manifest used for execution is a temporary audit-runner detail.

### Next Small Step

Run full validation and then decide whether the scorer-audit suite is sufficient
for Week 3, or whether to add an explicit `PUBLIC_TEST_FAIL` case.

### Decision

Make scorer-audit manifest override application and diff recording generic over
the validated `ManifestOverrides` model.

### Reasoning

The allowlist should live in the Pydantic schema, not in duplicated
timeout-specific branches. The audit runner can then mechanically apply whatever
nested override shape the schema accepts and record the same shape as nested
`from`/`to` evidence.

This keeps the current override surface narrow:

```yaml
manifest_overrides:
  limits:
    timeout_seconds: 1
```

But if another override is deliberately added later, the code path should not
need another hardcoded `limits.timeout_seconds` branch.

### Shipped

- Replaced timeout-specific manifest override application with recursive nested
  override application.
- Replaced flat `limits.timeout_seconds` audit evidence with nested JSON:

```json
{
  "limits": {
    "timeout_seconds": {
      "from": 120,
      "to": 1
    }
  }
}
```

- Regenerated `experiments/harness_audit/scorer_audit/`.

### Ran

```bash
uv run pytest tests/scorers/test_audit.py
uv run ruff check src/agentenv/scorers/audit.py tests/scorers/test_audit.py
uv run agentenv scorers audit --cases data/harness_audit/scorer_cases --out experiments/harness_audit/scorer_audit
uv run pytest tests/scorers/test_audit.py tests/test_attempt.py
uv run pyright
uv run pytest
uv run ruff check .
```

### Result

- Focused scorer-audit tests passed.
- The nine-case scorer audit completed with `failed=0`.
- Focused attempt/audit tests passed.
- Pyright passed with `0 errors`.
- Full `pytest` passed with `52 passed`.
- Full Ruff passed.

### Self-Deception Trap

The recursive override helper is not the permission boundary. It must only be
fed data that has already passed the strict `ManifestOverrides` schema.

### Follow-Up

The first scorer-audit test was too broad. It mostly proved that the audit
runner could execute cases and that actual statuses matched the expectations in
`case.yaml`. That is useful integration coverage, but it did not unit-test the
manifest override contract itself.

Added focused tests for:

- accepting the only currently supported override:
  `manifest_overrides.limits.timeout_seconds`;
- rejecting unsupported top-level override fields;
- rejecting unsupported nested `limits` fields;
- rejecting invalid timeout values such as `0`;
- mechanically applying nested overrides and recording nested `from`/`to`
  evidence.

### Ran

```bash
uv run pytest tests/scorers/test_audit.py
uv run ruff check tests/scorers/test_audit.py
uv run pyright tests/scorers/test_audit.py
```

### Result

- `tests/scorers/test_audit.py`: `8 passed`.
- Ruff passed for the audit test file.
- Pyright passed for the audit test file.

### Self-Deception Trap

Do not confuse case-level expected statuses with unit tests of the audit code.
The case YAMLs define expected outcomes; separate tests still need to prove that
the runner enforces its own permission and artifact contracts.

### Follow-Up

Rename the ambiguous timeout audit case and add hidden-validation timeout
coverage.

### Reasoning

The previous `timeout_patch` name made it sound like patch application timed
out, but the submitted patch actually applied and then made the public check
hang. The case ID should name the phase being audited.

The phase-status convention remains:

```text
public check timeout: TIMEOUT / FAIL / NOT_RUN / PublicCheckTimeout
hidden check timeout: TIMEOUT / PASS / FAIL / HiddenValidationTimeout
```

The phase that times out is marked `FAIL`; phases after it are marked
`NOT_RUN`.

### Shipped

- Renamed `timeout_patch` to `public_check_timeout`.
- Added `hidden_check_timeout`, which passes the public check input and then
  hangs when hidden validators exercise other behavior.
- Regenerated `experiments/harness_audit/scorer_audit/`; the audit now has ten
  cases and all match expected statuses.

### Limitation

`patch_apply` timeout is still covered by focused unit tests in
`tests/test_attempt.py`, but not by a scorer-audit data case. A real
scorer-audit case would need a deterministic way to make `git apply` exceed the
timeout. A huge static patch is a poor audit artifact because it is
machine-speed dependent and bloats the case data.

### Next Design Question

Should patch-apply timeout stay as unit-level orchestrator coverage, or should
the audit runner grow an explicit fault-injection case type for harness-phase
timeouts?

### Follow-Up

Add an explicit `PUBLIC_TEST_FAIL` scorer-audit case.

### Reasoning

The suite already had patches that failed hidden validation after passing
public checks, but it did not directly cover the public-check failure boundary.
That boundary matters because hidden validators must not run after public checks
fail.

### Shipped

- Added `data/harness_audit/scorer_cases/public_test_fail/`.
- Updated scorer-audit expectations.
- Removed accidental ordering coupling from `tests/scorers/test_audit.py`.

### Result

The scorer audit now has eleven cases and all match expected statuses.

```text
public_test_fail: PUBLIC_TEST_FAIL / FAIL / NOT_RUN
```

### Testing Lesson

The audit integration test should not care about case ordering when asserting
status semantics. Ordering is a report determinism concern; semantic assertions
should be keyed by `case_id`.

### Decision

Skip `fake_test_output_spoof` and `collateral_damage_import_break` for the Week
3 scorer audit.

### Reasoning

The current scorer audit already covers the status boundaries these would
exercise:

- fake success-looking output is mostly a reward-hacking lesson; this harness
  uses subprocess return codes for status, and public-test tampering is already
  covered by `patch_changes_tests`;
- collateral import damage is another form of `PUBLIC_TEST_FAIL`, now covered
  directly by `public_test_fail`.

Adding redundant cases would make the audit suite look broader without adding a
new invariant.

### Result

No case data was added for those two manual suggestions. The empty directories
created during exploration were removed.

### Decision

Implement `agentenv controls run` as an orchestrator module:
`src/agentenv/orchestrators/controls_run.py`.

### Reasoning

Control calibration is not a new task schema or scorer. It coordinates the
same pieces as `eval_run.py`: task-pack discovery, manifest controls, repeated
attempt execution, artifact persistence, and run-level reporting. Keeping it in
`orchestrators/` makes that boundary explicit.

Expected outcomes are inferred from control names for now:

```text
oracle: PASS / PASS / PASS
bad.noop: HIDDEN_TEST_FAIL / PASS / FAIL
bad.public_only: HIDDEN_TEST_FAIL / PASS / FAIL
```

### Shipped

- Added `src/agentenv/orchestrators/controls_run.py`.
- Added `agentenv controls run --task-pack <path> --repeats <n> --out <dir>`.
- Added `tests/test_controls_run.py`.
- Generated `experiments/runs/control_calibration/` with repo-agnostic naming.

### Output Shape

```text
experiments/runs/control_calibration/
  control_report.md
  control_results.jsonl
  control_run_manifest.json
  attempts/
    <task_id>__<control>__repeat_<nnn>/
```

### Result

Running the current task pack with three repeats produced nine attempts and no
expectation mismatches:

```text
oracle: 3/3 attempt_status: PASS; public_status: PASS; hidden_status: PASS
bad.noop: 3/3 attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL
bad.public_only: 3/3 attempt_status: HIDDEN_TEST_FAIL; public_status: PASS; hidden_status: FAIL
```

### Boundary

`eval run` records policy outcomes. `controls run` is stronger: it compares
known controls against inferred expectations and treats mismatches as harness
calibration failures.

### Report Readability

The Markdown report labels status triples explicitly as `attempt_status`,
`public_status`, and `hidden_status`. A compact display like
`HIDDEN_TEST_FAIL / PASS / FAIL` was too easy to misread because `PASS` and
`FAIL` appear in multiple fields.

### Decision

Start sandbox invariant documentation with the hidden-validator visibility
boundary.

### Reasoning

The first local sandbox invariant should be precise and testable:

```text
Hidden validators must exist in the task package, but must not be present inside
the prepared agent workspace.
```

This is the core measurement boundary. If the agent-visible workspace contains
hidden validators, hidden scoring is no longer hidden.

### Shipped

- Added `docs/sandbox_invariants_v0.md`.

### Limitation

This document currently describes the local workspace model only. It does not
claim Docker isolation, network isolation, or hostile-code containment.

### Shipped

- Added `tests/sandbox/test_invariants.py` with a focused test for the first
  sandbox invariant.

### Result

The test asserts both sides of the boundary:

- manifest-declared hidden validator paths exist in the task package;
- the same paths are absent from the prepared agent workspace.

### Ran

```bash
uv run pytest tests/sandbox/test_invariants.py tests/test_local_repo_env.py
uv run ruff check tests/sandbox/test_invariants.py
uv run pyright tests/sandbox/test_invariants.py
```

### Decision

Add the same local workspace visibility invariant for control patches.

### Reasoning

Control patches are the same class of private calibration asset as hidden
validators. They must exist in the task package but remain absent from the
prepared agent workspace.

The test should derive paths from the manifest, not hardcode the current toy
task layout. That keeps the invariant attached to the task contract:

```text
manifest.controls.oracle
manifest.controls.bad.noop
manifest.controls.bad.public_only
```

### Shipped

- Added `Invariant 2: Control Patches Are Not Agent-Visible` to
  `docs/sandbox_invariants_v0.md`.
- Added
  `tests/sandbox/test_invariants.py::test_control_patches_are_not_present_in_prepared_agent_workspace`.

### Ran

```bash
uv run pytest tests/sandbox/test_invariants.py tests/test_local_repo_env.py
uv run ruff check tests/sandbox/test_invariants.py
uv run pyright tests/sandbox/test_invariants.py
```

### Result

The focused sandbox checks now cover hidden validators and control patches as
agent-invisible task-package assets.

### Decision

Add a workspace freshness invariant.

### Reasoning

Repeated evals and control runs are only trustworthy if every attempt starts
from a fresh copy of `workspace_seed`.

The invariant is:

```text
Each attempt must start from a fresh copy of workspace_seed.
Mutating one prepared workspace must not mutate workspace_seed or any later
prepared workspace.
```

### Shipped

- Added `Invariant 3: Each Attempt Starts From A Fresh Workspace Seed Copy` to
  `docs/sandbox_invariants_v0.md`.
- Added
  `tests/sandbox/test_invariants.py::test_mutating_one_prepared_workspace_does_not_mutate_seed_or_later_workspace`.

### Ran

```bash
uv run pytest tests/sandbox/test_invariants.py tests/test_local_repo_env.py
uv run ruff check tests/sandbox/test_invariants.py
uv run pyright tests/sandbox/test_invariants.py
```

### Result

The test mutates one prepared workspace, then verifies that the task
`workspace_seed` and a later prepared workspace still contain the original file
contents and do not inherit an attempt-local file.

### Decision

Add a leakage-canary visibility invariant across workspace files and attempt
artifacts.

### Reasoning

The task leakage canary is a private marker. It should stay in task metadata and
must not appear in files available in the prepared workspace or in persisted
attempt evidence.

The invariant scans both surfaces:

- prepared workspace file contents;
- every generated file under the persisted attempt artifact directory.

### Shipped

- Added `Invariant 4: Leakage Canary Is Not Agent-Visible` to
  `docs/sandbox_invariants_v0.md`.
- Added
  `tests/sandbox/test_invariants.py::test_leakage_canary_is_absent_from_workspace_and_attempt_artifacts`.

### Ran

```bash
uv run pytest tests/sandbox/test_invariants.py tests/test_local_repo_env.py
uv run ruff check tests/sandbox/test_invariants.py
uv run pyright tests/sandbox/test_invariants.py
```

### Result

The focused sandbox checks now verify that the canary is absent from the
prepared workspace and from every generated file under the attempt artifact
directory.

### Decision

Add a task-manifest visibility invariant.

### Reasoning

`task.yaml` is a harness contract, not an agent input. It contains private
measurement metadata such as hidden-validator paths, control patch paths, and
the leakage canary.

The important distinction is:

```text
allowed: artifact records task_manifest_path for provenance
not allowed: prepared workspace or attempt artifacts embed task.yaml contents
```

### Shipped

- Added `Invariant 5: Task Manifest Contents Are Not Agent-Visible` to
  `docs/sandbox_invariants_v0.md`.
- Added
  `tests/sandbox/test_invariants.py::test_task_manifest_contents_are_absent_from_workspace_and_attempt_artifacts`.

### Ran

```bash
uv run pytest tests/sandbox/test_invariants.py tests/test_local_repo_env.py
uv run ruff check tests/sandbox/test_invariants.py
uv run pyright tests/sandbox/test_invariants.py
```

### Result

The test verifies `task.yaml` is absent from the prepared workspace and that
manifest-only markers such as `hidden_validators:`, `controls:`, and
`leakage_canary:` are absent from every generated file under the attempt
artifact directory.

### Test Refinement

The first version hardcoded the standard artifact file list. That was too weak
for an invariant test because adding a new artifact could create a leak without
the test noticing. The scanner now walks all files under the generated attempt
artifact directory and checks bytes instead of assuming text-only files.

### Decision

Add a repeatability invariant for deterministic control runs.

### Reasoning

Workspace freshness proves one prepared workspace does not mutate the seed or a
later prepared workspace. Repeatability is a separate trust boundary: repeated
attempts of the same deterministic control should produce stable observable
results.

The invariant applies to all manifest-defined controls, not only the oracle.

Stable fields:

```text
attempt_status
public_status
hidden_status
final_diff_hash
```

Expected-to-vary fields:

```text
attempt_id
run_id
timestamps
durations
temporary paths
artifact directories
```

### Shipped

- Added `Invariant 6: Deterministic Control Repeats Are Stable` to
  `docs/sandbox_invariants_v0.md`.
- Added
  `tests/sandbox/test_invariants.py::test_repeated_control_runs_produce_stable_statuses_and_final_diff_hashes`.

### Ran

```bash
uv run pytest tests/sandbox/test_invariants.py tests/test_controls_run.py
uv run ruff check tests/sandbox/test_invariants.py
uv run pyright tests/sandbox/test_invariants.py
```

### Result

The test runs every current control twice and verifies that each `(task_id,
control)` group has one stable status/diff tuple.

### Decision

Add the first Docker smoke path with network disabled.

### Reasoning

Docker smoke should start as environment calibration, not a claim of secure
hostile-code containment. The first useful check is small:

```text
Can the harness run a command inside Docker with --network none, and does a
network probe fail under that setting?
```

The smoke runner uses two probes:

- startup probe: `echo docker_smoke_ok` should return `0`;
- network probe: `wget ... https://example.com` should return non-zero under
  `--network none`.

### Shipped

- Added `configs/sandbox/docker_none.yaml`.
- Added `src/agentenv/sandbox/docker_smoke.py`.
- Added `agentenv sandbox smoke --config <config> --out <dir>`.
- Added `tests/sandbox/test_docker_smoke.py` with a mocked Docker subprocess
  path.
- Generated `experiments/sandbox/docker_smoke/`.

### Ran

```bash
uv run pytest tests/sandbox/test_docker_smoke.py
uv run ruff check src/agentenv/sandbox/docker_smoke.py src/agentenv/cli.py tests/sandbox/test_docker_smoke.py
uv run pyright src/agentenv/sandbox/docker_smoke.py tests/sandbox/test_docker_smoke.py
uv run agentenv sandbox smoke --config configs/sandbox/docker_none.yaml --out experiments/sandbox/docker_smoke
```

### Result

The real Docker smoke passed:

```text
startup: returncode 0
network_probe: returncode 1 under --network none
status: PASS
```

Docker pulled `busybox:1.36` during the smoke run. The pull output recorded the
image digest in `docker_smoke_result.json` probe stderr.

### Limitation

This is a smoke check only. It proves the local Docker path can run a container
with network disabled for this probe. It does not prove production-grade
sandboxing, syscall isolation, filesystem mount policy, resource limits, or
protection against hostile code.
