# Week 10 Plan

Status: in progress on 2026-07-22. The source-record boundary, planned
train/selection disjointness, efficiency-review contract, and initialized
18-row queue are complete. Review decisions, filtering, training, and policy
evaluation have not started.

## Theme

Week 10 turns the Week 9 positive-SFT inventory into one controlled comparison
of an unchanged base policy, a broad eligible SFT treatment, and a stricter
efficiency-filtered SFT treatment.

The manual's Week 10 goal is:

```text
turn manual review into reproducible filtering and test whether fine-tuning
and filtering change behavior relative to the frozen base policy
```

The learning objectives are:

```text
data filtering as a predeclared experimental variable
task-disjoint training and development selection
baseline-controlled post-training comparison
matched training exposure
same-path base and adapter evaluation
paired policy selection with an explicit abstention outcome
```

The point is not to prove broad model improvement. The point is to run the
smallest comparison that can distinguish:

```text
effect observed after broad eligible SFT
effect observed after efficiency-filtered SFT
incremental difference attributable to the filtering treatment
```

## Week 10 Primary Claim Target

The strongest acceptable Week 10 claim is:

```text
On a frozen task-disjoint development selection set, under one deterministic
serving and evaluation path, the repo compared the exact pinned base policy
against token-budget-matched raw-eligible and efficiency-filtered LoRA
treatments and reported paired success, regression, token, and action outcomes.
```

This claim remains valid if the result is negative, neutral, tied, or too weak
to select a policy.

An acceptable closure result is also:

```text
The filtering policy and task-disjointness gates were implemented and audited,
but a same-path base/adapter comparison was blocked; the blocker and
filtering-only evidence were preserved without substituting a confounded
comparison.
```

## Starting Point

Weeks 1-9 are closed.

Current task-pack state:

```text
task pack: data/task_packs/repo_patch_python_v0
practice: 1
dev: 19
heldout_private: 6
public_calibration: 0
total: 26
```

The six heldout-private tasks remain unopened by natural-model evaluation and
must not be used for filtering, training, prompt or decoder tuning,
hyperparameter selection, policy selection, or scorer iteration.

The Week 9 post-training path is:

```text
eval attempts
-> evidence-only trajectories
-> trajectory review
-> training-use candidates
-> optional deterministic repair and repair review
-> positive-SFT contiguous-prefix review
-> source-level PositiveSFTExampleRecord export
-> target-model token and label materialization
-> explicit training authorization
-> operational LoRA smoke
```

Current trainer-shaped SFT inventory:

```text
positive-SFT manifests: 8
completed materializations: 18
failed materializations: 0
sequence-length exclusions: 0
materialization errors: 0
```

The 18 source examples come from six dev tasks:

```text
preserve_cli_error_codes: 5
repair_jsonl_deduper: 7
repair_query_encoding: 1
repair_record_chunking: 1
repair_relative_path: 3
repair_template_expansion: 1
```

The current materialized rows contain 10,205 supervised assistant tokens in
one complete pass. This number is preflight context, not the frozen Week 10
budget. The resolved raw-treatment manifest must compute and pin the authority
used by training.

All eight current SFT materialization manifests use the Week 9
`explicit_user_override` authorization for a known source-runtime mismatch.
Both Week 10 SFT arms inherit that limitation. Filtering may improve the
selected behavior but cannot wash away the upstream authorization caveat.

The Week 9 LoRA smoke used:

```text
base checkpoint: Qwen/Qwen2.5-Coder-3B-Instruct
revision: 89fe5444e8baf5736e70f528f1edcc79e6616ef6
input protocol: configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml
selected examples: 1
real optimizer steps: 3
```

That adapter proves training mechanics only. It is not a Week 10 treatment and
must not be reused as `S_raw` or `S_filtered`. Both treatment adapters begin
from fresh matching step-zero state over the exact pinned base.

Core scoring invariant:

```text
task success = nested AttemptStatus PASS
public-check success = diagnostic only
prompt-loop completion = not task success
```

## Resolved Experimental Arms

Week 10 has three primary policy arms:

```text
B0
  exact pinned base checkpoint
  no adapter

S_raw
  B0 plus a fresh LoRA adapter
  trained from the broad Week 9-authorized positive-SFT pool
  restricted to frozen train-dev task ids and hashes

S_filtered
  B0 plus a separate fresh LoRA adapter
  trained from the subset accepted by the frozen efficiency-review policy
  restricted to the same frozen train-dev task ids and hashes
```

`raw` does not mean arbitrary trajectory data. Every `S_raw` unit must already
satisfy all Week 9 gates for split, provenance, leakage, harness integrity,
orchestration validity, reward-hack handling, positive-SFT prefix review,
serialization, loss ownership, and explicit training authorization.

The intended treatment difference is:

```text
which already-authorized positive-SFT examples receive a fixed supervised-token
training budget
```

Do not change base checkpoint, tokenizer, model-input protocol, LoRA topology,
optimizer family, optimizer budget, learning-rate schedule, serving path,
decoding, task set, scorer, or inference budgets between `S_raw` and
`S_filtered`.

## Resolved Efficiency-Filtering Boundary

Week 9 asked:

```text
Is this exact contiguous assistant prefix sufficiently trustworthy and clean to
authorize for positive loss?
```

