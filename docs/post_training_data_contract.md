# Post-Training Data Contract

## Purpose

This document defines when an evaluated agent trajectory may be considered for
post-training and what additional transformation is required before a trainer
may consume it.

The central boundary is:

```text
trusted trajectory evidence
  -> reviewed training candidate
  -> objective-specific dataset record
  -> serialized tokens or comparison pair
  -> training loss
```

Passing an evaluation does not make a trajectory trainable. Conversely, an
unsuccessful trajectory can still be useful as labeled negative or adversarial
evidence. Neither fact determines which tokens should receive loss.

Week 9 is a data-contract and filtering exercise. This contract does not claim
that the current data improves a model or supports an unbiased post-training
evaluation.

## Authorities And Responsibilities

Each layer answers a different question:

| Layer | Authoritative question |
| --- | --- |
| Eval and trajectory artifacts | What happened, under which task, policy, harness, and scorer? |
| Harness audit and control calibration | Was the measurement system trustworthy for these exact tasks and harness bytes? |
| Human review | Is the trajectory acceptable for the downstream uses being considered? |
| `TrainingCandidateRecord` | Which broad data uses are permitted by the current policy? |
| Dataset builder | What exact example, negative record, or comparison pair is valid for one objective? |
| Serializer and loss mask | Which model-visible tokens are context and which assistant tokens receive loss? |

These layers must not silently substitute for one another. In particular:

```text
task success != training eligibility
training eligibility != a constructed training example
a valid dataset row != a valid token-level loss
```

`TrainingCandidateRecord.content_eligibility` is the single authority for
broad positive-SFT, negative-example, preference-data, and analysis use. A
downstream builder may apply stricter objective-specific rules, but it must not
override a denied use.

## Fail-Closed Trust Root

Final training-data release requires one current, mutually consistent trust
root:

- the harness-audit artifact has aggregate, agent-layer, and scorer-layer
  status `PASS`;
- the audit case hashes and complete harness runtime hash still match the
  current repository;
- control calibration has `overall_match=true` and stable flake detection;
- the calibrated task ids and task-manifest hashes match the source eval;
- required public-check idempotency calibration is present for declared
  idempotent checks;
- trajectory and review manifests and JSONL payloads match their pinned hashes;
- the task manifest, split lock, eval config, and referenced trajectory
  artifacts match their recorded hashes.

If this trust root is missing, failed, stale, or mismatched, the pipeline must
produce no training-authorized release. Hash-pinned candidate, review, source,
and materialization artifacts may still be constructed for development, but
they must remain explicitly `not_authorized` and must not be consumed by a
trainer.

Raw audit and eval artifacts may still be inspected to diagnose and repair the
harness. That debugging activity is outside the training-data pipeline.

## Allowed Sources

The current implemented training source is a model-generated agent trajectory
whose policy type is `agent_model`.

The trajectory must:

- come from the `practice` or `dev` split recorded in its hash-pinned task
  manifest and split lock;
- have an accepted trajectory review;
- contain the required agent attempt id, task view, task-run result,
  prompt-loop result, and decoding configuration;
- contain no detected canary or hidden-validator exposure in model-visible
  evidence;
- contain no harness orchestration failure;
- have a complete reward-hack catalogue evaluation;
- remain linked to hash-pinned source artifacts.

An ordinary model-caused failure can still be interpretable. For example, a
malformed tool call or disallowed command may be useful negative evidence when
the harness correctly recorded it. This is different from an orchestrator
failure that makes the measurement itself untrustworthy.

### Sources Not Yet Supported

Human-repaired responses could eventually be useful, but they are not a
current allowed training source. Supporting them requires a distinct contract
that preserves:

- the original trajectory and response hashes;
- the repaired response hash;
- the repair author and review decision;
- the exact edited spans and reason;
- a model-compatible serialization of the repaired behavior.

Until that exists, editing a transcript in place must not turn a failed or
wasteful trajectory into a positive example.

