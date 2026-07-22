# Week 9 Plan

## Theme

Week 9 turns reviewed trajectories into post-training data artifacts without
contaminating evals.

The manual's Week 9 goal is:

```text
build trainable datasets without contaminating evals
```

The learning objective is:

```text
post-training data contracts, trace quality labels, loss masking, and
preference-pair validity
```

The point is not to prove model improvement. The point is to define and enforce
which trajectories may become SFT examples, negative examples, preference
pairs, or analysis-only records, and to make invalid examples fail in code
rather than relying on reviewer memory.

## Spike Selection Decision

Continue with the default Week 9-12 training-data spike.

The manual lists three alternate spikes:

```text
Alternate A: Task/Eval Quality Spike
Alternate B: Runtime/Systems Spike
Alternate C: Reward/Scorer Hardening Spike
```

Do not switch to an alternate spike now.

Reasoning:

- Alternate A is tempting because the suite is small and the real-model pass
  rate is currently 0/3, but Week 9 does not need to claim improvement or create
  a large positive dataset. A valid training-data spike can conclude that there
  are zero positive SFT examples and still teach the right data-contract lesson.
- Alternate B is not the right default because replay, artifact hashing, and
  control stability are currently good enough for data-contract work.
- Alternate C is not the right default because Week 8 already measured the
  obvious reward-hack classes and documented remaining holes. Week 9 should
  carry those holes forward as data-use gates instead of expanding the
  reward-hack suite immediately.

Constraint on the selected spike:

```text
Treat Week 9 as trace-filtering and dataset-contract plumbing, not as a
model-improvement experiment.
```

Switch away from the default spike only if Week 9 uncovers one of these
blockers:

- source trajectory or review artifacts cannot be validated by hash;
- scorer/control evidence no longer supports trusting task success;
- reward-hack traces can enter positive training paths;
- preference pairs cannot be made auditable without changing scorer or task
  contracts;
- loss-masking/tool-call serialization cannot be specified against the current
  prompt-loop transcript format.

## Starting Point

Weeks 1-8 are closed.

Current architecture:

```text
task manifest + seed_workspace -> patch/control/agent policy -> orchestrator ->
public checks -> hidden scorer -> attempt artifacts -> replay/report
```

For model policies:

```text
eval config -> model client -> prompt loop -> typed tools -> candidate patch ->
existing attempt/scorer path -> eval matrix report
```

Core scoring invariant:

```text
task success = nested AttemptStatus PASS
public checks = diagnostic only
prompt-loop completion = not task success
```

Week 8 added the training-data invariant:

```text
candidate content eligibility is separate from task success, final training
authorization is separate from both, and reward-hack evidence must never become
a positive training example by accident
```

Historical Qwen artifacts remain useful acquisition and failure-analysis
evidence, but several predate the current harness runtime pins and the
objective-specific positive-SFT prefix review. They are not the current
training-data trust root and their old row counts must not be treated as current
eligibility claims.

Current implemented data flow:

```text
trajectory export
-> trajectory review
-> non-authorized training candidate export
-> optional deterministic repair and repair review
-> positive-SFT prefix review
-> non-authorized source-level PositiveSFTExampleRecord export
-> target-model token materialization
-> final dataset release gate
```

The checkpoint-specific serialization authority is now implemented under
`src/agentenv/models/input_protocol*.py`. The Qwen2.5-Coder-3B protocol pins an
immutable model revision, the exact tokenizer artifacts, the exact upstream
chat-template bytes, the `role/content` projection, the generation and
completed-transcript operations, and the current AgentEnv JSON-content tool
protocol. Provider-native tool serialization is explicitly unsupported.

Target-model tokenization and label materialization are now implemented. A
source-level positive-SFT example remains model-independent; its materialized
derivative is the trainer-shaped record, though still explicitly unauthorized
until final release.

The selected target checkpoint's Qwen2.5 protocol no longer injects the
Qwen3-specific `/no_think` soft switch. Fresh no-suffix Qwen2.5-Coder-3B
acquisition and trajectory artifacts now live at:

```text
experiments/runs/week_09_qwen2_5_coder_3b_no_suffix_eval_v1
experiments/runs/week_09_qwen2_5_coder_3b_no_suffix_trajectory_export_v0
```

The seven prompt loops completed and were scored, although all seven hidden
checks failed. They are therefore potential prefix-review sources, not claimed
successful demonstrations. Older Qwen2.5 records remain historical evidence
conditioned on the removed suffix.

