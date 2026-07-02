# Week 6 Implementation Notes

## 2026-06-30

### Shipped

- Added explicit split-lock checking through:
  - `src/agentenv/tasks/splits.py`
  - `agentenv tasks check-splits <splits.lock.json>`
- Refactored `validate_task_pack` to use the shared split-membership check
  instead of keeping duplicate split logic in `tasks/validate.py`.
- Encoded the first Week 6 split invariants:
  - task YAML `split` must match `splits.lock.json`;
  - a task cannot appear in more than one split;
  - every discovered task YAML must be assigned in `splits.lock.json`;
  - `splits.lock.json` cannot reference unknown task IDs;
  - duplicate task IDs in task YAMLs are rejected.

### Ran

```bash
uv run pytest tests/test_task_splits.py
uv run agentenv tasks check-splits data/task_packs/repo_patch_python_v0/splits.lock.json
uv run pytest tests/test_task_splits.py tests/test_task_manifest.py
uv run ruff check .
uv run pyright
git diff --check
```

### Result

```text
valid repo_patch_python_v0 tasks=4 practice=1 dev=3 heldout_private=0 public_calibration=0
```

Focused tests:

```text
tests/test_task_splits.py -> 6 passed
tests/test_task_splits.py tests/test_task_manifest.py -> 16 passed
```

Static checks:

```text
uv run ruff check . -> passed
uv run pyright -> 0 errors
git diff --check -> passed
```

### Failure Or Surprise

The core split membership logic already existed inside full task-pack
validation. The Week 6 change was to expose it as its own explicit boundary
with targeted tests and operator-facing CLI output, then make full task-pack
validation call that shared boundary.

### Decision

Start Week 6 with split enforcement before flake detection. This protects the
task/split boundary before running repeated controls or trajectory exports.

### Next Small Step

Add task hashing for instructions, visible tests, and task assets.

## 2026-06-30 Hashing Checkpoint

### Shipped

- Added task-pack hashing through:
  - `src/agentenv/tasks/hashing.py`
  - `agentenv tasks hash <task-pack> --out <report.json>`
- Added per-task hash records so eval subsets can later reference task identity
  at task granularity.
- Added pack-level hashes for:
  - `manifest.yaml`;
  - `splits.lock.json`;
  - aggregate `pack_record_hash`.
- Added per-task hashes for:
  - `task.yaml`;
  - normalized instruction text;
  - normalized visible tests;
  - each `required_task_files` entry from the pack manifest;
  - full task directory contents;
  - aggregate `task_record_hash`.
- Added `extra_task_files` to flag task-local files outside the declared
  required-file contract.
- Excluded volatile cache/build directories such as `__pycache__`,
  `.pytest_cache`, `.ruff_cache`, `.venv`, `build`, and `dist`.

### Ran

```bash
uv run pytest tests/test_task_hashing.py
uv run agentenv tasks hash data/task_packs/repo_patch_python_v0 \
  --out experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
uv run pytest tests/test_task_hashing.py tests/test_task_splits.py tests/test_task_manifest.py
uv run ruff check .
uv run pyright
git diff --check
uv run pytest -n auto
```

### Result

```text
hashed repo_patch_python_v0 tasks=4 pack_record_hash=xxh64:fb449de6b09683dc
wrote experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
```

Focused tests:

```text
tests/test_task_hashing.py -> 6 passed
tests/test_task_hashing.py tests/test_task_splits.py tests/test_task_manifest.py -> 22 passed
uv run pytest -n auto -> 355 passed
```

Static checks:

```text
uv run ruff check . -> passed
uv run pyright -> 0 errors
git diff --check -> passed
```

### Decision

Use exact byte hashes for task assets and directory contents. Use normalized
text hashes only for instruction text and visible tests.

Keep generated hash reports outside the task pack. The task pack remains the
source artifact; hash reports are derived evidence under `experiments/reports/`.

### Next Small Step

Run full checks, then decide whether to wire task hashes into eval manifests now
or continue with repeated-control flake detection.

## 2026-06-30 Eval Manifest Task Hashes

### Shipped

- Added inline selected-task hashes to eval manifests:
  - `run_manifest.json` for single-policy evals;
  - `eval_matrix_manifest.json` for all-policy eval matrices.
- Added `eval_task_hashes_v0` with:
  - `task_pack_id`;
  - `selected_task_hash_set`;
  - one selected task record per configured eval task;
  - both `required_task_files` and `required_task_files_hash` in each selected
    task record, matching the task-pack hash report shape for required inputs;
  - `full_task_dir_hash` for the broader task-local drift signal.
