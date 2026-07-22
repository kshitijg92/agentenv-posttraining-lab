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

### Data Availability, Trainability, And Evaluability Are Separate Gates

Having candidate examples does not mean the project can train them, and having
a trained adapter does not mean the project can measure its effect.

```text
data availability -> reviewed source examples or comparison ingredients exist
trainability      -> exact tokenizer, serialization, loss mask, model weights,
                     objective, and runtime can consume them
evaluability      -> the exact base and adapted policies can be compared on a
                     split whose relationship to training is declared
```

These gates fail independently. A lab can have dozens of potential preference
comparisons but no trainable checkpoint. It can complete a tiny SFT run yet
have no way to serve the adapter through the evaluator. It can evaluate the
adapter on its training tasks yet have no evidence about heldout behavior.

The self-deception trap is to treat completion of the most visible stage as
proof that the whole experimental loop exists. Downstream readiness should be
audited from the intended claim backward: what comparison makes that claim
meaningful, how will both policies be served, what training artifact produces
one of them, and what authorized data feeds that artifact?

### A Recovered Successful Trajectory Can Still Be A Bad SFT Target

Task success validates the final task outcome, not every action in the path to
that outcome. A model can issue an invalid tool call, recover, and eventually
pass the hidden validator. Imitating the full contiguous transcript would then
teach both the avoidable error and its recovery.

This creates an objective-specific distinction:

```text
successful endpoint                         -> trustworthy outcome evidence
clean successful path                       -> possible direct SFT target
successful path containing an earlier error -> repair, truncate before the
                                                 error, use for a recovery
                                                 objective, or reject
```

Masking only the failed action is not automatically sufficient because later
assistant behavior remains conditioned on that action and its tool response.
For a clean-behavior SFT objective, the context itself can be contaminated even
when the bad action carries no loss.

### An In-Sample Post-Training Eval Has A Narrow But Valid Meaning

Training on dev-task trajectories does not make later evaluation on those same
tasks worthless. It can still test whether the training loop runs, whether the
adapter can be served, whether trained examples regress, and whether expected
behaviors were memorized.

It changes the permissible claim:

```text
evaluation on training tasks -> plumbing, memorization, and regression evidence
evaluation on a frozen unseen slice -> possible generalization evidence,
                                        subject to the rest of the protocol
```

Relabeling already inspected or trained-on tasks as heldout does not restore
the missing counterfactual. If the final claim needs unseen-task evidence, the
slice must be frozen before training and before its outcomes are used to tune
the data, prompt, decoding, or scorer.

### Heldout Authorship Is Not The Same As Outcome Contamination

A task author must inspect the task instruction, seed bug, hidden validator,
and controls to establish that the measurement works. Calling those bytes
"private" cannot mean nobody responsible for the evaluator has ever seen
them.

The relevant untouched boundary is policy feedback:

```text
task/scorer author inspects contract before freeze -> necessary calibration
evaluated policy sees hidden validator             -> leakage
model outcome changes training or eval choices     -> heldout contamination
```

Oracle, known-bad, and scripted-agent controls can run before freeze because
they encode author knowledge and test the harness/scorer contract. Natural-
model attempts are different: their outcomes reveal how the policy interacts
with the slice and can influence prompts, data, decoding, or hyperparameters.

This boundary prevents two opposite mistakes: treating an uncalibrated task as
rigorous merely because nobody inspected it, and spending heldout information
by iterating on real model failures before the experiment is fixed.

### A Pre-Training Baseline Need Not Be Evaluated Before Training

"Pre-training baseline" should identify the unadapted checkpoint, not impose a
wall-clock order that leaks heldout outcomes into training decisions.

Running the base model on heldout tasks first and inspecting the result can
change which examples are selected, which hyperparameters are tried, or which
prompt is used. The slice is then no longer untouched for the adapted policy.

The safer sequence is:

```text
freeze tasks
freeze training and evaluation choices
train adapter
run exact base and adapter as one paired evaluation
inspect both results
```

If operational constraints require an earlier base run, its outcomes must be
sealed until the adapter and evaluation protocol are fixed. Causal comparison
depends on information flow, not just checkpoint timestamps.
## SFT Data Preparation

### A Causal-LM Sequence Contains Many Supervised Predictions

One serialized training sequence is not one indivisible prediction target. In
teacher-forced causal-language-model training, the model receives the complete
token sequence in one forward pass, but causal attention prevents each
position from seeing tokens to its right. Every loss-bearing position therefore
defines its own next-token prediction from the prefix available at that
position.

For a conceptual token sequence:

```text
b e c c a
```

one causal forward pass can train predictions equivalent to:

```text
predict e from b
predict c from b e
predict c from b e c
predict a from b e c c
```

The prefixes do not need to be materialized as four independent dataset rows.
They are evaluated in parallel under the causal mask and combined into the
training loss. Actual BPE tokens need not correspond to individual characters;
the same reasoning applies to whatever token sequence the tokenizer produces.

This clarifies an initially confusing use of the word `example`. A logical
reviewed trajectory, a physical dataset row, an optimizer unit, an assistant
decision, and an individual next-token target are different units. Counting
rows alone does not measure how many prediction targets the trainer receives.

### Causal Attention And Loss Masking Answer Different Questions

Two masks participate in agent SFT and should not be conflated:

```text
causal attention mask -> which preceding tokens a position may use as context
loss/label mask       -> which next-token predictions contribute direct loss
```

In an aggregated agent trajectory, system, user, assistant, and tool tokens can
all be present in the causal context. Labels for system, user, and tool spans
can be set to the ignore index while approved assistant spans remain
loss-bearing. An assistant token can therefore attend to the task instruction,
earlier assistant actions, and tool observations without training the policy
to generate the environment's observations.

Ignored context positions have no direct next-token target loss. They are not
computationally absent: the model still learns how to represent and use them
through gradients from later loss-bearing assistant positions. Likewise, the
presence of later turns in the same physical sequence does not leak future
information into an earlier assistant target, because causal attention blocks
that path.

### Transition Aggregation Creates More Rows, Not More Unique Targets

Consider a trajectory with three assistant responses:

```text
S          = system message
U          = user message
A1, A2, A3 = successive assistant messages, including any assistant tool calls
T1, T2     = successive tool-result or tool-observation messages
```

```text
S, U, A1, T1, A2, T2, A3
```

Trajectory aggregation can serialize it once:

```text
input:  S U A1 T1 A2 T2 A3
loss:   - - A1  - A2  - A3
```

Transition aggregation can instead construct:

```text
record 1: S U A1                 -> loss on A1
record 2: S U A1 T1 A2          -> loss on A2
record 3: S U A1 T1 A2 T2 A3    -> loss on A3
```

If each approved assistant token receives loss exactly once, both forms contain
the same unique conditional targets. The transition form duplicates preceding
context and creates more independently addressable optimizer records; it does
not automatically create additional behavioral evidence.

Trajectory aggregation already presents different effective context lengths.
`A1` is predicted from the short prefix before it, `A2` from a longer prefix,
and `A3` from a longer one still. The total padded length of a batch row is not
the same thing as the causal context length available to each prediction.

Transition records can nevertheless be useful because individual decisions can
be filtered, reviewed, sampled, weighted, or salvaged independently. They can
also make batching by length easier. Those are data-management and optimization
advantages, not new next-token targets.

The two forms are not automatically optimization-equivalent. Equivalence at
the conditional-likelihood level requires the same serialization, the same
context for each target, exact-once label coverage, and compatible token-level
weighting. Per-record averaging can give a short response and a long response
equal weight, whereas a token-level trajectory mean gives the long response
more influence. Long trajectories also create more transition rows and may be
sampled more often. Dropout, minibatch composition, and optimizer scheduling
can introduce further differences even when the intended conditional targets
match.

The durable lesson is:

```text
more physical rows != more unique supervision
aggregation policy also defines sampling and weighting policy
```

### Pretraining Chunks And Agent Decisions Have Different Semantic Risks

Fixed-length pretraining blocks are primarily a physical way to expose a long
token stream to a bounded-context model. Every position inside a block still
contributes a local next-token target. Losing distant context at an arbitrary
block boundary can be tolerable for broad language modeling because the goal is
to learn statistical continuation across a large corpus.

For example, suppose a simplified stream contains these conceptual tokens and
the physical block length is six:

```text
original stream:
  The | rain | stopped | . | Becca | opened | the | window | .

block 1:
  The | rain | stopped | . | Becca | opened

block 2:
  the | window | .
```

Inside block 1, causal training still produces several targets: predict
`rain` from `The`, predict `stopped` from `The rain`, and so on. Inside block 2,
however, predicting `window` may use only `the`; it no longer has the narrative
prefix saying that Becca opened it. That is a real context loss, but broad
pretraining can still obtain useful local continuation signal from enormous
amounts of text. The physical blocks are not a claim that every continuation
has retained all of its document-level meaning.

An agent action has a more explicit state dependency. A tool call or final
answer may depend on the original task, system constraints, tool definitions,
an early file observation, and several subsequent results. Cutting immediately
before that action can turn a valid demonstration into a different claim:

```text
original claim: choose this action after seeing the actual preceding state
chunked claim:  choose this action from only the surviving token suffix
```

Those are not interchangeable training examples. A chunk boundary can remove
the evidence that justified the action while leaving the action loss-bearing.
The resulting row may look syntactically valid and still teach an unjustified
decision.

For example, consider this approved agent history:

```text
S:  Edit implementation files only; never modify tests.
U:  Fix the parser so quoted fields may contain newlines.
A1: read_file("src/parser.py")
T1: The parser resets its in_quotes state at every physical line.
A2: read_file("tests/test_parser.py")
T2: The failing case expects a quoted newline to remain inside one field.
A3: edit_file("src/parser.py", preserve in_quotes across physical lines)
```

