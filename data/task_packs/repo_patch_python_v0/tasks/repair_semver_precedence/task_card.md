# Task: repair_semver_precedence

## What It Measures

This task measures contract-driven parsing and multi-stage ordering where a
plausible lexical comparison passes the public examples but violates numeric
and prerelease precedence.

## What It Does Not Measure

It does not measure the complete SemVer specification, build metadata,
dependency solving, package registries, or third-party version libraries.

## Human Solve Estimate

15-25 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect the seeded lexical comparison.
- Parse and validate the deliberately narrow grammar.
- Compare numeric core components.
- Apply release and prerelease identifier precedence rules.
- Normalize the result to -1, 0, or 1.

## Public Check

The public check covers only versions for which lexical and numeric ordering
agree. The seed passes it.

## Hidden Validator

The hidden tests cover numeric ordering, release-versus-prerelease ordering,
mixed prerelease identifiers, malformed versions, large integers, and input
types.

## Known Shortcuts

String comparison and simple dot-splitting both pass the public check but fail
valid prerelease cases and strict validation.

## Oracle Summary

The oracle uses one anchored ASCII grammar, validates numeric prerelease
identifiers, and compares parsed components without converting the full version
to floats.

## Bad Control Summary

The no-op retains lexical ordering. The public-only control compares only
numeric core components and therefore fails prerelease behavior.

## Agent Control Summary

The task includes happy, malformed-output, and recoverable-tool-error scripts
using the restricted tool loop.

## Flake Risks

Pure local Python with no time, randomness, network, locale, or filesystem
dependency.

## Provenance

Self-authored synthetic task. It contains no employer-private, proprietary, or
benchmark-heldout material.
