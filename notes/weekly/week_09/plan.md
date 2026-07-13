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
training eligibility is separate from task success, and reward-hack evidence
must never become a positive training example by accident
```

Current Week 7/8 artifact state:

```text
eval suite:
  experiments/runs/qwen_model_eval_suite_sampling_4096

trajectory export:
  experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_export

trajectory review:
  experiments/runs/qwen_model_eval_suite_sampling_4096_trajectory_review

training candidates:
  experiments/runs/qwen_model_eval_suite_sampling_4096_training_candidates

positive SFT export:
  experiments/runs/qwen_model_eval_suite_sampling_4096_positive_sft

reward-hack audit:
  experiments/runs/reward_hack_audit_week_08_v1
```

Current training-candidate summary:

```text
records: 21
trainable: 3
positive_sft: 0
negative_examples: 3
preference_data: 2
analysis_only: 18
```

Current positive SFT summary:

```text
record_count: 0
```

This is expected. The current Qwen model trajectories include public-pass /
hidden-fail and cannot-grade failures, not successful hidden-pass agent
trajectories.

## Existing Implementation Surface

Week 7 already created part of the Week 9 surface:

```text
src/agentenv/training/schema.py
src/agentenv/training/builder.py
src/agentenv/training/export.py
src/agentenv/training/sft_builder.py
tests/training/test_training_schema.py
tests/training/test_training_builder.py
tests/training/test_training_export.py
tests/training/test_sft_builder.py
```

Existing CLI:

```text
agentenv training candidates export
agentenv training sft export
```

Manual artifacts still missing or incomplete:

```text
docs/post_training_data_contract.md
preference dataset schema/builder/export
negative-example export boundary
tool-call serialization and loss-masking tests
configs/train/week09_sft_smoke.yaml
configs/train/week09_dpo_deferred.yaml
docs/dpo_deferred_note.md
notes/weekly/week_09/implementation_notes.md
notes/weekly/week_09/learnings.md
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
the repo can define, validate, and export post-training data candidates while
rejecting contaminated, untrusted, or split-forbidden examples in code
```

## Design Priority

Preserve data-use boundaries:

- positive-SFT review requires trustworthy model-generated trajectory evidence,
  a trainable split, no leakage, no orchestration failure, and a passing
  reward-hack gate; task success prioritizes review but is not required;
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

## First Design Question

Before implementing new schemas or builders, decide:

```text
What should count as one trainable SFT example in this repo, and which evidence
must make it ineligible even if the task succeeded?
```

Do not implement the full SFT/preference pipeline before answering this. The
answer controls source provenance, split rules, review gates, reward-hack
exclusion, leakage checks, and loss-masking expectations.

## Planned Outputs

Primary planned artifacts:

```text
notes/weekly/week_09/plan.md
notes/weekly/week_09/implementation_notes.md
notes/weekly/week_09/learnings.md
docs/post_training_data_contract.md
docs/dpo_deferred_note.md
configs/train/week09_sft_smoke.yaml
configs/train/week09_dpo_deferred.yaml
```

Likely code/test artifacts, after design:

```text
src/agentenv/training/preference_schema.py
src/agentenv/training/preference_builder.py
tests/training/test_preference_pairs.py
tests/training/test_tool_call_serialization.py
tests/training/test_loss_masking.py
```

Possible code/test artifacts, depending on design:

```text
src/agentenv/training/negative_examples.py
src/agentenv/training/sft_schema.py
src/agentenv/training/serialization.py
src/agentenv/training/loss_masking.py
configs/data/post_training_week09.yaml
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
- repair-selection CLI wiring remains before a real repaired artifact smoke.

Self-deception trap:

```text
Passing public checks or emitting a plausible final answer does not create an
SFT target.
```

### Checkpoint 3: Preference-Pair Boundary

Purpose:

```text
Define preference data only where the comparison basis is auditable.
```

Start with the current two eligible public-pass/hidden-fail Qwen trajectories
as possible rejected sides. Do not assume a chosen side exists until the
contract says what can validly be chosen.

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

### Checkpoint 4: Tool-Call Serialization And Loss Masking

Purpose:

```text
Specify how prompt-loop transcripts become trainable token sequences.
```

Tests should cover:

- chat template formatting;
- EOS handling;
- assistant/action loss masking;
- masking user prompts;
- masking tool observations;
- malformed tool-call rejection;
- no inclusion of hidden validator or review metadata.

Done when:

- the intended mask policy is written down;
- tests encode the policy;
- any missing tokenizer/model dependency is isolated from pure serialization
  tests.

Self-deception trap:

```text
A valid JSONL row is not necessarily trainable if the loss mask teaches the
model to imitate user prompts, tool outputs, or evaluator metadata.
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
  --harness-audit experiments/harness_audit/week_09_harness_audit_v1 \
  --control-calibration experiments/runs/week_09_control_calibration_v0 \
  --out experiments/runs/week_09_training_gate_smoke_candidates \
  --overwrite

uv run agentenv training sft export \
  --candidates experiments/runs/week_09_training_gate_smoke_candidates \
  --out experiments/runs/week_09_training_gate_smoke_positive_sft \
  --overwrite
```

The historical Qwen trajectory export predates the current task hashes and is
expected to fail this gate. It must not be silently re-exported with current
calibration evidence.

## Fallback

If GPU training or positive data is blocked:

- do not manufacture positive rows;
- run tokenizer/serialization/loss-mask tests instead;
- write `docs/dpo_deferred_note.md`;
- keep positive SFT export empty and valid;
- preserve logs or blocker notes;
- continue filtering and preference-schema work.

Do not claim model improvement from this week.