This prohibition does not include the narrow deterministic mechanical repair
defined below. That repair is a reproducible dataset transformation which only
deletes already-proven redundant call/result pairs; it does not rewrite model
content or substitute a human-authored answer.

External datasets are also out of scope. The current records do not carry a
license contract suitable for importing or redistributing external data.

## Forbidden Sources And Uses

The following sources are forbidden from every trainable path:

- `heldout_private` trajectories;
- `public_calibration` trajectories;
- oracle patches, known-bad controls, and scripted agent controls;
- non-model policy trajectories;
- stale or hash-mismatched artifacts;
- trajectories produced under failed or missing harness calibration;
- trajectories with actual private-content or hidden-validator exposure;
- trajectories with harness orchestration failures;
- trajectories whose reward-hack evaluation is incomplete;
- trajectories missing required model-agent evidence;
- unreviewed, rejected, or `needs_followup` trajectories.

Controls calibrate the measurement system. They are not demonstrations of the
unique or ideal reasoning path and must not be promoted into chosen responses
without a separate, explicit demonstration-source contract.

Private leakage has a stronger rule than ordinary negative behavior:

```text
blocked attack without private exposure -> possibly labeled adversarial data
actual private exposure                 -> never copied into training data
```

A metadata-only candidate may remain useful for counting or failure analysis,
but leaked bytes must not be reproduced in a downstream dataset.

## Split And Contamination Rules

| Split | Training-data use | Evaluation interpretation after use |
| --- | --- | --- |
| `practice` | Allowed subject to all other gates | Diagnostic only; not evidence of generalization |
| `dev` | Allowed subject to all other gates | Diagnostic only; not evidence of generalization |
| `heldout_private` | Forbidden | Reserved for held-out measurement |
| `public_calibration` | Forbidden | Reserved for public calibration and harness checks |

The split recorded at trajectory creation is authoritative and hash-pinned. A
later task move must not retroactively reclassify an old trajectory.

Once any task, transcript, patch, preference, or repaired target is used for
training, evaluation on that task is contaminated for model-improvement
claims. Re-running the same `practice` or `dev` tasks can test plumbing or
memorization, but cannot demonstrate held-out improvement.

## Trace Quality Is Multi-Dimensional

Do not collapse trajectory quality into one `good` or `bad` label. The
following dimensions carry different meanings:

| Dimension | Relevant states | Meaning |
| --- | --- | --- |
| Task outcome | `scored_pass`, `scored_fail`, `cannot_grade` | Whether trusted scoring produced success, failure, or no grade |
| Runtime outcome | normal lifecycle, model/tool failure, orchestration failure | Whether behavior was interpretable versus the harness failing |
| Review | accepted, rejected, needs follow-up, not reviewed | Human data-use adjudication |
| Leakage | clear, canary leaked, hidden validators visible | Whether private evaluator information crossed the boundary |
| Reward hacking | `not_detected`, `ambiguous`, `confirmed`, incomplete evaluation | What the pinned detector catalogue found and how it was adjudicated |
| Mechanical redundancy | complete with no blocks, complete with blocks, incomplete | Whether immediate repeated tool actions were mechanically redundant under trusted state evidence |

`not_detected` means that the current pinned detector catalogue did not fire.
It is not proof that no exploit exists.

A successful trajectory may contain wasteful actions. A failed trajectory may
contain many useful actions. Outcome labels alone do not provide step-level
credit assignment.

## Positive SFT Contract

### Unit Of Data

One trainer-ready SFT example is not merely a transcript JSON object. It is:

```text
model-visible context
+ selected assistant-produced target spans
+ deterministic serialization and tokenization
+ a loss mask
+ hash-pinned source and transformation provenance
```

`PositiveSFTExampleRecord` is intentionally a source-level message record and
must not be described as trainer-ready. Its model-specific derivative,
`PositiveSFTTrainingMaterializationRecord`, persists the canonical `input_ids`,
aligned trainer labels, and pinned transformation provenance.

The initial trainer-ready representation uses trajectory aggregation: one
approved message prefix is serialized once, rather than expanded into one row
per assistant turn. Causal attention still gives every approved assistant token
its actual preceding prefix inside that sequence.

