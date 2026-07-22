# Task: repair_retry_schedule

## What It Measures

This task measures numerical contract validation and overflow-safe iterative
computation. The intended result is simple, but the direct exponent formula can
raise or create non-finite intermediates before applying the cap.

## What It Does Not Measure

It does not measure wall-clock retries, jitter, asynchronous execution,
distributed backoff, sleeping, or probabilistic schedules.

## Human Solve Estimate

10-20 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Validate exact numeric and integer input categories.
- Convert accepted numeric inputs to finite floats.
- Build the schedule iteratively.
- Saturate at the cap before multiplication can overflow.

## Public Check

The public check uses small positive numbers where direct exponentiation works.
The seed passes it.

## Hidden Validator

The hidden tests cover zero attempts, immediate caps, unit multipliers,
overflow-scale values, booleans, non-finite values, invalid ranges, and
unrepresentably large integers.

## Known Shortcuts

A list comprehension using `multiplier ** i` passes the public example but can
overflow and accepts booleans as integers.

## Oracle Summary

The oracle validates float representability and uses a saturating recurrence
that never needs exponentiation.

## Bad Control Summary

The no-op keeps direct exponentiation. The public-only control validates only
the attempt count and retains overflow behavior.

## Agent Control Summary

The task includes happy, malformed-output, and recoverable-tool-error scripts.

## Flake Risks

Deterministic arithmetic with no time, randomness, network, or filesystem
dependency.

## Provenance

Self-authored synthetic task. It contains no employer-private, proprietary, or
benchmark-heldout material.
