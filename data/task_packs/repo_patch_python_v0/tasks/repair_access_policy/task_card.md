# Task: repair_access_policy

## What It Measures

This task measures multi-module contract repair across parsing, pattern
semantics, and decision precedence. It distinguishes validating a rule language
from evaluating already-valid rules.

## Structural Complexity

Four source files and roughly ten functions or methods participate. The public
facade is intentionally thin; meaningful repair requires following imports into
models, patterns, and the engine.

## Human Solve Estimate

35-55 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Trace the facade into rule parsing and pattern matching.
- Separate query-value validation from rule-pattern validation.
- Enforce exact rule keys, finite non-string axes, nonempty axes, and uniqueness.
- Match only complete colon-delimited prefixes.
- Validate the complete ruleset before evaluating any rule.
- Accumulate allow evidence while letting any applicable deny dominate.

## Public Check

The public tests cover exact allow, default deny, a global wildcard, and a
simple non-overlapping deny. They do not exercise overlapping rules, malformed
later rules, or prefix-boundary lookalikes.

## Hidden Validator

The hidden tests cover deny precedence in both orders, complete prefix segment
matching, global wildcards, generator rules, exact key sets, malformed axes,
duplicates, invalid effects and wildcard placement, invalid queries, full
prevalidation, empty rules, case sensitivity, and non-mutation.

## Known Shortcuts

Returning the first matching rule passes non-overlapping public examples but
makes policy meaning depend on order. Raw string prefix matching lets
`billing:*` match `billinger:read`. Evaluating before parsing all rules can hide
a malformed later rule behind an early allow.

## Controls

The public-only control repairs validation and colon-prefix matching while
retaining first-match-wins evaluation, providing a targeted negative control
for precedence.

## Flake Risks

None expected; evaluation is pure and order is explicit.

## Provenance

Self-authored synthetic development task with no private or benchmark-derived
content.
