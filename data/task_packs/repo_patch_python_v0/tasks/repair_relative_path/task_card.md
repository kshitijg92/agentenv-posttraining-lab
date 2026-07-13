# Task: repair_relative_path

## What It Measures

This task measures component-wise normalization under a containment invariant.
It distinguishes syntactic normalization from unsafe cleanup such as stripping
an absolute-path prefix or preserving an escaping parent component.

## What It Does Not Measure

It does not measure symlink resolution, platform-native Windows paths,
filesystem permissions, archive extraction, or URL normalization.

## Human Solve Estimate

5-15 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect the seeded `normpath` shortcut.
- Validate the path representation before normalization.
- Process components with an explicit stack.
- Reject root escape and empty canonical results.

## Public Check

The public check covers dot and duplicate-slash cleanup. The seed passes it.

## Hidden Validator

The hidden tests cover parent resolution, root escape, absolute and backslash
forms, NUL bytes, trailing separators, empty results, and input types.

## Known Shortcuts

`posixpath.normpath(...).lstrip('/')` passes the public example but converts
absolute or escaping paths into apparently safe relative paths.

## Oracle Summary

The oracle validates forbidden representations first, then applies a small
component stack with a fail-closed root boundary.

## Bad Control Summary

The no-op preserves the unsafe shortcut. The public-only control adds shallow
type validation but still strips unsafe path prefixes.

## Agent Control Summary

The task includes happy, malformed-output, and recoverable-tool-error scripts.

## Flake Risks

Pure string processing with no filesystem, locale, network, randomness, or
time dependency.

## Provenance

Self-authored synthetic task. It contains no employer-private, proprietary, or
benchmark-heldout material.