Week 10 asks a narrower additional question:

```text
Among already-authorized positive-SFT examples, is every assistant action in
this exact source example causally defensible enough for the stricter treatment?
```

This is an efficiency treatment, not a generic high-quality-data claim.

An action has a defensible causal role when it does at least one of the
following:

- acquires new task-relevant information;
- changes the workspace toward the solution;
- validates or diagnoses a materially relevant state.

An action is rejectable as avoidable only when the reviewer can identify the
exact assistant message and explain why removing it leaves the later approved
trajectory coherent without removing useful information, state change, or
validation evidence.

Resolved policy details:

- raw action count and token count are review-prioritization and reporting
  signals, not filtering authority;
- a short trajectory is not automatically better than a long trajectory;
- a passing pre-edit public-test run is allowed as prudent baseline diagnosis;
- exact repeated reads of unchanged content may be semantically avoidable even
  when the mechanical redundancy detector did not fire;
- apparently unused environment inspection may be rejectable only with a
  concrete downstream-use rationale;
- hindsight-dependent judgments should abstain rather than force rejection;
- filtering excludes the whole source example;
- filtering does not delete, reorder, truncate, mask, or rewrite actions;
- a future behavior-changing repair would require its own provenance and
  outcome contract and is not part of this treatment.

Current calibration candidates include:

```text
positive_sft_example_a5ef0f3a430cc454
positive_sft_example_aab1e627500f226b
  repeated the unchanged src/validate_records.py read after a passing check

positive_sft_example_b535bb9c0f7ca71b
positive_sft_example_bf8626bdcb21216d
  inspected pyproject.toml before standard-library-only repairs with no clear
  later dependence on that observation
```

These are calibration candidates, not pre-populated decisions. The frozen
review artifact remains the decision authority.

Passing pre-edit checks in these examples remain allowed under the resolved v1
policy. Comparator-supported shorter trajectories are evidence for review, but
the existence of a shorter successful path does not by itself prove that every
extra exploratory action was imprudent.

## Resolved Review Boundary

Efficiency review is reviewer-agnostic. A human or LLM may populate the queue.
Reviewer identity and notes are provenance; reviewer type does not change the
artifact contract.

Reuse the repository's shared review vocabulary and provenance machinery:

```text
review_status:
  not_reviewed
  reviewed

review_decision:
  accepted
  rejected
  needs_followup
```

Week 10 must use a distinct efficiency-review artifact rather than mutate or
overload the Week 9 positive-SFT prefix-review artifact.

Decision semantics:

```text
accepted
  every included assistant action has a defensible causal role
  source example may enter S_filtered

rejected
  one or more exact avoidable assistant actions are cited
  source example remains available to S_raw but not S_filtered

needs_followup
  reviewer abstains because the efficiency judgment is not trustworthy
  source example remains available to S_raw but not S_filtered

not_reviewed
  queue is incomplete
  filtered export and S_filtered training are blocked
```

The semantic efficiency decision binds to the exact source-level
`PositiveSFTExampleRecord` hash, not to target-tokenizer-specific token ids.
The filtered materialization export must separately prove that every selected
materialized row points back to the exact reviewed source hash.

This ownership split means:

```text
source messages changed
  -> prior efficiency review no longer applies

tokenizer or materializer implementation changed, source messages unchanged
  -> semantic review may remain valid
  -> target-model materialization and experiment snapshot must be resolved again
```

Queue completeness is a pre-training gate:

- exactly one row exists for every train-dev positive-SFT source example;
- every row resolves to the exact source hash;
- `not_reviewed` count is zero before filtered export;
- every reviewed row has review id, reviewer id, decision, and reason provenance;
- every rejection names at least one exact assistant message id;
- rejected message ids must exist, be unique, and have role `assistant` in the
  source example;
- `needs_followup` remains a countable abstention rather than an implicit tie or
  acceptance;
- source messages remain immutable.

## Derived Training Tasks And Planned Selection Tasks

The exact filtering unit is the existing `PositiveSFTExampleRecord`. There is
no separate task-partition config, schema, manifest, or CLI.

Training task ids are derived from the 18 exact source records:

```text
preserve_cli_error_codes
repair_jsonl_deduper
repair_query_encoding
repair_record_chunking
repair_relative_path
repair_template_expansion
```

Selection task ids are declared by the future selection eval config:

```text
repair_config_precedence
repair_header_merge
repair_duration_parser
repair_semver_precedence
repair_csv_projection
repair_retry_schedule
repair_interval_coalescing
repair_alias_chain
repair_inventory_transaction
repair_access_policy
repair_config_inheritance
repair_event_rollup
repair_job_dispatch
```

Current preflight:

```text
train-dev count: 6
selection-dev count: 13
intersection: empty
union: the 19 then-current dev tasks
```

Ownership remains at existing boundaries:

```text
PositiveSFTExampleRecord
  -> owns the exact messages, source identity, task id, and upstream provenance

efficiency-review and raw/filtered manifests
  -> pin the exact source example ids and record hashes they consume

selection eval config and eval manifests
  -> own the thirteen selection ids and exact selected-task hashes

policy comparison
  -> verifies that every arm used the same selection-task hash set
```

Required gates:

- every one of the 18 current source records appears exactly once in the
  initialized efficiency-review queue;