## Existing Implementation Surface

The current training package is organized by contract ownership:

```text
src/agentenv/training/candidates/
src/agentenv/training/repairs/
src/agentenv/training/positive_sft/
src/agentenv/training/README.md
tests/training/
```

Existing CLI:

```text
agentenv training candidates export
agentenv training positive-sft review-init
agentenv training positive-sft review-validate
agentenv training positive-sft export
agentenv training positive-sft materialize
```

Remaining major artifacts or boundaries:

```text
preference dataset schema/builder/export
negative-example export boundary
configs/train/positive_sft_smoke.yaml
configs/train/dpo_deferred.yaml
docs/dpo_deferred_note.md
```

Repo-native placement should be decided deliberately. The manual names
standalone scripts such as `scripts/make_sft_dataset.py`, but the repo already
uses typed builders plus `agentenv training ...` CLI commands. Prefer extending
that pattern unless a script boundary is clearly better.

## Non-Claims

Week 9 must not claim:

- model improvement;
- reward robustness;
- heldout generalization;
- broad coding-agent capability;
- production-grade sandbox security;
- that zero positive SFT rows is a failure;
- that public-pass/hidden-fail rows are near-success positive examples;
- that preference pairs are valid without an auditable basis.

The strongest acceptable claim is:

```text
the repo can define, validate, and export non-authorized post-training data
candidates while reserving actual training authorization for a fail-closed final
release boundary
```

## Design Priority

Preserve data-use boundaries:

- positive-SFT review requires model-generated trajectory evidence, a trainable
  split, no leakage, no orchestration failure, and a passing reward-hack gate;
  task success prioritizes review but is not required;
- positive-SFT export additionally requires a source-pinned, accepted review
  that authorizes one contiguous assistant-message prefix;
- public PASS is never sufficient for positive SFT;
- hidden-validator leakage blocks reward-dependent training use;
- heldout-private and public-calibration traces never enter trainable paths;
- model-authored success-looking files are not authoritative evidence;
- preference pairs require a concrete auditable comparison basis;
- chosen and rejected sides must not be identical;
- harness, orchestration, flaky-measurement, or environment failures cannot
  become positive examples; an otherwise trustworthy task failure may yield a
  human-approved prefix before its causal error;
- loss masking must train only on intended assistant/action tokens, not user
  prompts, tool observations, scorer output, hidden validators, or review
  metadata.
- candidate construction, repair, prefix review, and token materialization remain
  explicitly non-authorized development artifacts; final release alone requires
  matching harness-audit and control-calibration evidence.

## Resolved Positive-SFT Design Boundary

The source-level and token-level units are now distinct:

```text
PositiveSFTExampleRecord
  = reviewed, hash-pinned, model-independent message prefix

trainer-ready positive-SFT record
  = target-model-specific input_ids, labels, and materialization provenance
```

Task success is not required for the source record. The objective-specific
review selects a contiguous prefix ending at an approved assistant message.
For the initial token materialization, use one trajectory-aggregated sequence,
the exact tokenizer compatible with the target checkpoint, and the implemented
pinned model-input protocol. System, user, and tool-observation tokens are
context only; approved assistant tokens receive loss.

Examples exceeding `max_sequence_length` are excluded whole. Do not truncate,
arbitrarily chunk, overlap, or summarize them. The remaining open design
boundary is resolved: every accepted source example produces exactly one
materialization-result record. Completed records persist tokens and labels;
failed records preserve either an explicit overlength exclusion or an
untrustworthy materialization error. No source example may disappear silently
from accounting.

## Planned Outputs

Primary planned artifacts:

```text
notes/weekly/week_09/plan.md
notes/weekly/week_09/implementation_notes.md
notes/weekly/week_09/learnings.md
docs/post_training_data_contract.md
docs/dpo_deferred_note.md
configs/train/positive_sft_smoke.yaml
configs/train/dpo_deferred.yaml
```

Remaining code/test boundaries, after design:

```text
target-model token materialization under training/positive_sft/
tests/training/test_token_materialization.py
tests/training/test_loss_masking.py
preference schema/builder/export under training/
tests/training/test_preference_pairs.py
```

Possible later boundaries:

```text
negative-example dataset/export objective
runtime-aligned context management for overlength examples
configs/data/post_training.yaml
```

