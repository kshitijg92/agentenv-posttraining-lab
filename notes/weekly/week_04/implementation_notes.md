# Week 4 Implementation Notes

## 2026-06-23

### Decision

Separate submitted-attempt success from task calibration.

### Reasoning

A submitted patch succeeds only when the final attempt status is:

```text
attempt_status: PASS
public_status: PASS
hidden_status: PASS
```

Control policies are not part of a submitted patch's success condition. They
are the calibration evidence that makes the task result trustworthy:

```text
oracle passes
known-bad controls fail for expected reasons
```

This distinction keeps the baseline report from mixing task-result evidence
with harness-trust evidence.

### Shipped

- Added `docs/scoring_contract.md`.
- Added `docs/task_authoring_checklist.md`.
- Generalized the task provenance checklist language to cover
  employer-private, third-party-proprietary, and benchmark-heldout material
  instead of naming one employer-specific source.

### Next Small Step

Add task-pack metadata and split lock for `repo_patch_python_v0`, keeping
`toy_python_fix_001` in `practice` and reserving newly authored tasks for
`dev`.

### Decision

Keep all newly authored tasks in `dev`; leave `heldout_private` empty for now.

### Reasoning

Week 4 is task authoring and baseline construction. We will inspect task
instructions, hidden validators, controls, and failure modes while building.
Calling any of these tasks heldout would be fake rigor.

The toy task remains `practice` because it shaped the harness. New tasks should
enter `dev` until there is enough process discipline to preserve a genuinely
unseen heldout split.

Durable task-pack metadata, task ids, config names, code paths, and experiment
directories should describe the artifact rather than the learning calendar.
Weekly labels belong in `notes/weekly/...`.

### Shipped

- Added `data/task_packs/repo_patch_python_v0/manifest.yaml`.
- Added `data/task_packs/repo_patch_python_v0/splits.lock.json`.

### Next Small Step

Decide the first new `dev` task's behavioral contract before creating files.

### Decision

Make `agentenv tasks validate <task-pack>` a static integrity gate for the task
pack, not a dynamic control-calibration runner.

### Reasoning

The task-pack validation contract should be fast enough to run while authoring
tasks. It should check structural and leakage-boundary invariants:

```text
required files come from manifest.yaml
task ids and splits match splits.lock.json
workspace_seed does not contain private task assets or markers
hidden validator files are not exact duplicates of public tests
```

Repeated oracle/no-op/public-only execution is dynamic calibration. It remains
under `agentenv controls run` so reports can distinguish static task-pack
validity from runtime scorer evidence.

The duplicate-test check is intentionally conservative. It catches exact
normalized hidden/public test duplication; it does not prove semantic
difference between public and hidden tests.

### Shipped

- Added task-pack and split-lock schemas.
- Added `validate_task_pack(...)`.
- Updated `agentenv tasks validate` to accept either one `task.yaml` or a task
  pack directory.
- Added focused task-pack validation tests for required files, private markers,
  split mismatch, and duplicate hidden/public test files.

### Next Small Step

Run focused validation, then decide the first new `dev` task's behavioral
contract.

### Decision

Create the first new `dev` task as `repair_jsonl_deduper`.

### Reasoning

The contract is small but less toy-like than `toy_python_fix_001`:

```text
input/output are JSONL blobs
records are JSON objects
duplicate identity comes from caller-supplied dedupe_key
first-seen record is preserved
malformed JSONL, non-object lines, and missing dedupe keys raise ValueError
```

This gives the hidden validator a natural public-only shortcut to catch:
hardcoding `"id"` instead of honoring the caller-supplied key.

### Shipped

- Added `data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/`.
- Added `repair_jsonl_deduper` to the `dev` split.

### Next Small Step