In the full trajectory, `A3` is justified by the user request, the source-code
observation in `T1`, the expected behavior in `T2`, and the system constraint
against changing tests. An arbitrary later chunk might instead contain only:

```text
T2: The failing case expects a quoted newline to remain inside one field.
A3: edit_file("src/parser.py", preserve in_quotes across physical lines)
```

The edited file happens to be correct, but the training claim has changed. The
model is now rewarded for making that edit without seeing the task constraint
or the source evidence that localized the defect. If the boundary lands inside
the structured tool call, it can be worse still:

```text
chunk begins: "replacement": "preserve in_quotes ..." }
```

Loss on that suffix would teach a serialization fragment without the assistant
role marker, tool name, or preceding arguments that give it meaning.

Sequence packing is also different from arbitrary trajectory chunking. Packing
places several already-valid sequences into a physical batch representation
while preserving attention boundaries. It improves utilization; it does not
repair an overlength semantic example or authorize removal of its context.

For example, two independently valid short examples can share one physical
allocation:

```text
example X: [Sx, Ux, Ax]
example Y: [Sy, Uy, Ay]

packed storage: [Sx, Ux, Ax] [Sy, Uy, Ay]
attention rule: Ax attends only within X; Ay attends only within Y
```

Neither example is missing its own required prefix, and `Ay` is prevented from
treating example X as context. Packing saves padding and compute; chunking the
middle or end of one overlength trajectory would change what its actions are
conditioned on.

### Overlapping Windows Are A Context Policy, Not A Free Repair

Overlapping windows initially appear to solve overlength trajectories: repeat
some preceding tokens in each window, mask repeated labels, and supervise later
assistant actions once. This can avoid duplicate direct loss, but it does not
establish that the surviving context is sufficient or faithful.

For example, use messages as simplified window units and suppose an approved
trajectory is:

```text
S:  Edit implementation files only; never modify tests.
U:  Fix quoted-newline parsing.
A1: read_file("src/parser.py")
T1: The parser incorrectly resets in_quotes at each physical line.
A2: read_file("tests/test_parser.py")
T2: The expected result preserves a newline inside the quoted field.
A3: edit_file("src/parser.py", preserve in_quotes across lines)
T3: Edit completed.
A4: run_tests()
T4: All public tests passed.
```

With a six-message window and a two-message overlap, materialization might
produce:

```text
window 1: [S, U, A1, T1, A2, T2]
window 2: [A2, T2, A3, T3, A4, T4]
```

This creates two separate problems. First, `A2` appears in both windows. If its
labels remain active twice, the read action is silently given twice the weight.
Masking the second copy restores exact-once direct supervision, but it does not
solve the second problem: when `A3` receives loss in window 2, it cannot see the
system prohibition against editing tests, the original task wording, or `T1`'s
source-level evidence that identified the defect. The real rollout chose `A3`
after seeing all of those facts.

Always prepending `S` and `U` would preserve some constraints, but it would
consume window capacity and still omit `T1`; choosing which older messages to
retain would itself become a context-selection policy. A larger overlap only
delays the same decision. By contrast, if the deployed agent also generated
`A3` from exactly `[A2, T2]` plus a pinned system/task prefix, then training on
that same window could be faithful to its runtime context policy.

For a later action, an overlapping window may omit:

```text
the original task or system instruction
an early observation that constrains the correct action
the reason a file or tool result should be trusted
an earlier error whose consequences remain in the workspace
```

Increasing the overlap merely moves the arbitrary boundary. It does not prove
that discarded information is causally irrelevant. Repeating selected headers
or synthesizing a summary changes the context again and requires its own
validity argument.

Overlapping windows become principled only when they reproduce a declared
model-visible context policy, such as the same sliding-window or context-
compression mechanism used during inference, or when a review establishes
that the retained state is sufficient for the supervised decision. Otherwise
they train the action under a counterfactual context that the rollout model did
not actually use.

They also require an exact-once supervision invariant. If a loss-bearing token
appears in two overlapping windows, it is silently upweighted unless one copy
is masked. Even with that accounting fixed, the two copies may occupy different
positions or see different histories, so they are not semantically identical.

The conservative initial policy is therefore:

```text
aggregate the approved trajectory once when it fits
reject it when canonical serialization exceeds max_sequence_length
do not silently crop, split, summarize, or overlap it
```

This policy preserves semantic clarity but sacrifices data yield. It will also
bias the accepted dataset toward shorter trajectories and potentially easier
tasks. Overlength rejection must remain an explicit, measured exclusion reason,
with length and outcome distributions reported. Otherwise a clean-looking SFT
dataset can conceal the fact that it excludes the long-horizon behavior the
agent ultimately needs to learn.

### A Rollout Is A Series Of Tokenized Inference Calls

`Rollout token` and `training token` describe provenance, not different token
types.

During an agent rollout, every assistant turn normally involves a new inference
request:

```text
P1 = exact prompt token ids for system, task, tools, and current history
G1 = token ids sampled for the first assistant response

P2 = newly serialized and tokenized prompt including response 1 and tool result 1
G2 = token ids sampled for the second assistant response
```

The token-level rollout is consequently a sequence of `(prompt, generation)`
pairs, not necessarily one contiguous token array. Later prompts repeat much of
the earlier history. Concatenating `P1, G1, P2, G2` would duplicate context and
would not produce the desired trajectory-aggregated SFT sequence.

Rollout tokens are the exact ids the behavior model consumed and emitted in
those calls. They are tied to the rollout model, tokenizer revision, chat
template, tool serialization, special-token policy, and provider behavior. If
the provider exposes only text rather than token ids, exact rollout-token
provenance is unavailable and must not be reconstructed by assertion.

Training tokens are the ids actually passed to the model during a later
gradient update. For trajectory aggregation, the approved structured messages
are serialized once with the pinned training tokenizer and chat template. The
resulting `input_ids` and aligned labels are a model-specific derivative of the
reviewed message-level example.

The durable boundary is:

```text
reviewed messages -> behavioral training source
canonical training serialization -> model-specific input_ids and labels
per-turn rollout ids -> evidence of what the behavior policy actually saw and emitted
```

A message-level example can therefore remain meaningful across training models
while each tokenizer/template combination produces a different training-token
artifact. Persisting the final training ids and labels, together with pinned
tokenizer and serializer provenance, makes the actual gradient input auditable.

### Deterministic Tokenization Does Not Make Decoding One-To-One

A pinned BPE encoder is deterministic: one input string and one set of encoder
options produce one canonical token-id sequence. That does not make the decoder
injective. BPE vocabularies contain both smaller pieces and merged pieces, so
several valid token sequences can concatenate to the same bytes.

For a toy vocabulary:

```text
token 10 -> "be"
token 11 -> "c"
token 42 -> "bec"
```

both of these decode to the same visible text:

```text
decode([10, 11]) = "bec"
decode([42])     = "bec"
```

The deterministic encoder may choose the canonical merged form:

```text
encode("bec") = [42]
```

Therefore the usual lossless-text property can hold:

```text
decode(encode(text)) == text
```

while exact token-id recovery does not:

```text
encode(decode([10, 11])) != [10, 11]
```

Generation makes this distinction operational. A language model chooses token
ids directly and is not constrained to emit the encoder's canonical
segmentation of the eventual decoded text. It may generate `[10, 11]` even
though retokenizing the resulting text yields `[42]`.

Tokenization also does not generally distribute over concatenation:

```text
encode(text_a) + encode(text_b) != encode(text_a + text_b)
```

A merge may become available across the boundary. Chat-template separators,
whitespace, tool-call wrappers, normalization, and special tokens add further
boundary effects. An assistant response can consequently have one id sequence
when it is originally generated and another when its decoded text is
retokenized as history in the next rollout prompt.

The phrase `reconstructed rollout tokens` is therefore dangerous. Retokenized
text may be a perfectly valid canonical training representation, but it is not
proof of the ids sampled by the rollout model.

### SFT Can Use Canonical Training Tokens Without Claiming Exact Replay

Positive SFT learns from an approved behavioral demonstration. It does not
normally require the training sequence to reproduce every token boundary from
the original inference calls. Canonical retokenization is valid when the
training tokenizer, chat template, tool representation, assistant-span
boundaries, and label policy are explicitly pinned and the resulting sequence
is inspected as the artifact that will receive loss.

This tolerance must not be generalized to objectives that depend on the
behavior policy's exact action probabilities. Policy-gradient calculations,
off-policy corrections, and some KL or log-probability comparisons need the
actual rollout action ids and their original boundaries. Canonical training
tokens cannot retroactively establish those quantities.

There is also a semantic limit to message reconstruction. If the rollout
provider inserted hidden formatting, if tool definitions were omitted from the
record, or if a runtime context manager summarized or dropped history, then
serializing the apparent full transcript does not recreate the context the
model saw. A canonical SFT rendering can still be deliberately chosen, but it
must be described as a training representation rather than exact rollout
replay.

For the initial positive-SFT path, the clean claim is:

```text
one approved message-level example
-> one pinned canonical trajectory serialization
-> assistant-only loss labels
-> one persisted training record if it fits max_sequence_length
-> explicit exclusion if it does not fit
```

This keeps the current experiment small while preserving the distinctions
needed to introduce transition aggregation or a runtime-aligned context manager
later without pretending that arbitrary chunking was already valid.

### The Target Checkpoint Owns The Training Tokenizer

A tokenizer is not interchangeable preprocessing placed in front of an LLM. A
token id selects one row of the model's input embedding table and one output
class in its language-model head. The vocabulary-to-id mapping is therefore
part of the checkpoint's parameter interface.

If SFT updates Model A, the default contract is to use the exact tokenizer
artifacts compatible with Model A's starting checkpoint: vocabulary, merge
rules, normalizer, special-token mapping, configuration, and pinned revision.
Rollout token ids from Model B cannot be fed directly to Model A merely because
both models decoded them into the same text. The same integer id may identify
unrelated byte strings in the two vocabularies.

