# Task: repair_config_inheritance

## What It Measures

This task measures repair of a filesystem-backed configuration pipeline. It
combines recursive traversal, merge semantics, schema validation, path
containment, and cycle detection.

## Structural Complexity

Five source files separate public types, schema validation, merging, recursive
loading, and the facade. Correctness depends on preserving invariants across
all of those boundaries rather than repairing one local function.

## Human Solve Estimate

50-75 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Trace the facade through recursive loading, schema parsing, and finalization.
- Keep the containment root fixed while resolving includes relative to each
  including file.
- Distinguish active-recursion cycles from legal repeated includes.
- Merge nested sections field by field in the specified precedence order.
- Reject unknown keys and Python edge cases such as bool-as-int and non-finite
  JSON numeric constants.

## Public Check

The public tests cover defaults, a fully local document, and one direct include
whose sections do not overlap. They do not require recursion, containment,
cycle detection, or fieldwise merging.

## Hidden Validator

The hidden tests cover recursive relative includes, include and local
precedence, fieldwise section and label merging, cycles, path and symlink
escape, missing files, malformed JSON, exact key sets, numeric edge cases,
fresh outputs, and validation of every included document.

## Known Shortcuts

Loading only direct includes passes the public example. Shallow replacement of
`service`, `limits`, or `labels` silently loses inherited fields. Resolving an
include relative to the entry file instead of the including file breaks nested
trees, while changing the containment root at each level permits escape.

## Controls

The public-only control repairs recursive loading, containment, cycles, and
schema validation but retains shallow section replacement. It isolates the
fieldwise-merge requirement as a plausible hidden failure.

## Flake Risks

None expected. Tests create isolated temporary trees and compare deterministic
values.

## Provenance

Self-authored synthetic development task with no private or benchmark-derived
content.
