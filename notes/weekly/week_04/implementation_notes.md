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
