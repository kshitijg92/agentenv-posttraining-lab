# Task: repair_record_chunking

## What It Measures

This task measures generalizing list-oriented code to a one-shot iterable,
precise runtime validation, and simple collection ownership semantics.

## What It Does Not Measure

It does not measure asynchronous streams, unbounded iterators, distributed
batching, memory optimization, or concurrency.

## Human Solve Estimate

5-15 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Validate `size` without accepting booleans as integers.
- Materialize the iterable once while normalizing non-iterable errors.
- Slice the materialized values into fresh ordered chunks.
- Handle empty and short final chunks.

## Public Check

The public test uses a list and a positive size; the seed passes it.

## Hidden Validator

The hidden tests use a one-shot generator, empty input, invalid sizes,
non-iterables, and mutation checks for fresh chunk lists.

## Known Shortcuts

Calling `len` and slicing the original input passes the list-only public case
but fails for generators.

## Oracle Summary

The oracle validates the size, converts the input once under `try/except`, and
slices only the resulting list.

## Bad Control Summary

The no-op and public-only controls retain list-only behavior.

## Agent Control Summary

The standard happy, malformed-output, and recoverable-tool-error scripts are
included.

## Flake Risks

Pure deterministic collection processing.

## Provenance

Self-authored synthetic task with no employer-private, proprietary, or
benchmark-heldout material.