- raw and filtered construction pins exact source record hashes;
- train task ids are derived from the consumed source records rather than
  copied into a second config;
- every selection eval attempt belongs to one of the thirteen configured
  selection-dev tasks and is hash-pinned by the eval manifest;
- derived train task ids and configured selection task ids are disjoint;
- no practice, heldout-private, or public-calibration task appears;
- selection-task hash mismatch blocks the affected eval/comparison snapshot;
- unrelated repository or task-pack additions do not invalidate existing
  source-record, dataset, or eval artifacts.

The current 26-task pack hashes to:

```text
pack_record_hash: xxh64:70af6abbb3ae1d61
```

That whole-pack value is diagnostic provenance, not filtering authority.
Filtering follows exact `PositiveSFTExampleRecord` hashes, while selection
evaluation follows the selected-task hashes already owned by eval manifests.

## Artifact And Regeneration Policy

This is an unreleased learning lab. Do not add compatibility shims, migration
layers, aliases, or schema-version bumps for in-progress Week 10 contracts.

Use clean current shapes and regenerate or overwrite in-progress artifacts when
the learning boundary changes.

Distinguish:

```text
mutable working configuration
-> explicit experiment freeze
-> immutable comparison snapshot
```

The experiment freeze occurs immediately before raw and filtered dataset
construction, after the source-record scope, filtering rubric, review queue,
model-input protocol, training exposure policy, serving path, decoding,
metrics, and selection rule are approved.

Practical invalidation rules:

- changing source messages invalidates review and dataset artifacts that pin
  the prior source record;
- changing a selection task invalidates eval artifacts that pin the prior task
  hash;
- adding an unrelated task or editing an unrelated task does not invalidate
  existing source-record, dataset, or selected-task artifacts;
- documentation, notes, report formatting, unrelated tests, and unrelated code
  do not require training-data regeneration;
- a semantic change to selected task bytes, filtering, tokenization, loss
  ownership, training, serving, scoring, or decoding requires regenerating only
  the downstream comparison outputs that depend on it;
- old in-progress experiment paths may be overwritten deliberately;
- old artifacts need not remain loadable through compatibility code.

Record Git SHA for provenance, but do not use every Git change as a global
invalidation key.

Also distinguish:

```text
artifact integrity
  persisted files still match their own recorded hashes

current-code equivalence
  current code would reproduce the same transformation
```

Current-code equivalence is required only for a new claim that reruns or
depends on that transformation. It should not create a standing obligation to
rebuild every historical artifact after ordinary lab development.

## Resolved Training-Exposure Policy

The comparison matches learning exposure using loss-bearing assistant tokens,
not total serialized sequence length.

The raw arm defines the budget:

```text
target supervised-token budget
  = supervised assistant tokens in one complete frozen pass over S_raw
```

The filtered arm cycles deterministically through complete accepted examples
until it reaches approximately the same supervised-token budget.

Hold constant:

- fresh base checkpoint state;
- fresh matching adapter initialization policy;
- LoRA target modules, rank, alpha, and dropout;
- optimizer type and hyperparameters;
- learning-rate schedule;
- optimizer-step budget;
- batch and gradient-accumulation policy;
- training seed;
- maximum sequence length;
- loss reduction and assistant-only labels;
- checkpoint/save behavior.

Training schedules must use complete materialized examples. Do not truncate a
row merely to hit the budget exactly. Persist the explicit source-example
schedule and report any unavoidable overshoot or undershoot.

Report for each treatment:

- unique source-example count;
- unique task count and distribution;
- source-policy/model distribution;
- supervised tokens in one unique pass;
- target and observed supervised-token exposure;
- total context tokens processed;
- per-example exposure count;
- optimizer steps;
- repeated-example count and maximum repeat count;
- effective epochs or equivalent exposure ratio.

Repetition in `S_filtered` is part of filtering-induced reweighting and must be
visible. Do not describe the comparison as controlling unique data quantity.

## Resolved Deterministic Selection Evaluation

Initial Week 10 selection uses deterministic greedy generation:

```text
strategy: greedy
temperature: 0.0
num_return_sequences: 1
seed: null
one rollout per task and policy
```

The exact `max_new_tokens`, timeout, max turns, stop sequences, and other
decoding fields must be pinned in the selection config before any arm is run.
The repository already has schedule-neutral greedy decoding configs; choose or
create one current config rather than embedding week labels in source APIs.

There is one training run per SFT arm and one evaluation rollout per frozen
selection task and policy:

```text
policies: 3
selection tasks: 13
primary model-policy attempts: 39
```

Do not claim sampling variance, training-seed robustness, or statistical
significance from this design. A one-task difference is a fragile development
result even when it is the predeclared selection outcome.

## Resolved Policy-Selection Rule

Selection is a lexicographic decision with a valid abstention outcome.

Hard gates come first:

- identical frozen selection task ids and hashes;
- same scorer and harness path;
- same model-input protocol and tokenizer;
- same serving implementation for base and adapters;
- same decoding and inference budgets;
- no hidden-validator exposure;
- no scorer, harness, or infrastructure failure treated as model failure;
- no confirmed reward-hack behavior accepted as a successful policy result.

Primary metric:

```text
count of task cells with nested AttemptStatus PASS
```

With one deterministic rollout, the paired cell is one frozen task id.

