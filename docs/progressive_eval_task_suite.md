# Progressive Python Repo-Patch Task Suite

## Purpose

This development-only suite creates a larger behavioral surface for model
evaluation, trajectory acquisition, positive-SFT review, and action-level
preference discovery. The six tasks live in the `dev` split of
`repo_patch_python_v0` because they share its domain, tools, scoring contract,
and artifact lifecycle.

The pack also contains a frozen heldout-private slice. That freeze protects the
exact heldout membership and task bytes, not the unrelated development-task
inventory. Whole-pack and split-lock hashes recorded at freeze time remain
historical provenance; adding dev tasks does not constitute a heldout refreeze.

The progression is structural rather than a claim of measured difficulty.
More functions, files, and interacting invariants usually increase navigation
and integration burden, but actual model difficulty must be established from
controlled runs rather than inferred from file count.

## Complexity Matrix

| Order | Task | Source files | Main interaction burden |
|---:|---|---:|---|
| 1 | `repair_alias_chain` | 1 | normalization, alias graph validation, deterministic resolution |
| 2 | `repair_inventory_transaction` | 3 | validation, duplicate aggregation, atomic state transition |
| 3 | `repair_access_policy` | 4 | rule parsing, segmented wildcards, deny precedence |
| 4 | `repair_config_inheritance` | 5 | recursive files, precedence, path containment, schema validation |
| 5 | `repair_event_rollup` | 6 | JSONL parsing, exact cents, deduplication, time filtering, aggregation |
| 6 | `repair_job_dispatch` | 7 | input normalization, dependency graph, capacity-aware deterministic waves |

The suite intentionally varies more than raw size:

- pure versus filesystem-backed behavior;
- independent validation versus cross-record invariants;
- immutable transformations versus transaction-like semantics;
- one-step outputs versus multi-stage pipelines;
- local precedence versus graph and scheduling constraints.

## Measurement Boundaries

Every task is in `dev`. Its traces may be inspected, used to tune prompts or
decoding, and considered for training after the ordinary eligibility and review
pipeline. Consequently, performance on these same tasks after training is an
in-distribution regression or memorization measurement, not an untouched
generalization claim.

The frozen `heldout_private` tasks remain unchanged in the same pack. This dev
slice does not duplicate, relabel, modify, or derive from them.

## Public And Hidden Checks

Public checks establish importability and a narrow happy path. They are not a
complete executable specification. The written task instruction is visible and
authoritative; hidden validators exercise additional cases already covered by
that contract, including malformed inputs, cross-record interactions,
non-mutation, ordering, and atomicity.

Each task includes:

- an oracle patch that passes public and hidden checks;
- an empty no-op control that passes the deliberately narrow public checks and
  fails hidden checks;
- a plausible public-only patch that passes public checks while violating a
  named hidden invariant;
- happy, malformed-output, and recoverable-tool-error agent controls.

Controls establish harness discrimination. They do not predict how a natural
model will distribute errors across the progression.

## Intended Use

Use the ordered task list to report per-task and per-complexity-band outcomes.
Do not collapse the suite immediately into one scalar: failures on a
single-file graph normalization task and a seven-file scheduler may have very
different implications for data construction and training.

For acquisition, retain exact task identity, model policy, decoding policy,
runtime provenance, and full trajectories. Repeated attempts can create useful
same-context alternatives, but task success alone does not authorize positive
SFT or determine a preference direction.

## Eval Configs

Three schedule-neutral configs make the suite usable at different checkpoints:

- `configs/eval/progressive_dev_controls.yaml` runs all six scorer controls and
  all three scripted-agent controls. It contains 36 primary attempts plus one
  replay per policy.
- `configs/eval/progressive_dev_acquisition.yaml` runs two sampled attempts for
  each task across seven local model sizes and families. Its 84 attempts are
  intended to create heterogeneous successful, failed, and partial
  trajectories for later review; the config does not imply that all listed
  models are equally capable or currently loaded.
- `configs/eval/progressive_dev_budget_matrix.yaml` compares greedy, ordinary
  sampling, and a high token/turn upper bound for three anchor models. Its 54
  attempts help distinguish task difficulty from a decoding-budget ceiling.

The acquisition and budget configs overlap deliberately but answer different
questions. Do not merge their rows without retaining policy, decoding, attempt,
and runtime provenance. A larger row count is not a larger number of independent
tasks.

## Calibration Evidence

The authored checkpoint was calibrated with two consecutive runs of every
scorer and scripted-agent control:

```text
records: 72
oracle: 12/12 expected PASS
no-op: 12/12 expected public PASS, hidden FAIL
public-only: 12/12 expected public PASS, hidden FAIL
happy agent: 12/12 completed and hidden PASS
recoverable agent: 12/12 completed and hidden PASS
malformed agent: 12/12 invalid model output
flake groups: 36 checked, 0 drifted
public-check idempotency: 6/6 IDEMPOTENT at repeat_count=2
```

This establishes deterministic harness discrimination for the authored
controls. It does not establish empirical natural-model difficulty, positive
training yield, preference-pair yield, or post-training improvement.