Calibrate `repair_jsonl_deduper` with task-pack validation and the three
control attempts.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/oracle.patch --out /tmp/agentenv-repair-jsonl-oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_noop.patch --out /tmp/agentenv-repair-jsonl-noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_public_only.patch --out /tmp/agentenv-repair-jsonl-public-only
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
```

### Result

Task-pack validation passed:

```text
valid repo_patch_python_v0 tasks=2
```

The new task's direct controls produced the expected status tuples:

```text
oracle: PASS / PASS / PASS
bad.noop: HIDDEN_TEST_FAIL / PASS / FAIL
bad.public_only: HIDDEN_TEST_FAIL / PASS / FAIL
```

The repeated pack-level control run passed across the practice task and the new
dev task:

```text
attempts=18 failed=0
```

### Calibration Fix

The first draft of `oracle.patch` and `bad_public_only.patch` had invalid diff
hunk line counts and produced `PATCH_APPLY_ERROR`. The patch bodies were correct;
the control files were fixed by correcting the hunk headers.

### Next Small Step

Run repo checks, then design the second `dev` task contract.

### Test Maintenance

Adding a second task exposed two one-task-era test assumptions:

- `tests/test_task_manifest.py` expected the task pack to contain one task.
- `tests/test_controls_run.py` expected two repeats across one task and three
  controls, for six attempts.

The controls test now checks the current task id set and derives the expected
attempt count from:

```text
task_count * control_count * repeats
```

### Ran

```bash
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run ruff check tests/test_controls_run.py tests/test_task_manifest.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Full validation passed:

```text
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 18 trace files
```

### Next Small Step

Design the second `dev` task contract before creating files.

### Decision

Make first-seen retention explicit in the agent-visible seed code.

### Reasoning

First-seen retention is part of the task contract, not a hidden trick. The task
instruction already states it, but the seed function docstring only said that
duplicates were removed. Relying on the public test alone to imply first-seen
semantics would make the task more ambiguous than necessary.

The hidden validators should test edge cases and shortcut resistance; they
should not be the only place where core semantics are specified.

### Shipped

- Updated the `dedupe_jsonl(...)` seed docstring to state first-seen retention.
- Updated the `oracle` and `bad_public_only` control patch context to match the
  new seed file.

### Next Small Step