### Required Eligibility

A source candidate may enter positive-SFT prefix review only when:

- `content_eligibility.positive_sft_review_eligible` is true;
- the trajectory review is accepted;
- confirmed reward hacking is absent;
- any ambiguous reward-hack finding has an explicit human `cleared` decision.

It may produce a `PositiveSFTExampleRecord` only when:

- an objective-specific positive-SFT review accepts a contiguous prefix ending
  at one exact assistant message id;
- the output record passes a fresh leakage scan after transformation.

Public-check success, prompt-loop completion, a plausible final answer, or a
successful-looking patch is insufficient.

Task success is not a positive-SFT requirement. A trustworthy failed trajectory
may contain an accepted prefix before its earliest causal error, while a
successful trajectory may contain actions that should not be imitated. Task
outcome may prioritize scarce review effort, but the objective-specific prefix
review determines which assistant behavior is authorized for positive loss.

### Mechanical Redundancy

Mechanical-redundancy evidence is not itself a positive-SFT eligibility
decision. The positive-SFT transformation must nevertheless handle it
explicitly:

- a complete assessment with no blocks needs no redundancy-specific action;
- a complete assessment with blocks forbids the raw full-transcript example;
  only a validated deterministic repair may produce a positive-SFT derivative;
- an incomplete assessment must not be represented as "no redundancy" and
  blocks any claim that the raw transcript is a clean positive target.

The initial deterministic repair may only delete each detector-identified
redundant assistant tool call and its matching tool-result message. It must
retain the baseline call and result, preserve the order and typed values of
every other message, keep the source trajectory immutable, and carry
hash-pinned provenance sufficient to reproduce the transformation. The repaired
transcript must have valid call/result linkage and pass a fresh leakage scan. If
the matching result cannot be identified unambiguously or the transformed
message sequence is malformed, the example is rejected from positive SFT.

Repair records have a one-to-many relationship with training candidates. A
repair-export manifest contains one hash-pinned reference to its source
training-candidate export manifest. The referenced candidate manifest remains
authoritative for the candidate JSONL and its trajectory and review provenance;
the repair manifest does not duplicate those fields. Harness-audit and
control-calibration provenance enter only at final training-data release.

Each repair record carries the exact source training-candidate record hash plus
its trajectory and eval-attempt ids. Loading must locate the candidate by those
ids, require the record hash to match, and require the repair's original
mechanical-redundancy assessment to equal the candidate assessment. The ids are
join keys, while the hash and referenced export establish authority.

A record is created only for an actual repair attempt; there is no no-op repair
record. Absence is interpreted with the candidate assessment:

```text
complete assessment, zero blocks, no repair -> original transcript may proceed
complete assessment, blocks, no repair      -> positive SFT is blocked
complete assessment, blocks, valid repair   -> repaired transcript may proceed
incomplete assessment                       -> positive SFT is blocked
```

The initial repair statuses are:

- `completed`: a changed transcript artifact was persisted and its after-repair
  assessment is complete with zero blocks;
- `cannot_complete`: valid source evidence could not be transformed safely and
  the method-specific details contain a non-empty reason;
- `repair_error`: repair execution or persistence failed unexpectedly and the
  record contains an error class and message.

Non-completed repairs do not carry a repaired artifact or after-repair
assessment. Source artifact or candidate hash failures abort the repair export
rather than becoming per-record repair errors.

Every emitted repair record, including `cannot_complete` and `repair_error`,
has exactly one repair-review record. Candidates for which no repair was needed
have no repair record and therefore no repair review. The review artifact pins
the source repair-export manifest, and each review row carries both the
`repair_id` join key and the canonical hash of the exact source repair record.
Missing, duplicate, unknown, or hash-mismatched review rows invalidate the
review artifact.

Repair-review acceptance is scoped to the claim represented by the repair
record. For a `completed` repair, an accepted review may establish that the
transformation and resulting artifact are acceptable. For `cannot_complete`
or `repair_error`, acceptance means only that the recorded failure outcome is
accurate; it never supplies a repaired artifact or authorizes training use.
`not_reviewed`, `rejected`, and `needs_followup` do not satisfy the
repair-specific positive-SFT gate.

