# Week 2 Implementation Notes

## 2026-06-20

### Decision

Start Week 2 by building a config-driven eval runner around the existing Week 1
attempt path.

### Reasoning

Week 1 proved that one submitted patch can be applied, publicly checked, hidden
scored, and written to an artifact bundle. Week 2 needs to move one level up:
from "run this specific patch" to "run this named policy over this task set
under a recorded config."

The first useful runner does not need an LLM agent. It should run the current
control policies:

- oracle
- bad-noop
- bad-public-only

This gives replay and reporting a stable run directory to consume. Replay needs
a recorded attempt to reconstruct. Reporting needs a run-level manifest and
attempt summaries. Without that run-level wrapper, replay/reporting would be
coupled directly to ad hoc Week 1 command outputs.

### What This Step Should Prove

- A config can select the task set.
- A named policy can select the right control patch.
- The existing orchestrator still distinguishes oracle, no-op, and public-only
  behavior.
- Eval output has a run-level identity, not only per-attempt artifacts.

### Self-Deception Trap

Do not confuse running all control patches with evaluating a model. These are
calibration policies. Their job is to keep the measurement setup honest before
adding agents, more tasks, or training data.

### Next Small Step

Create a reusable eval config and an `agentenv eval` command that can run one
named control policy over `toy_python_fix_001`.

### Shipped

- Added `configs/eval/control_policies.yaml`.
- Added a config-driven eval-run orchestrator.
- Added `agentenv eval --config <config> --policy <policy> --out <run-dir>`.
- Added focused eval-run tests.

### Ran

```bash
uv run pytest tests/test_eval_run.py
uv run pytest
uv run ruff check .
uv run pyright
uv run agentenv eval --config configs/eval/control_policies.yaml --policy oracle --out experiments/runs/control_policies_oracle
uv run agentenv eval --config configs/eval/control_policies.yaml --policy bad-noop --out experiments/runs/control_policies_bad_noop
uv run agentenv eval --config configs/eval/control_policies.yaml --policy bad-public-only --out experiments/runs/control_policies_bad_public_only
```

### Result

- `oracle` produced `PASS`.
- `bad-noop` produced `HIDDEN_TEST_FAIL`.
- `bad-public-only` produced `HIDDEN_TEST_FAIL`.
- The top-level eval run now writes `run_manifest.json`.
- Per-attempt artifacts still live under nested attempt directories.
- `pytest`, `ruff`, and `pyright` pass.

### Failure Or Surprise

Running `uv` inside the managed sandbox could not write to `/home/kshitij/.cache/uv`.
The tests and CLI were rerun with sandbox approval for `uv` commands.

`pyright` initially scanned task fixtures under `data/` and failed on imports that
are only valid inside prepared task workspaces. This exposed a repo-boundary
issue, so `pyright` is now scoped to `src` and `tests`.

### Decision

Use week-agnostic artifact names for reusable repo objects. The learning plan
can say "Week 2", but code and configs should use durable names such as
`control_policies`.

Scope static type checking to lab code and tests, not task-pack fixture code.
Task packs are eval data whose imports may only resolve inside prepared
workspaces.

### Refactor

The first eval-run implementation put config schema, loading/path validation,
and execution in `orchestrators/eval_run.py`. That worked, but it violated the
same separation used for task manifests.

The eval config code was first split into schema/validate/orchestrator, but
`evals/validate.py` still contained too much resolver logic. That blurred the
same boundary that `tasks/validate.py` keeps clear.

The eval config code is now split as:

```text
src/agentenv/evals/schema.py
  Pydantic config shape

src/agentenv/evals/validate.py
  YAML loading and validate_eval_config_paths(...)

src/agentenv/evals/resolve.py
  task-pack resolution, task id resolution, policy selection, control patch
  resolution

src/agentenv/orchestrators/eval_run.py
  eval lifecycle and artifact writing
```

This keeps the orchestrator focused on running attempts, not defining or
validating config formats. It also makes config validation an explicit phase
instead of something that happens accidentally while resolving runtime objects.

### Attempt Persistence Boundary

The direct attempt CLI and eval runner both need the same operation:

```text
run one patch attempt, then persist its artifact bundle
```

Instead of duplicating that sequence at both call sites, I added:

```text
src/agentenv/orchestrators/attempt_runner.py
  run_and_persist_patch_attempt_to_dir(...)
```

The split is now:

```text
attempt.py
  execute one patch attempt and return AttemptRun

attempt_io.py
  write AttemptRun artifacts

attempt_runner.py
  compose execution plus persistence for operator/eval paths
```

This avoids making `attempt.py` depend on artifact writing while also keeping
`attempt_io.py` from owning execution.

### Replay Python Slice

Before implementing replay, I clarified the design:

- Replay consumes an eval run artifact directory, not an eval config.
- Replay should reject replay artifacts as input.
- Top-level replay statuses are `PASS`, `MISMATCH`, and `REPLAY_ERROR`.
- Per-attempt comparisons check:
  - `status`
  - `public_status`
  - `hidden_status`
  - `error_class`
  - `final_diff_hash`
- Replay writes fresh attempt artifacts so mismatches are auditable.

The first Python-only replay module now lives in:

```text
src/agentenv/replay/runner.py
```

It writes:

```text
replay_manifest.json
replay_result.json
replay_results.jsonl
trace.jsonl
attempts/
```

The first example replay was generated at:

```text
experiments/replays/control_policies_oracle/
```

Result:

```text
PASS
```

The important boundary is that `replay_results.jsonl` is not the process trace.
It is the per-attempt comparison record. The replay process trace is
`trace.jsonl`.

I initially wrote source and replay attempt artifact directories as identical
relative paths, which was confusing when reading `replay_results.jsonl` alone.
The comparison records now include both:

```text
*_artifact_ref
  relative path inside the source or replay bundle

*_artifact_path
  absolute local path for direct inspection
```

The replay attempt directory still mirrors the source attempt directory under a
different root. This keeps source/replay pairing obvious without adding extra
suffixes to attempt directory names.

### Replay CLI

Added a thin CLI wrapper around the Python replay function:

```bash
uv run agentenv replay experiments/runs/control_policies_oracle --out experiments/replays/control_policies_oracle
```

The CLI does not implement replay logic. It calls `run_replay(...)`, prints the
top-level replay status, and points to `replay_result.json`.

Example result:

```text
PASS attempts=1
```
