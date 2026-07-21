# Overall Action Preference Rubric v0

```text
rubric_id: overall_action_preference
rubric_version: overall_action_preference_v0
adjudication_scope: overall_action_preference
```

## Purpose And Unit Of Judgment

Compare exactly two assistant actions that were actually observed under the
same model-visible context and canonical workspace state.

The judgment is local:

```text
shared decision context C
alternative action A
alternative action B
```

Complete source rollouts are supporting evidence about what followed each
action. They are not themselves the chosen and rejected training units.

Repaired, edited, or otherwise synthetic actions are outside this rubric's v0
scope.

## Priority Order

Apply these priorities in order:

1. Preserve or improve the likelihood that the continuation policy can solve
   the task correctly.
2. Only when both actions satisfy priority 1, prefer the action that enables a
   more efficient continuation.

Efficiency must not outweigh credible evidence that an action makes task
success less likely.

## Action Properties

An action is affirmatively useful when the reviewer can explain from context
`C` how it does at least one of the following:

- obtains task-relevant information that is not already available;
- makes a task-relevant workspace or environment change;
- performs justified validation;
- reports or terminates appropriately given the available evidence;
- otherwise preserves or advances a concrete path toward solving the task.

An action is entirely unnecessary when, given context `C`, it adds no new
task-relevant information, state change, validation, or justified termination
and does not preserve a necessary path toward solving the task.

An action hampers continuation when an action-level causal explanation shows
that it reduces expected task solvability or needlessly increases the work,
tool budget, turn budget, execution risk, or recovery burden of a continuation
that would otherwise remain viable.

Uncertainty about whether an action was necessary or hampering is not evidence
that it was.

## Evidence Rule

Every `preferred` decision requires a nonempty action-level explanation grounded
in context `C`.

Downstream rollout evidence may support that explanation, but terminal task
success, task failure, or reward alone must never determine the preference.
Later actions, observations, and different continuation policies can explain a
terminal outcome without establishing that the compared action caused it.

Reviewers must not use hidden validators, private evaluator information, or
other information unavailable at the original decision boundary as a reason
that an action was better.

## Decisions

### `preferred`

Select exactly one source alternative only when an action-level explanation
establishes one of these cases:

- one action is affirmatively useful and the other is entirely unnecessary;
- one action preserves task solvability and the other hampers it;
- both actions preserve task solvability, but one clearly enables a more
  efficient continuation without introducing a worse correctness or execution
  risk.

Do not choose the lesser of two flawed actions. If neither action is
affirmatively acceptable, use `ambiguous`.

### `tie`

Use `tie` only when both actions are affirmatively acceptable and sufficient
evidence supports that neither is materially better under the priority order.
A tie is a confident equivalence judgment, not missing information.

### `ambiguous`

Use `ambiguous` when the comparison is structurally valid but a defensible
direction is unavailable, including when:

- both actions are flawed;
- neither action is affirmatively justified from context `C`;
- evidence is insufficient or conflicting;
- causal attribution from the actions to rollout outcomes is unclear;
- an efficiency advantage may come with reduced task solvability;
- both actions may be acceptable, but equivalence is not established strongly
  enough for `tie`.

### `invalid`

Use `invalid` when the comparison contract is broken rather than merely hard to
judge, including mismatched decision contexts, identical actions, missing or
corrupt source evidence, or provenance that cannot be validated.

## Examples

### Useful action versus unnecessary repetition

The context already contains a successful `read_file` result and unchanged
workspace state. One alternative immediately repeats the exact same call; the
other performs a justified next diagnostic action. Prefer the next diagnostic
action when its usefulness can be explained from `C`.

### Different outcomes without local attribution

One source rollout eventually succeeds and the other fails, but both compared
actions were reasonable and the later continuations diverged substantially.
Do not infer a preference from the terminal outcomes. Return `tie` only with
evidence of equivalence; otherwise return `ambiguous`.

### Both actions are flawed

One action performs a wasteful tool call and the other makes a poorly justified
workspace edit. Even if one appears less damaging, return `ambiguous`; this v0
rubric does not create lesser-of-two-flawed-actions preferences.

### Clear efficiency difference between viable actions

Both actions preserve a justified route to solving the task. One obtains the
needed evidence directly, while the other requires additional redundant steps
without adding information or reducing risk. Prefer the direct action only when
the efficiency claim is supported without lowering expected task success.