Consequently, a selected repaired transcript may enter positive-SFT review only
when the source candidate is independently positive-SFT-review eligible, the
exact selected repair record is `completed`, its repair review is accepted and
bound to that record hash, and the transformed output passes its downstream
validations. A repair review cannot clear source-level split, leakage, harness,
reward-hack, or trajectory-review blockers, and it cannot substitute for the
objective-specific positive-SFT prefix review.

One candidate may have multiple completed repairs. Positive-SFT review
initialization must select a specific `repair_id`; it must not choose implicitly
based on directory order, recency, or whichever record loads first. That
selection is pinned in the positive-SFT review source, not recorded as a
globally preferred repair in the repair artifact.

Each positive-SFT row distinguishes an `original` source from a `repaired`
source. Both forms pin the exact training-candidate record and transcript
artifact. A repaired row additionally pins the selected repair record and
repair-review record and records the accepted repair-review id. Its example id
is derived from the exact selected source rather than from `trajectory_id`
alone. The positive-SFT review manifest directly pins the candidate export and,
when used, the repair export and repair-review artifact. The positive-SFT export
manifest directly pins that review artifact and the output JSONL; the candidate
and repair chain remains transitively reachable rather than being redeclared.

A completed repair proves only that the declared deterministic transformation
was reproduced and validated. It does not change task outcome, human-review
state, reward-hack evidence, split, or candidate eligibility, and therefore
cannot upgrade an otherwise ineligible candidate into positive SFT.

For the current `mechanical_redundancy_deletion` method only, a positive-SFT
consumer may inherit the source trajectory's already trusted task-outcome
claim, whether pass or fail. This is valid because the repair deletes only a
call/result pair whose workspace state and normalized observation were proven
equivalent to a retained baseline, while every subsequent action remains
unchanged. The repair does not create a new outcome claim; it preserves the
authority of the source claim under a narrowly state-and-observation-preserving
transformation. That inherited outcome is provenance, not positive-SFT
authorization.

This inheritance is not a general property of `completed` repairs. Future
human, model, hybrid, or behavior-changing repairs require their own outcome
evidence or re-evaluation policy before they may support positive SFT.

Loss masking is not an accepted repair. Masking a redundant call gives it zero
direct SFT pressure, but the call and observation remain in the context for
later loss-bearing targets. That can normalize the wasteful behavior and alter
what the model learns to do next. The redundant call/result pair must be absent
from the positive-SFT derivative.

An auditable preference comparison may separately use the original redundant
action as rejected behavior. That is a different objective and does not make
the unmodified transcript a positive-SFT example.

The positive-SFT builder now implements this policy. A positive-SFT-review-
eligible candidate with a complete zero-block assessment uses its original
transcript. A candidate with blocks produces no review row unless the caller
explicitly selects a repair id. An explicit invalid selection is a hard error
rather than a silent exclusion. Loading a persisted positive-SFT export
revalidates its pinned candidate, repair, and review sources and
deterministically rebuilds the rows.

### Loss-Bearing Tokens

The intended default mask is:

| Token source | Present as context? | Receives SFT loss? |
| --- | --- | --- |
| System instruction | Yes | No |
| User task input | Yes | No |
| Valid chosen assistant tool call | Yes | Yes |
| Tool observation | Yes | No |
| Valid chosen assistant final response | Yes | Yes |
| Detector-identified redundant call and result | No; removed by deterministic repair | No |
| Scorer output, hidden validator, review metadata | No | No |

The positive-SFT prefix review, not task success, establishes which contiguous
assistant-message prefix is intended for imitation. The exported source record
ends at the accepted assistant-message boundary, so rejected or recovery
behavior after that boundary is absent rather than merely masked. Malformed
tool calls inside the accepted prefix and unhandled mechanical redundancy must
fail closed during serialization.

### Canonical Token Materialization

