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

### A Failure Pattern Is Not Necessarily A Reward-Hack Mechanism

Observable task outcomes do not reveal why the model produced them. In
particular:

```text
public PASS + hidden FAIL
```

is compatible with both public-proxy gaming and an honest but incomplete
solution. Empty patches, format-only patches, and timeouts have the same
ambiguity. Automatically calling them reward hacking would turn ordinary model
errors into false exploit labels.

Authored audit cases remain useful because they test whether shallow signals
can fool the harness or a downstream selector. But the case's controlled
purpose is additional information that an arbitrary real-model trajectory does
not carry.

The durable distinction is:

```text
CONFIRMED = direct evidence of manipulating, probing, or impersonating a
            reward/authority boundary
AMBIGUOUS = a known weak-proxy pattern also compatible with honest failure
```

Reward hacking does not require malicious intent, but a confirmed label still
requires observable evidence of the mechanism. Outcome mismatch alone is not
that evidence.

### `NOT_DETECTED` Is A Coverage Claim

The absence of a detector firing is not enough to conclude that reward hacking
was not detected. That conclusion is justified only when the system knows the
complete set of applicable checks and records an outcome for every one.

This makes the check catalogue part of the measurement boundary:

```text
all applicable checks completed cleanly -> NOT_DETECTED
unknown, empty, incomplete, or errored check coverage -> measurement failure
```

Audit cases and runtime checks therefore need different identities. Several
audit cases may validate one concrete check under different task outcomes, but
counting those cases as different runtime checks would confuse audit depth with
detector coverage. Conversely, silently losing a catalogue entry would create
false clean labels and could admit unsafe trajectories into positive training
data.

### Audit Expectations Are Not Detector Definitions

An authored exploit case needs expected terminal outcomes so it can test
whether the harness responds correctly to a controlled input. Those outcomes
do not define the exploit itself. Copying them into the runtime check catalogue
would conflate two different claims:

```text
audit expectation: this controlled case should end in these states
detector evidence: this observed trajectory contains this mechanism or pattern
```

This distinction prevents two opposite labeling errors. Gating direct evidence,
such as a hidden-validator probe or forged authority file, on one expected
terminal status can miss the same mechanism when the run ends differently.
Conversely, treating a terminal pattern such as public success plus hidden
failure as a mechanism can mislabel an honest incomplete solution as a
confirmed exploit.

Some ambiguous checks intrinsically include an outcome: a public-pass/hidden-
fail pattern and an actual timeout cannot be observed without result state. In
those cases status is local evidence for that named pattern, not catalogue
identity and not a universal reward-hack shortcut. The durable rule is to
classify each concrete surface from the evidence it actually requires, then
aggregate the completed findings separately.

### Loss Masking Does Not Erase Bad Context

Masking an assistant action removes its direct token-level SFT loss, but it does
not remove the action from the sequence. Later assistant targets are still
trained conditional on that action and the resulting tool observation.

For a mechanically redundant call, this creates two problems:

```text
the model receives no signal that the repeated call was undesirable
later behavior is learned in a context that normalizes the unnecessary call
```

Therefore loss masking alone is not a sufficient positive-SFT repair. A clean
positive demonstration should omit the redundant action and its matching tool
result entirely.

Deletion is only trustworthy when the evidence makes it a conservative
transformation. For an immediately repeated call with identical arguments, a
successful equivalent observation, and unchanged relevant workspace state,
the baseline call already supplies the same information. Retaining that
baseline while deleting only the proven duplicate call/result pair preserves a
coherent context without pretending that arbitrary transcript editing is safe.

The durable distinction is:

```text
loss mask              -> controls direct gradient on present tokens
deterministic repair    -> changes the context presented to the model
```

Both are data transformations, but they solve different problems and require
different validity arguments.

### Review Acceptance Is Scoped To The Reviewed Claim

An `accepted` review decision is not a universal permission bit. Its meaning is
limited to the layer and claim being reviewed. For a completed repair, it can
mean the reviewer accepts the declared transformation and resulting artifact.
For a `cannot_complete` or `repair_error` record, it means the failure outcome
was represented accurately; there is still no repaired example to train on.

