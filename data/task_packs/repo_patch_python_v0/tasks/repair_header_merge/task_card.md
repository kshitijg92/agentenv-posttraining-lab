# Task: repair_header_merge

## What It Measures

This task measures whether an agent can implement case-insensitive merge
semantics while preserving deterministic insertion order and validating an
input contract that the public example does not exercise.

## What It Does Not Measure

It does not measure HTTP protocol completeness, multi-value headers, network
clients, framework integration, or large-repository navigation.

## Human Solve Estimate

10-20 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect the seeded exact-key dictionary merge.
- Validate both inputs and detect case-insensitive duplicates per input.
- Index defaults by `casefold()` while retaining their order.
- Replace matching defaults in place with override spelling and values.
- Append unmatched overrides in override order and return a fresh dictionary.

## Public Check

The public check covers an exact-spelling replacement and a new key. The seed
passes it.

## Hidden Validator

The hidden tests cover mixed-case replacement, output ordering, duplicate and
type validation, and input immutability.

## Known Shortcuts

`dict.update` passes the public test but creates two keys when spellings differ
only by case and does not reject ambiguous inputs.

## Oracle Summary

The oracle validates ordered items, indexes defaults by normalized name, and
performs position-preserving replacement.

## Bad Control Summary

The no-op and public-only controls retain exact-key merge semantics, so they
pass the public example and fail hidden mixed-case behavior.

## Agent Control Summary

The task includes happy, malformed-output, and recoverable-tool-error scripts
using the same restricted tool loop as the other pack tasks.

## Flake Risks

Pure local Python with fixed mappings; no time, randomness, network, or
filesystem-state dependency.

## Provenance

Self-authored synthetic task. It contains no employer-private, proprietary, or
benchmark-heldout material.