Recalibrate `repair_jsonl_deduper` after the seed-docstring change.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/oracle.patch --out /tmp/agentenv-repair-jsonl-oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_noop.patch --out /tmp/agentenv-repair-jsonl-noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_public_only.patch --out /tmp/agentenv-repair-jsonl-public-only
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run ruff check data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/workspace_seed/src/jsonl_tools.py data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/workspace_seed/tests/test_public.py data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/hidden_tests/test_behavior.py
```

### Result

Recalibration passed after the docstring change:

```text
task pack validation: valid repo_patch_python_v0 tasks=2
oracle: PASS
bad.noop: HIDDEN_TEST_FAIL
bad.public_only: HIDDEN_TEST_FAIL
repeated controls: attempts=18 failed=0
focused pytest: 9 passed
ruff on task files: all checks passed
```

### Decision

Make `ValueError` explicit in the agent-visible seed docstring.

### Reasoning

The exception type is also core task semantics. If the agent only sees the seed
workspace and public tests, requiring `ValueError` only in hidden validators
would be ambiguous. The hidden validators should verify malformed JSONL,
non-object lines, and missing-key behavior, but the expected exception type
should be visible.

### Shipped

- Updated the `dedupe_jsonl(...)` seed docstring to require `ValueError` for
  malformed JSONL, non-object lines, and missing dedupe keys.
- Updated the `oracle` and `bad_public_only` control patch context.

### Next Small Step

Recalibrate `repair_jsonl_deduper` after the visible `ValueError`
contract update.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/oracle.patch --out /tmp/agentenv-repair-jsonl-oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_noop.patch --out /tmp/agentenv-repair-jsonl-noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_public_only.patch --out /tmp/agentenv-repair-jsonl-public-only
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run ruff check data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/workspace_seed/src/jsonl_tools.py data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/workspace_seed/tests/test_public.py data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/hidden_tests/test_behavior.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Recalibration passed after making `ValueError` visible:

```text
task pack validation: valid repo_patch_python_v0 tasks=2
oracle: PASS
bad.noop: HIDDEN_TEST_FAIL
bad.public_only: HIDDEN_TEST_FAIL
repeated controls: attempts=18 failed=0
focused pytest: 9 passed
focused ruff on task files: all checks passed
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 18 trace files
```

### Decision

Use meaningful task slugs as task ids instead of numeric suffixes for new tasks.

### Reasoning

The task pack version already scopes the suite, and the task directory slug
already gives each task a stable namespace. A suffix such as `_001` is premature
unless there are multiple intentionally versioned variants of the same task.

If a later task is materially different, it should get a descriptive slug rather
than an opaque sequence number.

### Shipped

- Removed the numeric suffix from the repair JSONL deduper task id.
- Updated `splits.lock.json`, controls tests, task card, and leakage canary.

### Next Small Step

Regenerate `dev_controls` so generated evidence uses the current task id.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/oracle.patch --out /tmp/agentenv-repair-jsonl-oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_noop.patch --out /tmp/agentenv-repair-jsonl-noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_public_only.patch --out /tmp/agentenv-repair-jsonl-public-only
rm -rf experiments/runs/dev_controls
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run ruff check data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/workspace_seed/src/jsonl_tools.py data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/workspace_seed/tests/test_public.py data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/hidden_tests/test_behavior.py tests/test_controls_run.py tests/test_task_manifest.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Rename and recalibration passed:

```text
task pack validation: valid repo_patch_python_v0 tasks=2
oracle: PASS
bad.noop: HIDDEN_TEST_FAIL
bad.public_only: HIDDEN_TEST_FAIL
repeated controls: attempts=18 failed=0
focused pytest: 9 passed
focused ruff: all checks passed
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 18 trace files
stale numeric task id search: no matches
```

### Decision

Do not require specific `ValueError` message wording in
`repair_jsonl_deduper` hidden validators.

### Reasoning

The visible task contract requires `ValueError` for malformed JSONL, non-object
lines, and records missing the dedupe key. It does not specify exact error
message text.

Matching message substrings would accidentally score incidental phrasing instead
of the intended behavior. Hidden validators should only check message text when
the message is part of the visible contract.

### Shipped

- Removed `pytest.raises(..., match=...)` from the three invalid-input hidden
  tests.

### Next Small Step

Recalibrate `repair_jsonl_deduper` after relaxing hidden error-message checks.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/oracle.patch --out /tmp/agentenv-repair-jsonl-oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_noop.patch --out /tmp/agentenv-repair-jsonl-noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/controls/bad_public_only.patch --out /tmp/agentenv-repair-jsonl-public-only
rm -rf experiments/runs/dev_controls && uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run ruff check data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/hidden_tests/test_behavior.py tests/test_controls_run.py tests/test_task_manifest.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Recalibration passed after removing message matching:

```text
task pack validation: valid repo_patch_python_v0 tasks=2
oracle: PASS
bad.noop: HIDDEN_TEST_FAIL
bad.public_only: HIDDEN_TEST_FAIL
repeated controls: attempts=18 failed=0
focused pytest: 9 passed
focused ruff: all checks passed
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 18 trace files
```

### Decision

Create the second `dev` task as `preserve_cli_error_codes`.

### Reasoning

This task is still single-file and local, but less function-kata-like than the
JSONL deduper. It has a small internal call chain:

```text
load_jsonl -> summarize_records -> main
```

The visible contract lives in constants, docstrings, and the task instruction:

```text
success exits 0
usage errors exit 2
missing input files exit 3
malformed JSONL, invalid record schema, or duplicate ids exit 4
records require string id and string status
expected user/input errors should not print tracebacks
```

Hidden validators check the visible contract without requiring exact error
message wording or JSON key order.

### Shipped

- Added `data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/`.
- Added `preserve_cli_error_codes` to the `dev` split.

### Next Small Step

Calibrate `preserve_cli_error_codes` with task-pack validation and the three
control attempts.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/controls/oracle.patch --out /tmp/agentenv-preserve-cli-oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/controls/bad_noop.patch --out /tmp/agentenv-preserve-cli-noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/controls/bad_public_only.patch --out /tmp/agentenv-preserve-cli-public-only
rm -rf experiments/runs/dev_controls && uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run ruff check data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/workspace_seed/src/validate_records.py data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/workspace_seed/tests/test_public.py data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/hidden_tests/test_cli_behavior.py tests/test_controls_run.py tests/test_task_manifest.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Calibration passed:

```text
task pack validation: valid repo_patch_python_v0 tasks=3
oracle: PASS
bad.noop: HIDDEN_TEST_FAIL
bad.public_only: HIDDEN_TEST_FAIL
repeated controls: attempts=27 failed=0
focused pytest: 9 passed
focused ruff: all checks passed
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 27 trace files
```

### Calibration Fix

The first draft of `oracle.patch` had fragile hand-written hunk counts and
produced `PATCH_APPLY_ERROR`. The patch was replaced with an exact diff
generated from the seed and oracle file contents, then verified with
`git apply --check` before rerunning the harness.

### Next Small Step

Review task quality for the two new `dev` tasks before deciding whether to add a
third new task or move to the dev-baseline config/reporting path.

### Decision

Create the third new `dev` task as `repair_config_precedence`.

### Reasoning

This task increases complexity without making the config surface artificially
large. It has two source files and four public tests, but keeps the setting
shape small:

```text
Settings(host="localhost", port=8080, debug=False)
environment > JSON config > defaults
env vars: APP_HOST, APP_PORT, APP_DEBUG
debug accepts only bool, "true", or "false"
```

The useful difficulty is in the shortcuts, not in adding more fields:

```text
only APP_PORT is wired
unknown config keys are silently ignored
bool ports accidentally pass as ints
debug strings are not parsed
```

Hidden validators check those visible-contract edges without requiring exact
error-message wording.

### Shipped

- Added `data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/`.
- Added `repair_config_precedence` to the `dev` split.
- Updated task-pack control tests and manifest-count tests for four tasks.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/oracle.patch --out /tmp/repair_config_precedence_oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/bad_noop.patch --out /tmp/repair_config_precedence_noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/bad_public_only.patch --out /tmp/repair_config_precedence_public_only
rm -rf experiments/runs/dev_controls && uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Calibration passed:

```text
task pack validation: valid repo_patch_python_v0 tasks=4
oracle: PASS
bad.noop: HIDDEN_TEST_FAIL
bad.public_only: HIDDEN_TEST_FAIL
repeated controls: attempts=36 failed=0
focused pytest: 9 passed
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 36 trace files
```

### Calibration Fix

The first draft of `oracle.patch` passed a source-tree `git apply --check` but
failed in the copied workspace used by the orchestrator. The fix was to
regenerate the oracle diff from old/new temp copies and validate it against a
copied seed workspace before rerunning direct controls.

### Calibration Refinement

Added a mixed hidden case for default/config/environment merging:

```text
default port remains 8080
JSON config sets host
APP_DEBUG sets debug
```

This catches a more realistic public-only shortcut: treating environment as an
isolated source instead of merging it over config values. The updated
`bad_public_only.patch` now implements most of the visible contract but drops
config-derived values when only `APP_HOST` or `APP_DEBUG` is present. It passes
public tests and fails hidden on exactly this mixed merge case.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/oracle.patch --out /tmp/repair_config_precedence_oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/bad_public_only.patch --out /tmp/repair_config_precedence_public_only
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/bad_noop.patch --out /tmp/repair_config_precedence_noop
rm -rf experiments/runs/dev_controls && uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Refined calibration passed:

```text
task pack validation: valid repo_patch_python_v0 tasks=4
oracle: PASS
bad.noop: HIDDEN_TEST_FAIL
bad.public_only: HIDDEN_TEST_FAIL
bad.public_only hidden output: 1 failed, 6 passed
repeated controls: attempts=36 failed=0
focused pytest: 9 passed
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 36 trace files
```

### Review Fixes

Fixed the three suite-review findings:

- Added `pytest>=9.1.0` to every task seed `pyproject.toml` so public and hidden
  pytest checks do not rely on the outer `agentenv` virtualenv.
- Added a `preserve_cli_error_codes` hidden test for non-object JSONL lines
  exiting `4` without a traceback.
- Added `repair_config_precedence` hidden tests for JSON config numeric-string
  ports and `APP_DEBUG="false"` overriding config to `False`.

### Ran

```bash
env -u VIRTUAL_ENV uv run pytest tests/test_public.py
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/controls/oracle.patch --out /tmp/fix_preserve_oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/controls/bad_noop.patch --out /tmp/fix_preserve_noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/preserve_cli_error_codes/controls/bad_public_only.patch --out /tmp/fix_preserve_public_only
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/oracle.patch --out /tmp/fix_config_oracle
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/bad_noop.patch --out /tmp/fix_config_noop
uv run agentenv attempt run --task-manifest data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/repair_config_precedence/controls/bad_public_only.patch --out /tmp/fix_config_public_only
rm -rf experiments/runs/dev_controls && uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run pytest tests/test_controls_run.py tests/test_task_manifest.py
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_controls").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Review fixes passed:

