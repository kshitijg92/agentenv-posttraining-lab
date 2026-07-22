# Heldout Evaluation Protocol

## Purpose

The heldout-private slice supports one narrow question:

```text
After the training and evaluation decisions are frozen, does the adapted policy
behave differently from its exact base policy on newly authored tasks that were
not used for training or iteration?
```

It does not by itself establish broad coding-agent generalization. Six tasks
provide task-level evidence and a weak directional estimate, not strong
statistical support.

## What Untouched Means

The task author and scorer maintainer may inspect task instructions, seed
workspaces, hidden validators, and controls before the slice is frozen. That is
required to establish that the tasks measure their declared contracts.

The evaluated natural-model policies must not see the hidden validators or
controls. More importantly, no natural-model outcome from this slice may be
used to change:

- training examples, labels, repairs, or filtering;
- the base checkpoint, tokenizer, adapter configuration, or training seed;
- prompts, tool schemas, action serialization, or system instructions;
- decoding parameters, turn/token budgets, or retry policy;
- task instructions, public checks, hidden validators, or scoring rules; or
- which base/adapted result is reported.

Authorship is not contamination. Outcome-dependent iteration is the relevant
contamination boundary.

## Pre-Freeze Calibration

Before freeze, the six tasks were exercised only with deterministic controls:

```text
oracle patches:             6/6 hidden PASS
no-op patches:              6/6 public PASS, hidden FAIL
public-only patches:        6/6 public PASS, hidden FAIL
happy agent controls:       6/6 hidden PASS
recoverable agent controls: 6/6 hidden PASS
malformed agent controls:   6/6 invalid model output
replay groups:              6/6 PASS, 0 mismatched attempts
public-check idempotency:   6/6 IDEMPOTENT at repeat_count=2
```

This calibration validates task and harness behavior. It does not consume the
slice's natural-policy measurement budget because scripted controls already
encode task-author knowledge and are not policies being compared.

The exact task hashes and local control evidence are pinned by:

```text
data/task_packs/repo_patch_python_v0/heldout_private.freeze.json
```

## Freeze Point

The freeze record contains six `heldout_private` task records and states that
zero natural-model attempts existed at freeze time. The repository test suite
recomputes those task hashes and fails if any frozen task byte, task manifest,
split assignment, or control-gate config drifts.

The freeze record also preserves the whole-pack and complete split-lock hashes
observed at the freeze point. Those are historical provenance, not a rule that
the development inventory can never grow. Current validation requires the
frozen heldout ID set and every frozen heldout task hash to remain exact. New
`dev` tasks may be added to the same task pack without refreezing or weakening
the heldout claim.

After freeze:

- task defects discovered before the natural-policy run may invalidate and
  replace the slice only if the freeze is explicitly abandoned and no model
  outcome has been observed;
- a defect discovered after a natural-policy outcome invalidates that task for
  the paired comparison; do not repair it and count a rerun as if untouched;
- harness bugs may be fixed, but the whole paired evaluation must be rerun from
  the pinned base and adapter under one new declared harness runtime; and
- additional tasks belong to a future heldout slice, not an expansion chosen
  after seeing this slice's results.

## Base And Adapter Timing

"Pre-training baseline" describes the base checkpoint, not necessarily the
wall-clock order in which evaluation is run. Inspecting base-model heldout
outcomes before finalizing training can contaminate model, data, prompt, or
hyperparameter decisions.

Preferred sequence:

1. freeze heldout task bytes;
2. freeze training data, tokenizer/serialization, adapter configuration, seed,
   prompt, decoding, and inference budgets;
3. complete training without inspecting heldout natural-model outcomes;
4. serve the exact base and adapted policies through the same provider path;
5. run both policies as one paired evaluation operation; and
6. inspect and report both results, including regressions and failures.

If the base policy is evaluated earlier for operational reasons, its results
must remain sealed and must not influence any later choice.

## Comparison Invariants

The paired run must hold constant:

```text
base checkpoint and tokenizer
provider and chat template
prompt and tool/action contract
decoding configuration and seed policy
turn, token, timeout, and retry budgets
task bytes and scorer runtime
```

The intended treatment difference is the trained adapter. If serving the base
and adapter requires different providers, quantization, templates, or action
translation, the result is confounded and must be reported as such.

## Permitted Claims

With six tasks, report exact task outcomes and paired changes. Acceptable
language is:

```text
Under this frozen six-task synthetic repo-patch slice and this exact runtime,
the adapted policy changed these task outcomes relative to its base policy.
```

Do not claim broad coding ability, benchmark improvement, stable population
effect, or general post-training benefit from this slice alone.
