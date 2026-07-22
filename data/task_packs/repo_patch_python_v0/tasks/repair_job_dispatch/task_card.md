# Task: repair_job_dispatch

## What It Measures

This task measures repair of a graph-constrained scheduler. It combines input
normalization, cross-record validation, cycle detection, stable priority, wave
semantics, and capacity backfilling.

## Structural Complexity

Seven source files separate models, local validation, graph validation,
ordering, scheduling, report construction, and the public facade. A correct
local ordering function is insufficient if readiness or capacity state changes
at the wrong boundary.

## Human Solve Estimate

80-110 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Normalize the complete iterable without mutating caller-owned records.
- Validate local fields before checking graph-wide identity and dependency
  invariants.
- Detect cycles independently of scheduling progress.
- Snapshot completed jobs at wave start so a dependency cannot unlock its
  child in the same wave.
- Continue scanning after a non-fitting ready job to backfill remaining slots.

## Public Check

The public tests cover empty input, independent priority ordering, and a linear
dependency whose slot sizes force separate waves anyway. They do not expose
same-wave dependency leakage or backfill behavior.

## Hidden Validator

The hidden tests cover previous-wave readiness, capacity backfill, stable ties,
multi-level graphs, generator inputs, exact key sets, Python bool-as-int,
duplicate and malformed ids, unknown/self dependencies, cycles, full
prevalidation, non-mutation, and complete exactly-once scheduling.

## Known Shortcuts

Updating the completed set while a wave is still being assembled lets a child
run alongside its dependency. Breaking at the first job that does not fit
wastes capacity even when a later job fits. Converting jobs directly into an
id-keyed dictionary can silently erase duplicate ids.

## Controls

The public-only control fully repairs normalization and graph validation while
retaining the scheduler's same-wave readiness and first-nonfit defects. It
isolates scheduling semantics from input validation.

## Flake Risks

None expected; ties are resolved by explicit input position rather than hash or
set iteration.

## Provenance

Self-authored synthetic development task with no private or benchmark-derived
content.