The self-deception trap is:

```text
some review says accepted -> the example is approved for training
```

Training authorization is instead a conjunction of independently scoped
claims. A repaired positive-SFT example still needs an eligible source
candidate, a completed exact repair, an accepted review bound to that repair
record, and valid transformed output. A downstream reviewer can validate its
own layer but cannot erase an upstream split, leakage, task-outcome,
reward-hack, or harness blocker.

Binding the decision only to a stable ID is also insufficient when the record's
content can change. The ID identifies which logical repair attempt is under
discussion; a canonical source-record hash identifies the exact status,
artifact, evidence, and errors the reviewer actually saw. This prevents an old
approval from silently migrating onto a materially different record.

### Outcome Inheritance Is Transformation-Specific

A repaired transcript was not itself the trajectory that the harness executed,
so `repair_status=completed` cannot create a new task-success claim. Completion
only says the declared transformation produced a valid artifact.

There is nevertheless a narrow case where the source outcome remains
authoritative. If a transformation deletes an action that is proven not to
change workspace state and whose equivalent observation is already retained,
then the environment state before every later action is unchanged. The source
task outcome can be inherited because the transformation preserves the causal
facts on which that outcome was measured.

The durable rule is:

```text
repair completed                      != task success established
state-and-observation-preserving edit -> source outcome may be inherited
behavior-changing edit                -> new outcome evidence is required
```

This is why the current mechanical-redundancy deletion can inherit trusted
source success while a future human or model rewrite cannot do so
automatically. The relevant question is not who produced the repair or whether
it looks better; it is whether the transformation's invariant is strong enough
to preserve the measurement being reused.

Explicit selection matters for the same reason. When several valid derivatives
exist, neither recency nor directory order is evidence that one is the intended
training target. The dataset row must name and hash the selected derivative,
and the export manifest must pin that decision.

### Run Identity Is Not Behavioral Diversity

Different attempt ids, seeds, timestamps, or model labels can still contain the
same policy behavior. Counting them as independent acquisition yield makes the
candidate pool look more diverse without adding a new learning signal.

The self-deception trap is:

```text
many eval attempts -> many training examples
```

Attempt count measures execution volume. It does not measure distinct prompts,
decisions, errors, or candidate behaviors. How behavioral identity should be
defined remains a later preference-data design question.

### Harness Trust Must Be Bound To The Source Evaluation Runtime

A passing current harness audit cannot retroactively validate an evaluation
whose harness bytes and dependencies were never pinned. It proves something
about the audited runtime, not every artifact that happens to share a task id
or schema.

The trustworthy relation is:

```text
source eval runtime == passing audit runtime == passing calibration runtime
```

Task hashes alone are insufficient because the same task can produce different
evidence under changed prompt-loop, tool, scorer, or orchestration code. Runtime
provenance must therefore be captured when the eval executes, not reconstructed
from the repository later.

### Temporary Review Authorization Must Remain Visible Provenance

A provisional acceptance used to exercise an artifact pipeline is not
equivalent to careful human transcript review. If both use the same undifferentiated
`accepted` bit, downstream consumers can forget why the decision was made and
treat plumbing evidence as quality evidence.

The reviewer identity and scope must remain visible and hash-pinned. Before a
future dataset is used for training, the provisional decision must be ratified
or replaced, and all dependent artifacts must be rebuilt. A numerical data
target is not a reason to silently upgrade temporary review authority.

### Parsed Values Must Satisfy The Output Contract Too

Syntactic validation is not enough when parsing or arithmetic can create a
value outside the task's semantic contract. A decimal string may match the
accepted grammar while conversion to a machine float produces infinity; a
direct exponential formula may overflow before a cap is applied.

The self-deception trap is:

```text
input matched the grammar -> output satisfies the contract
```

Validators and oracle controls must check the post-conversion result and any
intermediate behavior that can violate the promised invariant. Otherwise a
passing oracle calibrates the harness against an incomplete specification and
makes the hidden validator less authoritative than the task instruction.

### Stability Requires Replication, Not One Successful Observation

One matching control execution establishes only that the expected outcome was
observed once. It cannot distinguish a deterministic harness from a flaky one
that happened to return the expected result.