For SFT on a target checkpoint, tokenization must use that checkpoint's exact
compatible tokenizer artifacts and pinned revision. Token ids are the interface
to the model's embedding and output-head rows; ids produced by a different
model's tokenizer are not interchangeable. A trajectory collected from another
behavior model may still be used as message-level evidence, but its structured
messages must be canonically serialized for the target model.

The chat template and tool representation are a separate, also-pinned policy.
They should match the intended training and deployment interface. Deliberately
teaching a new template is possible, but it is a behavioral-format change and
must not be confused with swapping the tokenizer vocabulary.

For the initial Qwen2.5 target, the model-input protocol pins the immutable
checkpoint and tokenizer revision, tokenizer file hashes, exact upstream
chat-template bytes, required special-token assertions, and the message fields
that reach serialization. It defines two operations:

```text
generation serialization          -> append the assistant generation header
completed-transcript serialization -> include assistant content and end of turn
```

Assistant prefill and provider-native tool serialization are unsupported. The
current tool actions remain assistant JSON content, while tool observations are
structured messages projected through the pinned Qwen template.

For Qwen2.5-Coder-3B acquisition through Ollama, deployment serialization now
uses the same protocol record: AgentEnv renders the generation form and sends
the complete prompt through Ollama's native generate transport with provider
templating disabled. The protocol YAML is a hash-pinned transitive dependency
of the model config, and each model-run provenance artifact embeds the resolved
protocol record, source path, and observed source hash. This parity claim is
specific to the 3B protocol-backed path; it does not extend to model configs
that still use provider-owned OpenAI-compatible chat serialization.

The initial materialization policy is:

```text
one approved PositiveSFTExampleRecord
-> one canonical target-model chat serialization
-> one trajectory-aggregated input_ids sequence
-> labels equal input_ids on approved assistant spans
-> labels equal -100 on system, user, and tool-observation spans
```

If the canonical sequence exceeds `max_sequence_length`, the whole example is
excluded under an explicit overlength reason. It is not truncated, split into
arbitrary chunks, placed into overlapping windows, or summarized. Such
transformations would define a different context policy and require a separate
contract. Overlength exclusions must remain countable so the resulting bias
toward shorter trajectories is visible.

The materializer also fails an example explicitly when tokenizer normalization
changes the canonical rendering, decoded tokens do not reconstruct that
rendering, token offsets leave source characters uncovered, or one token crosses
a model/context ownership boundary. These are materialization-validity failures,
not overlength policy exclusions.

The materialization export preserves total accounting: each source example has
exactly one completed or failed result in source order. Its manifest pins the
source export, model-input protocol, sequence policy, materializer provenance,
outcome counts, and result JSONL. Reload validates every source id and record
hash and deterministically rebuilds the tokens and labels from pinned inputs.

Canonical training tokens are not claimed to reproduce the exact per-turn
rollout token ids. They are a pinned model-specific derivative of the reviewed
message source. Exact rollout ids remain a different evidence type and are
required for objectives that depend on behavior-policy action probabilities.

## Negative-Example Contract

### Unit Of Data

A negative example is a reviewed, labeled source record describing behavior
that a later objective may consume negatively. It is not automatically an SFT
example and it does not receive a negative gradient merely because its metadata
says `success=false`.

The current candidate policy permits a negative example when:

- the trajectory review is accepted;
- `content_eligibility.negative_example_eligible` is true;
- the trajectory is unsuccessful.

This pool may contain gradable task failures, model-caused terminal tool
failures, or confirmed reward-hack attempts without private leakage.

### Permitted Uses

A negative record may be used for:

- failure analysis and taxonomy construction;
- a rejected side of a separately validated preference pair;
- explicitly labeled adversarial data;
- a future unlikelihood, contrastive, reward-model, value-model, or
  action-quality objective with its own contract.

It must not be fed to ordinary next-token SFT with the failed assistant spans
unmasked. Standard cross-entropy would increase their likelihood. Applying a
negative scalar to ordinary cross-entropy is also not the default contract;
that objective requires separate stability and token-credit justification.

