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
own layer but cannot erase an upstream split, leakage, reward-hack, or harness
blocker.

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
