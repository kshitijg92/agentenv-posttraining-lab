# Task Authoring Checklist

Use this checklist before adding any task to a baseline.

## Required Files

Each task directory must contain:

```text
task.yaml
task_card.md
workspace_seed/
hidden_tests/
controls/oracle.patch
controls/bad_noop.patch
controls/bad_public_only.patch
```

## Task Shape

- The task is in the `repo_patch_python` domain.
- The task has one focused behavioral bug.
- The intended fix is small enough for a strong engineer to solve in roughly
  10-30 minutes.
- The seed workspace is self-contained and local.
- The public test is useful but incomplete.
- The hidden validators check behavior not proven by the public test.
- The task does not need network access, external services, wall-clock timing,
  randomness, or host-specific paths.
- The task is not a broad refactor, multi-service integration, or architecture
  cleanup.

## Manifest Checks

`task.yaml` must specify:

- stable task id,
- domain,
- split,
- instruction,
- workspace seed path,
- allowed tools,
- public checks,
- hidden validators,
- scoring primary,
- limits,
- controls,
- replay capture,
- leakage canary.

Manifest paths must be relative to the task directory and must not escape it.

The split must match `splits.lock.json` once the split lock exists.

## Instruction Checks

- The instruction states the desired behavior clearly.
- The instruction does not mention hidden tests, controls, canaries, or private
  evaluator files.
- The instruction gives enough information for a human to solve the task without
  seeing hidden validators.
- Hidden tests do not introduce requirements that contradict or materially
  extend the instruction.

## Public Check Checks

- Public checks run with the command declared in `task.yaml`.
- Public checks pass under the oracle patch.
- Public checks pass under the public-only bad patch.
- Public checks do not reveal all edge cases.
- Public checks do not depend on test order, network, time, randomness, or
  external state.

## Hidden Validator Checks

- Hidden validators pass under the oracle patch.
- Hidden validators fail under the no-op bad patch.
- Hidden validators fail under the public-only bad patch.
- Hidden validators are deterministic.
- Hidden validators live outside `workspace_seed/`.
- Hidden validators are not copied into the prepared agent workspace.
- Hidden validators check the actual behavior the task claims to measure.

## Control Checks

Expected control outcomes:

```text
oracle -> PASS / PASS / PASS
bad.noop -> HIDDEN_TEST_FAIL / PASS / FAIL
bad.public_only -> HIDDEN_TEST_FAIL / PASS / FAIL
```

For each task, run or include in repeated control calibration:

```bash
uv run agentenv attempt run --task-manifest <task>/task.yaml --submission <task>/controls/oracle.patch --out <out>
uv run agentenv attempt run --task-manifest <task>/task.yaml --submission <task>/controls/bad_noop.patch --out <out>
uv run agentenv attempt run --task-manifest <task>/task.yaml --submission <task>/controls/bad_public_only.patch --out <out>
```

Then run the pack-level repeated controls before including the task in a
baseline report.

## Task Card Checks

`task_card.md` must include:

- what the task measures,
- what it does not measure,
- human solve estimate,
- expected meaningful steps,
- public check summary,
- hidden validator summary,
- known shortcuts,
- oracle summary,
- bad control summary,
- flake risks,
- provenance statement.

The provenance statement must say whether the task is self-authored or identify
its source, and must state that it does not use employer-private,
third-party-proprietary, or benchmark-heldout material.

## Exclusion Checks

Exclude or block the task if:

- the oracle fails,
- either bad control passes,
- a bad control fails for the wrong reason,
- hidden validators leak into the workspace or artifacts,
- the instruction is ambiguous,
- results are flaky under repeated controls,
- the task requires external state,
- the hidden tests are doing the real specification work.

Write the blocker in notes with the task id, command, observed result, and
decision.

## Ready For Baseline

A task is ready for a baseline only when:

- all required files exist,
- the manifest validates,
- the task card is complete,
- oracle passes,
- no-op fails hidden validation,
- public-only fails hidden validation,
- repeated controls are stable,
- the task split is recorded,
- known limitations are written down.
