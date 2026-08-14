# Week 10 Learnings

## Quality Must Be Judged At The Exact Training Unit

Trusted trajectory provenance is necessary but does not make every action in a
trajectory desirable to imitate. Harness audits, hidden-validator outcomes,
leakage checks, and source review establish that the evidence is trustworthy.
The quality decision must still inspect the exact behavior that will receive
positive loss.

For contiguous-prefix SFT, the relevant question is:

```text
Is every assistant action retained in this exact prefix suitable to reinforce?
```

Judging the original full trajectory is too coarse when the training example
ends earlier. Judging only the tokenized row is too late and mixes semantic
behavior quality with tokenizer-specific representation. The semantic source
unit should be reviewed first; tokenization should preserve that decision.

## Outcome Does Not Solve Step-Level Credit Assignment

A successful trajectory can contain unnecessary actions, while a failed
trajectory can contain several useful actions before its first mistake.
Whole-task outcome therefore cannot identify which actions deserve positive
supervision.

For a failed trajectory, a conservative positive prefix ends before the first
causal error:

```text
useful inspection -> useful diagnosis -> first bad action
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
eligible prefix
```

This does not convert the failed trajectory into a successful demonstration.
It recovers only the earlier actions whose observations and effects remain
defensible. If the first action is already bad, no nonempty positive prefix
exists.

## Efficiency Is A Causal Judgment, Not A Length Threshold

Fewer actions or fewer tokens do not automatically mean better agent behavior.
An additional action may reduce uncertainty, inspect a relevant contract,
establish a baseline, validate a repair, or diagnose a surprising result.

An action is safely rejectable only when removing it preserves:

```text
the information available to later decisions
the relevant workspace state
the coherence of the remaining trajectory
the evidence supporting the final outcome
```

Action and token counts are useful screening and reporting signals. They are
not sufficient labels. Optimizing them directly without preserving correctness
rewards premature stopping and skipped validation.

## Matched Example Counts Do Not Mean Matched Learning Exposure

SFT examples can differ substantially in the number of assistant tokens that
receive loss. Giving raw and filtered datasets the same number of examples or
epochs can therefore give them different optimization budgets.

The controlled comparison should match loss-bearing exposure:

```text
raw one-pass supervised tokens -> target training budget
filtered complete examples     -> repeated to approximately the same budget
```

Complete examples should remain intact even when exact equality is impossible.
Any overshoot, repeated-example count, and effective exposure ratio must remain
visible. Repetition is part of the filtering treatment, not a hidden nuisance.

## Task Success Must Dominate Efficiency During Policy Selection

The purpose of an agent policy is to solve tasks. Token and action efficiency
are secondary properties and must not compensate for lower task success.

A conservative deterministic selection rule is lexicographic:

```text
1. compare trusted task success
2. if the same tasks succeed, compare token consumption
3. if still tied, compare action consumption
4. otherwise abstain
```

Equal success counts on different task identities are not a clean efficiency
tie. The policies may have different capabilities, so an abstention is more
honest than aggregating incomparable token totals into a winner.

## Per-Record Eligibility Does Not Guarantee Completion Coverage

A diagnostic prefix can be locally correct and still be weak evidence for a
policy that must complete a task. Prefix review answers whether the retained
actions are safe to reinforce. It does not answer whether the dataset as a
whole contains enough state-changing actions, validation-after-change, and
successful termination behavior.

This distinction matters when many accepted prefixes stop after inspection or
before the observation that would determine the next action. Such examples can
teach navigation and diagnosis, but they provide no positive continuation
target from that final observation into a repair. Dataset review must therefore
audit both local action quality and population-level workflow coverage:

```text
inspect -> diagnose -> change state -> validate changed state -> finish
```

A public check that already passes on the seed workspace is especially risky.
If successful demonstrations associate `public PASS` with finishing, while
most other examples teach only inspection, the policy can learn the shortcut
`public PASS -> finish` without reliably learning that the required repair must
come first.

## Token Matching Does Not Fully Match Behavioral Influence

Matching supervised-token exposure controls an important training-budget
difference, but it does not make every behavior equally influential. With one
sequence per optimizer step and a mean loss over that sequence's supervised
tokens, a short diagnostic prefix and a long complete repair each cause one
optimizer update.

The dataset therefore needs at least two complementary audits:

```text
supervised-token mass by behavior type
optimizer-step and action-target frequency by behavior type
```

Long writes may dominate token mass while short inspection prefixes dominate
update frequency. Reporting only one view can hide a strong training-mixture
imbalance.

## Disjointness Is Not Difficulty Matching

Train/selection disjointness prevents direct task contamination. It says
nothing about whether the two task populations occupy a comparable difficulty
range. Task validity, source-file count, turn budget, and a passing oracle are
also not empirical difficulty measurements.

Difficulty calibration must happen before freezing policy selection, using a
declared reference policy or other outcome evidence that is independent of the
treatments being compared. An all-failure floor is still a valid experimental
result, but it cannot distinguish two potentially different policies.

## Partial Progress Is Diagnostic Evidence, Not Replacement Success

A failed attempt can still reveal whether a policy is moving through useful
phases of work. Relevant inspection, information-gaining tests, correct state
changes, validation after change, and coherent termination can be reported
separately. Repeated reads of unchanged state and repeated checks without an
intervening change are evidence of a loop rather than additional progress.

This qualitative decomposition helps explain failures and choose the next
experiment. It must not be turned into a post-hoc score that overrides the
predeclared task-success metric. Otherwise an agent that explores plausibly but
never repairs anything can be promoted over one that solves the task.

## A Shared Harness Can Be Fair Yet Insensitive

Using the same harness for every policy makes a comparison fair with respect to
the harness. It does not guarantee that the harness supplies useful feedback or
enough resolution for the policies being studied. A shallow public check that
passes the broken seed, a tight turn budget, a rigid action interface, and one
greedy rollout can combine with a small policy to produce floors or repetitive
behavior.

Hidden validators should not be weakened to rescue the score. Instead, retain
true task success, preserve the failure traces, and treat harness affordances
and task calibration as part of failure analysis. A negative result under a
limited harness is still useful when its claim is scoped to that exact setup.