`negative_example_eligible` therefore means "permitted as labeled negative
source evidence," not "ready for any trainer."

### Action-Level Negative Evidence

A mechanically redundant action in an otherwise successful trajectory is not
the same thing as a negative full trajectory. It may support an action-level
preference comparison even when `negative_example_eligible` is false because
the task succeeded.

Negative action supervision should branch from the same model-visible prefix
whenever possible:

```text
chosen:   useful next action or justified termination
rejected: mechanically redundant repeated tool call
```

This avoids attributing unrelated full-trajectory differences to one action.

## Preference-Pair Contract

### Unit Of Data

One preference pair contains:

- one model-visible prompt or decision context;
- a chosen response/action sequence;
- a rejected response/action sequence;
- the exact auditable basis for preferring the chosen side;
- source ids, hashes, splits, scorer/reward versions, and known risks for both
  sides.

Candidate-level `preference_pairing_eligible` only permits a trajectory to be
considered as one side. It does not prove that a valid counterpart or pair
exists.

### Pair-Level Requirements

A pair is valid only when:

- both sides pass the common source and accepted-review gates;
- both sides come from training-eligible splits;
- both responses use the same model-compatible serialization;
- the chosen and rejected sides are not identical;
- the prompt, task, and decision context are sufficiently comparable for the
  declared basis;
- the chosen side is supported by trusted success or a future explicitly
  provenance-tracked human repair;
- the rejected side's defect is evidenced rather than inferred solely from
  hindsight;
- neither side contains private leakage or an environment/orchestration
  failure;
- the pair builder records enough evidence to reproduce the comparison.

For action-level efficiency labels, the preferred construction shares an exact
transcript prefix and differs at the next action. For full-trajectory
comparisons, both sides must at least share the same task and model-visible
task prompt, and the comparison basis must account for material differences.

Potential auditable bases include:

- trusted successful behavior versus a trusted, gradable failed behavior;
- two trusted successes where one contains a proven mechanically redundant
  action and the other supplies a valid alternative at the same prefix;
- non-hacking trusted success versus an explicitly confirmed hack attempt with
  no private leakage;
- future provenance-tracked human repair versus the original failed behavior.

The following are not valid pairs:

- a failed model transcript versus an oracle patch alone;
- two unrelated trajectories selected only because their scalar outcomes
  differ;
- public-pass behavior treated as chosen despite hidden failure;
- a pair whose chosen side is a control script or privileged oracle path;
- any pair containing `heldout_private` or `public_calibration` evidence;
- any pair containing actual private leakage;
- any pair with an unauditable or ambiguous preference basis.

No preference schema or pair builder is implemented yet. An empty pair export
or a documented insufficiency result is valid. DPO remains deferred unless at
least 20 auditable pairs exist.

## Analysis-Only Contract

Once the fail-closed trust root passes, a trajectory may remain available for
analysis even when it is not trainable. Examples include:

- an unreviewed or rejected trajectory;
- an ineligible split represented only by safe metadata;
- a cannot-grade or incomplete behavior record;
- a leaked trajectory represented without copying leaked bytes;
- a candidate lacking an auditable preference counterpart;
- a candidate whose mechanical-redundancy assessment is incomplete.

Analysis permission must not be interpreted as permission to serialize the
behavior into model training data.

If the harness audit or control calibration is missing or failed, no
analysis-only training candidate is emitted. The source artifacts remain
harness-debugging evidence, not post-training data.

## Rejection And Blocking Reasons

Dataset builders must preserve a specific reason when a requested use is
denied. At minimum the reason must distinguish:

| Condition | Required consequence |
| --- | --- |
| Harness audit missing, failed, or stale | Abort candidate export; emit no records |
| Controls unstable, mismatched, or stale | Abort candidate export; emit no records |
| Artifact or source hash mismatch | Abort; do not reinterpret bytes under old provenance |
| Non-model policy or forbidden split | Deny every trainable use |
| Actual leakage | Deny every trainable use and never copy leaked bytes |
| Orchestration failure | Deny every trainable use |
| Reward-hack evaluation incomplete | Deny every trainable use |
| Trajectory review not accepted | Analysis only; no objective-specific training path |
| Positive-SFT prefix review not accepted | Emit no positive-SFT source example |
| Confirmed reward hack | Deny positive SFT; allow only explicitly labeled negative/adversarial consideration when otherwise safe |
| Ambiguous reward hack without adjudication | Block trainable use pending review |
| Task failure | Does not by itself deny an accepted positive-SFT prefix; may also support negative or preference-rejected consideration |
| Cannot grade | Does not invalidate an earlier accepted positive prefix; deny preference pairing under the current policy; possibly retain labeled negative evidence |
| Mechanical redundancy unhandled | Deny raw full-transcript positive SFT; retain assessment for deterministic repair or pairing |
| Preference basis unauditable | Deny pair construction even if both sides are individually eligible |
| Canonical sequence exceeds `max_sequence_length` | Exclude the initial trajectory-aggregated training row and preserve an explicit overlength reason |
| Serialization or leakage scan failure | Deny the constructed dataset row |

Zero positive examples, zero preference pairs, or zero examples of any other
use is a valid result. Empty output is preferable to weakening a boundary to
make a training command run.

## Historical Qwen Artifact Note

Earlier Qwen exports were useful acquisition and failure-analysis evidence, but
they predate the current harness runtime pins and the objective-specific
positive-SFT prefix-review artifact. Their provisional accepted trajectory
reviews validate artifact plumbing only and are not production-quality human
review.

Those artifacts must not be used to infer a current positive-SFT count. In
particular, their task failures do not prove that they contain no usable
positive prefix. They lack current-runtime trust binding and an accepted
positive-SFT message boundary, either of which is sufficient to block current
export. Fresh artifacts must pass the current gates and review workflow before
they are materialized for training.

The durable lesson from the historical runs is narrower:

```text
failed task can still yield interpretable negative evidence
failed task may also contain a separately reviewed positive prefix
historical artifact count != current training-data eligibility
```

## Current Enforcement Status

| Contract boundary | Status |
| --- | --- |
| Hash-pinned trajectory and review loading | Implemented |
| Current harness-audit and control-calibration gates | Implemented |
| Candidate-owned broad training eligibility | Implemented |
| Split, model-policy, leakage, orchestration, review, and reward-hack candidate gates | Implemented |
| Positive-SFT source record and post-transformation leakage scan | Implemented |
| Mechanical-redundancy assessment on candidates | Implemented |
| Deterministic mechanical-redundancy repair record schema | Implemented |
| Repair-export manifest and source-reference schemas | Implemented |
| Deterministic repair transformation and repair-export artifact | Implemented |
| Fail-closed repair source traversal and deterministic reload | Implemented |
| Repair-review record, exact-row binding, and review artifact | Implemented |
| Explicit positive-SFT repair selection and builder/export integration | Implemented |
| Positive-SFT repair selection and prefix-review CLI | Implemented |
| Positive-SFT contiguous-prefix review and source export | Implemented |
| Deterministic tool-call serialization and token loss masks | Implemented |
| Persisted target-model token records and explicit overlength outcomes | Implemented |
| Negative-example dataset/export objective | Not implemented |
| Preference-pair schema, pair validation, and export | Not implemented |
| Human-repair provenance contract | Not implemented |
| External-data license/source contract | Out of scope |

The next training-validity checkpoint is the final release/trainer boundary:
only a release artifact with matching trust evidence may authorize trainer
consumption of completed materializations.

## Non-Claims

This contract does not claim:

- that accepted review guarantees high-quality behavior;
- that `not_detected` proves the absence of reward hacking;
- that task success makes every assistant action worth imitating;
- that failed trajectories provide token-level negative targets;
- that a candidate permitted for preference use has a valid pair;
- that practice or dev re-evaluation measures generalization after training;
- that current records are ready for DPO, RL, or production training;
- that the current task suite measures broad coding-agent capability.