Selection rule:

```text
1. A policy with more PASS task cells advances over a policy with fewer.
2. Equal PASS counts with different successful task ids produce abstention.
3. Identical successful task-id vectors compare token use on matched successful
   cells.
4. If token use ties under the pinned aggregation, compare action count on the
   same matched successful cells.
5. A remaining tie produces abstention.
```

`B0` participates in selection. If both adapters regress relative to `B0`, the
valid outcome is that neither SFT policy advances.

Efficiency metrics may never compensate for fewer task successes.

Fast failure must not look efficient. Token and action tie-breakers apply only
to matched successful task cells. Full-run token and action totals remain
descriptive report fields.

The comparison report must include:

- per-task outcome for all three policies;
- total PASS count and rate;
- typed non-pass counts;
- `fail -> pass` gains relative to `B0`;
- `pass -> fail` regressions relative to `B0`;
- raw-versus-filtered paired outcomes;
- prompt, completion, and total inference tokens when supported by the common
  serving path;
- valid tool-call count, final-answer count, invalid-output count, and total
  model turns;
- latency as descriptive evidence;
- selection decision or explicit abstention;
- exact rule branch that produced the decision.

The exact definitions and aggregation for `tokens consumed` and `actions
taken` must be frozen before the eval runs. Do not infer them after seeing
outcomes.

## Same-Path Serving Gate

Week 9 trained a local PEFT/LoRA adapter, while historical agent evaluations
primarily used an Ollama OpenAI-compatible path. Week 10 may not evaluate `B0`
through one path and the adapters through another and then call the difference
a fine-tuning effect.

Before full training, prove one common model-policy path can run:

```text
B0 with adapter disabled
SFT adapter with identical base and adapter enabled
```

The common path must preserve:

- exact base checkpoint and revision;
- exact tokenizer artifacts;
- exact AgentEnv model-input protocol;
- prompt-loop tool/action contract;
- generation serialization;
- greedy decoding;
- token accounting;
- timeout and budget semantics;
- raw model error attribution.

A tiny practice-task smoke through both base and a known adapter is sufficient
to establish path parity before the expensive comparison. It is not efficacy
evidence.

If common-path serving cannot be made trustworthy within the week, stop at the
filtering/training artifact boundary and report the comparison as blocked.
Do not use Ollama for `B0` and an in-process Transformers path for adapters and
call the result controlled.

## Non-Claims

Week 10 must not claim:

- broad coding-agent improvement;
- heldout or generalization improvement from selection-dev results;
- statistical significance from one deterministic rollout per task;
- training-seed robustness from one training run per arm;
- that accepted Week 9 review guarantees high behavioral quality;
- that the efficiency filter measures every dimension of dataset quality;
- that fewer actions are always better;
- that token count is a monotonic quality signal;
- that matched supervised-token exposure matches unique information content;
- that filtered-example repetition is harmless;
- that the derived train and selection task sets are difficulty matched;
- that progressive-task source-file counts are measured difficulty labels;
- that an explicit learning-lab authorization override is a production data
  release;
- that same development-task pass count is a benchmark result;
- that a changed adapter or lower training loss proves efficacy;
- DPO benefit unless the conditional DPO comparison actually runs.

## Main Self-Deception Risks

### Duplicate Week 9 Review

Calling the existing positive-SFT prefix gate a new quality filter would create
no real treatment. Week 10 must ask the narrower efficiency question and retain
the Week 9 decision as immutable upstream evidence.

### Count-As-Quality

Action or token count alone can punish prudent exploration and reward lucky
guessing. Counts prioritize inspection and describe behavior; exact
causal-role evidence authorizes exclusion.

### Source-Policy Confounding

Several current efficiency candidates come from the Qwen3-Coder acquisition
source. A strict filter may change source-model distribution as well as action
efficiency. Report the distribution and limit causal language accordingly.

### Task Memorization

Different attempts from the same task are not independent. Task identity and
content hash, not trajectory id or seed, define the train/selection exclusion.

### Dataset-Size Confounding

Training raw once and filtered once would expose the policies to different
supervised-token budgets. Match supervised-token exposure and make repetition
visible.

### Serving-Path Confounding

Different base and adapter providers, chat templates, tokenizers, or tool
serialization can dominate the observed difference. Block the efficacy claim
unless one path serves all arms.

### Fast-Failure Efficiency

All-attempt token or action totals can reward policies that fail early. Apply
efficiency tie-breakers only on matched successful cells.

### Forced Winner

Equal pass counts over different task identities do not support a token-based
winner. Abstain.

### Development-As-Heldout

Selection-dev is development data and may guide policy choice. It can never be
relabeled as heldout evidence.

### Artifact Ceremony

Global Git or task-pack changes must not trigger full historical regeneration.
Pin only dependencies needed by the comparison snapshot and rebuild only the
affected current outputs.

## Planned Outputs

Week-specific notes and reports may use the Week 10 label:

