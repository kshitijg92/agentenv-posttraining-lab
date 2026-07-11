# Week 9 Learnings

## Purpose

This file records durable eval and post-training lessons from Week 9. It should
explain why a data boundary, eligibility rule, loss policy, leakage constraint,
or self-deception trap matters. Routine implementation details belong in
`implementation_notes.md` instead.

## 2026-07-09

### A Harness-Clean Trajectory Is A Candidate, Not Yet A Training Example

A trajectory that completes without an orchestration error has interpretable
evidence. That makes it eligible for downstream classification, but it does not
determine how the trajectory may be used.

The same harness-clean trajectory may become:

```text
positive SFT data
negative or adversarial data
one side of a preference pair
analysis-only evidence
```

Task success is one input to that decision, not the decision itself. A passing
trajectory can still be unsuitable because of leakage, reward hacking, an
ineligible split, weak provenance, poor trajectory quality, or an unauditable
comparison basis. A failed trajectory may still contain useful failure
evidence without being behavior that should be imitated.

The durable boundary is:

```text
valid source trajectory -> objective-specific eligibility -> constructed
training example
```

### Evidence And Data-Use Decisions Are Different Layers

Evidence describes what happened. Versioned assessments interpret that
evidence. Data-use eligibility decides what a declared policy permits, and a
dataset transformation decides what the trainer will actually consume.

These layers should not silently substitute for one another. In particular, a
derived success or quality signal is not itself permission to train, and an
eligibility decision does not describe the exact tokens or pairs that will
receive loss.

The durable distinction is:

```text
evidence and derived assessment -> what happened and how it was measured
data-use eligibility            -> whether a downstream use is permitted
dataset transformation          -> what the training objective consumes
```

Duplicating one policy decision at multiple stages creates competing sources of
truth. They can drift or let a downstream consumer select whichever answer is
convenient. A trustworthy pipeline should preserve evidence across stages while
keeping the authority for each decision unambiguous.

### An SFT Loss Mask Defines Which Behavior Is Imitated

All transcript tokens may be present as model context, but only selected token
positions need to contribute to the SFT loss.

For an agent transcript:

```text
system and user tokens      -> context, normally no loss
assistant tool-call tokens  -> possible imitation targets
tool-observation tokens     -> context, normally no loss
assistant final response    -> possible imitation target
```

Masking a token out does not remove it from the context. It prevents that token
from directly contributing a next-token cross-entropy gradient.

This distinction matters because tool observations are produced by the
environment, while tool calls are produced by the policy. Training the model to
imitate environment output would blur the actor/environment boundary.

### Standard SFT Does Not Give Negative Pressure To A Bad Action

Ordinary SFT increases the likelihood of every loss-bearing target token.
Masking an undesirable action gives it zero direct pressure; it does not teach
the model that the action was bad. Applying ordinary SFT to a raw failed
transcript can therefore teach the failure even when the row carries a
`success=false` label, because standard cross-entropy does not interpret that
metadata as a negative target.

A negative signal requires an objective that consumes negative evidence, such
as:

```text
a chosen/rejected preference objective
an explicit unlikelihood or contrastive objective
a reward or value model followed by policy optimization
an auxiliary action-quality classifier used for selection or optimization
```

Simply assigning a negative weight to normal cross-entropy is not a safe
default. It can create an unstable, unbounded objective and can penalize common
syntax tokens rather than the undesirable behavior.

### Negative Supervision Should Match The Semantic Action Boundary

An unnecessary tool call is an action-level error, not usually a token-level
error. Penalizing individual JSON tokens such as `read_file` can suppress valid
uses of the same tool in other contexts or teach superficial serialization
changes rather than better decisions.

A more informative comparison branches from the same transcript prefix:

```text
chosen:   the useful next action or justified termination
rejected: the unnecessary tool call
```

Keeping the prefix and downstream task outcome comparable makes the preference
basis auditable. Comparing two unrelated full trajectories creates confounds:
the pair may differ in correctness, length, formatting, recovery behavior, and
tool cost, so the learner cannot tell which difference justified the label.

### Outcome Labels Do Not Solve Credit Assignment

A trajectory-level PASS or FAIL does not identify which individual actions were
good or bad.

```text
a successful trajectory may contain wasteful actions
a failed trajectory may contain several useful actions before one bad decision
```

This is why a full transcript can be valuable outcome evidence without every
assistant span being a valid SFT target. Selective SFT needs step-level quality
judgments or a repaired target. Preference or reward-based objectives need an
auditable basis that connects the outcome to the compared behavior.

### Efficiency Rewards Create A Reward-Hacking Surface

Tool cost, latency, or action count can provide negative pressure against
unnecessary calls, but they must remain subordinate to trusted task success. A
policy rewarded too strongly for using fewer tools can learn to stop early,
skip validation, or submit no-op patches.

The self-deception trap is:

```text
lower tool usage != better agent behavior
```

An efficiency comparison is meaningful only when correctness and other safety
gates remain satisfied. Valid controls should include both an efficient correct
trajectory and behavior that saves cost by failing to do necessary work.

### Controls Calibrate Measurement; They Do Not Define Perfection

Oracle patches and scripted happy-path controls prove that the task is
solvable, the scorer accepts correct behavior, and the harness can execute the
intended lifecycle. They do not prove that the control's exact action sequence
is the unique or optimal way to solve the task.

