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

## Preference Optimization Usually Refines A Supervised Policy

The conventional post-training sequence is:

```text
pretrained policy -> instruction SFT -> preference optimization
```

Pretraining supplies broad language and task knowledge. Instruction SFT first
teaches the interaction distribution: how to follow requests, use the expected
conversation or tool interface, and complete representative tasks. DPO or RLHF
then primarily changes which behaviors the policy prefers within that
distribution. Asking preference optimization to start from the raw pretrained
policy is possible, but it combines learning the interface with learning the
preference ordering and makes the source of any change harder to interpret.

For the usual DPO comparison, the frozen reference and trainable policy begin
as exact copies of the same SFT checkpoint:

```text
SFT policy
  -> frozen reference
  -> trainable policy updated by DPO
```

This makes the causal question narrow: what did preference optimization add
beyond this exact supervised policy? The SFT parent therefore owns part of the
meaning of the DPO result. If that parent was designated for an exploratory
run rather than selected by the declared evaluation rule, the result must be
reported as exploratory rather than retroactively treating the parent as a
selection winner.

## Pair Exposure And Token Exposure Answer Different Questions

A DPO preference pair is the atomic training judgment: one shared context, one
chosen continuation, and one rejected continuation. A first deterministic pass
can therefore give every judgment equal exposure by consuming every pair once.
Stopping at an arbitrary token threshold may instead cut through the declared
pair order and leave some judgments unseen.

Token totals are still necessary, but their denominator must be named. Full
chosen-plus-rejected sequence tokens describe logical model input and compute;
chosen-plus-rejected response tokens describe the positions scored by the DPO
objective. Neither count changes the weighting implied by summed response log
probabilities. Length normalization would be a different objective decision,
not something a token-budget schedule silently provides.

Equal pair exposure also does not imply equal context or task exposure when one
context generates several auditable pairs. That multiplicity belongs in the
reported data distribution unless a context-balanced objective is explicitly
declared before training.

## Evaluation Disjointness Follows The Whole Policy Lineage

A post-trained policy has inherited exposure as well as exposure from its most
recent optimization stage. A DPO policy initialized from an SFT checkpoint has
seen every task that shaped the SFT parent and every task represented in the
preference pairs actually consumed by DPO. Checking only the parent dataset, or
only the newest dataset, can therefore certify a contaminated evaluation as
disjoint.

This differs from requiring two compared policies to have identical training
task sets. Parent-versus-child comparison is intended to isolate an additional
training intervention, so the child will normally have a larger lineage. The
necessary invariant is that every evaluation task is outside every compared
policy's complete lineage. Matching task sets is appropriate only for
treatments whose data scope is supposed to match.

A reused evaluation matrix is not automatically reusable evidence after a new
training stage. Its task inputs may be byte-identical to the earlier matrix yet
overlap the new treatment data. Split validation must be rerun against the
actual consumed units whenever the policy lineage changes.

## Preference-Loss Progress Does Not Guarantee Policy Progress

A preference objective can move in its intended mathematical direction while
the resulting policy becomes less useful as an agent. Lower observed DPO loss,
positive reward margins, nonzero gradients, and exact checkpoint reloads prove
optimization and persistence mechanics. They do not prove that the model
grounds actions in the current task, terminates coherently, or preserves the
parent policy's useful behavior.

This risk is especially visible when a small policy operates inside a long
prompt containing illustrative actions. A preference update can sharpen a
high-probability but task-independent attractor, causing the model to copy
demonstration-shaped actions repeatedly. Schema validity and high tool-call
counts can then make a collapsed policy look active even though it ignores
observed filenames, writes placeholder content, and never terminates.

Same-path rollout evaluation is therefore part of validating preference
training, not an optional downstream polish step. Task success remains the
primary measure, while action diversity, grounding in tool observations,
placeholder copying, repeated-state actions, and termination are diagnostic
checks that explain a negative result without converting partial motion into
success.