This is why the message-level positive-SFT source remains upstream of token
materialization:

```text
trajectory collected from Model B
-> reviewed structured messages
-> canonical serialization with Model A's tokenizer
-> Model A input_ids and labels
```

Changing Model A's token-id mapping while retaining its existing embedding and
output-head rows would be a severe interface error. Adding vocabulary entries
is technically possible only with an explicit model change such as resizing
and initializing new embedding/output rows, followed by enough training to
learn them. That is a tokenizer-and-architecture adaptation experiment, not an
ordinary small SFT run. Even changing merge or normalization rules while ids
remain compatible alters sequence lengths and the token distributions seen by
the pretrained model, so it should be deliberate rather than incidental.

The chat template is related but distinct. It determines how roles, tool calls,
tool results, separators, and end-of-turn markers are arranged using the
available vocabulary. A model can in principle be fine-tuned onto a new chat
template without replacing its tokenizer, but that teaches a new interaction
format. The training and deployment serializers must then agree, and a small
dataset may be insufficient to overcome the checkpoint's existing format
priors. Reusing the checkpoint's native pinned template is therefore the
conservative starting point unless the intended agent interface requires a
deliberate change.

Two kinds of drift should not be conflated:

```text
rollout-to-training retokenization drift
  = the reviewed text is canonically represented for the target model
  = acceptable for SFT when declared and pinned

training-to-deployment tokenizer/template drift
  = the model is invoked through a different token or formatting interface
  = an invalid or at least separately untested deployment contract
```

For exact behavior-policy probability calculations, canonical Model A training
tokens still cannot replace Model B's original rollout action ids. For positive
SFT, however, the target checkpoint's compatible tokenizer is authoritative
because those are the parameters receiving the gradient.

### The Model Input Protocol, Not The Serving Vendor, Should Be The Training Contract

A chat API accepts structured objects such as `system`, `user`, `assistant`,
and `tool` messages, but a causal language model does not consume those
objects. It consumes one sequence of token ids. A serializer must decide how
roles, message boundaries, tools, and generation boundaries appear in that
sequence:

```text
structured messages
-> model input protocol / chat template
-> checkpoint-compatible tokenizer
-> token ids
-> causal language model
```

The tokenizer and the chat template are related but separate contracts. The
tokenizer defines the mapping between text or special symbols and embedding
rows. The template decides which symbols and text are arranged around each
message. A provider's HTTP schema is another separate layer: two servers can
both accept an OpenAI-compatible `messages` array while producing different
model-visible token sequences.

For example, these three simplified serializations express roughly the same
conversation using materially different token protocols:

```text
Messages:
  system: You are concise.
  user: What is 2 + 2?
  assistant: 4

ChatML-like:
  <|im_start|>system
  You are concise.<|im_end|>
  <|im_start|>user
  What is 2 + 2?<|im_end|>
  <|im_start|>assistant
  4<|im_end|>

Llama-header-like:
  <|begin_of_text|><|start_header_id|>system<|end_header_id|>
  You are concise.<|eot_id|>
  <|start_header_id|>user<|end_header_id|>
  What is 2 + 2?<|eot_id|>
  <|start_header_id|>assistant<|end_header_id|>
  4<|eot_id|>

Instruction-wrapper-like:
  <s>[INST] You are concise. What is 2 + 2? [/INST] 4</s>
```

These are not cosmetic alternatives. The model was trained to interpret
particular control tokens and boundaries. The same base architecture can even
have instruction-tuned descendants that expect different formats. Hugging
Face's [chat-template documentation](https://huggingface.co/docs/transformers/chat_templating)
shows this explicitly and recommends applying the intended template during
training.

For open-weight models, the durable industry pattern is consequently to treat
the model-native input protocol as part of the model artifact. It is commonly
distributed beside the tokenizer in the model repository. A serving engine is
then configured to implement that protocol:

```text
                         +-> Ollama implementation --+
pinned model protocol ---+-> vLLM implementation ----+-> equivalent model-visible ids
                         +-> another server adapter --+
```

