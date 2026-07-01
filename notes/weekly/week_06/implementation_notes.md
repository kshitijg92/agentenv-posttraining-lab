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
  --out experiments/reports/repo_patch_python_v0_task_hashes.json
uv run pytest tests/test_task_hashing.py tests/test_task_splits.py tests/test_task_manifest.py
uv run ruff check .
uv run pyright
git diff --check
uv run pytest -n auto
```

### Result

```text
hashed repo_patch_python_v0 tasks=4 pack_record_hash=xxh64:fb449de6b09683dc
wrote experiments/reports/repo_patch_python_v0_task_hashes.json
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