```text
notes/weekly/week_10/plan.md
notes/weekly/week_10/implementation_notes.md
notes/weekly/week_10/learnings.md
notes/weekly/week_10/closure_audit.md
experiments/plans/week_10_positive_sft_matched_schedule/
experiments/runs/week_10_positive_sft_efficiency_review/
experiments/runs/week_10_positive_sft_raw/
experiments/runs/week_10_positive_sft_filtered/
experiments/models/week_10_positive_sft_raw_lora/
experiments/models/week_10_positive_sft_filtered_lora/
experiments/runs/week_10_selection_base/
experiments/runs/week_10_selection_raw/
experiments/runs/week_10_selection_filtered/
experiments/reports/week_10_filtering_quality.md
experiments/reports/week_10_base_vs_raw.md
experiments/reports/week_10_base_vs_filtered.md
experiments/reports/week_10_raw_vs_filtered.md
experiments/reports/week_10_policy_selection.md
```

Schedule-neutral repository surfaces should use names based on meaning rather
than week number. Likely configuration artifacts:

```text
configs/data/positive_sft_efficiency_filter.yaml
configs/train/positive_sft_lora_raw.yaml
configs/train/positive_sft_lora_filtered.yaml
configs/eval/qwen2_5_coder_3b_sft_selection.yaml
```

Likely code ownership, subject to inspection before creation:

```text
src/agentenv/training/positive_sft/efficiency_review.py
src/agentenv/training/positive_sft/filtering.py
src/agentenv/training/positive_sft/training_schedule.py
src/agentenv/reporting/policy_comparison.py
shared base/adapter model client under src/agentenv/models/
```

Do not create files merely to match the manual if an existing contract-owned
module is the cleaner home.

Conditional DPO artifacts are intentionally absent from the primary output
list. Create them only after an exact SFT policy is selected and the DPO
reference-policy contract is ready.

## Planned Checkpoints

### Checkpoint 1: Confirm The Existing Source And Selection Boundaries

Status: complete on 2026-07-22. No new source code, config, schema, CLI, or
artifact is retained for this checkpoint.

Purpose:

```text
Confirm that PositiveSFTExampleRecord is already the exact filtering unit and
that task disjointness can be enforced between existing dataset and eval
boundaries without introducing another authority.
```

Work:

- inventory the eight existing positive-SFT exports and 18 typed source rows;
- derive the six train task ids from `record.task_input.task_id`;
- declare the thirteen selection ids in the planned selection eval config;
- preflight that the derived train ids and planned selection ids are disjoint;
- confirm that their current union is the 19 dev tasks;
- leave source hashes to review/dataset artifacts and selection hashes to eval
  artifacts;
- remove the redundant task-partition implementation and generated snapshot.

Done when:

- all 18 source rows are accounted for;
- their six task ids are derived rather than copied;
- the planned thirteen selection ids are disjoint;
- no standalone task-partition artifact or duplicated authority remains;
- later review, dataset, eval, and comparison artifacts each pin only the
  dependencies they actually consume.

Self-deception trap:

```text
Turning a derivable relationship into a new config, schema, manifest, CLI, and
artifact does not make the experiment safer. It creates a second authority that
can drift from the exact SFT records and eval manifests that already own the
relevant facts.
```

### Checkpoint 2: Efficiency Review Contract And Queue

Status on 2026-07-22: implemented. The queue contains all 18 exact source
examples and validates with 18 `not_reviewed` rows. Populating decisions remains
Checkpoint 3 work.

Purpose:

```text
Represent one objective-specific efficiency judgment per exact train-dev
PositiveSFTExampleRecord.
```

Work:

- reuse shared review status, decision, id, reviewer, and notes provenance;
- define a distinct efficiency-review record and manifest;
- bind every row to exact source example id and record hash;
- define exact avoidable-action evidence using assistant message ids;
- pin the efficiency rubric id/config hash;
- initialize one queue row per source example;
- render enough context for human or LLM review without exposing hidden
  validator content;
- validate total accounting and source reconstruction;
- make `not_reviewed` a hard filtered-export blocker;
- keep `needs_followup` as an explicit abstention.

Done when:

- all 18 source examples appear exactly once in the initialized queue;
- malformed or hash-mismatched rows fail;
- rejected rows without valid assistant-message witnesses fail;
- source messages cannot be mutated through review;
- reviewer identity remains provenance rather than pipeline authority;
- focused tests cover accepted, rejected, abstained, missing, duplicate, and
  unknown rows.

### Checkpoint 3: Populate And Validate The Efficiency Review

Purpose:

```text
Create the frozen decision evidence that distinguishes S_filtered from S_raw.
```

Work:

- review the four current calibration candidates first;
- confirm that pre-edit baseline testing remains allowed;
- review all remaining source examples under the same rubric;
- record exact evidence and rationale for every decision;
- validate the completed review artifact;
- summarize accepted, rejected, and needs-followup counts;
- inspect rejection concentration by task and source policy;
- stop if the rubric cannot distinguish semantic inefficiency consistently.

Done when:

- `not_reviewed` count is zero;
- every rejection has exact assistant-message evidence;
- every abstention has a non-empty uncertainty reason;
- all source hashes reconstruct;
- no decision was based on selection-dev or heldout outcomes;
- the review can be consumed without knowing whether the reviewer was human or
  an LLM.

Self-deception trap:

```text
Filling the queue to obtain a desired filtered count is post-hoc dataset
construction. Zero or few filtered exclusions are valid results.
```

### Checkpoint 4: Raw And Filtered Dataset Artifacts

Purpose:

```text
Construct two exact trainer-source populations from one shared authorized
materialization inventory.
```

