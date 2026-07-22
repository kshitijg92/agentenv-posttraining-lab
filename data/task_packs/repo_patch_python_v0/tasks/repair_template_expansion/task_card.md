# Task: repair_template_expansion

## What It Measures

This task measures syntax-aware single-pass transformation. It exposes the
difference between parsing the source template and repeatedly replacing text in
an already modified result.

## What It Does Not Measure

It does not measure a general template language, conditionals, loops, nested
expressions, escaping beyond dollar signs, file rendering, or HTML safety.

## Human Solve Estimate

10-20 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Validate the mapping independently of which keys are referenced.
- Scan the original template left to right.
- Distinguish `$$` from `${name}` and reject all other dollar syntax.
- Append replacement strings without rescanning them.

## Public Check

The public check contains one known placeholder. The seeded repeated-replace
implementation passes it.

## Hidden Validator

The hidden tests cover literal dollars, escaped placeholder syntax, adjacent and
repeated placeholders, non-recursive replacement, malformed and unknown
placeholders, mapping validation, and input types.

## Known Shortcuts

Looping over mapping entries with `str.replace` passes the public example but is
order-dependent, recursively expands some replacement values, and cannot reject
unknown or malformed syntax.

## Oracle Summary

The oracle validates one ASCII identifier grammar and scans only the original
template, appending replacement values directly to the output buffer.

## Bad Control Summary

The no-op retains repeated replacement. The public-only control adds shallow
type checks but keeps its recursive and syntax-blind behavior.

## Agent Control Summary

The task includes happy, malformed-output, and recoverable-tool-error scripts.

## Flake Risks

Pure deterministic string processing with no time, randomness, network,
filesystem, or locale dependency.

## Provenance

Self-authored synthetic task. It contains no employer-private, proprietary, or
benchmark-heldout material.