Only create these if they clarify the boundary. Do not split files just to match
the manual if the existing repo-native structure remains cleaner.

## Planned Checkpoints

### Checkpoint 1: Data Contract Boundary

Purpose:

```text
Define what data uses exist and what evidence gates each use.
```

Questions to answer:

- What is one SFT example?
- What is one negative example?
- What is one preference pair?
- What can be analysis-only?
- Which sources are allowed?
- Which sources are forbidden?
- Which split rules are hard blockers?
- Which leakage, reward-hack, or review states block each data use?

Done when:

- `docs/post_training_data_contract.md` exists;
- the contract distinguishes allowed, forbidden, trainable, and analysis-only
  sources;
- rejection reasons are explicit;
- the contract states that zero positive SFT rows is valid;
- the contract records how Week 8 reward-hack holes constrain Week 9 exports.

### Checkpoint 2: SFT Contract Audit

Purpose:

```text
Compare the current positive-SFT export against the data contract.
```

Done when:

- existing `PositiveSFTExampleRecord` fields are checked against the contract;
- missing fields or unnecessary fields are written down;
- source hash, review, task manifest, and leakage gates are verified;
- current zero-row export is regenerated or validated;
- tests prove bad positive examples are rejected by code.

Current state:

- original and repaired positive-SFT sources have exact provenance;
- repaired rows require an explicit completed, accepted repair selection;
- the repair/review source chain is hash-pinned and rebuilt on load;
- current deterministic deletion has a narrow task-outcome inheritance rule;
- positive-SFT review records bind an exact accepted assistant-message boundary;
- source export materializes only that contiguous approved prefix;
- repair selection and positive-SFT review/export CLI wiring are implemented;
- Qwen2.5-Coder-3B inference now consumes the pinned model-input protocol via
  AgentEnv rendering and Ollama native raw generation;
- the same protocol now pins a generation-ownership annotation and rejects any
  ownership-aware render whose bytes differ from the canonical Qwen render;
- the materialization result union now represents completed token/label output,
  explicit overlength failures, and other materialization failures with exact
  source, protocol, sequence-policy, and materializer provenance;
- the materialization exporter preserves one result per source row, pins its
  source export and protocol, and rebuilds persisted labels on load;
- a real Qwen2.5-Coder-3B practice prefix materialized successfully with the
  pinned tokenizer into 843 tokens, including assistant-only end-of-turn loss;
- target-model positive-SFT token materialization is complete; final training
  authorization, trainer consumption, and the smoke-training decision remain
  separate boundaries.

Self-deception trap:

```text
Passing public checks or emitting a plausible final answer does not create an
SFT target.
```

### Checkpoint 3: Canonical Positive-SFT Token Materialization

Purpose:

```text
Turn approved source-level message prefixes into auditable trainer-ready tokens.
```

Settled policy:

- use the exact tokenizer compatible with the target base checkpoint;
- pin the tokenizer revision, chat template, and tool-call serialization;
- serialize each approved prefix once using trajectory aggregation;
- derive model-generated Python Unicode-string spans from the pinned ownership
  annotation while requiring exact canonical-render parity;
- give loss only to approved assistant-produced spans;
- keep system, user, and tool-observation spans as context with ignored labels;
- reject the whole example when it exceeds `max_sequence_length`;
- do not truncate, chunk, overlap, or summarize overlength examples.

Done when:

- the materialization outcome preserves exact source-record provenance;
- successful token ids and trainer-style labels are persisted;
- explicit overlength exclusions remain countable;
- tokenizer/template failures cannot be mistaken for policy exclusions;
- tests verify assistant-only loss, tool-call boundaries, EOS handling, and no
  hidden validator, scorer, or review metadata;
- persisted records are rebuilt or validated against their pinned inputs.

Current state: implemented and verified with both focused fixtures and the
pinned Qwen2.5-Coder-3B practice artifact.

Self-deception trap:

```text
A source-level JSONL row is not trainer-ready, and silently dropping every long
trajectory can make the resulting dataset look cleaner than its coverage is.
```

### Checkpoint 4: Preference-Pair Boundary

Purpose:

```text
Define preference data only where the comparison basis is auditable.
```

Start with trustworthy original model trajectories as possible alternatives.
Task success, gradability, trajectory-level behavioral acceptance, mechanical
redundancy, and reward-hack findings are evidence rather than discovery labels.
Actual leakage, ineligible splits, orchestration failures, and missing or
incomplete source evidence remain hard exclusions. Do not assume a chosen side
exists until an auditable adjudication says what can validly be preferred.

