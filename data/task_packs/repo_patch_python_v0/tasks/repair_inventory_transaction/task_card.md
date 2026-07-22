# Task: repair_inventory_transaction

## What It Measures

This task adds a multi-module transaction boundary. It measures whether a patch
can coordinate validation and state-transition logic while preserving atomicity,
ordering, aggregation, and non-mutation.

## Structural Complexity

Three source files and six named functions or methods participate. The primary
fix spans `inventory_validation.py` and `inventory_service.py`; the result
contract lives separately in `inventory_models.py`.

## Human Solve Estimate

25-40 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect the immutable result type and both validation helpers.
- Reject Python's boolean-as-integer edge case consistently.
- Materialize requests once and aggregate duplicate SKUs before availability.
- Validate all records and unknown references before computing a result.
- Preserve inventory order and first-request order in fresh dictionaries.
- Make failure atomic and report all shortfalls rather than the first one.

## Public Check

The public tests cover a unique-SKU successful reservation, one insufficient
request, basic invalid quantity handling, and non-mutation. They do not cover
duplicate request lines, multiple shortfalls, generators, or bool values.

## Hidden Validator

The hidden tests cover duplicate aggregation, aggregate-only insufficiency,
multiple shortfalls and ordering, malformed inventory and request shapes,
unknown SKUs, booleans, generators, empty inputs, complete prevalidation, fresh
result dictionaries, and input non-mutation on success and failure.

## Known Shortcuts

Checking each request line separately misses aggregate insufficiency. Building
a dict directly from request pairs keeps only the final duplicate. Mutating a
copy incrementally before discovering failure can return a partially applied
transaction.

## Controls

The no-op and public-only controls both pass the narrow public cases. The
public-only control improves boolean validation but deliberately retains
last-write-wins request normalization.

## Flake Risks

None expected. The task is a pure deterministic transformation.

## Provenance

Self-authored synthetic development task with no private or benchmark-derived
content.