Work:

- resolve `S_raw` from all frozen train-dev authorized materializations;
- resolve `S_filtered` by joining accepted efficiency reviews through exact
  source-example hashes;
- preserve one result per source row in accounting;
- emit machine-readable exclusion reasons for rejected and abstained rows;
- compute unique task, source policy, example, context-token, and supervised-
  token distributions;
- verify no selection-dev or heldout source enters either arm;
- produce the filtering-quality report before training.

Done when:

- raw and filtered manifests are hash-pinned and reloadable;
- every raw row is either selected or explicitly excluded from filtered;
- no source row disappears silently;
- the raw count is expected to be 18 unless upstream current contracts are
  intentionally regenerated before freeze;
- filtered count may validly be zero;
- filtering report includes source-policy concentration and borderline cases;
- the exact supervised-token budget authority is frozen.

### Checkpoint 5: Common Base/Adapter Serving Smoke

Purpose:

```text
Prove B0 and a LoRA adapter can execute the same agent path before spending time
on full treatment training.
```

Work:

- inspect the current model client and Week 9 LoRA loader boundaries;
- choose one common local serving implementation;
- load the exact base with no adapter;
- load the exact base with a known adapter through the same implementation;
- render prompts through the pinned Qwen2.5 input protocol;
- run deterministic greedy generation;
- report exact prompt/completion token accounting and model errors;
- execute one practice-task agent smoke for both forms;
- verify hidden scorer lifecycle remains unchanged.

Done when:

- provider, tokenizer, prompt bytes, decoding, action parser, tools, budgets, and
  scorer path match;
- adapter-disabled `B0` is not secretly an Ollama alias or different checkpoint;
- adapter-enabled inference changes only adapter composition;
- a serving-path limitation is typed and documented rather than hidden.

Stop rule:

```text
Do not begin comparative training if the resulting adapters cannot be evaluated
through the exact B0 path.
```

### Checkpoint 6: Deterministic Matched Training Schedules

Purpose:

```text
Resolve explicit raw and filtered example schedules with approximately equal
supervised-token exposure and identical optimizer budgets.
```

Work:

- calculate one-full-pass raw supervised-token target from the frozen artifact;
- make the raw schedule one exact complete pass;
- cycle filtered examples deterministically to approach the same target;
- preserve complete examples only;
- pin schedule order, seed, per-example repetitions, step boundaries, and token
  totals;
- hold optimizer steps and all training hyperparameters constant;
- detect an empty or too-small filtered set before GPU execution;
- write the expected exposure table before either training run.

Done when:

- both schedules are persisted and content-hashed;
- target and observed supervised-token counts are explicit;
- full context-token cost is also reported;
- per-example repeat counts are inspectable;
- no training-time random sampler can silently change exposure;
- schedule mismatch outside the predeclared tolerance blocks training.

### Checkpoint 7: Train S_raw And S_filtered

Purpose:

```text
Produce two fresh adapters whose intended difference is the frozen data
treatment.
```

Work:

- derive clean schedule-neutral raw and filtered training configs;
- start both adapters from fresh matching step-zero initialization;
- use the pinned Qwen2.5-Coder-3B base and tokenizer;
- reuse Week 9 qualification checks in proportion to risk;
- run the exact persisted schedules;
- preserve losses, gradient/adapter ownership checks, runtime, hardware, seeds,
  configs, source hashes, and final adapter hashes;
- reload both adapters through the common serving path;
- do not inspect selection-dev outcomes between arms.

Done when:

- both runs complete or have typed preserved blockers;
- base tensors remain frozen;
- only intended adapter parameters are optimized;
- training manifests reconstruct exact data and schedule provenance;
- adapter packages reload exactly;
- one arm is not retrained based on the other's downstream outcome.

### Checkpoint 8: Freeze Selection Metrics And Eval Config

Purpose:

```text
Make the comparison decision rule executable before seeing policy outcomes.
```

Work:

- pin the thirteen selection task ids and hashes;
- pin greedy decoding and all inference budgets;
- define exact token-consumption fields and aggregation;
- define exact action-count fields and aggregation;
- encode nested-PASS primary authority;
- encode typed failure treatment;
- encode paired gains and regressions;
- encode equal-count/different-task abstention;
- encode efficiency tie-breakers only for identical success vectors;
- permit `B0` or abstention as final decision.

Done when:

- one config drives all three policy arms;
- report code can apply the rule without hand interpretation;
- no metric definition depends on observed Week 10 outcomes;
- scorer, infra, model, task, and policy failures remain distinguishable;
- all three output directories are empty or intentionally overwriteable before
  the first arm runs.

### Checkpoint 9: Deterministic Selection-Dev Evaluation

Purpose:

```text
Run the 39-attempt paired comparison through one path.
```

Run order:

```text
B0
S_raw
S_filtered
```

The order is operational only. Do not change configuration after seeing an
earlier arm.

Done when:

- every arm covers all thirteen frozen task cells or records typed invalid
  cells;
- each attempt has exact model, adapter, prompt, task, scorer, decoding, token,
  action, and runtime provenance;
- task success uses nested PASS only;
- hidden validators remain unavailable during the model phase;
- no heldout task is loaded or reported;
- common-path parity is revalidated from run manifests.

