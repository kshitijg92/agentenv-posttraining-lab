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
