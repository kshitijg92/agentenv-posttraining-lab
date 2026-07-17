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

The next missing boundary is target-model tokenization and label
materialization. A source-level positive-SFT example is not yet a trainer-ready
batch.

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
```

Remaining major artifacts or boundaries:

```text
persisted target-model positive-SFT token records
explicit token-materialization exclusion outcomes
preference dataset schema/builder/export
negative-example export boundary
tokenizer-conformance and loss-masking tests
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
- the materialization result union now represents completed token/label output,
  explicit overlength failures, and other materialization failures with exact
  source, protocol, sequence-policy, and materializer provenance;
- target-model token materialization remains before any training smoke.

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

Start with eligible gradable trajectories as possible rejected sides. Do not
assume a chosen side exists until the contract says what can validly be chosen.

Done when:

- preference-pair schema is defined;
- invalid pairs are rejected in tests;
- a builder either writes valid JSONL or documents insufficient pairs;
- DPO remains deferred unless at least 20 auditable pairs exist.

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