```text
clean copied-seed public checks with VIRTUAL_ENV unset: pass
task pack validation: valid repo_patch_python_v0 tasks=4
preserve_cli_error_codes direct controls: PASS / HIDDEN_TEST_FAIL / HIDDEN_TEST_FAIL
repair_config_precedence direct controls: PASS / HIDDEN_TEST_FAIL / HIDDEN_TEST_FAIL
repeated controls: attempts=36 failed=0
focused pytest: 9 passed
pytest: 72 passed
ruff: all checks passed
pyright: 0 errors
dev_controls trace validation: 36 trace files
```

### Next Small Step

Design the dev-baseline eval config contract before creating the YAML.

### Decision

Keep the first dev-baseline eval config control-only.

### Reasoning

The existing eval config schema already supports runnable control-patch
policies. Week 4's plan asks for three scripted policies:

```text
noop -> bad.noop
public-tests-only -> bad.public_only
oracle -> oracle
```

The 12-week manual lists `simple-prompt-loop` only as an optional Week 4 stretch
and explicitly says not to block Week 4 on real LLM agent integration. The
model/agent baseline config belongs to Week 5.

### Shipped

- Added `configs/eval/dev_baseline.yaml`.

### Ran

```bash
uv run agentenv eval --config configs/eval/dev_baseline.yaml --policy noop --out experiments/runs/dev_noop
uv run agentenv eval --config configs/eval/dev_baseline.yaml --policy public-tests-only --out experiments/runs/dev_public_only
uv run agentenv eval --config configs/eval/dev_baseline.yaml --policy oracle --out experiments/runs/dev_oracle
uv run agentenv replay experiments/runs/dev_oracle --out experiments/replays/dev_oracle
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=[]; roots=[Path("experiments/runs/dev_noop"), Path("experiments/runs/dev_public_only"), Path("experiments/runs/dev_oracle"), Path("experiments/replays/dev_oracle")]; [paths.extend(sorted(root.rglob("trace.jsonl"))) for root in roots]; [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Baseline artifact generation passed:

```text
noop: HIDDEN_TEST_FAIL=3
public-tests-only: HIDDEN_TEST_FAIL=3
oracle: PASS=3
oracle replay: PASS attempts=3
trace validation: 16 trace files
```

### Next Small Step

Create the dev-baseline report. `agentenv report compare` does not exist yet,
so either add the smallest compare path or write the report directly from the
generated manifests without overstating automation.

### Decision

Add a first-class full eval config mode before building the consolidated
dev-baseline report.

### Reasoning

The current eval command ran one selected policy from a config. That was enough
for early control calibration, but a baseline report is naturally about the
whole policy set defined by one eval config:

```text
dev_baseline x {noop, public-tests-only, oracle}
```

The clean next abstraction is a parent eval-matrix artifact, not a loose report
over manually grouped run directories.

### Shipped

- Added `run_eval_config_all_policies(...)`.
- Added `uv run agentenv eval --config <config> --all-policies --out <dir>`.
- Added `eval_matrix_v0` parent manifests at:

```text
<out>/eval_matrix_manifest.json
<out>/policies/<policy>/run_manifest.json
```

The existing `--policy` mode still writes a single `eval_run_v0` artifact.

### Ran

```bash
uv run pytest tests/test_eval_run.py
uv run ruff check src/agentenv/orchestrators/eval_run.py src/agentenv/cli.py tests/test_eval_run.py
uv run pyright src/agentenv/orchestrators/eval_run.py src/agentenv/cli.py tests/test_eval_run.py
uv run agentenv eval --config configs/eval/dev_baseline.yaml --all-policies --out /tmp/agentenv-dev-baseline-matrix
uv run pytest
uv run ruff check .
uv run pyright
```

### Result

Full eval config mode passed:

```text
temporary dev_baseline matrix: policies=3 attempts=9 HIDDEN_TEST_FAIL=6 PASS=3
focused eval tests: 5 passed
pytest: 73 passed
ruff: all checks passed
pyright: 0 errors
```

### Next Small Step

Generate the durable dev-baseline matrix artifact, then teach reporting to read
`eval_matrix_v0` and produce `experiments/reports/dev_baseline.md`.

### Ran

```bash
uv run agentenv eval --config configs/eval/dev_baseline.yaml --all-policies --out experiments/runs/dev_baseline
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_baseline").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Durable dev-baseline matrix generation passed:

```text
policies=3
attempts=9
status_counts: HIDDEN_TEST_FAIL=6, PASS=3
trace validation: 12 trace files
artifact: experiments/runs/dev_baseline/eval_matrix_manifest.json
```

### Next Small Step

Teach reporting to read `eval_matrix_v0` and produce
`experiments/reports/dev_baseline.md`.

### Shipped

- Added `eval_matrix_v0` support to `agentenv report`.
- Added a consolidated eval matrix report with:
  - task count and task ids,
  - policy summary,
  - final/public/hidden pass rates,
  - oracle and known-bad calibration rates,
  - environment/harness and scorer/orchestrator failure rates,
  - median attempt runtime,
  - trace and attempt artifact links,
  - explicit non-claims.
- Added a reporting test for eval matrix artifacts.
- Generated `experiments/reports/dev_baseline.md`.

### Current Report Limitations

`eval_matrix_v0` does not yet capture:

```text
hidden-validator file hashes
oracle replay result
task exclusions as structured data
```

The report states these limitations explicitly instead of inferring them from
outside artifacts.

### Ran

```bash
uv run pytest tests/test_reporting.py tests/test_eval_run.py
uv run ruff check src/agentenv/reporting/markdown.py tests/test_reporting.py
uv run pyright src/agentenv/reporting/markdown.py tests/test_reporting.py
uv run agentenv report experiments/runs/dev_baseline --out experiments/reports/dev_baseline.md
uv run pytest
uv run ruff check .
uv run pyright
```