Treating every deviation from a control as negative would collapse two
different concepts:

```text
control mismatch
behavioral error
```

A real agent may need to inspect files, reduce uncertainty, recover from a
mistake, or validate an alternative repair. A scripted control can skip that
exploration because its author already knows the solution. **Penalizing every
extra action would reward imitation of the control's privileged path rather
than good problem-solving under uncertainty.**

The conservative boundary is:

```text
different from control != bad
demonstrably dominated under trusted evidence -> possible negative preference
uncertain quality -> analysis only
```

This distinction also protects provenance. Current scripted controls are
harness-calibration evidence, not automatically model-training data. Promoting
one into a chosen training response would require a deliberate contract for
human- or script-authored demonstrations and a compatible policy-output
serialization.

### Negative Labels Require Stronger Evidence Than Positive Eligibility

It is often easier to prove that a trajectory is valid and successful than to
prove that one of its actions was unnecessary. A successful trace can contain
reasonable exploratory actions that happen not to affect the final patch.
Hindsight alone does not show that the action was irrational when it was taken.

Negative efficiency labels should therefore be limited to behavior with an
auditable comparison basis, such as mechanically redundant actions in a
deterministic state or two otherwise comparable successful trajectories where
one is clearly dominated. If the evidence does not isolate the undesirable
difference, the safer data-use decision is to leave the behavior unlabeled.

The self-deception trap is:

```text
the control used fewer actions, therefore every additional action was waste
```

This would create precise-looking preference data whose labels actually encode
the author's preferred path rather than measured agent quality.

### Tool Execution Success Is Different From Validator Success

For `run_tests`, a command can execute successfully while reporting that tests
failed. These are two different signals:

```text
tool execution status -> did the command run and return a valid observation?
validator outcome     -> did the tested behavior pass or fail?
```

If a public check is proven repeat-stable and task-state-preserving, immediately
rerunning the same command from the same relevant workspace state is
mechanically redundant whether the observed validator outcome is PASS or FAIL.
A repeated failure adds no information merely because the result is negative.

The repeatability contract needs more than an author-written determinism flag.
Calibration should show that repeated runs from the same relevant state produce
the same normalized observation and do not mutate task-relevant state. Volatile
timing fields and incidental cache files must not be mistaken for meaningful
behavioral drift.

Timeouts and tool-execution errors are different. Retrying them may be rational
because the first call did not produce a trusted validator observation. They
should not inherit the mechanical-redundancy label used for normally completed
PASS or FAIL results.

If a check declared repeat-stable produces different normalized outcomes, the
system should treat that as determinism or task-flake evidence. It should not
label the later call redundant or treat a lucky rerun as model improvement.

### Private Exposure And Adversarial Evidence Are Different Cases

A blocked reward-hack attempt with no private-content exposure may be useful as
explicitly labeled adversarial evidence. A transcript containing actual private
validator content is different: training on it can reproduce the information
the leakage boundary was meant to protect.

The conservative rule is:

```text
attack attempt without exposure -> possibly adversarial, subject to its own contract
actual private-content exposure -> not training data
```

Leakage checks therefore protect both eval validity and downstream data use.

### Calibration Must Share The Measured Execution Contract

A calibration can look stable because the harness gives it cleaner conditions
than the model-facing or scoring path. For example, directing temporary files
to a fresh controlled directory only during calibration could remove
cross-run state that remains present during real `run_tests` calls.

The required invariant is:

```text
calibration execution contract == measured execution contract
```

The concrete filesystem paths may differ, but the state semantics, environment
rules, timeout policy, and command behavior must match. Otherwise calibration
proves a property of a special laboratory path rather than the system whose
trajectories will be labeled.

This also clarifies which state is meaningful. Task workspace state persists
and is measured; command-owned temporary state is disposable and reset. If a
public check needs state to survive across invocations, that state must live in
the measured workspace rather than in an incidental operating-system temp
directory.

### A Passing Audit Is Version-Scoped Evidence

An audit result does not establish timeless trust in “the harness.” It only
supports the narrower claim that one exact harness runtime satisfied one exact
set of audit cases under one pinned dependency environment.

Schema names and logical IDs are insufficient provenance. The same task ID or
case ID can refer to changed bytes, and the same source code can behave
differently under changed dependencies. A trustworthy downstream gate must bind
the audit, controls, and source trajectories through content hashes and the
schema versions that define how those hashes were constructed.

The self-deception trap is:

```text
the harness audit passed once, therefore current trajectories are trustworthy
```

Changing the harness source, task inputs, audit cases, dependency lock, or
relevant runtime identity invalidates that inference and requires recalibration.

### Invalid Audit Cases Must Remain In The Denominator

A malformed or unexecutable audit case is not a passing case and must not be
silently skipped. Dropping it can turn a broken audit suite into an apparently
perfect one simply by reducing the set being measured.

The fail-closed distinction is:

```text
executed expectation mismatch -> FAIL
audit machinery produced no trustworthy comparison -> INCONCLUSIVE
```

Both block downstream training-data export, but the distinction matters for
diagnosis: `FAIL` is evidence of a harness-contract violation, while
`INCONCLUSIVE` says the measurement itself must be repaired before trust can be
established.
