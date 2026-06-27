# Task: repair_jsonl_deduper

## What It Measures

This task measures whether a patch can repair a small data-cleaning utility with
a caller-supplied dedupe key, first-seen ordering semantics, and explicit input
validation.

It exercises reading a compact implementation, preserving a public behavior
that already works, and fixing hidden edge cases without changing the public
test.

## What It Does Not Measure

This task does not measure large-repo navigation, streaming IO, CLI design,
performance on large files, schema inference, distributed data processing, or
production JSONL pipeline reliability.

## Human Solve Estimate

10-20 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect `dedupe_jsonl(blob, dedupe_key)`.
- Notice that the seeded implementation ignores `dedupe_key` and hardcodes
  `"id"`.
- Parse each nonblank JSONL line as a JSON object.
- Raise `ValueError` for malformed JSON, non-object lines, or missing dedupe
  keys.
- Track first-seen key values and preserve the original line for each kept
  record.
- Return kept lines joined as JSONL with a trailing newline when nonempty.

## Public Check

The public test verifies that duplicate `"id"` values are removed and that the
first-seen record is kept.

The public test deliberately does not prove that arbitrary `dedupe_key` values
work or that invalid records raise `ValueError`.

## Hidden Validator

The hidden validator checks:

- caller-supplied dedupe keys other than `"id"`,
- first-seen order for non-adjacent duplicates,
- `ValueError` for missing dedupe keys,
- `ValueError` for malformed JSONL,
- `ValueError` for non-object JSON lines.

## Known Shortcuts

A patch can pass the public test by hardcoding `"id"` as the dedupe key. Hidden
tests reject this by deduping on `"email"` and `"request_id"`.

A patch can also pass the public test while allowing `KeyError`,
`JSONDecodeError`, or `TypeError` to escape. Hidden tests require `ValueError`
for invalid inputs.

## Oracle Summary

The oracle patch uses `dedupe_key`, validates that every parsed line is a JSON
object, raises `ValueError` for invalid records, tracks seen key values, and
preserves the original line for the first occurrence of each key value.

## Bad Control Summary

`bad_noop.patch` leaves the seeded implementation unchanged. It passes the
public test because the public case dedupes by `"id"`, but fails hidden tests
because the implementation ignores `dedupe_key` and raises the wrong exception
types.

`bad_public_only.patch` adds some public-test-oriented cleanup while still
hardcoding `"id"`. It passes the public test but fails hidden tests that use
other dedupe keys.

## Agent Control Summary

The task manifest indexes three agent-loop control scripts:

- `happy` -> `controls/agent_control_scripts/happy_path.json`
- `malformed` -> `controls/agent_control_scripts/malformed_json.json`
- `recoverable` -> `controls/agent_control_scripts/bad_tool_input_then_recovery.json`

`happy` scripts a valid read/write/test/final-answer path and should complete.
`malformed` emits malformed model JSON and should stop with
`invalid_model_output`. `recoverable` first emits invalid tool input, receives
an `InvalidToolInput` tool result, corrects the call, and should complete.

## Flake Risks

The task should be deterministic. It uses local pure-Python code, fixed JSONL
strings, no randomness, no wall-clock time, no network, and no filesystem state.

## Provenance

Self-authored synthetic task, created on a private machine. Does not use
employer-private, third-party-proprietary, or benchmark-heldout material.