### Result

Consolidated dev-baseline report generation passed:

```text
report: experiments/reports/dev_baseline.md
oracle pass rate: 3/3
known-bad final PASS rate: 0/6
known-bad public-pass/hidden-fail rate: 6/6
environment/harness failure rate: 0/9
scorer/orchestrator failure rate: 0/9
focused tests: 8 passed
pytest: 74 passed
ruff: all checks passed
pyright: 0 errors
```

### Next Small Step

Decide whether to extend `eval_matrix_v0` to include replay linkage and hidden
validator hashes now, or record those as Week 4 limitations and close the
remaining Week 4 notes.

### Report Refinement

Added a control-expectation quick-check table to the eval matrix report.

### Reasoning

The policy summary showed observed rates but did not encode the expected
calibration pattern:

```text
oracle: final PASS, public PASS, hidden PASS
noop: final HIDDEN_TEST_FAIL, public PASS, hidden FAIL
public-tests-only: final HIDDEN_TEST_FAIL, public PASS, hidden FAIL
```

The report now makes those expectations explicit and marks each policy
`ON_TRACK` or `OFF_TRACK`.

### Report Path Decision

Use artifact-type subdirectories for generated reports:

```text
experiments/reports/evals/
experiments/reports/replays/
experiments/reports/eval_matrices/
```

The canonical consolidated dev-baseline report is now:

```text
experiments/reports/eval_matrices/dev_baseline.md
```

The root-level `experiments/reports/dev_baseline.md` was regenerated during the
transition but should not be treated as the preferred path going forward.

### Ran

```bash
uv run pytest tests/test_reporting.py
uv run ruff check src/agentenv/reporting/markdown.py tests/test_reporting.py
uv run pyright src/agentenv/reporting/markdown.py tests/test_reporting.py
uv run agentenv report experiments/runs/dev_baseline --out experiments/reports/eval_matrices/dev_baseline.md
uv run agentenv report experiments/runs/dev_baseline --out experiments/reports/dev_baseline.md
uv run pytest
uv run ruff check .
uv run pyright
```