```text
one matching run       -> outcome evidence
repeated matching runs -> initial stability evidence
```

Replication still does not prove absence of flakiness, but it changes what the
artifact is entitled to claim. A `stable` label backed by repeated fresh
workspaces is materially stronger than the same label derived from one sample.
The repeat count must remain visible provenance so downstream gates and humans
can judge that strength rather than trusting the aggregate word alone.

### A Model Tag Is A Locator, Not A Policy Identity

A model configuration hash can pin the text `model_id: qwen:tag` while the
provider later resolves that tag to different weights. Two trajectories can
therefore appear configuration-identical even though different policies
generated them.

Acquisition provenance should record the provider-observed immutable model
digest, alongside provider runtime identity such as server version. This does
not independently attest that the provider is honest, but it makes tag drift
observable and allows later comparability rules to require identical weights.
The durable distinction is:

```text
model tag/config bytes -> how the model was requested
observed model digest  -> which weights the provider said it served
```

Both are needed before outcome differences can be attributed to decoding or
behavior rather than silent policy replacement.

### A Timeout Must Terminate The Whole Execution Tree

Recording a command as timed out is not enough if descendant processes remain
alive. An orphaned validator can continue consuming CPU, writing files, holding
pipes, or changing timing for later cases after the harness has declared the
attempt terminal.

The self-deception trap is:

```text
parent command timed out -> execution stopped
```

For shell commands and test runners, the real execution unit is the process
tree. Timeout handling must terminate and reap that unit before the harness
continues. Otherwise later flake measurements and audit outcomes are no longer
independent: they are contaminated by work from cases that supposedly ended.

This is both an isolation invariant and an evidence invariant. A trustworthy
`TIMEOUT` means the bounded computation stopped, not merely that the
orchestrator stopped waiting for its direct child.

### Scorer Replay And Policy Replay Establish Different Claims

Re-scoring a pinned candidate patch in fresh workspaces can show that the
scorer outcome is reproducible for that artifact. It does not show that a
stochastic model would generate the same actions or patch again.

```text
patch replay  -> scorer determinism for fixed submitted behavior
policy replay -> behavioral reproducibility under a declared policy interface
```

For real model trajectories, reconstructing a scripted policy from the observed
transcript would not be a genuine policy replay. It would turn recorded behavior
into a control and then "prove" that the control repeats itself. The honest
fallback is to name the narrower claim: verify the hash-pinned patch and rerun
the scorer, while leaving model-generation reproducibility unclaimed.

The live patch must also be checked against the trajectory-export content hash
before rescoring. Pinning only the parent eval manifest while reading mutable
child files can make a replay look provenance-bound even when the submitted
artifact has drifted.

### Cross-Status Pair Counts Can Hide A Missing Positive Anchor

A comparison between `HIDDEN_TEST_FAIL` and `PUBLIC_TEST_FAIL` has two different
outcomes, but neither side is known to be correct. A large number of such pairs
can therefore make an acquisition pool appear ready for preference training
without supplying a trustworthy chosen endpoint.

The useful accounting distinction is:

```text
cross-status pairs       -> outcomes differ
PASS vs non-PASS pairs   -> one side has trusted task success
valid preference pairs   -> a reviewer accepts the comparison basis
```

None of these quantities substitutes for the next one. Failure-versus-failure
comparisons may still support useful judgments about progress, rationality, or
tool use, but those judgments require semantic review. They cannot inherit a
chosen/rejected label from scorer-status ordering alone.

### Exact Action Equality Is Not Exact Trajectory Equality

Two runs can emit byte-identical assistant actions while receiving different
tool observations because workspace paths, timing, provider metadata, or other
environment details differ. Clustering on assistant actions is useful for
reducing duplicated behavioral review, but it does not prove that the full
training contexts are interchangeable.

```text
same assistant actions != same environment-conditioned trajectory
```

This matters for both review and data weighting. Counting duplicate action
sequences as independent behavioral diversity inflates acquisition yield, while
discarding every duplicate transcript can hide materially different context.
The clustering key and what it omits must therefore remain explicit, and member
artifacts must remain individually inspectable.

