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

## Deterministic Evaluation Improves Comparability, Not Confidence

Greedy decoding with one rollout per task removes sampling variation from the
initial comparison and makes paired failures easier to inspect. It does not
establish robustness across generation samples, training seeds, or nearby
decoding settings.

The valid claim is narrow:

```text
under this frozen deterministic protocol, these policies produced these paired
task outcomes
```

A one-task advantage on a small development set remains fragile even when the
selection rule was declared in advance. It is evidence for choosing the next
policy to study, not broad evidence of model improvement.

## Filtering Concentration Should Be Reported, Not Corrected Post Hoc

Quality rejections may cluster by task, source policy, or behavior type.
Changing individual decisions to balance those groups would make the rubric
outcome-dependent and hide what the filter actually selected.

Preserve the decisions, then report:

```text
which tasks and policies lost examples
how much supervised-token mass was removed
whether raw and filtered task support stayed comparable
where repeated exposure became concentrated
```

Concentration is part of the treatment and its limitations. It should inform
interpretation, not retroactively rewrite the labels.