Done when:

- unlabeled shared-context comparison schema is defined;
- invalid comparisons are rejected in tests;
- deterministic discovery aggregates identical actions and enumerates distinct
  action pairs without using task outcome;
- reviewer-specific adjudication is defined and pins the exact source candidate,
  rubric, reason, decision time, and reviewer-specific provenance;
- the v0 overall-action rubric prioritizes task solvability over efficiency,
  requires local causal justification, and abstains when both actions are bad;
- unlabeled comparison discovery is persisted as a source-pinned export;
- adjudication is persisted as a separate source- and rubric-pinned review;
- every validated preferred adjudication is persisted in an exhaustive,
  reference-only preference-pair export;
- an atomic DPO training-materialization record requires two complete branches
  with one identical masked prompt and response-only labels, while leaving
  reference-model selection to the later training run;
- repeated observations supporting one preference alternative are all
  source-validated but materialize as one pair rather than frequency-weighted
  duplicates;
- the materialization export writes one completed or failed row per source pair,
  pins the target-model input protocol, defaults to unauthorized, and requires
  a recorded explicit override for learning-lab trainer consumption;
- DPO training remains deferred unless at least 20 auditable pairs exist; the
  present review has now met that minimum with 29 pairs across 20 contexts.

Self-deception trap:

```text
A failed model trace plus an oracle patch is not automatically a preference
pair unless the chosen response is represented in the same trainable format and
its provenance is allowed.
```

### Checkpoint 5: Smoke Training Decision

Purpose:

```text
Decide whether a tiny SFT smoke is legitimate this week.
```

Run a smoke only if:

- the data contract is written;
- the dataset builder produces legitimate positive examples;
- source data hashes are pinned;
- loss-masking tests pass;
- the config records base model, tokenizer, data hash, seed, git SHA, hardware,
  and runtime.

If positive SFT remains empty, do not force training. Preserve the blocker note
and continue with filtering, preference, and masking work.

Checkpoint status on 2026-07-22: completed as an operational LoRA smoke. An
explicitly authorized positive-SFT materialization supplied one 1,404-token
example with 497 effective shifted assistant targets. The pinned
Qwen2.5-Coder-3B-Instruct checkpoint completed three optimizer steps with
ordinary rank-8 LoRA adapters on `q_proj`, `k_proj`, `v_proj`, and `o_proj`,
using `alpha / rank = 1`. A separate two-step diagnostic run qualified the
training setup and was discarded. A freshly initialized adapter and optimizer
then performed all three real optimizer steps beginning at step 0.

The run artifact proves the intended mechanics: the optimizer contained exactly
the adapter parameters; every intended adapter received finite, nonzero gradient
evidence and changed during the configured two-step qualification run; the
fresh real-training adapter, frozen base, and optimizer isolation matched the
qualified initialization; every frozen base tensor remained bitwise unchanged;
and the saved adapter reloaded over the pinned base with exactly identical
adapter state, base state, and probe logits. Detailed per-parameter inspection
is confined to the discarded qualification run rather than imposed on real
training steps. This is an execution and invariant check, not evidence that
task quality improved.

## Verification Plan

Focused checks after each implementation checkpoint:

```bash
uv run pytest tests/training
uv run ruff check .
uv run pyright
git diff --check
```

Artifact checks as needed:

```bash
uv run agentenv trajectories review-validate \
  --source experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_export \
  --reviews experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_review

uv run agentenv training candidates export \
  --trajectories experiments/runs/week_09_training_gate_smoke_trajectory_export \
  --reviews experiments/runs/week_09_training_gate_smoke_trajectory_review \
  --out experiments/runs/week_09_training_gate_smoke_candidates \
  --overwrite

uv run agentenv training positive-sft review-init \
  --candidates experiments/runs/week_09_training_gate_smoke_candidates \
  --out experiments/runs/week_09_training_gate_smoke_positive_sft_review \
  --overwrite

uv run agentenv training positive-sft review-validate \
  --reviews experiments/runs/week_09_training_gate_smoke_positive_sft_review

uv run agentenv training positive-sft export \
  --candidates experiments/runs/week_09_training_gate_smoke_candidates \
  --reviews experiments/runs/week_09_training_gate_smoke_positive_sft_review \
  --out experiments/runs/week_09_training_gate_smoke_positive_sft \
  --overwrite
```

