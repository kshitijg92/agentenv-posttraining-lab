# Task: repair_alias_chain

## What It Measures

This is the smallest task in the progressive pack. It measures whether a patch
can coordinate normalization, graph validation, and ordered resolution across
three functions in one module. The difficult cases are relational: an alias can
target another alias, and normalization can create collisions not visible in
the raw strings.

## What It Does Not Measure

It does not measure filesystem navigation, multi-module integration, network
behavior, persistence, or large-codebase search.

## Human Solve Estimate

15-25 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect all three public functions rather than patching only the final facade.
- Centralize the visible ASCII normalization contract.
- Materialize and validate canonical and requested iterables once.
- Validate the entire alias graph before returning an index.
- Resolve transitive targets with explicit missing-target and cycle detection.
- Preserve the specified insertion and request order without mutating inputs.

## Public Check

The public tests cover already-normalized canonical names, direct aliases, and
duplicate-preserving request order. They do not exercise transitive aliases or
normalization collisions.

## Hidden Validator

The hidden tests cover ASCII trimming and lowercase normalization, generators,
transitive chains, missing targets, cycles, normalized duplicate canonicals,
alias/canonical and alias/alias collisions, malformed mappings and iterables,
request validation, insertion order, and non-mutation.

## Known Shortcuts

One-hop resolution passes the public examples but fails transitive chains.
Lowercasing without validating after trimming misses malformed and empty names.
Using a set for canonical names loses the required order.

## Controls

The oracle implements full graph validation. The no-op passes the narrow public
examples but fails hidden normalization and chain cases. The public-only patch
adds normalization but intentionally retains one-hop resolution.

## Flake Risks

None expected. The task is pure Python with no clock, randomness, subprocess,
filesystem, or network dependency.

## Provenance

Self-authored synthetic development task. It contains no benchmark-heldout,
frozen-heldout, employer-private, or third-party-proprietary material.
