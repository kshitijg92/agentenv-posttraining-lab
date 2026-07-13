# Task: repair_duration_parser

## What It Measures

This task measures precise parsing of a small textual contract, unit
conversion, and consistent error normalization beyond a visible seconds-only
example.

## What It Does Not Measure

It does not measure natural-language duration parsing, localization, date/time
arithmetic, clocks, scheduling, or floating-point numerical analysis.

## Human Solve Estimate

10-15 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect the seeded suffix-only implementation.
- Define an exact full-string decimal grammar.
- Convert milliseconds, seconds, minutes, and hours to seconds.
- Reject whitespace, signs, exponents, malformed values, and non-strings.

## Public Check

The public check covers positive integer seconds, which the seed already
handles.

## Hidden Validator

The hidden tests cover all units, decimals, zero, invalid grammar, negative and
non-finite spellings, and non-string inputs.

## Known Shortcuts

Stripping a final `s` passes the public check while misparsing `ms` and ignoring
the remaining units and grammar.

## Oracle Summary

The oracle full-matches a narrow ASCII decimal regex and applies an explicit
unit multiplier.

## Bad Control Summary

The no-op and public-only patches retain seconds-only behavior.

## Agent Control Summary

Happy, malformed-output, and recoverable-tool-error scripts cover the standard
agent orchestration cases.

## Flake Risks

Pure deterministic string parsing with no external state.

## Provenance

Self-authored synthetic task with no employer-private, proprietary, or
benchmark-heldout material.