- Kept eval hashes selected-task scoped. Eval manifests do not include
  task-pack-level hashes, because adding an unused task should not invalidate an
  eval over an unchanged selected task set.

### Ran

```bash
uv run pytest tests/test_task_hashing.py tests/test_eval_run.py
uv run ruff check .
uv run pyright
git diff --check
uv run pytest -n auto
uv run agentenv eval \
  --config configs/eval/scorer_control_policies.yaml \
  --policy oracle \
  --out experiments/runs/task_hash_manifest_smoke \
  --overwrite
```

### Result

The smoke eval manifest contained:

```json
{
  "schema_version": "eval_task_hashes_v0",
  "selected_task_hash_set": "xxh64:5516e0988567c439",
  "selected_tasks": [
    {
      "full_task_dir_hash": "xxh64:1a569dd4b44a8af5",
      "required_task_files_hash": "xxh64:70419960e3a22949",
      "task_id": "toy_python_fix_001"
    }
  ],
  "task_pack_id": "repo_patch_python_v0"
}
```

Focused tests:

```text
tests/test_task_hashing.py tests/test_eval_run.py -> 26 passed
uv run pytest -n auto -> 357 passed
```

Static checks:

```text
uv run ruff check . -> passed
uv run pyright -> 0 errors
git diff --check -> passed
```

### Decision

Eval comparability is keyed by `selected_task_hash_set`, not by task-pack hash.

The standalone task-pack hash report can still include pack-level context, but
eval manifests should only inline the hashes of tasks actually selected by the
eval config.

### Next Small Step

Move to repeated-control flake detection.

## 2026-07-01 Eval Task Hash Comparison Helper

### Shipped

- Added an eval-layer helper that accepts either an artifact directory or a
  manifest JSON file.
- The loader distinguishes `eval_run_v0` (`run_manifest.json`) from
  `eval_matrix_v0` (`eval_matrix_manifest.json`) at the boundary.
- The comparison logic operates on the common `task_hashes` payload and returns
  semantic drift data:
  - overall `matched` or `drifted` status;
  - task-pack-id match;
  - selected-task-hash-set match;
  - selected task IDs added or removed;
  - selected tasks whose hashes changed;
  - required-task-file drift details when the manifest includes
    `required_task_files`.
- Exposed the helper through `agentenv eval compare-task-hashes`.
- The CLI prints a compact terminal summary and can optionally write the full
  structured comparison JSON with `--out`.
- Kept CLI code thin by moving comparison summary rendering into the helper
  module and using eval-orchestrator layer-count helpers for eval CLI status
  output.

### Design

Reports should eventually summarize the helper's status, not dump raw hashes.
Raw hashes stay in JSON manifests; Markdown can later say whether task input
provenance matched or drifted.

## 2026-07-01 Control Flake Detection Manifest

### Shipped

- Added manifest-only `flake_detection` to `control_run_manifest.json`.
- Added repeat artifact stability groups under `groups.scorer` and
  `groups.agent`.
- Each scorer `(task_id, control_name)` repeat group compares repeat 1..N
  against repeat 0.
- Each agent `(task_id, control_name)` repeat group compares repeat 1..N
  against repeat 0.
- Agent artifact comparison is dynamic based on the repeat-0 artifact surface:
  prompt-loop-only controls compare agent-level artifacts only; controls that
  reach scoring also compare nested `attempt/*` scorer artifacts. If later
  repeats add, remove, or change files relative to repeat 0, that is drift.
- The manifest stores per-file normalized hashes in `items_compared` and stores
  per-repeat drift details only for repeats that drifted.
- `control_report.md` includes a compact `Flake Detection` section with
  overall, scorer, and agent stability counts. It points to
  `control_run_manifest.json` for per-file hashes and drift details instead of
  dumping those details into the human report.
- `overall_match` now requires both:
  - every control record matches the expected semantic outcome;
  - `flake_detection.status` is `stable`.

### Normalization

Scorer artifact normalization includes all files in the scorer artifact
directory:

- `attempt.json`;
- `run_manifest.json`;
- `final.diff`;
- `stdout.txt`;
- `stderr.txt`;
- `error.txt`;
- `trace.jsonl`.

The normalizer removes or rewrites volatile evidence:

- run IDs and attempt IDs;
- timestamps;
- durations, model latency, and stdout/stderr byte counts;
- repo root paths;
- generated agentenv temp workspace paths;
- pytest temp paths, including pytest's ellipsized `...pytest-N` and
  `...ytest-N` path rendering.

The intent is to detect deterministic artifact drift without failing because of
expected run-local identifiers, paths, or timing.