For example, vLLM normally reads a chat template from the tokenizer
configuration and also permits an explicit template override; it does not
require a separately trained model for each server. See the
[vLLM chat-template contract](https://docs.vllm.ai/en/latest/serving/openai_compatible_server/#chat-template).
Ollama packages a model-specific Go-syntax `TEMPLATE` in its Modelfile, which
it describes as the full prompt sent to the model. See the
[Ollama Modelfile template contract](https://docs.ollama.com/modelfile#template).

Calling a template a `Hugging Face template` can therefore obscure ownership.
For a Qwen checkpoint, the template stored in its Hugging Face tokenizer
artifacts is better understood as a Qwen model-interface artifact distributed
through Hugging Face. Hugging Face need not be the inference provider. An
Ollama template for the same checkpoint should ideally be a different
implementation of the same model protocol rather than a new training target.

Provider defaults must still not be assumed equivalent. Differences often
appear precisely in agentic cases:

```text
Canonical tool result:
  <|im_start|>tool
  {"result":"ok"}<|im_end|>

Possible provider rewrite:
  <|im_start|>user
  <tool_response>{"result":"ok"}</tool_response><|im_end|>
```

A model may handle one representation much better because it saw that form in
instruction tuning. Other possible drift includes moving the system prompt
into the first user message, changing tool-schema placement, injecting a
reasoning directive, omitting empty content, using a different assistant
generation header, or treating the final assistant message as a prefill.

The correct portability invariant is token-level conformance on the semantic
cases the agent uses:

```text
canonical_ids(messages, tools, generation_mode)
==
provider_ids(messages, tools, generation_mode)
```

Checking only a plain user-assistant exchange is insufficient. Conformance
fixtures must cover system messages, multiple turns, tool definitions, tool
calls, tool results, generation prompts, completed assistant turns, and any
adapter-level prompt transformations. An API adapter that appends a directive
such as `/no_think` changes the model-visible prompt even if the chat template
itself is unchanged.

Prompt text, template controls, and provider controls are three different
interventions even when their names suggest the same intent:

```text
model-visible soft switch:  append "/no_think" to a message
template-level hard switch: render a non-thinking template branch
provider request control:   send a structured option outside the messages
```

The first becomes ordinary input tokens. It is valid only when the checkpoint
was trained to interpret that token sequence as a control. The second changes
serialization before tokenization. The third delegates the decision to the
serving backend, which may select a template branch, set generation behavior,
or reject the option. They cannot be treated as interchangeable without
observing the final model-visible token sequence and generation semantics.

The Qwen2.5 acquisition exposed this boundary concretely. AgentEnv's generic
prompt adapter appended `/no_think` to the system message, and Ollama passed it
through as literal text. Qwen3 documents that text as a soft thinking switch,
but the selected Qwen2.5-Coder checkpoint does not document such a protocol.
The fact that a provider accepted the request did not make the directive a
valid checkpoint control; it merely meant the model received extra tokens.

This also reveals a provenance requirement. A stored logical transcript can
omit a suffix that a request adapter injected at rollout time. Reconstructing
training data from only that logical transcript then misstates the context
under which the assistant actions were sampled. When an accidental
model-visible adapter is removed, silently deleting it from old trajectories
is not a repair: it changes their causal context. The clean response is to
retain the old records as historical evidence and regenerate acquisition under
the intended protocol.

If a provider implementation differs, the preferred response for an
open-weight model is usually to configure the provider to use the canonical
model protocol. Training provider-specific weights is necessary only when the
provider cannot reproduce that protocol, or when the different interface is an
intentional deployment target. Training on several implicit formats without
recording which one each example uses can instead teach conflicting boundary
semantics.

Closed hosted fine-tuning has a different ownership boundary. The customer
usually supplies structured messages, while the provider privately owns
serialization, tokenization, weights, and serving. The resulting custom model
is already tied to that provider and model version. For example, OpenAI's
[fine-tuning API](https://platform.openai.com/docs/api-reference/fine-tuning)
accepts message-form training records rather than customer-materialized token
arrays. Provider coupling is expected there because the resulting weights are
not an independently deployable artifact.

The self-deception trap is to infer token portability from request-schema
portability. `OpenAI-compatible` says that two servers accept similarly shaped
JSON; it does not say that the model sees the same tokens. For an open-weight
training lab, the clean contract is:

```text
training pins the target checkpoint's model input protocol
deployment backends demonstrate conformance to that protocol
provider-specific behavior is recorded as an explicit divergence
```

### Loss Ownership Follows Who Must Produce A Token At Inference

Assistant-only SFT does not simply assign loss to every token physically found
inside an `assistant` message string, nor does it mask every token inserted by
the serializer. The relevant question is:

> Given the prompt available when generation begins, which tokens must the
> model produce as its action?

Consider a simplified Qwen/ChatML rendering:

```text
<|im_start|>system
Answer using the required JSON protocol.<|im_end|>
<|im_start|>user
What is 6 * 7?<|im_end|>
<|im_start|>assistant
{"final_answer":"42"}<|im_end|>
```

For ordinary assistant generation, the runtime serializer supplies everything
through the assistant header. The model begins generation after:

```text
<|im_start|>assistant\n
```

The intended ownership is therefore:

```text
Rendered span: <|im_start|>system\n
  produced by: runtime/template
  label:       -100

Rendered span: Answer using the required JSON protocol.
  produced by: runtime/template
  label:       -100

Rendered span: <|im_end|>\n
  produced by: runtime/template
  label:       -100

Rendered span: <|im_start|>user\n
  produced by: runtime/template
  label:       -100

Rendered span: What is 6 * 7?
  produced by: runtime/template
  label:       -100

Rendered span: <|im_end|>\n
  produced by: runtime/template
  label:       -100

Rendered span: <|im_start|>assistant\n
  produced by: runtime/template
  label:       -100

Rendered span: {"final_answer":"42"}
  produced by: model
  label:       corresponding token ids

Rendered span: <|im_end|>
  produced by: model
  label:       <|im_end|> token id

Rendered span: \n after the assistant <|im_end|>
  produced by: runtime/template when the completed turn becomes context
  label:       -100
```

The repeated appearance of `<|im_end|>` does not imply repeated ownership.
The system and user end markers describe context constructed before inference,
so they are masked. The assistant end marker is the model's end-of-turn action,
so it receives loss.

This can initially feel backwards because the API response normally contains
only the visible assistant text:

```json
{"final_answer":"42"}
```

The serving layer may consume or strip the generated end-of-turn token before
returning that text. Its absence from the response transcript does not prove
that the model was not expected to generate it. Conversely, a training
materializer may append `<|im_end|>` while constructing labels even though the
literal transcript omitted it. Physical insertion by the materializer does
not determine loss ownership; deployment generation semantics do.

With causal-language-model shifting, the prediction after the final `}` is the
assistant `<|im_end|>` token:

```text
context ending in: ... "42" }
next supervised target: <|im_end|>
```

Giving that target loss teaches the model when the assistant action is
complete and when control should return to the harness. Masking it supplies no
new positive pressure for correct termination. The model might still stop due
to its earlier training, an external stop string, a constrained-decoding
engine, or the maximum generation length, but the SFT example would not teach
the desired boundary directly.

In an agent, termination tokens are behavioral rather than decorative. Failing
to close an assistant turn can cause the model to append unrelated text, merge
two protocol actions, exceed a parser's accepted payload, or run until a token
limit. Correct content followed by incorrect termination can therefore become
an orchestration failure.

The same ownership rule applies to tool syntax. Suppose a deployment protocol
expects the model to emit:

```text
<tool_call>{"name":"read_file","arguments":{"path":"a.txt"}}</tool_call><|im_end|>
```

If the model must generate the `<tool_call>` wrappers, JSON, and end-of-turn
marker, all of those tokens are part of the supervised assistant action. If a
provider instead asks the model for only JSON and inserts the wrappers after
generation, the inserted wrappers are not model targets. Tool-result wrappers
are normally produced by the environment when the next prompt is serialized,
so they remain context-only even though the model must learn how to react to
them.

For a multi-turn approved trajectory, the pattern repeats:

```text
system/user/tool context       -> visible through attention, labels = -100
assistant content              -> labels = token ids
assistant end-of-turn          -> labels = end-of-turn token id
next tool observation          -> visible through attention, labels = -100
next assistant content         -> labels = token ids
next assistant end-of-turn     -> labels = end-of-turn token id
```

There is one important qualification: an end marker should receive loss only
if the chosen deployment protocol actually expects the model to emit it. If a
server stops generation through an external mechanism before that token and
the model never owns it, training it as an action would create a mismatch.
This is another reason to pin generation semantics alongside the template
rather than inferring them from visible transcript text.

The durable loss-mask invariant is:

```text
loss-bearing tokens = the approved token actions the deployed model must generate
context-only tokens = everything supplied to the model before or between those actions
```

Message role is a useful first approximation, but exact ownership is defined
by the model input and generation protocol.

### Character-Level Ownership Bridges Rendering And Token Loss

Loss is applied to tokens, but the information needed to decide ownership
exists before tokenization. The renderer still knows which output fragments
represent supplied context, template scaffolding, or model-generated actions.
After rendering, the tokenizer sees only one flat string; role and provenance
are no longer intrinsic properties of its characters.

Character-level ownership preserves that information across the boundary. It
does not require storing one flag for every character. A compact sequence of
non-overlapping spans is enough:

```text
rendered text:
<|im_start|>assistant\n{"final_answer":"42"}<|im_end|>\n

ownership spans:
context -> <|im_start|>assistant\n
model   -> {"final_answer":"42"}
model   -> <|im_end|>
context -> \n after the completed assistant turn
```

This granularity matters because a rendered assistant turn mixes ownership.
The runtime supplies the assistant header, the model produces the response and
end-of-turn action, and the completed-turn serializer supplies the following
separator. Labeling the whole assistant message would supervise runtime-owned
scaffolding. Labeling only the original message content would omit the
model-owned end-of-turn token.

Token identity alone also cannot recover ownership. The same Qwen
`<|im_end|>` token id can occur after system, user, assistant, and tool content:

```text
system <|im_end|>       -> context-only occurrence
user <|im_end|>         -> context-only occurrence
assistant <|im_end|>    -> model-generated occurrence
tool context <|im_end|> -> context-only occurrence
```

The token id says what symbol occurred, not who was responsible for producing
that particular occurrence. Ownership must remain attached to its position in
the rendered transcript.

Tokenizing each rendered fragment separately is not a safe substitute. BPE is
deterministic for a fixed string, but tokenization is not generally
compositional. In a hypothetical vocabulary containing token `ab`:

```text
tokenize("ab")              -> ["ab"]
tokenize("a") + tokenize("b") -> ["a", "b"]
```

Therefore this transformation is not guaranteed to preserve the canonical
model input:

```text
tokenize(context fragment) + tokenize(model fragment)
```

The correct sequence is to render the entire approved transcript once,
associate ownership spans with that exact rendering, and tokenize the complete
string once. A tokenizer that exposes offsets can then map each token back to
the characters it covers:

```text
token lies wholly in a model span   -> label is the token id
token lies wholly in context spans  -> label is -100
token crosses an ownership boundary -> materialization is ambiguous
```

For example, imagine one token covered both the newline at the end of the
runtime-supplied assistant header and the first character of the assistant
answer:

```text
token characters: "\nF"
ownership:         context + model
```

A token is atomic. Supervising it would apply positive pressure to some
runtime-owned text; masking it would discard supervision for some model-owned
text. Silently choosing either label hides a protocol/tokenizer mismatch. A
conservative materializer should reject the example unless the ownership can
be aligned unambiguously. Explicit Qwen special tokens and separators may make
such crossings unlikely, but that is an invariant to test rather than assume.

Character spans are intermediate audit evidence, not necessarily permanent
trainer payload. The final trainer record may contain only `input_ids`,
`labels`, counts, and pinned provenance, provided the ownership spans can be
deterministically re-derived and the persisted labels can be validated against
them.

The self-deception trap is to build a plausible-looking assistant mask by
tokenizing messages or fragments independently. The labels may have the right
length and still describe a token sequence different from the canonical full
prompt. Character ownership keeps the semantic origin of the text intact until
the exact full-sequence tokens and loss labels have been established.

### Span Coordinate Systems Are Part Of The Training Contract

A span written as `(start=1, end=2)` is not meaningful until its coordinate
system is named. The numbers might count Python Unicode-string positions,
UTF-8 bytes, UTF-16 code units, or tokenizer tokens. These systems coincide on
simple ASCII, which makes an offset bug easy to miss in apparently convincing
tests.

Consider the string:

```text
AΩB
```

Its representations differ:

| Representation | Length | Range selecting `Ω` |
| --- | ---: | --- |
| Python Unicode string | 3 positions | `[1, 2)` |
| UTF-8 bytes | 4 bytes | `[1, 3)` |
| Model tokens | tokenizer-dependent | tokenizer-dependent |

`Ω` is Unicode code point `U+03A9`. Python indexes it as one string position,
but UTF-8 encodes it as two bytes, `CE A9`. Therefore:

```python
text = "AΩB"

len(text)                  # 3 Python Unicode-string positions
len(text.encode("utf-8"))  # 4 bytes
text[1:2]                  # "Ω"
```

The same distinction appeared in a rendered agent transcript containing two
`Ω` symbols:

```text
complete rendering: 131 Python string positions, 133 UTF-8 bytes
model-owned range:  [100, 130) in Python string indices
selected text:      {"final_answer":"Ω"}<|im_end|>
```

One `Ω` occurred before the owned range and another inside it. Consequently,
the corresponding UTF-8 byte range was `[101, 132)`, not `[100, 130)`. Applying
the Python indices directly to encoded bytes would select the wrong boundary.

Even “character” is too imprecise as a unit. A displayed `é` may be represented
as one Unicode code point:

```text
U+00E9                 -> é
```

or as two code points that render as one visual glyph:

```text
U+0065 U+0301          -> e + combining acute accent -> é
```

Likewise, some emoji that appear as one glyph consist of several code points.
Visual glyph counts are therefore unsuitable for machine-auditable ownership
spans.

Render equality and span coordinates answer different questions:

```text
UTF-8 byte equality
-> did canonical and annotated templates produce exactly the same model input?

Python Unicode-string indices
-> which substring did the ownership renderer mark as model-generated?

token offsets
-> which final training tokens cover that substring?
```

The token materializer may map ownership to loss only after proving that the
tokenizer's offsets refer to the same original text and after explicitly
converting coordinate systems when they differ. A token wholly inside a
model-owned range can receive its token id as a label; a token wholly outside
receives `-100`; an unresolvable crossing must not be guessed.

This also creates a cross-language portability concern. Python indexes Unicode
strings by code point, while JavaScript indexes strings by UTF-16 code unit.
An emoji outside the Basic Multilingual Plane can occupy one Python position
but two JavaScript positions. Persisting bare integers without their coordinate
system makes an otherwise hash-pinned artifact ambiguous to another consumer.

The durable invariant is:

```text
every persisted or exchanged span names its coordinate system
every ownership-to-token mapping proves or performs the required conversion
ASCII-only conformance tests are insufficient
```

The self-deception trap is to validate offset logic only on ASCII transcripts.
On ASCII, code-point, UTF-8-byte, and UTF-16-unit offsets often have identical
numbers, so a fundamentally incorrect mapping can appear perfect until a real
task contains non-ASCII paths, source code, tool output, or user text.

### Public Agent-Training Systems Use Several Aggregation Policies

There is no single public industry convention that makes every agent trace one
row or every assistant turn one row. The durable pattern is that the physical
representation should preserve the context required by each supervised action:

```text
full-trajectory aggregation -> efficient when the approved trace fits
transition aggregation      -> independently addressable decisions with real prefixes
overlength exclusion        -> conservative when context cannot be preserved
runtime-aligned compression -> appropriate when the deployed agent uses the same policy
```

[Agent Lightning's aggregation discussion](https://agent-lightning.github.io/posts/trajectory_level_aggregation/)
explicitly contrasts trajectory and transition aggregation and documents
retokenization and chat-template drift. [NVIDIA's multi-turn agent SFT
recipe](https://docs.nvidia.com/nemo/automodel/recipes-e2e-examples/agent-sft)
supervises assistant/tool-call spans while masking user and tool observations
and exposes explicit truncation behavior. [ms-swift's training
parameters](https://github.com/modelscope/ms-swift/blob/main/docs/source_en/Instruction/Command-line-parameters.md)
distinguish pretraining split behavior from SFT overlength handling. These are
examples of design choices rather than proof that one layout is universally
correct.

The self-deception trap is to copy the row format of a public system without
also copying the context policy, loss reduction, weighting, and runtime
assumptions that make that format meaningful.

### Schema Rebuildability And Training Authorization Are Different Claims

An immutable trajectory can remain valid evidence after a downstream candidate
or dataset schema changes. Rebuilding the derived record from the same pinned
trajectory and review can restore schema validity without rerunning the model.
That does not make the rebuilt row training-authorized.

Final authorization additionally asks whether the source eval ran under the
same harness runtime that was audited and calibrated for release:

```text
source evidence still loads
  != derived artifact still matches the current schema
  != current harness is authorized to interpret that evidence for training
```

This distinction matters especially when runtime provenance hashes the full
package source and dependency lock. Adding training-only code can then change
the recorded harness runtime even if rollout and scoring behavior did not
change. Under a strict equality policy, the honest choices are to acquire again
after the code stabilizes or explicitly design and validate a narrower runtime
boundary. Silently treating the change as irrelevant defeats the provenance
gate.

The self-deception trap is to regenerate manifests around old rows and call
them current. Rebuilding proves deterministic derivation; it cannot manufacture
the missing runtime equivalence evidence.

### Complete Rollouts Are Preference Evidence, Not Automatically The Loss Unit

Two agent rollouts may begin from the same task, workspace, tool contract, and
model-visible history, then diverge at one assistant action:

```text
shared context C
├── A1 -> observation O1 -> later action B1 -> ... -> rollout outcome R1
└── A2 -> observation O2 -> later action B2 -> ... -> rollout outcome R2
```

The complete branches are valuable evidence because they reveal the
consequences associated with `A1` and `A2`. They are not automatically the right
trainable chosen and rejected sequences. Full-trajectory preference loss would
apply pressure across every later assistant action in each branch. That can
reward incidental or redundant behavior in a successful branch and penalize
sensible diagnosis or recovery behavior in a failed branch. It also introduces
long-horizon length and credit-assignment effects that are unrelated to the
first decision.

For an action-level preference pair, the trainable claim is narrower:

```text
prompt:   exact shared context C
chosen:   one assistant action A1
rejected: one assistant action A2
evidence: references to the complete downstream rollouts
```

Only `A1` and `A2` share the same conditioning context. The later actions do
not:

```text
context for B1 = C + A1 + O1
context for B2 = C + A2 + O2
```

Comparing `B1` directly with `B2` would confound action quality with different
histories and environment states. Either later action may still support
positive SFT within its own reviewed context or form another preference pair
against an alternative generated from that exact context. It simply cannot
inherit loss from the original branch-point comparison.

This separates two artifacts with different authority:

```text
complete rollout -> evidence used to justify or review the preference
shared-context action pair -> unit that receives pairwise preference loss
```

### Task Outcome Does Not Establish A Local Action Preference

Task success and failure summarize whole-trajectory outcomes. They do not
provide local credit assignment for every action in those trajectories.

For example, a successful rollout may contain an unnecessary repeated file
read before eventually producing a correct patch. Terminal success does not
make that repeated read a desirable chosen action. Conversely, a failed
rollout may begin with a precise diagnosis and correct edit, then fail because
of a later formatting mistake. Terminal failure does not make the earlier
diagnosis a valid rejected action.

This is the same reason positive SFT no longer requires whole-task success. A
human-approved good prefix may come from a failed trajectory, while a
successful trajectory may require repair or prefix truncation before receiving
positive supervision. Preference data needs the same discipline:

```text
trajectory outcome -> evidence about the complete run
action preference  -> reviewed claim about alternatives under one shared state
```

A terminal success/failure contrast can prioritize pairs for review, but it is
not sufficient by itself to authorize `A1 > A2`. The preference may instead be
established by:

- a human comparing the two actions under the shared context and a written
  rubric;
- a deterministic auditor that proves a narrow action property;
- an LLM judge operating under a pinned, audited comparison protocol;
- controlled branch evaluation in which both actions receive comparable
  downstream evaluation.

Each authority has a scope. A deterministic auditor that proves one tool call
is mechanically redundant does not prove that every aspect of the other action
is superior. A human judgment can be inconsistent or under-informed. An LLM
judge can prefer verbosity, ordering, or model-specific style and may reproduce
the same reward-hacking weaknesses as the policies being judged. Judge
disagreement or insufficient evidence should produce an ambiguous or review
outcome, not a forced preference label.

The self-deception trap is to treat a scalar terminal reward as if it contained
token- or action-level causal attribution. It does not.

### Source Models And The Reference Model Have Different Roles

Chosen and rejected actions do not need to originate from the same model. They
may come from different checkpoints, different model families, separate samples
from one model, human repair, or search. DPO trains a target model by scoring
both actions under the target and a frozen reference model; the models that
originally generated the candidates are provenance, not mathematical
participants in the loss.

The roles are distinct:

```text
source policy M1 -> produced candidate action A1
source policy M2 -> produced candidate action A2
target policy    -> being updated by preference training
reference policy -> frozen anchor used by the DPO objective
```

Cross-model candidate pairs are valid only when both actions are alternatives
under the same exact model-visible context, branch-point environment state, and
action protocol. Both must also be representable by the target model's pinned
serialization and tokenizer.

Different source models create a separate evidence risk. If M1 generates the
rest of branch one and M2 generates the rest of branch two, a terminal outcome
difference reflects the first actions plus every later decision made by two
different continuation policies. A continuation policy is the model and
decoding process that selects subsequent actions from each branch-specific
history. Therefore terminal success alone cannot isolate whether `A1` or `A2`
was better.

Using the same source model does not automatically solve this problem: sampling
randomness and divergent observations still affect later behavior. Controlled
continuations, repeated branch evaluations, or direct action judgment can make
the evidence stronger.

Cross-model pairing can also leak easy style shortcuts. If every chosen action
comes from M1 and every rejected action comes from M2, the learner may identify
verbosity, formatting, or phrasing associated with M1 rather than learn the
intended behavioral distinction. Source identity must therefore remain visible
for dataset analysis even though source-model equality is not an eligibility
rule.

### Positive SFT And DPO Encode Different Training Claims

Positive SFT is supervised imitation. Given one approved assistant action, it
maximizes the likelihood of its tokens under their real preceding context:

```text
positive-SFT loss =
  negative sum of approved assistant-token log probabilities
```

It has no rejected alternative, preference margin, reference policy, scalar
reward, critic, or online environment interaction. It is supervised
post-training rather than reinforcement learning.

DPO consumes a chosen and rejected action under one shared context. It changes
their relative likelihood while anchoring the update to a frozen reference
model. DPO is derived from a KL-regularized RLHF objective, but its optimization
uses an offline supervised-style pairwise loss. It does not require PPO, a
separate learned reward model, a critic, or online policy-gradient rollouts.

The distinction is:

```text
positive SFT -> make this approved action more likely
DPO          -> make this chosen action more likely relative to this rejected action
online RL    -> sample actions and optimize using observed reward signals
```

Calling all three simply “post-training” is convenient operationally but hides
their different data contracts and credit-assignment assumptions.

### The DPO Preference Margin Is Reference-Adjusted Relative Movement

For one shared context `C`, DPO separately scores the chosen and rejected
assistant actions. An action score is the sum of log probabilities of its
model-generated tokens; context and tool-observation tokens condition those
probabilities but are not themselves action-score terms.

The reference-adjusted shifts are:

```text
chosen_shift =
  log p_target(chosen | C) - log p_reference(chosen | C)

rejected_shift =
  log p_target(rejected | C) - log p_reference(rejected | C)

preference_margin = chosen_shift - rejected_shift
```

A positive margin means the target has moved toward the chosen action relative
to the rejected action compared with the reference policy. A zero margin means
it preserves the reference model's relative preference, and a negative margin
means it has moved in the wrong direction. DPO applies a logistic loss that
pushes this margin upward.

The chosen action does not need to begin with a larger raw probability than the
rejected action. The margin measures relative movement from the reference, not
an isolated chosen-action likelihood. This is why DPO is not merely positive
SFT on the chosen side plus a metadata label saying the other side was bad.

Action-level comparison reduces trajectory-length confounding but does not
eliminate sequence-length effects entirely: the likelihood of each assistant
action still sums over its tokens. Length, formatting, and verbosity therefore
remain pair-quality dimensions to inspect rather than reasons to abandon the
shared-context invariant.

### Preference Discovery Admits Trustworthy Evidence, Not Only Good Behavior

Preference data requires actions that may eventually become both chosen and
rejected. Requiring task success, a completed score, or prior behavioral
acceptance before discovery would preferentially remove the mistakes that make
preference learning possible.

The admission question is therefore:

```text
Did this action really occur under trustworthy, non-leaky conditions?
```

It is not:

```text
Was this action successful or already judged desirable?
```

A failed task, malformed action, mechanically redundant call, or confirmed
reward-hack attempt may be useful comparison evidence. None automatically
becomes the rejected side. Preference direction still requires a reviewer or
auditor that can justify the local comparison.

Harness and data-integrity failures are different. An orchestration failure,
missing observation, invalid split, or incomplete detector run can make the
record untrustworthy rather than merely bad behavior. Those conditions remain
discovery exclusions.

### Rejected Preference Text Must Still Be Free Of Private Leakage

Calling one action `rejected` does not make its bytes harmless. DPO evaluates
both chosen and rejected completions under the target and reference policies;
both sides participate in the loss. A rejected completion containing a secret,
hidden validator, or private transcript can still expose and potentially teach
that content.

The safe distinction is:

```text
real non-leaky exploit attempt -> possible rejected preference evidence
actual private/evaluator leak  -> forbidden from ordinary preference training
```

Negative direction is not a privacy mechanism.

### A Repaired Transcript Is Not Executed Rollout Evidence

A deterministic repair can create a valid positive-SFT target when its narrow
transformation contract is proven. It cannot retroactively establish what the
environment or policy would have done after the edited action sequence.

For example, deleting a redundant tool call changes the history on which every
later action is conditioned. Reusing the original suffix as if it had followed
the repaired prefix would assert an unexecuted counterfactual continuation.

Therefore preference discovery starts from original prompt-loop trajectories.
A repaired action can become rollout evidence only if it is re-executed and
recorded as a new trajectory under its real resulting state.

### Repeated Actions Are Evidence Multiplicity; Distinct Actions Are Alternatives

Suppose ten rollouts contain the same shared context `C` and the same assistant
action `A`. They are ten observations of one alternative, not ten different
actions. Producing duplicate `C, A` training rows would overweight sampling
frequency without adding a new behavioral choice.

If the ten actions are all distinct, there are instead up to:

```text
10 choose 2 = 45
```

valid unordered comparisons to review. Those 45 comparisons remain highly
correlated because they share one context. A trustworthy report must preserve
both accepted-pair count and unique-shared-context count; combinatorial growth
must not masquerade as independent dataset diversity.

### Shared Context Requires Logical Content And Environment State

Random message IDs identify occurrences, so separately sampled rollouts can
have different IDs while presenting identical content to the policy. They must
not be used as context equality. Conversely, matching message text alone is
insufficient when a tool has silently changed the workspace.

An agentic shared decision state needs at least:

```text
same task hashes
same harness/tool runtime
same ordered logical-message hashes through C
same canonical workspace hash before the action
```

Source model identity and decoding policy remain provenance rather than an
equality rule. This allows actions sampled from different models to be compared
under the same logical state while retaining enough evidence to detect style or
continuation-policy confounds later.

### Review Abstention Is A Data-Quality Decision, Not A Missing Label

A preference reviewer is not required to force every comparison into chosen
and rejected sides. When the evidence does not isolate which local action is
better, `ambiguous` is the truthful result. When the alternatives are
semantically equivalent, `tie` is the truthful result. Neither state should be
silently converted to a directional pair to meet a dataset-size target.

This creates a useful fail-closed boundary:

```text
explicit preferred decision -> may become a preference pair
tie                         -> no directional training claim
ambiguous                   -> no directional training claim
invalid                     -> unusable comparison
```

The self-deception trap is to treat reviewer coverage as the objective. A
larger fully labeled dataset can contain more invented certainty than a smaller
dataset with principled abstentions.

### Successful Materialization Proves Representation, Not Authorization

Deterministically rebuilding token records can prove that source references
resolve, templates and tokenizer bytes are pinned, ownership masks are
well-defined, sequence limits are respected, and chosen/rejected branches share
the claimed prompt. These are necessary representation invariants.

They do not prove that the source evidence was acquired under the current
trusted harness, that a record should be authorized for training, or that
training on it will improve behavior. Those are separate trust, policy, and
empirical claims:

```text
materialization success -> the approved claim has a reproducible token form
evidence trust          -> every required source and runtime gate passes
training authorization  -> policy permits a trainer to consume the artifact
training efficacy       -> a controlled post-training evaluation shows change
```

Conflating these levels turns a clean serialization audit into an unsupported
claim about data safety or model quality.

### Re-Derivation Cannot Repair Stale Source Provenance

A derived artifact may be rebuilt perfectly under new code while still relying
on trajectories acquired under an older harness runtime. The new derivation
can validate its own transformation, but it cannot retroactively show that the
old acquisition would have behaved identically under the new runtime.

Provenance trust flows from sources to derivatives. It does not flow backward:

```text
stale acquisition + current deterministic derivation
  -> useful development artifact
  -> not current-runtime trusted evidence
```

The evidence remedies are to retain the mismatch or reacquire after the runtime
is frozen. Rehashing or re-exporting the old evidence is not reacquisition. A
scope-limited owner may separately accept that known risk and authorize a
non-production exercise, but that policy exception must not relabel the source
as trusted.

### Authorization Is Permission; Trust Is Evidence

It is useful to default authorization from trust gates, but the concepts are
not identical. Trust is an evidence claim about how an artifact was produced.
Authorization is a policy decision about whether a particular consumer may use
it. In a production path, policy should normally require all trust invariants.
In a learning lab, an owner may knowingly accept a documented mismatch to
exercise the trainer.

The safe override preserves both truths:

```text
source runtime mismatch: still present
normal trust gate: still failed
learning-lab trainer permission: explicitly granted
production suitability: not claimed
```

Simply replacing `not_authorized` with `authorized` would erase why the normal
gate failed and make later readers infer stronger evidence than exists. An
atomic override identity and reason preserve the exception's scope and prevent
authorization from becoming provenance laundering.

### LoRA Compresses The Learned Update, Not The Base Model

Parameter-efficient fine-tuning (PEFT) is a family of adaptation methods;
LoRA is one PEFT method. For a selected pretrained weight matrix `W`, ordinary
full fine-tuning may learn an unconstrained update having the same shape as
`W`. LoRA freezes `W` and learns the update through two smaller matrices:

```text
W:  d_out x d_in
A:  r x d_in
B:  d_out x r

delta_W = (alpha / r) B A
adapted_W = W + delta_W
```

The rank of a matrix is the number of independent directions in its linear
transformation, equivalently the dimension of its output space. Because the
LoRA update passes through an `r`-dimensional bottleneck:

```text
rank(delta_W) <= r
```

For `r = 1`, the update has the form `b a_transpose`. It first measures how
much an input points along direction `a`, producing one scalar, and then
changes the output along direction `b`. Rank `r` permits up to `r` such
intermediate directions. "Low-rank" means that `r` is much smaller than
`min(d_in, d_out)`; it is not another name for merely having fewer scalar
parameters.

Crucially, LoRA makes no claim that the pretrained matrix is low-rank. The
three ranks are different facts:

```text
rank(W)         may be 4096
rank(delta_W)   may be at most 8
rank(adapted_W) may still be 4096
```

The hypothesis is that an already capable model can be adapted by changing a
small number of directions, not that the knowledge in the original model fits
in that small subspace. Conflating these claims makes LoRA sound as though it
replaces a rich base transformation with a tiny one; it actually overlays a
constrained correction on that transformation.

The parameter saving follows from the factorization. For one `4096 x 4096`
weight matrix:

```text
unconstrained full update: 4096 * 4096             = 16,777,216 parameters
rank-8 LoRA update:        8 * 4096 + 4096 * 8     =     65,536 parameters
```

Only `A` and `B` receive optimizer updates, but the frozen base weight still
participates in the forward computation and in propagating gradients to the
adapters. "Frozen" therefore means "not updated," not "absent from training."
The smaller trainable state reduces gradient storage, optimizer state,
distributed gradient communication, and per-adaptation checkpoint storage.
It does not eliminate most base-model computation or all activation memory.

Loss ownership and LoRA answer orthogonal questions:

```text
loss mask -> which token errors are allowed to create a learning signal?
LoRA      -> which parameters are allowed to respond to that signal?
objective -> what learning signal is computed, such as SFT or DPO?
```

The same LoRA parameterization can therefore be used with positive SFT, DPO,
or another objective. It does not itself determine which behavior is good or
which assistant tokens should receive loss.

LoRA also does not make the base model disappear at inference. If a toy base
model has 100 parameters and its adapter has 10, unmerged serving needs the
100 base parameters plus the 10 adapter parameters and computes both branches:

```text
y = W x + (alpha / r) B(Ax)
```

Alternatively, the adapter can be merged before serving:

```text
adapted_W = W + (alpha / r) B A
y = adapted_W x
```

The merged matrix has the original dense shape, so this can remove the adapter
branch's small latency overhead, but serving still requires a full base-sized
model. The adapter is small; the adapted policy is not a ten-parameter model.
QLoRA addresses a different bottleneck by storing the frozen base weights in a
quantized representation while training higher-precision LoRA adapters.

The durable distinction is:

```text
LoRA reduces adaptation cost and adaptation artifact size.
It does not by itself reduce the underlying model's inference size.
```

### LoRA Target Coverage Is An Experimental Hypothesis, Not A Compute Default

Choosing where to attach LoRA is not one decision called "adapter size." At
least four distinct choices are involved:

```text
target coverage -> which weight matrices may change
depth coverage  -> which repeated transformer blocks may change
rank            -> dimensionality available to each low-rank update
scale           -> strength with which each learned product enters the model
```

Available memory and compute constrain these choices, but they do not determine
which choice is correct. If compute were unlimited, full fine-tuning would
become another candidate; it would not prove that updating every parameter is
better for a small or narrow dataset. Broader trainable capacity can fit more
behavior, but it can also memorize the training set, disturb useful pretrained
behavior, and make a weak evaluation look convincing.

The common target scopes in a dense decoder illustrate the different
hypotheses:

```text
query + value projections   -> narrow historical LoRA baseline
all attention projections   -> adaptation throughout attention
attention + MLP projections -> adaptation throughout transformer-block linears
embeddings or output head   -> separate vocabulary/output-distribution decision
```

Descriptions such as "attention changes routing" and "MLPs change features"
are useful intuitions, not causal guarantees about where tool use, reasoning,
or instruction following lives. Those behaviors emerge from interacting
components across depth. Arbitrarily adapting only late layers, or only query
and value projections, therefore introduces an inductive assumption that must
be tested rather than presented as architectural fact.

The original LoRA experiments made narrow attention targeting a familiar
default. The [QLoRA experiments](https://arxiv.org/abs/2305.14314) later found
that covering all linear transformer-block layers was important for matching
full fine-tuning in their setting. This supports all-block-linears as a strong
baseline, not as a universal theorem. Applying that target pattern to an
unquantized base is still ordinary LoRA; QLoRA specifically adds quantized
storage and computation for the frozen base weights.

Controlled comparisons must also say what is being held constant. A same-rank
comparison answers which complete practical configuration works better, but
the broader target also receives more trainable parameters. An approximately
parameter-matched comparison asks a different question about where a similar
capacity budget should be distributed. For the pinned Qwen model, for example:

```text
q_proj + v_proj at rank 64:       14,745,600 adapter parameters
all attention at rank 32:         14,745,600 adapter parameters
all block linears at rank 8:      14,966,784 adapter parameters
```

Even this comparison is not perfectly assumption-free: target coverage and
rank distribution necessarily change together. The correct conclusion is not
that one experiment isolates a timeless property, but that its controlled
variables and remaining confounds are visible.

Training loss is especially weak evidence for selecting among these scopes.
A higher-capacity adapter may simply memorize the supervised examples more
quickly. Target selection requires an unchanged base-model comparison and
heldout behavioral evaluation; multiple seeds become important once the goal
advances beyond verifying that the training path works.

### LoRA Optimizes Two Factors, While The Model Experiences Their Product

LoRA does not directly optimize the effective weight update. It parameterizes
that update through two trainable matrices:

```text
scale = alpha / r
delta_W = scale * B A
adapted_W = W + delta_W
```

The map from `(A, B)` to `B A` is bilinear. It is linear in either factor when
the other is fixed:

```text
B (2A) = 2 B A
(2B) A = 2 B A
```

It is not jointly linear in both factors:

```text
(2B) (2A) = 4 B A

(B1 + B2) (A1 + A2)
  = B1 A1 + B1 A2 + B2 A1 + B2 A2
```

The cross terms matter for optimization. A learning rate controls the
optimizer's separate steps in `A` and `B`; it is not a direct learning rate on
`delta_W`. The gradient of each factor also depends on the current value of the
other factor. Consequently, changing a forward scale and changing the optimizer
learning rate can have related effects without producing identical training
dynamics.

The standard initialization makes this concrete:

```text
A = small random values
B = zero
delta_W = zero
```

Initially, `B` can receive a gradient because `A` is nonzero, while `A` receives
no gradient through the zero `B`. After `B` moves away from zero, both factors
can learn. Under a plain first SGD step, with `G` denoting the loss gradient at
the effective weight:

```text
gradient_B = scale * G * A_transpose
B_after_step = -learning_rate * scale * G * A_transpose

delta_W_after_step
  = scale * B_after_step * A
  = -learning_rate * scale^2 * G * A_transpose * A
```

This example is deliberately simplified, but it shows why doubling `scale` is
not generally equivalent to doubling the learning rate. Adam, clipping, weight
decay, schedules, and later updates make the relationship still less exact.
The [original LoRA paper](https://arxiv.org/html/2106.09685#S4) describes tuning
the scaling constant as *roughly* equivalent to tuning learning rate when
initialization is adjusted appropriately; the qualification is important.

The scaling factor is therefore not required for LoRA's expressive power. A
fixed nonzero scale can be absorbed into one factor. It is an optimization and
normalization convention. Keeping it separate from optimizer learning rate is
useful because the controls act at different boundaries:

```text
learning rate -> optimizer motion in the stored A and B parameterization
scale         -> contribution of their product to the model's forward function
```

The learning rate exists only during training. The scale remains part of the
trained adapter's meaning at inference and determines the contribution merged
into the base weight. It also gives rank changes an explicit normalization
policy, permits a common optimizer schedule across adapters, and makes adapter
strength visible rather than hiding it in the norms produced by a particular
initialization and training run.

These benefits do not make scale and learning rate fully independent
hyperparameters. They are strongly coupled, and under particular
initialization and optimization assumptions one can partially compensate for
the other. The value of the separate scale is that it defines the function
represented by fixed adapter tensors, while the learning rate defines how the
optimizer searches for those tensors. Treating the two as identical confuses
function-space magnitude with parameter-space motion.

Rank and scale must not be changed accidentally in the same experiment. If
`alpha` remains fixed while `r` increases under conventional LoRA, then
`alpha / r` decreases; an observed difference can no longer be attributed to
rank alone. The lab therefore holds the explicit forward scale constant across
rank comparisons:

```text
alpha / r = 1
alpha = r
```

This value is a transparent experimental invariant, not a claim that scale one
is universally optimal. Adapter rank controls the dimensionality available to
the update, target coverage controls where updates can enter the network,
forward scale controls how strongly their product participates, and learning
rate controls optimizer motion in factor space. Treating those four choices as
one vague "LoRA size" knob makes ablation results uninterpretable.

### A Loss Mask Selects Prediction Errors, Not Model Context

Three different masks or alignments are easy to conflate in causal-language-
model SFT:

```text
causal mask     -> a position may attend only to allowed earlier positions
attention mask  -> real tokens are visible; padding tokens are not
loss labels     -> selected next-token predictions contribute cross-entropy
```

For the initial positive-SFT policy, the important combinations are:

| Token role | Attention mask | Training label | Meaning |
| --- | ---: | ---: | --- |
| System, user, or tool observation | `1` | `-100` | Visible context, no direct loss term |
| Approved assistant-generated token | `1` | That token's id | Visible context and supervised target |
| Batch padding | `0` | `-100` | Neither visible context nor a target |

Changing a context token's attention mask to zero would remove information from
the model. Assigning it label `-100` does not remove it: the model may still use
that token to predict every later supervised assistant token. This is why
"masked token" should be read as "loss-masked token," not "token hidden from
the model."

#### The causal shift

A causal model emits one vocabulary distribution at every input position. The
distribution emitted after position `t` predicts the token at position `t+1`.
Trainer APIs conventionally accept `labels` aligned with `input_ids`, then
perform the one-position shift inside the causal-LM loss.

Consider this toy serialized transcript:

| Position | Token | Token id | Stored label |
| ---: | --- | ---: | ---: |
| 0 | system token | 10 | `-100` |
| 1 | user token | 20 | `-100` |
| 2 | question terminator | 21 | `-100` |
| 3 | assistant token `4` | 40 | `40` |
| 4 | assistant token `!` | 41 | `41` |
| 5 | assistant end-of-turn | 99 | `99` |

The stored arrays are:

```text
input_ids = [10,   20,   21, 40, 41, 99]
labels    = [-100, -100, -100, 40, 41, 99]
```

The causal loss pads the labels on the right and shifts them left relative to
the logits. The comparisons actually made are:

| Logit position | Context ends with | Shifted target | Direct loss? |
| ---: | --- | ---: | --- |
| 0 | system token | `-100` | no |
| 1 | user token | `-100` | no |
| 2 | question terminator | `40` | yes: predict first assistant token |
| 3 | assistant `4` | `41` | yes: predict next assistant token |
| 4 | assistant `!` | `99` | yes: predict assistant end-of-turn |
| 5 | end-of-turn | padded `-100` | no |

Equivalently:

```text
shifted_labels = [-100, -100, 40, 41, 99, -100]
```

This is why checking the unshifted mask alone is insufficient. A one-position
mistake could train on the last user token, omit the first assistant token, or
teach the model to continue after the intended end of turn.

Suppose the model assigns these probabilities to the correct targets at the
three supervised comparisons:

```text
p(40 | tokens 0..2) = 0.50
p(41 | tokens 0..3) = 0.25
p(99 | tokens 0..4) = 0.80
```

With the usual mean reduction over non-ignored targets:

```text
loss_40 = -log(0.50) = 0.6931
loss_41 = -log(0.25) = 1.3863
loss_99 = -log(0.80) = 0.2231

total_loss = (0.6931 + 1.3863 + 0.2231) / 3
           = 0.7675
```

The denominator is three supervised token targets, not six sequence tokens.
At an ignored logit position, the direct derivative of the loss with respect
to that position's logits is zero. PyTorch's `ignore_index=-100` implements
this omission, and the pinned Transformers causal-LM loss performs the shift
before applying that cross-entropy.

#### Direct loss and indirect influence are different

The zero direct derivative at an ignored prediction position does not imply
that its input token has no effect on gradients. In a causal transformer, the
representations of earlier context tokens supply keys and values used by later
assistant positions. A supervised loss at a later position can therefore send
a gradient backward through attention to computations involving earlier
system, user, and tool-observation tokens.

The distinction is:

```text
predicting a context token itself -> no supervised error term
using that context to predict an assistant token -> part of the gradient path
```

If the user token in the toy example changed, the probabilities assigned to
tokens `40`, `41`, and `99` could change, so the supervised loss could change.
That is intended: the model must learn the assistant behavior *conditional on*
the user request. What positive SFT avoids is teaching the model to generate
the user request or the environment's tool observation.

The same assistant token can have both roles. Its own identity may be a direct
supervised target, and after it is present in the prefix it becomes context for
predicting the next assistant token. Token-level causal loss therefore creates
many next-token learning signals from one transcript without treating each
message as an independent example.

#### A frozen token embedding does not freeze its contextual representation

The phrase "a context token receives gradient" can hide four different objects:

```text
token id                 -> a discrete integer in the serialized input
embedding row            -> a persistent parameter looked up for that id
contextual representation -> a temporary activation produced at a model layer
adapter weights          -> persistent trainable parameters used in that computation
```

The token id is data and cannot receive an optimizer update. A hidden-state
activation can have a nonzero derivative during backpropagation, but it is not
a persistent parameter: it is discarded after the training step. The optimizer
updates only trainable parameters reached by that derivative.

Under LoRA, the base embedding table and base transformer weights are normally
frozen. The initial embedding lookup for a system token therefore remains
identical:

```text
system_token_id = 10
embedding_before = frozen_embedding_table[10]
embedding_after  = frozen_embedding_table[10]

embedding_before == embedding_after
```

That fixed vector is subsequently processed by layers whose effective linear
maps include trainable adapters:

```text
effective_weight = frozen_weight + adapter_update
contextual_state = effective_weight * preceding_state
```

After the adapter changes, the same fixed input can produce a different
activation. In a scalar toy layer:

```text
frozen embedding e = 2
frozen base weight w = 3
LoRA factors a = 1 and b = 0 at step 0

state_before = (w + b*a) * e
             = (3 + 0*1) * 2
             = 6
```

Suppose assistant-token loss propagates through this system-token computation
and the optimizer changes only `b` to `-0.25`:

```text
state_after = (w + b*a) * e
            = (3 - 0.25*1) * 2
            = 5.5
```

The token id is still `10`, the frozen embedding is still `2`, and the frozen
base weight is still `3`. Only the adapter changed, yet the contextual state is
now `5.5` instead of `6`. Later assistant positions can attend to the keys and
values derived from that changed state, so their predicted distributions can
also change.

This is precisely how a loss-masked system instruction can shape learning. The
model is not trained to reproduce the instruction as an output target. Instead,
assistant-token losses teach the trainable adapters how that instruction should
affect later assistant behavior:

```text
system-token label is ignored
-> no direct error for predicting the system token
-> system-token computation influences a supervised assistant prediction
-> backward signal passes through that computation
-> adapter parameters on the path may be updated
-> the same instruction can induce different future behavior after training
```

The raw embedding and any computation before the first adapted operation remain
unchanged. Contextual states downstream of adapted operations may change. It is
therefore more precise to say that activations *carry gradients* and parameters
*receive updates*; tokens themselves do neither.

### Frozen Parameters Can Transmit Gradient Without Receiving Updates

"Frozen" means that a parameter is not an optimization variable. It does not
mean deleting its operation from the forward pass, detaching its output, or
running the whole frozen model under `no_grad`.

For a frozen linear transformation:

```text
y = W_frozen x
```

backpropagation may still need the value of `W_frozen` to carry the downstream
gradient to an earlier trainable component:

```text
gradient_x = W_frozen_transpose * gradient_y
```

What freezing suppresses is accumulation and optimization of the parameter's
own gradient:

```text
W_frozen.requires_grad = false
W_frozen.grad = None
W_frozen is absent from optimizer parameter groups
```

The mathematical derivative with respect to `W_frozen` exists, but the training
runtime need not construct or store it. PyTorch records the parts of the graph
needed to reach leaves with `requires_grad=true`; intermediate vector-Jacobian
products can pass through operations involving frozen values without producing
a `.grad` tensor for those frozen parameter leaves.

This differs from wrapping the base forward pass in `torch.no_grad()` or
calling `detach()` at a block boundary. Those operations can sever the graph
and prevent the loss from reaching adapters earlier in the network. Parameter
freezing is selective; no-grad execution is a graph-level operation.

Also, intermediate activations normally do not retain a public `.grad` field
unless explicitly requested. Observing `activation.grad is None` is therefore
not proof that the gradient path was absent. Gradient flow is established by
the dependency graph, adapter gradients, and resulting updates—not by expecting
every intermediate tensor to retain a gradient buffer.

#### Worked two-layer LoRA example

Take a scalar two-layer network with one rank-one LoRA adapter at each layer
and scale one:

```text
h = (w1 + b1*a1) * x
y = (w2 + b2*a2) * h
loss = 0.5 * (y - target)^2
```

Use:

```text
x = 2
target = 20

w1 = 3    frozen
w2 = 4    frozen

a1 = 1    trainable
a2 = 1    trainable
b1 = 0    trainable
b2 = 0    trainable
```

The zero `b` factors make both effective LoRA updates zero at step 0. The
adapter-enabled model is therefore initially identical to the frozen base:

```text
h = (3 + 0*1) * 2 = 6
y = (4 + 0*1) * 6 = 24
loss = 0.5 * (24 - 20)^2 = 8
```

Start backward propagation at the supervised output:

```text
gradient_y = y - target = 4
```

At layer 2:

```text
gradient_b2 = gradient_y * a2 * h
            = 4 * 1 * 6
            = 24

gradient_a2 = gradient_y * b2 * h
            = 4 * 0 * 6
            = 0
```

The gradient that continues through the second layer to `h` uses the frozen
base value `w2`:

```text
gradient_h = gradient_y * (w2 + b2*a2)
           = 4 * (4 + 0)
           = 16
```

That transmitted gradient reaches the adapter in layer 1:

```text
gradient_b1 = gradient_h * a1 * x
            = 16 * 1 * 2
            = 32

gradient_a1 = gradient_h * b1 * x
            = 16 * 0 * 2
            = 0
```

The mathematical derivatives with respect to the frozen weights would be:

```text
derivative_with_respect_to_w2 = gradient_y * h = 24
derivative_with_respect_to_w1 = gradient_h * x = 32
```

But because `w1` and `w2` are frozen leaves, the runtime does not accumulate
those values into `w1.grad` or `w2.grad`, and the optimizer cannot update them.
Their values still carried the error signal to both adapters.

With plain SGD and learning rate `0.01`, the first update is:

```text
b1 = 0 - 0.01*32 = -0.32
b2 = 0 - 0.01*24 = -0.24
a1 = 1 - 0.01*0  =  1
a2 = 1 - 0.01*0  =  1
```

The next forward pass is:

```text
h = (3 - 0.32) * 2 = 5.36
y = (4 - 0.24) * 5.36 = 20.1536
```

The example happens to reduce the loss sharply, but loss reduction is not the
point of the example and is not an operational smoke-success requirement. The
important observations are:

```text
the loss reached adapters in both layers
the frozen second layer transmitted gradient to the first adapter
the zero-initialized b factors changed on the first step
the a factors correctly had zero first-step gradients
w1 remained exactly 3 and w2 remained exactly 4
```

On later steps, nonzero `b1` and `b2` allow `a1` and `a2` to receive gradients.
Requiring every LoRA factor to have a nonzero gradient on the first backward
pass would therefore incorrectly reject standard initialization. A stronger
qualification check spans at least two optimizer steps: every intended logical
adapter must be connected, receive finite gradient evidence when mathematically
expected, and change in at least one factor.

That detailed inspection is qualification evidence, not an operation that must
run throughout a long training job. Inspecting every parameter tensor and
bringing each reduction result back to the host can repeatedly synchronize the
accelerator and substantially reduce throughput.

Qualification steps also change the adapter and optimizer state. Treating those
same steps as the beginning of the real run makes diagnostic work an implicit
part of the learned checkpoint. A cleaner boundary is to qualify one setup,
discard it, reconstruct the setup from the same pinned base, configuration, and
seed, and require the fresh initial hashes and optimizer membership to match.
Real training can then start at step 0 without detailed tensor inspection. The
extra short run buys a sharper claim:

```text
qualified setup -> proved that this exact initialization and wiring can learn
discarded state -> diagnostic updates do not become hidden training warmup
fresh setup      -> exact initial state matches what was qualified
real training    -> begins at step 0 under ordinary runtime checks
```

Ordinary training can retain cheap continuous health checks such as finite loss
and finite aggregate gradient norm. Exact frozen-base comparison and adapter
save/reload checks belong at run boundaries. This keeps three different claims
separate:

```text
qualification: the intended fresh trainable setup is wired and updates
runtime health: real optimization has not become numerically invalid
boundary integrity: initialization parity, frozen state, and persisted adapter semantics are correct
```

### Operational Training Success Is Not Training Efficacy

These mechanics define whether a training operation really occurred:

```text
nonempty supervised-token set
correct shifted masked loss
finite backward pass connected to intended adapters
adapter-only optimizer ownership
changed adapter state
unchanged frozen state
correct save and reload
```

They do not establish that the model improved. A smoke run need not have a
monotonically decreasing loss, beat the base policy, or generalize to heldout
tasks to satisfy the operational contract. Requiring such an outcome would
encourage hyperparameter tuning against what should be an implementation
check. Efficacy remains a separate paired evaluation claim made only after the
training and evaluation policy is frozen.

Sources for the library semantics used above:

- [PyTorch `CrossEntropyLoss` and `ignore_index`](https://docs.pytorch.org/docs/stable/generated/torch.nn.CrossEntropyLoss.html)
- [Transformers 4.57.3 causal-LM loss shift](https://github.com/huggingface/transformers/blob/v4.57.3/src/transformers/loss/loss_utils.py)
- [PyTorch autograd mechanics and parameter freezing](https://docs.pytorch.org/docs/stable/notes/autograd)
- [PEFT LoRA scaling, initialization, and forward path](https://github.com/huggingface/peft/blob/v0.18.0/src/peft/tuners/lora/layer.py)
