# Task: repair_event_rollup

## What It Measures

This task measures repair of a staged data pipeline where validation order is
part of correctness. Parsing, exact decimal semantics, duplicate identity,
windowing, aggregation, and output order interact across module boundaries.

## Structural Complexity

Six source files divide data models, line parsing, timestamp parsing,
deduplication, aggregation, and orchestration. Several locally plausible fixes
remain globally wrong if stages run in the wrong order.

## Human Solve Estimate

65-90 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Trace the full pipeline rather than patching only the facade.
- Preserve exact decimal values from input through formatted output.
- Validate every line and compare all duplicate ids before window filtering.
- Distinguish identical duplicate replay from conflicting id reuse.
- Preserve first in-window user order while aggregating multiple events.

## Public Check

The public tests cover a small valid window, blank lines, and simple
credit/debit arithmetic. Their values are float-safe, contain no duplicates,
and already happen to be in alphabetical user order.

## Hidden Validator

The hidden tests cover high-magnitude decimal precision, duplicate collapse and
conflict, conflicts and malformed events outside the requested window, exact
window boundaries, first-appearance ordering, canonical timestamps, exact key
sets, malformed decimal grammar, and empty windows.

## Known Shortcuts

Converting through float appears correct for small values but loses cents at
large magnitudes. Filtering before deduplication hides conflicting ids outside
the window. Keeping the first event for every duplicate without comparing its
content turns corruption into silent data loss.

## Controls

The public-only control repairs exact parsing and deterministic aggregation but
retains first-wins duplicate handling and filters before deduplication. It is a
targeted negative control for pipeline-stage ordering and conflict detection.

## Flake Risks

None expected; no wall clock or locale-dependent behavior is used.

## Provenance

Self-authored synthetic development task with no private or benchmark-derived
content.
