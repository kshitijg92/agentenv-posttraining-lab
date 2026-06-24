# Task: preserve_cli_error_codes

## What It Measures

This task measures whether a patch can preserve a small CLI contract across a
multi-function implementation. It requires understanding how JSONL loading,
record summarization, and CLI exit-code handling interact.

## What It Does Not Measure

This task does not measure large-repo navigation, streaming performance,
complex argument parsing, localization, shell portability, or production CLI
observability.

## Human Solve Estimate

15-30 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect the visible exit-code constants and function docstrings.
- Fix `load_jsonl(...)` so it validates JSON object records with string `id`
  and string `status`.
- Reject duplicate `id` values as invalid input.
- Keep `summarize_records(...)` focused on counting statuses.
- Update `main(...)` so usage errors, missing files, and invalid input preserve
  distinct exit codes.
- Avoid tracebacks for expected user and input errors.

## Public Check

The public test verifies the success path only: a valid JSONL file exits `0`,
prints a JSON object of status counts to stdout, and writes nothing to stderr.

## Hidden Validator

The hidden validator checks:

- missing input file exits `3`,
- malformed JSONL exits `4`,
- invalid record schema exits `4`,
- duplicate `id` exits `4`,
- missing CLI argument exits `2`,
- expected user/input errors do not print tracebacks,
- successful output is JSON and is compared structurally, not by key order.

The hidden validator does not require exact error-message wording.

## Known Shortcuts

A patch can pass the public test by preserving only the happy path and leaving
all expected errors collapsed to exit code `1`. Hidden tests reject that.

A patch can also pass the public test while ignoring `id` validation. Hidden
tests reject missing, non-string, and duplicate ids.

## Oracle Summary

The oracle patch validates each JSONL line, raises `FileNotFoundError` for
missing input files, raises `ValueError` for invalid input, counts status values,
and maps expected errors to the documented exit codes.

## Bad Control Summary

`bad_noop.patch` leaves the seeded implementation unchanged. It passes the
public success-path test but fails hidden tests because it collapses expected
errors to the wrong exit code and does not validate duplicate ids.

`bad_public_only.patch` fixes only the usage-error exit code. It still passes
the public success-path test but fails hidden tests for missing files and
invalid input.

## Flake Risks

The task should be deterministic. It uses local temporary files, subprocess CLI
calls, pure Python JSON parsing, no randomness, no network, and no wall-clock
assertions.

## Provenance

Self-authored synthetic task, created on a private machine. Does not use
employer-private, third-party-proprietary, or benchmark-heldout material.