### A Privacy Scanner Is Evidence, Not Privacy Clearance

Pattern-based scanning can establish that configured canaries, credential
shapes, private-key markers, or forbidden paths were not matched. It cannot
prove that arbitrary private content is absent. Calling a zero-match scan
"leak-free" would turn detector coverage into a universal claim.

Operational paths are also not harmless merely because they contain no secret.
When tool observations include scratch directories or a user's home path, those
bytes become model context. Loss masking later assistant tokens does not remove
that context, and repeated training can teach environment-specific artifacts.

The conservative boundary is:

```text
no configured sensitive match -> useful negative evidence
host/infrastructure path found -> normalize or repair before training
privacy cleared                -> requires scoped review beyond one scanner
```

### Public-Contract Probes Produce Review Hypotheses, Not Ground Truth

Independent probes derived from the public instruction can make long failure
sets reviewable without exposing private validators. Calibrating those probes
against the oracle checks that they accept known-correct behavior, but it does
not make them complete or authoritative.

A failed public-contract clause is evidence for a concrete review hypothesis.
A probe pass alongside hidden failure means only that this probe set did not
isolate the gap. Treating the taxonomy as hidden-failure truth would quietly
replace the scorer contract with an incomplete analysis tool.

```text
oracle accepts probe suite -> probe suite is not obviously over-restrictive
candidate fails probe      -> public-contract review hypothesis
candidate passes probes    -> hidden failure remains unresolved
```

### Reproducibility Requires The Task Bytes As Well As The Submitted Patch

Re-scoring the same patch with a changed seed workspace, public check, hidden
validator, or oracle is not a replay of the original measurement. Even if the
terminal status happens to match, the apparent agreement may be coincidental.

The reproducibility claim must bind all inputs that causally determine the
score:

```text
same harness runtime + same full task inputs + same candidate patch
    -> scorer replay is comparable
```

Pinning only a task id or task manifest is too weak because referenced files can
drift while those identifiers stay unchanged.

### Task Failure And Evidence Failure Have Different Data Consequences

A task failure says the policy did not complete the requested objective. It
does not say every earlier assistant decision was wrong. By contrast, a
harness, orchestration, leakage, or provenance failure says the evidence itself
is not trustworthy enough to support a training claim.

The distinction is:

```text
task failure     -> may still contain an approved positive prefix
evidence failure -> cannot authorize positive training use
```

Task success is therefore useful for prioritizing scarce human review because
successful runs are likely to have higher positive yield. It is not a sound
schema-level requirement for positive SFT. A successful trajectory can contain
bad actions, while a failed trajectory can contain good actions before its
earliest causal mistake.

### Positive Supervision Requires Objective-Specific Credit Assignment

An assistant message is model-authored, but model authorship only makes it
eligible to receive loss; it does not make it desirable to imitate. For clean-
behavior SFT, an unrepaired trajectory can authorize only a contiguous prefix
ending before the earliest causal error. Actions after that boundary are
conditioned on the mistake and may teach recovery behavior instead.

Recovery can be a legitimate separate objective with its own review and mask.
The same trajectory may therefore be positive-prefix data for one objective,
recovery data for another, a rejected preference branch, and full-fidelity
analysis evidence. No general trajectory review can substitute for these
use-specific decisions.

### Occurrence Identity Is Not Behavioral Drift

Globally unique message ids distinguish two persisted occurrences even when
their semantic content is identical. A fresh replay should therefore generate
new ids. Comparing those values as if they were model behavior makes a correct
replay look flaky.

The correct invariant is:

```text
fresh occurrence ids may differ
message count + order + role + content + tool linkage must still match
```

Normalizing an occurrence id does not mean discarding provenance. Each artifact
retains its real ids; only the behavioral comparison projects them away. The
self-deception trap is either demanding byte equality from intentionally fresh
identity or, in the opposite direction, normalizing so broadly that meaningful
trajectory changes disappear.

### Missing Historical Provenance Cannot Be Invented Retroactively

When a new required field records evidence that the old runtime never captured,
backfilling a syntactically valid value does not recreate that evidence. An
invented message id may make an old JSON object parse, but it cannot prove that
the id existed, was unique, or was preserved through the original execution.