### Checkpoint 10: Paired Comparison And Selection Decision

Purpose:

```text
Apply the predeclared rule without forcing a positive result or winner.
```

Required comparisons:

```text
B0 vs S_raw
B0 vs S_filtered
S_raw vs S_filtered
```

Required report evidence:

- per-task three-arm outcome table;
- pass counts and typed non-pass counts;
- paired gains and regressions;
- invalid comparison cells and reasons;
- tokens and actions on matched successful cells;
- descriptive all-attempt efficiency metrics;
- source data and training-exposure summaries;
- serving-path parity evidence;
- exact selected policy, `B0`, or abstention;
- negative and neutral results;
- limitations and non-claims.

Done when:

- the selection rule is applied mechanically;
- equal pass counts over different successful tasks abstain;
- a lower-pass policy cannot win on efficiency;
- `B0` may remain the selected policy;
- the report does not describe selection-dev evidence as heldout improvement;
- the result can be regenerated from archived manifests and attempt artifacts.

### Checkpoint 11: Conditional DPO Decision

Purpose:

```text
Decide whether preference optimization is a justified incremental experiment
after the base/SFT comparison is complete.
```

Run DPO only when:

- an exact SFT policy was selected rather than abstained or rejected;
- at least 20 auditable preference pairs survive the frozen train-dev task,
  leakage, provenance, and runtime gates;
- the DPO policy and frozen reference can start from identical selected-SFT
  weights and serialization semantics;
- adapter composition and reference log-probability evaluation are trustworthy;
- the incremental comparison can use the same selection-dev path.

If those conditions fail, preserve the existing 29 materialized pairs and write
an explicit deferral. Do not force DPO merely because the pair count exists.

Conditional required comparisons:

```text
S_selected vs P_dpo
B0 vs P_dpo
```

DPO is the first feature to cut if Week 10 time or measurement trust is tight.

### Checkpoint 12: Closeout

Purpose:

```text
Make the final claim no broader than the evidence.
```

Done when:

- `implementation_notes.md` records material implementation decisions;
- `learnings.md` records durable filtering, selection, and comparison lessons;
- `closure_audit.md` maps claims to exact configs, manifests, runs, and reports;
- task, dataset, model, adapter, scorer, protocol, and report hashes are listed;
- stale or overwritten in-progress artifacts are not presented as independent
  evidence;
- heldout remains unopened;
- the next Week 11 reliability target follows from actual blockers or results.

## Planned Command Shapes

These are intended interfaces, not promises that the commands already exist.
Use cleaner repo-native names during implementation if inspection shows a
better ownership boundary. Do not preserve abandoned shapes through aliases.

Validate the current task pack:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv tasks check-splits \
  data/task_packs/repo_patch_python_v0/splits.lock.json
```

Initialize and validate efficiency review:

```bash
uv run agentenv training positive-sft efficiency-review-init \
  --materialization experiments/runs/natural_model_anchor_contrast_acquisition/positive_sft_materializations/devstral-sampling \
  --materialization experiments/runs/natural_model_anchor_contrast_acquisition/positive_sft_materializations/qwen2-5-coder-14b-sampling \
  --materialization experiments/runs/natural_model_anchor_contrast_acquisition/positive_sft_materializations/qwen3-coder-30b-sampling \
  --materialization experiments/runs/natural_model_dev_coverage_acquisition/positive_sft_materializations/devstral-sampling \
  --out experiments/runs/week_10_positive_sft_efficiency_review \
  --overwrite

uv run agentenv training positive-sft efficiency-review-validate \
  --reviews experiments/runs/week_10_positive_sft_efficiency_review
```

Construct raw and filtered artifacts:

```bash
uv run agentenv training positive-sft filter \
  --reviews experiments/runs/week_10_positive_sft_efficiency_review \
  --raw-out experiments/runs/week_10_positive_sft_raw \
  --filtered-out experiments/runs/week_10_positive_sft_filtered \
  --report-out experiments/reports/week_10_filtering_quality.md \
  --overwrite
```

Resolve matched schedules:

```bash
uv run agentenv training positive-sft schedule \
  --raw experiments/runs/week_10_positive_sft_raw \
  --filtered experiments/runs/week_10_positive_sft_filtered \
  --out experiments/plans/week_10_positive_sft_matched_schedule \
  --overwrite
```

Train the SFT arms:

```bash
uv run agentenv training positive-sft train-lora \
  --config configs/train/positive_sft_lora_raw.yaml \
  --source experiments/runs/week_10_positive_sft_raw \
  --out experiments/models/week_10_positive_sft_raw_lora \
  --overwrite

uv run agentenv training positive-sft train-lora \
  --config configs/train/positive_sft_lora_filtered.yaml \
  --source experiments/runs/week_10_positive_sft_filtered \
  --out experiments/models/week_10_positive_sft_filtered_lora \
  --overwrite
```

Run deterministic selection evaluation:

```bash
uv run agentenv eval \
  --config configs/eval/qwen2_5_coder_3b_sft_selection.yaml \
  --policy-id base \
  --out experiments/runs/week_10_selection_base \
  --overwrite

uv run agentenv eval \
  --config configs/eval/qwen2_5_coder_3b_sft_selection.yaml \
  --policy-id raw-sft \
  --adapter experiments/models/week_10_positive_sft_raw_lora \
  --out experiments/runs/week_10_selection_raw \
  --overwrite