Historical Qwen trajectories may exercise the non-authorized development
pipeline, but a later release finalizer must reject any source whose exact eval
runtime and task hashes do not match its pinned trust artifacts.

## Fallback

If GPU training or positive data is blocked:

- do not manufacture positive rows;
- run tokenizer/serialization/loss-mask tests instead;
- write `docs/dpo_deferred_note.md`;
- keep positive SFT export empty and valid;
- preserve logs or blocker notes;
- continue filtering and preference-schema work.

Do not claim model improvement from this week.

## Current Acquisition Checkpoint (2026-07-13)

Two current-runtime acquisition suites now cover all 13 dev tasks:

```text
156 trajectories
20 hidden PASS
116 scored test failures plus one blocked INVALID_SHORTCUT
19 unscored model-loop failures
49 PASS-vs-non-PASS combinations with matching logical initial context
41 such combinations after exact assistant-behavior distinction
36 such combinations after exact patch distinction
```

Seven of thirteen dev tasks have at least one trusted positive anchor. The
second acquisition added the first passes for `repair_query_encoding` and
`repair_template_expansion`; six harder tasks still have no pass.

The aggregate harness audit passes, control calibration is stable at three
repeats, and all 14 declared public checks are idempotent across two seed-state
runs. All 156 trajectory reviews remain `not_reviewed`, so all 156 training
candidates remain analysis-only.

Newer-model practice gates did not justify further acquisition: `gpt-oss:20b`
used an unsupported provider-native tool-call channel, and Qwen3.5-27B ended
three of three repeated smokes in invalid model output. Neither model was
admitted by weakening the existing action contract.

This satisfies the acquisition-groundwork objective for later review of at
least 20 comparison candidates. It does not satisfy Checkpoint 3: no
chosen/rejected authority, comparability rule beyond initial context, review
decision, preference record, serialization contract, or DPO loss policy has
been designed.

The next guided design question remains:

```text
Which differences between two trajectories with the same logical initial
context are allowed before a human preference judgment becomes too confounded
to support one chosen/rejected label?
```

## Review And Downstream-Readiness Checkpoint (2026-07-13)

The `not_reviewed` counts above describe the acquisition checkpoint before the
AI-proxy review pass. They are superseded by this later state:

```text
trajectory reviews:
  accepted for objective-specific consideration: 101
  needs_followup: 55

rebuilt training-candidate eligibility:
  positive-SFT prefix review: 100
  negative-example use: 81
  preference pairing: 82

positive-SFT-specific reviews:
  accepted: 18
  needs_followup: 80
  rejected: 2

positive-SFT source-level exports: 18 examples
```

The reviewer identity is explicitly recorded as an AI proxy acting on the
user's behalf. General trajectory acceptance permits only objective-specific
consideration. It is not an approval to imitate the entire transcript, and it
does not establish a preference direction.

The two rejected successful trajectories each contained a failed tool action
in the contiguous history before recovery. This is expected evidence that task
success alone does not make a transcript a clean positive target.

The acquisition foundation is now sufficient for the remaining SFT and
preference design. A separate downstream-readiness audit found that additional
natural-model acquisition is not the next blocker. The pre-training foundations
still missing are:

```text
an exact trainable base checkpoint and tokenizer
a minimal training runtime
a same-stack path for evaluating the base model and trained adapter
an exact pre-training baseline
an untouched evaluation slice if the experiment intends to measure anything
  beyond in-sample plumbing, memorization, or trained-example regression
```

The current environment has a 16 GiB RTX 4080 SUPER and enough host memory and
disk for a small smoke, but contains none of the expected PyTorch/Hugging Face/
PEFT training packages. `agentenv training` currently constructs data
artifacts; it does not train a model.

Do not solve these gaps by selecting a checkpoint, serving architecture, or
heldout task distribution without the corresponding guided design decision.
In particular, do not relabel any of the 13 inspected dev tasks as heldout.

Readiness audit:

```text
experiments/analysis/downstream_foundation_readiness.md
```

## Heldout-Private Foundation Checkpoint (2026-07-13)

The untouched-evaluation prerequisite above is now established without running
any natural-model policy on it.

Six newly authored tasks were added directly to `heldout_private`; no inspected
dev task was relabeled. Before freeze, only deterministic scorer and scripted-
agent controls were run:

