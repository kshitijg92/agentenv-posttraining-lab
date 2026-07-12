# Task: repair_query_encoding

## What It Measures

This task measures translating an explicit serialization contract into
deterministic ordering, repeated-value handling, validation, and correct
percent encoding.

## What It Does Not Measure

It does not measure URL parsing, HTTP requests, browser behavior, nested query
languages, security policy, or framework-specific conventions.

## Human Solve Estimate

10-20 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Validate a mapping with string keys.
- Distinguish scalar strings from finite sequences of strings.
- Sort keys but preserve per-key value order.
- Percent-encode keys and values with RFC 3986 space behavior.
- Emit repeated pairs and handle empty sequences and mappings.

## Public Check

The public check uses already sorted ASCII scalar values, which the seed
handles.

## Hidden Validator

The hidden tests cover key sorting, repeated values, encoding, Unicode, empty
inputs, and invalid key/value types.

## Known Shortcuts

Joining raw `key=value` strings passes the public case but fails encoding,
ordering, and multi-value semantics.

## Oracle Summary

The oracle validates through `Mapping` and `Sequence`, expands values, and uses
`urllib.parse.quote(..., safe="")` for both keys and values.

## Bad Control Summary

The no-op and public-only controls retain raw scalar joining.

## Agent Control Summary

The task carries the standard happy, malformed-output, and recoverable error
scripts.

## Flake Risks

Pure deterministic local serialization.

## Provenance

Self-authored synthetic task with no employer-private, proprietary, or
benchmark-heldout material.