uv run agentenv eval \
  --config configs/eval/qwen2_5_coder_3b_sft_selection.yaml \
  --policy-id filtered-sft \
  --adapter experiments/models/week_10_positive_sft_filtered_lora \
  --out experiments/runs/week_10_selection_filtered \
  --overwrite
```

Build the comparison report:

```bash
uv run agentenv report compare-policies \
  experiments/runs/week_10_selection_base \
  experiments/runs/week_10_selection_raw \
  experiments/runs/week_10_selection_filtered \
  --out experiments/reports/week_10_policy_selection.md
```

## Verification Plan

Focused checks after each new boundary:

```bash
uv run pytest tests/training
uv run pytest tests/tasks tests/evals tests/reporting
uv run ruff check .
uv run pyright
git diff --check
```

Full closeout checks:

```bash
uv run pytest -n auto
uv run ruff check .
uv run pyright
git diff --check
```

Artifact validation must cover:

- positive-SFT source reconstruction;
- train task ids derived from exact consumed source records;
- efficiency-review total accounting and evidence references;
- raw/filtered total accounting;
- matched training schedules;
- training authorization and adapter provenance;
- common serving-path identity;
- deterministic decoding config equality;
- selection task hash equality;
- paired report reconstruction;
- heldout absence from all train, review, model-selection, and report inputs.

## Cut Plan And Fallbacks

Cut in this order:

1. DPO optimization.
2. Training replicates.
3. Stochastic evaluation repeats.
4. Extra report polish.
5. Optional visualization.

Do not cut:

- unchanged `B0` arm;
- train/selection task disjointness at dataset/eval consumption;
- exact selected-task hashes;
- Week 9 hard eligibility gates;
- complete efficiency-review accounting;
- same-path base/adapter serving;
- matched supervised-token exposure;
- paired regression reporting;
- explicit abstention;
- heldout isolation;
- limitations and non-claims.

If the filtered set is empty:

- preserve the valid zero-row artifact;
- do not weaken the rubric;
- report that the intended training comparison is blocked;
- retain filtering-quality evidence as the primary result.

If the filtered set is too small for a meaningful schedule:

- run only an explicitly labeled plumbing overfit if useful;
- do not present it as the controlled SFT comparison;
- keep the data-quality report primary.

If training fails:

- preserve logs and typed failure artifacts;
- keep the review, raw/filtered, and schedule artifacts;
- do not substitute the Week 9 smoke adapter;
- close with a filtering-only result.

If common serving fails:

- do not compare Ollama base outcomes with in-process adapter outcomes;
- preserve a serving blocker note;
- defer model-quality comparison.

If all policies score zero or all score thirteen:

- report the floor or ceiling explicitly;
- abstain from policy selection unless the predeclared primary rule genuinely
  distinguishes them;
- do not elevate token/action efficiency into a capability claim.

If equal pass counts occur on different task identities:

- abstain as designed;
- report the different success sets;
- do not force a winner with incomparable efficiency totals.

## Notes Discipline

Use `implementation_notes.md` for:

- actual file and command changes;
- resolved routine mechanics;
- blockers and debugging evidence;
- changes to the planned checkpoint sequence;
- exact regeneration and overwrite decisions.

Use `learnings.md` only for durable eval/post-training lessons:

- eligibility versus quality filtering;
- semantic action efficiency versus count heuristics;
- task-level contamination;
- matched token exposure and repetition;
- base-controlled interpretation;
- paired policy selection and abstention;
- serving-path confounding;
- development selection versus heldout evidence.

Do not use `learnings.md` for helper placement, naming, test organization,
formatting, or routine refactor details.

## Week 10 Done Criteria

Week 10 is complete when:

- train task ids are derived from the exact raw/filtered source records;
- the selection eval config and eval manifests pin the exact thirteen
  selection-dev ids and task hashes;
- train and selection task ids are disjoint;
- every train-dev positive-SFT source has one completed efficiency-review row;
- every rejection has a machine-readable reason and exact action evidence;
- no selection-dev, heldout, practice, or public-calibration example enters
  training;
- raw and filtered artifacts have complete accounting;
- one raw pass defines the supervised-token budget;
- the filtered schedule deterministically matches that budget within the frozen
  full-example tolerance;
- `B0`, `S_raw`, and `S_filtered` use one base checkpoint, protocol, serving
  path, decoding config, task set, scorer, and inference budget;
- all three arms run the thirteen-task deterministic selection matrix or have a
  documented same-path blocker;
- base-versus-raw, base-versus-filtered, and raw-versus-filtered paired reports
  exist or are explicitly blocked;
- the predeclared winner/abstention rule is applied mechanically;
- negative or neutral results are written plainly;
- heldout-private remains unopened;
- the final claim remains scoped to this controlled development distribution.

## Next Implementation Step

Populate Checkpoint 3 only:

```text
apply the frozen efficiency rubric to all 18 exact queue rows
record reviewer provenance, decision, and rationale
for every rejection, identify exact avoidable assistant message ids
validate zero not_reviewed rows and report accepted/rejected/needs_followup counts
stop before filtering or training
```

Do not jump directly from this plan to filtering, training, adapter serving, and
evaluation in one pass.