### Result

Expectation-table report refinement passed:

```text
canonical report: experiments/reports/eval_matrices/dev_baseline.md
control expectations: oracle/noop/public-tests-only all ON_TRACK
focused reporting tests: 3 passed
pytest: 74 passed
ruff: all checks passed
pyright: 0 errors
```

### Next Small Step

Either remove or ignore the transitional root-level report, then close the
remaining Week 4 limitations and learnings.

### Decision

Replay all control-patch policies as part of the full eval config run.

### Reasoning

Replay is part of the measurement-trust story, not just a report decoration.
The full matrix says the controls behaved correctly once; replay says the same
recorded control attempts are reproducible.

For Week 4, replay is scoped to control policies because `replay` currently
reruns recorded patch submissions. That contract is clear for deterministic
scripted controls:

```text
oracle
noop
public-tests-only
```

It should not silently claim model-agent replay semantics before the Week 5
agent/model loop exists.

### Shipped

- Added `--replay-control-policies` for `agentenv eval --all-policies`.
- Full matrix runs now write replay artifacts under:

```text
experiments/runs/dev_baseline/replays/<policy>/
```

- `eval_matrix_manifest.json` now records replay summaries:

```text
policy
status
attempt_count
matched_attempts
mismatched_attempts
error_count
replay_result
```

- Eval matrix reports now include:
  - replay scope,
  - aggregate replay match rate,
  - per-policy replay checks.

### Ran

```bash
uv run pytest tests/test_eval_run.py tests/test_reporting.py
uv run ruff check src/agentenv/orchestrators/eval_run.py src/agentenv/cli.py src/agentenv/reporting/markdown.py tests/test_eval_run.py tests/test_reporting.py
uv run pyright src/agentenv/orchestrators/eval_run.py src/agentenv/cli.py src/agentenv/reporting/markdown.py tests/test_eval_run.py tests/test_reporting.py
uv run agentenv eval --config configs/eval/dev_baseline.yaml --all-policies --replay-control-policies --out experiments/runs/dev_baseline
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_baseline").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
uv run agentenv report experiments/runs/dev_baseline --out experiments/reports/eval_matrices/dev_baseline.md
uv run agentenv report experiments/runs/dev_baseline --out experiments/reports/dev_baseline.md
uv run pytest
uv run ruff check .
uv run pyright
```

### Result

Control-policy replay integration passed:

```text
durable matrix: policies=3 attempts=9 replays=3 HIDDEN_TEST_FAIL=6 PASS=3
replay scope: control_patch
replay match rate: 9/9
per-policy replay: oracle 3/3, noop 3/3, public-tests-only 3/3
trace validation: 24 trace files
focused tests: 9 passed
pytest: 75 passed
ruff: all checks passed
pyright: 0 errors
```

### Next Small Step

Close remaining Week 4 limitations and learnings. Hidden-validator file hashes
and structured task exclusions remain explicit report limitations.

### Closeout Docs

Removed the transitional root-level report:

```text
experiments/reports/dev_baseline.md
```

The canonical report path is:

```text
experiments/reports/eval_matrices/dev_baseline.md
```

### Shipped

- Added `docs/task_design_note_v0.md`.
- Added `notes/weekly/week_04/learnings.md`.

### Result

The task design note records:

```text
construct validity
what the suite measures
what it does not measure
control expectations
current weaknesses
non-claims
```

The Week 4 learnings record:

```text
task difficulty should come from behavioral contracts
hidden validators should verify visible semantics
controls are calibration evidence
replay is part of measurement trust
eval matrices are the right reporting unit for policy sets
```

### Next Small Step

Run final Week 4 verification.

### Ran

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run pytest
uv run ruff check .
uv run pyright
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/dev_baseline").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

### Result

Final Week 4 verification passed:

```text
task pack validation: valid repo_patch_python_v0 tasks=4
pytest: 75 passed
ruff: all checks passed
pyright: 0 errors
dev_baseline trace validation: 24 trace files
```
