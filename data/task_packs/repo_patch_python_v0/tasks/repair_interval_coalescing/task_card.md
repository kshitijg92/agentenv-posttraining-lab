# Task: repair_interval_coalescing

## What It Measures

This task measures validation, normalization before aggregation, and
non-mutation. The public example is already sorted, hiding the seed's dependence
on input order.

## What It Does Not Measure

It does not measure temporal types, open versus closed interval algebra,
floating-point endpoints, database range indexes, or interval trees.

## Human Solve Estimate

10-20 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Materialize and validate the finite iterable without mutating it.
- Convert valid pairs into fresh tuples.
- Sort by endpoints.
- Merge overlap and shared endpoints while preserving separate adjacent ranges.

## Public Check

The public check uses a sorted list with one shared endpoint. The seed passes it.

## Hidden Validator

The hidden tests cover unsorted and contained ranges, generators, zero-width
intervals, adjacency, input immutability, malformed pairs, booleans, and
reversed endpoints.

## Known Shortcuts

Merging in input order passes the public example but gives incorrect results for
unsorted data and excludes generic iterables.

## Oracle Summary

The oracle materializes validated tuples, sorts a fresh list, and applies one
deterministic merge scan.

## Bad Control Summary

The no-op preserves input-order assumptions. The public-only control adds a
list check but still skips sorting and full validation.

## Agent Control Summary

The task includes happy, malformed-output, and recoverable-tool-error scripts.

## Flake Risks

Pure deterministic data transformation with no time, randomness, network, or
filesystem dependency.

## Provenance

Self-authored synthetic task. It contains no employer-private, proprietary, or
benchmark-heldout material.
