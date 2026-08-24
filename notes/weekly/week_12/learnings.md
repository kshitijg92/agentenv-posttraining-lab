# Week 12 Learnings

## A Negative Result Needs A Fully Named Experimental Boundary

"Did not improve" is meaningful only when its denominator and conditions are
attached. The task identities, split, scorer contract, model protocol, decoding,
rollout count, and selection rule define the observation. Removing those
conditions turns a limited result into an unsupported claim about an algorithm.

The durable reporting pattern is:

```text
observed comparison
+ exact experimental boundary
+ counterevidence
+ limitation
-> scoped decision
```

Here, the decision is abstention and no observed benefit. It is not equivalence
and not a claim that SFT or DPO is generally ineffective.

## A Zero Floor Is Evidence About The Experiment And Its Resolution

All-zero outcomes are not missing results. They show that the frozen primary
metric did not discriminate the compared policies. That observation can reject
an improvement claim, but it cannot estimate a useful effect size or show that
the policies are behaviorally identical.

Diagnostics such as public pass, patch production, tokens, actions, loops, and
prompt copying help explain the floor. They must not be promoted after the fact
into a replacement success metric. The correct response is to preserve the
failure and design a future calibration experiment with a predeclared target
range.

## Passing Controls Establish Measurement Trust, Not Difficulty Calibration

Oracle, known-bad, scripted-agent, replay, idempotency, flake, leakage, and
reward-hack controls answer whether authored harness behaviors match their
contracts. They reduce the chance that a known mechanical failure produced the
zeroes.

They do not answer whether a strict action protocol and task distribution are
well matched to a 3B model. A harness can be internally reliable, fair across
treatments, and still insensitive at the capability range being measured.

## Failed Controls Belong In The Final Evidence History

A final green aggregate is stronger when earlier gate failures remain visible.
The expanded-task diagnostic demonstrates that invalid task assets were blocked
before use. The intentional drift fixture demonstrates that the flake detector
can make a report fail. Omitting these failures would erase evidence that the
controls can reject bad state.

Historical reports should therefore be classified, not summed. Canonical,
superseded, diagnostic, duplicate-view, and intentional-negative artifacts have
different authority and must never inflate model or task denominators.

## Policy Lineage, Not The Last Dataset Name, Defines Contamination

A DPO child inherits every task that shaped its SFT parent and adds its own
preference-source tasks. Evaluation disjointness must follow that complete
lineage. Byte-identical evaluation tasks are still contaminated if any ancestor
or current treatment consumed them.

Correcting a contaminated matrix does not erase it. The first matrix remains
diagnostic evidence about the process failure; the corrected lineage-disjoint
matrix alone owns the efficacy claim.

## Artifact Economy Makes Final Claims Easier To Audit

A synthesis report should interpret existing manifests and records, not become
a second source of run identity. One final report, a working evidence map, a
closure audit, and durable learnings were sufficient. A report-bundle CLI or
separate claim schemas would have duplicated authority without changing the
supported result.

The README should expose the operator path and headline boundaries, while the
full report owns detailed interpretation. This division keeps both surfaces
useful without making either an accidental parallel database.

## The Next Experiment Should Target The Dominant Uncertainty

Another training run would be attractive but poorly diagnostic while the base
and every treatment remain at zero. The dominant uncertainty is whether the
evaluation has useful resolution between the toy task and the frozen selection
tasks under this protocol and base model.

The six-task calibration ladder is intentionally small. Its value comes from
freezing task bytes and stop rules before six natural-model attempts:

```text
2-4/6 PASS -> enough resolution for a later training comparison
0-1/6 PASS -> investigate protocol or base capability
5-6/6 PASS -> calibrate a harder construct
```

Choosing the redirect before observing the outcomes prevents task iteration or
metric reinterpretation from quietly converting development calibration into
heldout-looking evidence.
