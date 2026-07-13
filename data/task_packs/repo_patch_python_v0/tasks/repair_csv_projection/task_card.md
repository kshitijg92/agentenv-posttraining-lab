# Task: repair_csv_projection

## What It Measures

This task measures whether an agent recognizes that delimiter-separated text
must be parsed according to a quoting grammar, while also enforcing tabular
shape and selection invariants omitted from the public example.

## What It Does Not Measure

It does not measure dialect inference, streaming large files, character-set
detection, dataframe libraries, or filesystem I/O.

## Human Solve Estimate

10-20 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Replace naive comma splitting with `csv.reader`.
- Validate the header, requested projection, and row widths.
- Select fields by requested column order.
- Serialize with `csv.writer` and a fixed line terminator.

## Public Check

The public check uses unquoted, rectangular CSV. The seed passes it.

## Hidden Validator

The hidden tests cover quoted commas and newlines, reordered projections,
header-only data, generators, malformed CSV, ragged rows, duplicate and unknown
columns, NUL bytes, and input types.

## Known Shortcuts

Splitting lines and commas passes the public example but corrupts quoted fields
and cannot validate CSV syntax reliably.

## Oracle Summary

The oracle parses strictly with the standard library, validates all rows and
column identities, and emits one canonical CSV representation.

## Bad Control Summary

The no-op keeps naive splitting. The public-only control adds shallow input
checks but still does not implement CSV quoting.

## Agent Control Summary

The task includes happy, malformed-output, and recoverable-tool-error scripts.

## Flake Risks

Pure deterministic standard-library parsing with no locale, time, randomness,
network, or filesystem dependency.

## Provenance

Self-authored synthetic task. It contains no employer-private, proprietary, or
benchmark-heldout material.