```text
task pack: 1 practice, 13 dev, 6 heldout-private
oracle: 6/6 hidden PASS
no-op: 6/6 public PASS, hidden FAIL
public-only: 6/6 public PASS, hidden FAIL
happy agent control: 6/6 hidden PASS
recoverable agent control: 6/6 hidden PASS
malformed agent control: 6/6 invalid model output
replay groups: 6/6 PASS, 0 mismatches
public checks: 6/6 IDEMPOTENT at repeat_count=2
natural-model attempts before freeze: 0
```

The task bytes and split are pinned by:

```text
data/task_packs/repo_patch_python_v0/heldout_private.freeze.json
docs/heldout_evaluation_protocol.md
tests/test_heldout_freeze.py
```

The heldout slice may not influence training data, filtering, prompts,
decoding, budgets, hyperparameters, scorer changes, or task selection. The
base checkpoint and adapter should be evaluated only after all such choices
are frozen, preferably as one paired operation through the same serving path.

The remaining hard execution foundation is therefore the trainable-model
round trip:

```text
exact base checkpoint + tokenizer
tokenizer-level serialization and loss mask
minimal adapter training runtime
same-path base and adapter serving
paired heldout evaluation after all choices are frozen
```

Checkpoint/model selection, loss-bearing spans, and adapter/serving semantics
remain guided post-training design questions. Task-pack authoring and control
mechanics do not require user design time.

## Materialization Merge And Catch-Up Checkpoint (2026-07-17)

The heldout-foundation statement above is superseded for tokenizer plumbing:
Qwen2.5-Coder-3B now has a hash-pinned model-input protocol, immutable tokenizer
revision, canonical/ownership templates, assistant-only label materialization,
and a native raw-prompt Ollama inference path. It still has no trainer or final
training-authorized release artifact.

The acquisition and materialization branches are now reconciled. Existing raw
trajectories and trajectory reviews remain valid development evidence, but the
candidate and positive-SFT derivatives must be regenerated under the current
schemas. Their source eval runtime predates the merged tree, so regeneration
alone cannot authorize training.

Catch-up order:

```text
1. use existing evidence to finish release/trainer and preference design
2. rebuild candidates/reviews/source exports for development as needed
3. materialize accepted SFT sources under the pinned target protocol
4. stabilize all source and dependency changes that enter runtime provenance
5. reacquire the selected model/task evidence under that final runtime
6. run final harness audit and repeated control calibration
7. rebuild, review, materialize, and issue the first authorized release
8. train and evaluate base versus adapter through the frozen heldout protocol
```

Do not spend another full natural-model acquisition before step 4: the current
strict runtime-equality gate would invalidate it after the next package or lock
change.

## Integrated SFT And DPO Materialization Checkpoint (2026-07-21)

The latest `week9` implementation has been merged into the acquisition
foundation. The current development evidence has been regenerated through both
training-data paths:

```text
source trajectories: 156

positive-SFT review opportunities: 100
  accepted: 18
  needs_followup: 80
  rejected: 2
positive-SFT materializations: 18 completed, 0 failed

preference comparison candidates: 117
comparison shared contexts: 63
  preferred: 29
  tie: 16
  ambiguous: 72
preferred-pair shared contexts: 20
DPO materializations: 29 completed, 0 failed
```

The reviewer provenance identifies Codex as an AI proxy acting under the
user's explicit authorization. Preference labels were based on local action
quality and available rollout evidence, never copied from terminal task
outcomes. Ambiguous comparisons remain abstentions: only explicitly preferred
adjudications can produce chosen/rejected pair records.

All 18 SFT records and 29 DPO pairs were deterministically reloaded through
their full pinned source chains. Token/label ownership, shared DPO prompt
prefixes, response-only labels, sequence bounds, and chosen/rejected inequality
were rechecked. On 2026-07-21 the user explicitly accepted the known source-
runtime mismatch for this non-production learning exercise. The 16 trainer-
shaped materialization manifests now record
`training_authorization=authorized` together with an
`explicit_user_override`, authorizer `kshitij`, and the exception rationale.
Upstream candidate, review, source, comparison, and pair artifacts remain
`not_authorized` construction evidence.

The next boundary is no longer data-contract or token-materialization plumbing.
It is target and reference checkpoint semantics, a minimal trainer, and paired
base-versus-adapter evaluation through the frozen heldout protocol. A normal
trust-gated release remains necessary before any production-style claim.