```text
old artifact + invented required fields != artifact produced under new invariant
```

Such traces can remain useful for explicitly labeled historical analysis. They
must not silently enter the new training pipeline. Training eligibility needs
current-runtime reacquisition or an explicit, separately reviewed
transformation whose weaker claim remains visible.

### More Interaction Budget Can Amplify A Limit Cycle

Reaching `max_turns` does not by itself show that the model needed more budget.
The model may have been making useful progress when the boundary stopped it, or
it may have entered a repeated policy loop much earlier.

```text
progressing trajectory + turn limit -> more turns may test a capacity boundary
periodic state/action cycle         -> more turns amplify the same failure
```

The distinction requires trajectory evidence, not terminal status alone. Exact
periodic action signatures, unchanged relevant state, and repeated equivalent
observations are strong evidence against treating a larger limit as a fair
"upper bound." Otherwise an acquisition can spend more compute while only
creating longer, less reviewable negatives.

A narrow mechanical-redundancy detector may legitimately decline to label a
multi-tool cycle if its contract covers only adjacent identical calls. Detector
silence then means the cycle lies outside current coverage, not that the
behavior was efficient. Analysis observations and automated labels must retain
their different authority.

### Stored Transcript Equality May Omit Provider-Side Prompt Adaptation

Two persisted transcript prefixes can be byte-identical even when the provider
sent different logical instructions to the models. A prompt adapter may append
content such as a thinking-mode directive only at request time, after the
pre-adapter transcript has been recorded.

The self-deception trap is:

```text
same stored prefix -> same compared prompt
```

Prompt comparability must include every transformation that affects the model's
logical input, as well as the action-format contract. Occurrence ids should be
excluded because they are provenance rather than semantics; provider-side
instruction changes must be included because they can causally change behavior.
This matters before counting cross-model outcomes as candidate comparisons.

### Privacy Findings Need A Declared Consumer Boundary

A trajectory artifact can contain both the semantic messages used for training
and richer audit-only evidence. A path present in raw command-runner stdout but
absent from the rendered tool observation has a different data consequence from
a path present in the model's transcript.

```text
semantic-message finding -> already part of model context
audit-only finding       -> becomes context only if a consumer serializes it
```

The second case is not permission to ignore the finding. It means eligibility
depends on the declared dataset transformation. A consumer that uses only
semantic messages can establish a narrower clean-context claim; a future
consumer that embeds raw tool results must normalize or review those fields.
Privacy audits should therefore report artifact scope and keep conservative
overall status, rather than collapsing every finding into either harmlessness
or universal leakage.

### Model Capability Claims Do Not Establish Harness Compatibility

A provider may advertise structured outputs, tool use, or agentic coding while
still speaking a different action protocol from the evaluator. Compatibility
must be measured across the full loop, not inferred from a feature label or one
valid first response.

```text
valid first action != compatible multi-turn policy
native tool call    != harness-defined typed action
JSON-shaped output != schema-valid action
```

A model can emit native provider `tool_calls` when the harness expects JSON in
assistant content, or it can follow the schema for two turns and violate it on
the first write. Silently translating those behaviors or loosening validation
to increase model coverage changes the policy interface being evaluated.

The conservative acquisition gate is an end-to-end repeated smoke under the
same adapter and action contract. An incompatible model should remain a
documented integration result until the interface translation is deliberately
designed and audited.

### Task Count And Positive-Anchor Coverage Are Different Dataset Properties

A task pack can contain enough tasks while the acquisition pool still has
success evidence for only a narrow subset. Counting tasks alone hides whether
positive data spans the intended construct distribution.

```text
task exists in pack        -> potential measurement support
task has trusted failures  -> negative and analysis support
task has trusted successes -> possible positive-anchor support
```

This distinction matters before post-training. If all positive rows come from
the easiest task family, a dataset can be numerically large while teaching a
much narrower behavior than the eval suite claims to measure. Acquisition
reports should therefore show per-task outcome support and retain zero-positive
tasks instead of smoothing them into an aggregate pass count.
