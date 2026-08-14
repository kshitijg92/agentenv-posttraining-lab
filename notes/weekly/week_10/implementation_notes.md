# Week 10 Implementation Notes

Current boundary as of 2026-07-23: action efficiency is an embedded judgment
on the existing `PositiveSFTReviewRecord`. There is no standalone efficiency
review artifact, schema, manifest, or CLI. The earlier standalone implementation
below is retained only as design history and is explicitly superseded. The
100-row review universe is complete at 98 prefix accepted, 2 prefix rejected,
94 efficiency accepted, 4 efficiency rejected, and no unresolved or abstained
decisions. Because training and policy evaluation have not started, the Week
10 experiment will use all 98 accepted prefixes and all 94
efficiency-accepted prefixes. The eight exports and materializations have been
regenerated successfully from the completed reviews.

## 2026-07-22 Source-Boundary Correction

### Decision

Use the existing `PositiveSFTExampleRecord` as the exact efficiency-review and
filtering unit. Do not introduce a standalone task-partition config, schema,
manifest, artifact type, resolver, validator, or CLI.

Training task ids are derived from the source records:

```text
train_task_ids =
  unique record.task_input.task_id values from consumed source records
```

Selection task ids belong to the selection eval config. Eval manifests already
pin the exact selected-task hashes. The dataset/eval or comparison workflow
must verify:

```text
train_task_ids intersect selection_task_ids == empty
```

The current preflight also confirms that the six derived train ids and thirteen
planned selection ids cover the 19 current dev tasks, but that whole-dev
coverage is not a new persisted authority.

### Why The Earlier Design Was Removed

The attempted task-partition layer duplicated facts already owned elsewhere:

- six train task ids were derivable from the 18 exact SFT source records;
- source record hashes belong in efficiency-review and dataset artifacts;
- thirteen selection task ids belong in the eval config;
- selected-task hashes are already produced by eval manifests.

Persisting those facts again would create a second authority that could drift
without strengthening filtering, leakage prevention, reproducibility, or policy
comparison.

The implementation was removed before Checkpoint 2:

- schedule-neutral partition config;
- task-partition source module and schemas;
- artifact type;
- resolve and validate CLI commands;
- focused partition tests;
- generated partition snapshot.

No compatibility alias, migration, or version bump was retained.

Verification after removal:

```text
agentenv training --help -> candidates, positive-sft, preferences only
focused CLI/artifact/positive-SFT tests -> 43 passed
uv run ruff check . -> passed
uv run pyright -> 0 errors, 0 warnings
```

### Retained Evidence

The task pack remains valid:

```text
task pack: repo_patch_python_v0
practice: 1
dev: 19
heldout_private: 6
public_calibration: 0
total: 26
```

The 18 exact positive-SFT source records still come from six dev tasks:

```text
preserve_cli_error_codes: 5
repair_jsonl_deduper: 7
repair_query_encoding: 1
repair_record_chunking: 1
repair_relative_path: 3
repair_template_expansion: 1
```

Those records became the direct inputs to the efficiency-review queue.

### Repository Guidance

`AGENTS.md` now includes an artifact-economy gate. Before adding a first-class
artifact or CLI surface, the design must identify its unique authority,
producers, consumers, and the exact property that would be lost without it. If
the relationship can be derived from existing typed records or checked at an
existing consumer boundary, it should not become another persisted layer.

### Checkpoint 1 Handoff

The next step from this checkpoint was to implement only the efficiency-review
contract and initialized 18-row queue over the existing
`PositiveSFTExampleRecord` sources.

## 2026-07-22 Checkpoint 2: Efficiency Review Queue

Status: superseded and removed on 2026-07-23. See the boundary-collapse note
below.

### Outcome

Checkpoint 2 is implemented. The existing positive-SFT training
materialization manifests are the entrypoint. Each completed materialization
row already carries:

```text
source_positive_sft_example_id
source_positive_sft_example_record_hash
```

The loader follows the materialization manifest's pinned positive-SFT export,
loads the exact `PositiveSFTExampleRecord`, and verifies the id, record hash,
record order, file hashes, and manifest counts. It trusts the already-approved
positive-SFT provenance boundary and does not reconstruct the earlier harness,
candidate, repair, and positive-SFT review workflow.

The four non-empty materialization artifacts contribute:

```text
natural_model_anchor_contrast_acquisition/devstral-sampling: 7
natural_model_anchor_contrast_acquisition/qwen2-5-coder-14b-sampling: 3
natural_model_anchor_contrast_acquisition/qwen3-coder-30b-sampling: 6
natural_model_dev_coverage_acquisition/devstral-sampling: 2
total: 18
```

The initialized artifact is:

```text
experiments/runs/week_10_positive_sft_efficiency_review
record_count: 18
not_reviewed: 18
reviewed: 0
rubric_hash: xxh64:69546da9c204d55d
```

It owns only the new judgment:

- exact source example id and hash;
- shared review status, decision, reviewer, and optional notes provenance;
- a required decision reason for completed reviews;
- exact avoidable assistant message ids for rejections.

Task ids, policy ids, sequence length, supervised-token count, action count,
and exact source messages are derived into `review_queue.md` for review. They
are not copied into the authoritative review rows. Reviews filter whole
examples; they never rewrite individual messages or labels.

### Commands

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

### Validation Boundary

Initialization and validation reject:

- missing, unknown, or duplicate source rows;
- duplicate source examples across materialization artifacts;
- source manifest, JSONL, id, hash, order, or count drift;
- failed materialization records;
- incomplete reviewed rows;
- rejected rows without exact assistant-message witnesses;
- witnesses that name unknown or non-assistant messages;
- unpinned or hash-mismatched review notes.

The initialized `not_reviewed` state is valid at this checkpoint so a reviewer
can populate the queue. The later filtered export must require zero
`not_reviewed` rows.

Focused verification:

```text
tests/training/test_positive_sft_efficiency_review.py
tests/test_artifacts.py
7 passed
ruff: passed
pyright: 0 errors, 0 warnings
full repository suite: 1206 passed
git diff --check: passed
```

### Next Small Step

Populate all 18 decisions under the frozen rubric, validate zero
`not_reviewed` rows, and report accepted, rejected, and `needs_followup`
counts. Stop before building raw or filtered training artifacts.

## 2026-07-23 Boundary Collapse: One Positive-SFT Review

### Decision

The positive-SFT prefix review and action-efficiency review are two judgments
over the same semantic object: the exact retained assistant prefix.
Materialization only tokenizes that prefix; it does not create a new semantic
review unit. Therefore efficiency now lives inside the existing
`PositiveSFTReviewRecord`.

The combined row keeps the existing prefix fields and adds one optional:

```text
efficiency_judgment
  rubric_id
  review_id
  reviewer_id
  review_decision
  decision_reason
  review_notes_ref
  avoidable_assistant_message_ids
```

The absence of `efficiency_judgment` is sufficient state:

```text
prefix not yet reviewed       -> efficiency blocked
prefix rejected or unresolved -> efficiency not applicable
prefix accepted + null        -> efficiency not reviewed
prefix accepted + judgment    -> efficiency reviewed
```

No second persisted review status or source identity is necessary.

### Removed Surface

The refactor removed:

- `PositiveSFTEfficiencyReviewRecord`;
- `PositiveSFTEfficiencyReviewManifest`;
- the `positive_sft_efficiency_review` artifact type;
- the standalone efficiency review implementation module;
- `efficiency-review-init` and `efficiency-review-validate`;
- the standalone efficiency review test module;
- `experiments/runs/week_10_positive_sft_efficiency_review`.

The change removes roughly 1,500 lines of standalone implementation and tests.

### Existing Artifact Migration

Before the prefix backlog was adjudicated, the eight existing positive-SFT
review artifacts contained 100 prefix-review rows:

```text
prefix accepted / efficiency reviewed: 18
prefix rejected or needs_followup / efficiency not applicable: 82
```

All rows contained the explicit nullable field. The initial 18 eligible rows
received completed judgments, while the then-inapplicable 82 rows retained
`efficiency_judgment: null`. The queue files at that checkpoint showed the 18
eligible rows with:

- the combined review row;
- the frozen efficiency rubric id;
- the exact retained prefix messages;
- exact assistant message ids and action count.

The old recursive review provenance contains absolute paths to a retired
worktree. The one-time queue refresh therefore used the adjacent hash-pinned
positive-SFT exports, whose messages are exactly the previously approved
prefixes. No compatibility path resolver was added.

The existing positive-SFT exports and token materializations were intentionally
not regenerated while judgments remained editable. Once backlog adjudication
completed, the valid training population expanded and the provisional
train/selection split had to be derived again. No trajectory, harness-audit,
or agent execution had to be rerun.

### Current Invariants

- Efficiency applies only when the prefix decision is `accepted`.
- Every completed judgment pins
  `positive_sft_action_efficiency_v0`.
- A rejected judgment requires at least one unique assistant message id.
- Evidence must identify an assistant message inside the retained prefix.
- Accepted and efficiency-abstained judgments cannot claim avoidable actions.
- Raw training uses every prefix-accepted materialization.
- Filtered training uses only rows with an accepted embedded judgment.
- Training consumes existing materialization records; no copied
  `PositiveSFTTrainingSelectionRecord` is introduced.

### Verification Policy

Focused checks are the default during this checkpoint. The full repository
suite is deferred until the Week 10 integration boundary.

```text
positive-SFT schema/review/artifact/CLI focused tests: 33 passed
Ruff focused checks: passed
Pyright focused checks: 0 errors, 0 warnings
combined artifact accounting: 8 artifacts, 100 rows, 18 reviewed, 0 pending
standalone efficiency artifact absent
full repository suite: deferred until the Week 10 integration boundary
```

### Next Small Step At That Checkpoint

The next step was to resolve raw and filtered inputs after the review universe
was complete. Later backlog adjudication expanded that universe, so the stale
18-row generated artifacts must be overwritten.

## 2026-07-23 Completed Embedded Efficiency Review

### Outcome

Codex reviewed the 18 prefixes in the already materialized Week 10 population
on the user's behalf under `positive_sft_action_efficiency_v0`. The accounting
for that frozen population is:

```text
reviewed: 18
accepted: 14
rejected: 4
needs_followup: 0
pending: 0

S_raw unique examples: 18
S_filtered unique examples: 14
raw assistant actions: 117
filtered assistant actions: 85
raw supervised tokens: 10,205
filtered unique supervised tokens: 7,000
```

The supervised-token figures describe the existing one-pass materializations.
They are reporting signals, not the matched-exposure training schedule.

### Rejected Prefixes

| Example | Task | Exact avoidable action | Reason |
|---|---|---|---|
| `positive_sft_example_d8ebdcf975f578ea` | `preserve_cli_error_codes` | `message_f01ad86192404fa1b0a14db56e31f54e` | Second unchanged `src/validate_records.py` read before any write |
| `positive_sft_example_59c8f157e4a63b5d` | `preserve_cli_error_codes` | `message_ada15f297b3148249f33dd2b3c81f55e` | Second unchanged `src/validate_records.py` read before any write |
| `positive_sft_example_1bb30cec2cc3dc78` | `preserve_cli_error_codes` | `message_41d73bea570c42efbd8dba27b01a69b2` | Unused `pyproject.toml` inspection before a standard-library-only repair |
| `positive_sft_example_c74d2c81780fd413` | `repair_jsonl_deduper` | `message_9e942f8f981644f2ae676732282a2003` | Unused `pyproject.toml` inspection before a standard-library-only repair |

The duplicate-read evidence was checked directly: each second tool result was
byte-for-byte equal to the first, and no write occurred between the reads.
The environment reads did not affect the subsequent edits or validation.

Passing pre-edit tests were not treated as waste. They remain allowed baseline
diagnosis under the frozen rubric.

### Concentration

```text
by source policy:
  devstral-sampling: 9 accepted, 0 rejected
  qwen2-5-coder-14b-sampling: 3 accepted, 0 rejected
  qwen3-coder-30b-sampling: 2 accepted, 4 rejected

by task:
  preserve_cli_error_codes: 2 accepted, 3 rejected
  repair_jsonl_deduper: 6 accepted, 1 rejected
  all four other training tasks: 6 accepted, 0 rejected
```

This concentration is a result to report, not a reason to change the rubric or
force a different filtered count.

### Focused Validation

The completion check:

- parsed all 100 rows through `PositiveSFTReviewRecord`;
- reconstructed exact messages for all 18 accepted prefixes from the adjacent
  hash-pinned positive-SFT exports;
- validated each rejected witness as an assistant message inside the retained
  prefix;
- proved the decision mapping covered the 18 accepted prefixes exactly once;
- refreshed all 18 combined queue rows;
- reported 14 accepted, 4 rejected, 0 needs-followup, and 0 pending.

The normal recursive `review-validate` command still encounters absolute paths
to the retired foundation worktree in historical upstream manifests. This
checkpoint did not add a compatibility resolver or mutate the older provenance
chain. Instead, the focused completion check used the adjacent hash-pinned
positive-SFT exports that contain the exact approved prefixes. The one-time
downstream regeneration should pin the current combined reviews and current
derived artifacts.

The full repository suite remains deferred until the Week 10 integration
boundary.

## 2026-07-23 Prefix Backlog Adjudication

### Why 80 Rows Said Needs Followup

The earlier AI-proxy review used one blanket decision for task-failed
trajectories:

```text
No positive prefix was adjudicated in this pass. The failed trajectory may
still contain useful early behavior, but accepting it requires
message-by-message credit assignment.
```

That label recorded deferred work; it was not evidence that 80 sources were
ambiguous or low quality. The backlog was reviewed assistant action by
assistant action under the existing contiguous-prefix contract.

The boundary was placed before the earliest:

- failed or invalid tool action;
- workspace write in a task-failed trajectory;
- premature final answer;
- repeated unchanged read.

A passing pre-edit public check remained an allowed diagnostic action. Five
automatically proposed boundaries were shortened by one action because an
unused `pyproject.toml` read had no downstream role.

### Decisions

Of the 80 unresolved rows:

```text
accepted exact diagnostic prefix: 79
rejected because the first action failed: 1
unresolved: 0
```

One older rejected row was corrected after the same rule was applied
consistently. It had four clean inspect-and-baseline actions before a malformed
write call, so the boundary now ends at the passing baseline check. The other
older rejection remains rejected because its first action reads a nonexistent
path; no nonempty clean prefix exists.

Current review-universe accounting:

```text
prefix accepted: 98
prefix rejected: 2
prefix unresolved: 0

efficiency accepted: 94
efficiency rejected: 4
efficiency abstained: 0
efficiency pending: 0
```

All 80 newly accepted prefixes pass efficiency review because the approved
boundary excludes the first failed, redundant, or otherwise avoidable action.
Across all 98 accepted prefixes there are 338 retained assistant actions, with
2 to 8 actions per prefix. The 80 newly accepted prefixes contribute 221 of
those actions. These counts describe retained behavior; action count alone did
not determine a decision.

### Review Labels

The persisted decision enum remains shared and still stores
`needs_followup`. Reports now use dimension-specific language:

```text
prefix needs_followup     -> prefix_unresolved
efficiency needs_followup -> efficiency_abstained
```

This avoids presenting unresolved prefix credit assignment and an efficiency
reviewer abstention as though they were the same operational state. No new
decision schema or compatibility alias was introduced.

### Training-Population And Split Correction

The earlier 18-row materialization population and
six-train-task/thirteen-selection-task split were provisional: neither training
nor policy evaluation had started. Completing prefix review expanded the
valid raw population to 98 prefixes across 11 tasks. Five were in the
provisional selection set:

```text
repair_config_precedence
repair_csv_projection
repair_duration_parser
repair_header_merge
repair_semver_precedence
```

There is no reason to discard those reviewed prefixes merely to preserve a
stale split. Week 10 will regenerate:

```text
S_raw: 98 prefix-accepted examples across 11 tasks
S_filtered: 94 efficiency-accepted examples across the same 11 tasks
policy selection: the remaining 8 dev tasks
```

The task sets still partition all 19 dev tasks with an empty intersection.
Before evaluation, the eight selection tasks must be checked for comparable
difficulty and frozen in the selection config. If that set is too small or
distributionally mismatched, add new dev tasks rather than train on a
selection task or throw away valid SFT units.

No task-partition artifact is needed. Training task ids are derived from the
regenerated source records; selection task ids belong to the eval config; their
disjointness is checked at the consuming boundary.

### Artifact Refresh And Focused Validation

The existing eight combined review artifacts were overwritten in place:

- all 100 rows parse as `PositiveSFTReviewRecord`;
- every accepted boundary identifies exactly one assistant source message;
- all newly accepted final actions have successful tool results;
- no newly retained prefix contains a workspace write;
- all four efficiency-rejection witnesses name retained assistant messages;
- review notes are hash-pinned after refresh;
- the queues contain all 98 exact accepted prefixes;
- no temporary inventory or adjudication script remains.

Focused checks:

```text
positive-SFT review/schema/builder and repair-export tests: 51 passed
Ruff on changed source and tests: passed
Pyright on changed source and tests: 0 errors, 0 warnings
full repository suite: deferred until the Week 10 integration boundary
```

## 2026-07-23 Regenerated 98-Row Training Population

### Provenance Refresh

The standard trajectory re-export could not load the historical model-config
payloads under the current stricter schema because they predate the required
model-input-protocol field. No compatibility parser was added.

Instead, the in-progress provenance chain used by positive-SFT construction was
refreshed in place:

- trajectory `eval_run_path`, eval-config path, splits-lock path, and
  task-manifest path now resolve inside the current worktree;
- trajectory JSONL and manifest hashes were recomputed;
- trajectory-review source paths and hashes were refreshed without changing
  review rows;
- training-candidate source paths and hashes were refreshed without changing
  candidate rows;
- combined positive-SFT review manifests now pin the current candidate
  manifests.

The refresh was transactional and ran the standard
`validate_positive_sft_review_artifact` path for all eight policies before
committing the changes. It validated 156 trajectory records, 100 combined
review rows, 98 accepted prefixes, and all embedded efficiency judgments.

### Export And Materialization

All eight positive-SFT exports were overwritten from the current combined
reviews:

```text
anchor contrast:
  devstral-sampling: 14
  qwen2-5-coder-14b-sampling: 15
  qwen3-14b-sampling: 15
  qwen3-coder-30b-sampling: 15

dev coverage:
  devstral-sampling: 6
  qwen2-5-coder-14b-sampling: 13
  qwen3-14b-sampling: 12
  qwen3-coder-30b-sampling: 8

total: 98
```

The corresponding target-model materializations use:

```text
protocol: qwen2_5_coder_3b_agentenv_json
max sequence length: 32,768
local pinned tokenizer: required
training authorization: explicit learning-lab override
```

Result:

```text
materialization artifacts: 8
records: 98
completed: 98
failed: 0
sequence-length exceeded: 0
materialization errors: 0
```

### Raw And Filtered Accounting

Every materialized row was joined back through its exact
`PositiveSFTExampleRecord` hash to the current combined review hash and
approved assistant boundary.

```text
S_raw:
  examples: 98
  tasks: 11
  supervised tokens: 16,412
  serialized sequence tokens: 97,005

S_filtered:
  examples: 94
  tasks: 11
  supervised tokens: 13,207
  serialized sequence tokens: 86,700

removed:
  examples: 4 (4.08%)
  supervised tokens: 3,205 (19.53%)
  serialized sequence tokens: 10,305 (10.62%)
```

All four exclusions come from `qwen3-coder-30b-sampling`:

```text
raw: 23 examples / 5,441 supervised tokens
filtered: 19 examples / 2,236 supervised tokens
```

Three exclusions are from `preserve_cli_error_codes` and one from
`repair_jsonl_deduper`. Both tasks remain represented after filtering, so raw
and filtered task support is identical.

The eleven training tasks and eight remaining dev tasks partition all nineteen
dev tasks with an empty intersection. No practice, heldout-private, or
public-calibration task entered either training population.

### Focused Verification

```text
standard combined-review validation: 8 / 8 artifacts
positive-SFT exports: 8 artifacts / 98 exact examples
materializations: 98 completed / 0 failed / 0 overlength / 0 errors
raw-to-filtered exact review join: 98 accounted / 94 selected / 4 rejected
focused positive-SFT tests: 52 passed
Ruff focused checks: passed
Pyright focused checks: 0 errors, 0 warnings
retired-worktree paths in the consumed provenance chain: 0
full repository suite: deferred until the Week 10 integration boundary
```

### Next Small Step

Wire the verified immutable local client into the eval model-config/provenance
boundary, reuse one loaded composition for an eval run, and execute one
practice-task agent smoke for both B0 and the known Week 9 adapter. Do not
construct the 16,412-token matched schedules or launch either treatment run
before that final path-parity check.

## 2026-07-23 Immutable Base/Adapter Local Serving Boundary

### Policy Composition Decision

One client instance now binds one immutable composition for its full lifetime:

```text
policy id
+ exact Hugging Face base repository and commit
+ optional local LoRA adapter directory and directory hash
```

There is no adapter-switching method. B0 uses the base with no adapter, while
an adapted policy uses the same loader and client class with one PEFT adapter
loaded on top. The adapter is not merged into the base.
`HuggingFaceRevisionPin` is frozen as well, so the nested base identity cannot
be mutated after constructing the otherwise frozen policy binding.

Before loading model weights, the adapted path requires:

- the adapter path and hash to be present together;
- the observed adapter-directory hash to match;
- `adapter_config.json` to name the exact base repository and revision;
- the model-input protocol checkpoint and tokenizer to match that base.

After PEFT loading, the client requires exactly one active adapter named
`policy`, no merged adapter, and no trainable serving parameters. This prevents
a nominal B1 run from silently becoming B0, a merged derivative, or a mutable
multi-adapter process.

### Deterministic Generation Contract

The local client implements the existing `ModelClient` protocol and:

- renders messages through the pinned AgentEnv model-input protocol;
- uses an explicit fresh Transformers `GenerationConfig` rather than inheriting
  repository sampling defaults;
- forces greedy generation and disables model-default fallback;
- rejects sampling, seeds, stop strings, top-k, and non-unit top-p rather than
  silently ignoring them;
- passes the pinned end-of-turn and padding token ids;
- reports exact serialized prompt and generated completion token counts;
- includes a generated terminal end-of-turn token in completion-token usage
  while removing special tokens from returned text;
- attributes context overflow, timeout, loading, tokenization, generation, and
  decoding failures with typed model responses where generation has begun.

The client rejects a request when
`prompt_tokens + max_new_tokens` exceeds the pinned model context window. It
does not silently shorten the generation budget.

### Focused Verification

```text
focused local-client, input-protocol, and LoRA-package/schema tests: 30 passed
Ruff focused checks: passed
Pyright focused checks: 0 errors, 0 warnings
full repository suite: deferred
```

A real RTX 4080 SUPER smoke then loaded the cached pinned
Qwen2.5-Coder-3B-Instruct checkpoint twice, releasing B0 before loading B1:

```text
B0:
  adapter id: null
  prompt tokens: 40
  completion tokens: 8
  total tokens: 48
  finish: stop_criteria_met
  error: null

Week 9 operational-smoke adapter:
  adapter id: xxh64:ccd2828a4bc5fbe1
  prompt tokens: 40
  completion tokens: 8
  total tokens: 48
  finish: stop_criteria_met
  error: null
```

Both outputs had the same SHA-256 on this tiny prompt. That is not a failure:
the Week 9 adapter had only three operational-smoke steps, and this check is
serving evidence, not efficacy evidence.

### Remaining Checkpoint 5 Work

This checkpoint is not yet complete. The client was exercised directly, not
through an eval config and practice-task prompt loop. The existing eval
orchestrator constructs remote-provider clients per attempt; the local path
must instead bind and load one immutable composition for the eval run, then
reuse it across that run's task attempts. Model config and provenance must pin
the base, optional adapter source, runtime dtype/device, and input protocol
without copying facts already authoritative in a completed LoRA training
manifest.

## 2026-08-07 Hash-Pinned Adapter Model Config Boundary

### Config Ownership

The local Transformers/PEFT model config now has one optional `adapter` field:

```text
adapter: null
```

for B0, or a relative `path + content_hash` reference to a positive-SFT LoRA
training-run manifest for an adapted policy.

The config does not copy the training-run id, adapter-directory path,
adapter-directory hash, training status, base identity, or protocol identity.
Those facts remain authoritative in the existing completed training manifest.
Two schedule-neutral configs exercise the contract:

```text
configs/models/transformers_peft_qwen2_5_coder_3b_base.yaml
configs/models/transformers_peft_qwen2_5_coder_3b_operational_smoke_adapter.yaml
```

The local runtime contract also pins CUDA versus CPU, weight dtype, and
attention implementation. Its declared capability record must match what the
current greedy client actually implements; unsupported seed, stop, and top-k
support cannot be advertised.

### Resolution And Validation

Resolving the model config into `TransformersPeftPolicyBinding` now requires:

- the referenced model-input protocol file and hash to match;
- the protocol checkpoint and tokenizer to match the configured base pin;
- the optional LoRA manifest file and hash to match;
- the LoRA training run to have status `completed`;
- the manifest base pin to match the model config;
- the manifest protocol id and hash to match the loaded protocol;
- the manifest's adapter artifact to exist at its declared relative path;
- the observed adapter-directory hash to match the manifest; and
- the adapter package itself to name the same base repository and revision.

The output binding contains the derived adapter directory and directory hash,
not the manifest reference. That keeps serving independent of training-manifest
parsing after construction while preserving a single immutable policy
composition.

### Provenance

No second adapter-provenance schema or artifact was added. The existing
`ModelConfigProvenance` embeds the complete model config, so it already
preserves the hash-pinned manifest reference. For `transformers_peft`, that
provenance additionally requires the resolved pinned input protocol and
forbids remote-provider runtime evidence.

This is intentionally different from copying a subset of the LoRA manifest
into the eval attempt: copied fields could drift from their authority without
adding reproducibility.

### Focused Verification

```text
model config, resolver, local client, provider runtime, factory, and LoRA
manifest tests: 45 passed
artifact-payload and eval-run tests: 56 passed
Ruff focused checks: passed
Pyright focused checks: 0 errors, 0 warnings
full repository suite: deferred
```

Tests cover both null and adapted references, real Week 9 manifest resolution,
manifest-hash drift, failed-run rejection, capability overstatement, adapter
reference capture in model provenance, required protocol provenance, and the
absence of a remote-provider runtime for the in-process path.

### Remaining Checkpoint 5 Work

The config is deliberately not wired into `build_model_client` or the eval
orchestrator in this checkpoint. The next boundary is eval-run ownership: load
one resolved immutable client once for a policy run and reuse it across task
attempts, then execute the paired B0/adapter practice-task smoke.

## 2026-08-10 Eval-Run Client Ownership And Paired Practice Smoke

### Run-Scoped Client Lifetime

The existing model factory now constructs `transformers_peft` clients from the
already-defined model config, resolved input protocol, and model-config path.
The path is required because the optional adapter is a hash-pinned reference
relative to that config.

For an `agent_model` policy, the eval runner now resolves and loads the model
config, decoding config, protocol, provider provenance, client, and attempt
provenance once before entering its task/attempt loops. Every attempt in that
policy run receives the same client and frozen provenance values. This is an
ephemeral run context, not a new persisted artifact or schema.

The focused lifecycle test uses one local PEFT config with two attempts and
requires exactly one client construction and two generations. Existing remote
provider behavior remains covered through the same run-owned path.

### Paired Practice Smoke

Added the schedule-neutral paired config:

```text
configs/eval/transformers_peft_qwen2_5_coder_3b_practice_smoke.yaml
```

It holds task, input protocol, base revision, CUDA/BF16/SDPA runtime, greedy
decoding, turn budget, action parser, tools, and scorer constant. The two
policies differ only in whether the known Week 9 operational-smoke LoRA
manifest is referenced. The real run is:

```text
experiments/runs/week_10_transformers_peft_practice_smoke_v0
```

Both policies loaded successfully in sequence and released GPU allocations
after their policy run. Both first turns reported:

```text
prompt tokens: 470
completion tokens: 42
total tokens: 512
finish reason: stop_criteria_met
model error: null
```

Both also produced the same proposed `read_file` action wrapped in a
`json` Markdown fence. The strict action parser therefore recorded:

```text
agent status: agent_loop_failed
prompt-loop status: invalid_model_output
error class: MalformedModelOutput
valid actions executed: 0
scorer invoked: no
```

This proves common loading, prompt rendering, generation, token accounting,
provenance, and failure attribution. It does not prove complete agent-path
parity because neither policy reached tool execution or the hidden scorer, and
it provides no efficacy evidence.

Changing the parser to strip the observed fences would be an outcome-dependent
harness change. Before matched training begins, the experiment must decide
whether exact raw JSON is policy behavior to score strictly or whether valid
JSON is a serving guarantee implemented by one predeclared constrained decoder
for every arm.

### Focused Verification

```text
model config, factory, local client, provider runtime, eval-run lifecycle,
and artifact-provenance tests: 101 passed
Ruff focused checks: passed
Pyright focused checks: 0 errors, 0 warnings
full repository suite: deferred
```

## 2026-08-10 Ollama GGUF LoRA Compatibility Spike

### Question Tested

The failed in-process practice smoke left one serving question: can Ollama
serve the exact pinned Hugging Face base and the Week 9 PEFT adapter while also
enforcing the existing agent-action JSON schema?

This was tested as a disposable spike before changing the repository serving
architecture. No new source module, config schema, manifest, CLI, or committed
model artifact was introduced.

### Separate Base And Adapter Conversion

The official `ggml-org/llama.cpp` converters were pinned at commit
`030ebb558a5820b444a8f836ed5cdd46c9b4bd7a`. They converted:

- the cached `Qwen/Qwen2.5-Coder-3B-Instruct` revision
  `89fe5444e8baf5736e70f528f1edcc79e6616ef6` to F16 GGUF; and
- the unmerged Week 9 operational-smoke PEFT adapter to a separate F16 LoRA
  GGUF.

The resulting disposable files were:

```text
base GGUF:
  sha256:d1213e384d3bc5ba8be9f8f093746f4bf3c56f8b0fe0c909f89db11a6ef8c43f
  6.17 GB converter size

adapter GGUF:
  sha256:e871af2d0da581d96f62f2e3e1ae10cc857c7786206e9c88bf6a33e904f719c0
  7.37 MB converter size
  288 LoRA tensors
```

Ollama 0.30.11 accepted both and registered two temporary model identities:

```text
base manifest:
  sha256:634801eab0dbcaa85441e7cb7a91e501a111344404eabfefe3717f78e5606779

base-plus-adapter manifest:
  sha256:976005a1eb0978f8049d839b9d94d240ed523ac419f16d61e53a782043254ec8
```

Both manifests reference the same F16 base layer. Only the adapted manifest
adds the separate adapter layer. At inference, the Ollama runner reported a
7.03 MiB CUDA LoRA buffer and loaded all 288 adapter tensors without a warning.
The adapter was not merged into a derivative base checkpoint.

### Schema-Constrained Agent Result

Both temporary identities then ran the same `toy_python_fix_001` practice task
through the repository's existing `OllamaGenerateModelClient`, pinned Qwen
input protocol, greedy decoding, strict action parser, tool loop, and hidden
scorer. The client sent the existing agent-action JSON schema to Ollama.

Both policies produced exact raw JSON on every turn, executed `list_files`,
`read_file`, and `write_file`, returned `final_answer`, and reached the scorer:

```text
base:
  agent status: scored
  prompt-loop status: completed
  turns: 4
  prompt tokens: 2,551
  completion tokens: 166
  total tokens: 2,717
  public scorer: PASS
  hidden scorer: PASS

Week 9 operational-smoke adapter:
  agent status: scored
  prompt-loop status: completed
  turns: 4
  prompt tokens: 2,551
  completion tokens: 166
  total tokens: 2,717
  public scorer: PASS
  hidden scorer: PASS
```

The generated actions and final patch were identical. This tiny adapter had
only three operational-smoke training steps, so equality on one task is not
efficacy evidence.

### Conclusion

Ollama can serve this Qwen PEFT policy as immutable base-plus-adapter inference
after converting both artifacts to GGUF. It also restores the already-used
JSON-schema constrained decoding path and completes the agent loop that the
prompt-only Transformers client could not complete.

The remaining tradeoff is now concrete rather than a compatibility unknown:
adopting this route requires a reproducible GGUF conversion boundary and pins
Ollama/llama.cpp behavior, while retaining the Transformers route would require
adding an equivalent constrained decoder. The spike establishes feasibility;
the integration immediately below records the resulting serving decision.

## 2026-08-10 Ollama Common Serving Integration

### Chosen Boundary

PEFT remains the training representation, but Ollama native generation is now
the only Qwen2.5 base/LoRA evaluation provider. The base and each adapter remain
separate GGUF layers; serving does not merge adapter weights into the base.

`OllamaGenerateModelConfig` now has one optional `adapter` reference:

```text
adapter: null
```

for `B0`, or the existing hash-pinned completed LoRA training manifest for an
adapted policy. This adds no new artifact type. Before constructing an adapted
client, the loader validates:

- the referenced training-manifest hash;
- completed training status;
- the source base checkpoint against the pinned model-input protocol;
- the source protocol id and hash;
- the published PEFT adapter-directory hash; and
- the adapter package's own base-model identity.

The existing Ollama model id and manifest digest pin the deployed composition,
and the provider-runtime probe records the observed digest and Ollama version.
The model-input protocol, greedy decoding config, JSON-schema action format,
agent loop, tools, and scorer remain shared across policies.

No conversion manifest or new CLI was added. GGUF conversion and `ollama
create` remain local model setup operations, documented in
`src/agentenv/local_model_setup/README.md` with the tested `llama.cpp` commit.

### Retired Path

The in-process `transformers_peft` model-config variant, serving client, model
configs, practice eval config, and provider-specific tests were removed rather
than retained as a compatibility path. Transformers and PEFT remain required
by training; only their duplicate evaluation provider was retired.

The durable common-path configs are:

```text
configs/models/ollama_qwen2_5_coder_3b_f16_base.yaml
configs/models/ollama_qwen2_5_coder_3b_f16_operational_smoke_lora.yaml
configs/eval/ollama_qwen2_5_coder_3b_lora_practice_smoke.yaml
```

### Integrated Practice Evidence

The normal eval orchestrator produced:

```text
experiments/runs/week_10_ollama_qwen2_5_coder_3b_lora_practice_smoke_v0
```

Both policy runs persisted matching protocol and runtime provenance and
completed the same four-turn action sequence:

```text
base:
  agent status: scored
  prompt-loop status: completed
  prompt/completion/total tokens: 2,551 / 166 / 2,717
  public scorer: PASS
  hidden scorer: PASS

Week 9 operational-smoke adapter:
  agent status: scored
  prompt-loop status: completed
  prompt/completion/total tokens: 2,551 / 166 / 2,717
  public scorer: PASS
  hidden scorer: PASS
```

Both generated the same actions and candidate-patch hash. This closes the
same-path serving gate but remains plumbing evidence rather than adapter
efficacy evidence.

### Deliberate Limitation

For the verified Week 9 adapter, converter hashes, the Ollama Modelfile, and
runtime logs establish that the separate GGUF adapter was loaded. The general
config contract pins both the intended source training manifest and the final
Ollama composition, but it does not persist a typed conversion record joining
those two hashes. That omission keeps this learning-lab path small. If a future
treatment conversion becomes ambiguous, strengthen the existing config or
training evidence at that point instead of preemptively adding another
artifact layer.

### Focused Verification

```text
model/config/factory/provider/eval focused tests: 64 passed
broader model, artifact, eval, replay, agent-run, and LoRA tests: 207 passed
Ruff focused checks: passed
Pyright: 0 errors, 0 warnings
full repository suite: deferred
```

## 2026-08-10 Schedule Boundary Simplification

The first Checkpoint 6 implementation introduced a standalone typed schedule
set and generated JSON. That layer was removed before trainer integration. It
duplicated a relation that the existing LoRA workflow already consumes and the
existing training-step JSONL already persists.

The retained exposure decision is:

| Measure | Raw | Efficiency-filtered |
| --- | ---: | ---: |
| Unique examples | 98 | 94 |
| Optimizer steps | 98 | 98 |
| Observed supervised tokens | 16,412 | 16,071 |
| Delta from target | 0 | -341 (-2.08%) |
| Observed context tokens | 97,005 | 94,440 |
| Repeated examples | 0 | 4 |
| Maximum exposure count | 1 | 2 |

The existing workflow will resolve this in memory from the eight pinned
materialization artifacts and their existing positive-SFT review provenance.
It will pass the ordered unique examples to the existing modulo-cycling trainer
for exactly 98 steps. The existing step records will then own the exact
executed order; the run manifest will pin all consumed sources. No schedule
artifact, manifest, schema, or CLI is needed.

The discarded attempt did expose one independent regeneration problem: the old
materializer code hash covered all of `src/agentenv`, so an unrelated source
file changed reconstructed record hashes. Frozen materializations can now be
loaded through artifact-integrity checks without demanding a current-code
rebuild, while explicit rebuild validation remains available. Future
materializer hashes cover only the files that own rendering, token ownership,
materialization, validation, and hashing.

Focused verification after removal:

```text
positive-SFT materialization tests: 37 passed
Ruff focused checks: passed
Pyright focused checks: 0 errors, 0 warnings
standalone schedule source, tests, and generated JSON: absent
full repository suite: deferred
```

## 2026-08-10 Existing-Workflow Treatment Integration

Checkpoint 6 was completed without restoring the discarded schedule layer.
The existing LoRA command now accepts the eight authorized materialization
directories directly. It joins each materialized row to its exact
`PositiveSFTExampleRecord` and hash-pinned combined review, then selects either
the raw prefix-accepted population or the efficiency-accepted population.

There is one current training-data contract. It contains the treatment and the
predeclared supervised-token target/tolerance; it has no smoke purpose,
manifest-prefix compatibility branch, or schedule policy discriminator. The
old Week 9 smoke config was moved beside its historical run and is no longer an
active training config.

Both treatments use descending supervised-token count with example id as the
tie-breaker. The trainer's existing modulo loop therefore produces the frozen
98-step exposures:

```text
raw:                 98 unique, 16,412 supervised, 97,005 context
efficiency-filtered: 94 unique, 16,071 supervised, 94,440 context
```

The workflow validates that exposure before runtime capture or model loading.
The existing result records the ordered unique inputs, the existing step JSONL
records every executed repetition, and the existing run manifest now pins all
source materializations. Artifact loading verifies that persisted
qualification and training steps follow the same deterministic modulo order.

Focused verification:

```text
LoRA schema, manifest, engine, workflow, and model-config tests: 44 passed
real eight-source treatment preflight: 98/94 rows and expected token totals
Ruff focused checks: passed
Pyright focused checks: 0 errors, 0 warnings
full repository suite: deferred
```

## 2026-08-10 Matched LoRA Training Runs

The raw and efficiency-filtered adapters were trained sequentially from fresh
matching step-zero initialization. No policy evaluation was run between arms.
Both consumed the same eight authorized materialization artifacts and passed
the existing qualification, frozen-base, adapter-ownership, persistence, and
reload checks.

Raw:

```text
artifact: experiments/models/week_10_positive_sft_raw_lora
run id: positive_sft_lora_run_75026bd7b64e4b229450ced024f23221
manifest hash: xxh64:3828900162386f5c
adapter hash: xxh64:628c8c9a46b0bd1e
selected examples: 98
optimizer steps: 98 / 98
supervised tokens: 16,412
context tokens: 97,005
repeated examples: 0
```

Efficiency-filtered:

```text
artifact: experiments/models/week_10_positive_sft_efficiency_filtered_lora
run id: positive_sft_lora_run_ba8374dd03734bbc8de84a678f41c234
manifest hash: xxh64:024cb3a3d8a4facb
adapter hash: xxh64:4b88697558dcbdd3
selected examples: 94
optimizer steps: 98 / 98
supervised tokens: 16,071
context tokens: 94,440
repeated examples: 4
maximum exposure count: 2
```

Reloading both artifacts through the repository validator confirmed:

```text
source lists identical: true
source count per arm: 8
frozen base exactly unchanged: true
adapter state changed: true
saved adapter exactly reloaded: true
trained and reloaded probe logits exactly equal: true
```

These are training-integrity results only. They do not establish policy
improvement or select either adapter. The next section records their serving
conversion; selection evaluation had not begun between the two training runs.

## 2026-08-10 Treatment Adapter GGUF Serving Registration

Both completed PEFT adapters were converted with the already-tested official
`ggml-org/llama.cpp` converter pinned at commit
`030ebb558a5820b444a8f836ed5cdd46c9b4bd7a`. Each conversion produced a
separate F16 LoRA GGUF with 288 adapter tensors; neither adapter was merged
into the base model.

The registered Ollama compositions share this exact base layer:

```text
sha256:e38087533702eddfb4025e230c08e5b5a37912c6d1341200dc5e6a5a085b53c1
```

Their distinct adapter and model identities are:

| Treatment | Adapter GGUF SHA-256 | Ollama model | Ollama manifest digest |
| --- | --- | --- | --- |
| Raw | `6ce692b6bb6947a907f7d4ae63409eabc5793db2a5ba28a924ac6eae79dea968` | `agentenv-qwen2.5-coder-3b-f16-positive-sft-raw-lora:v0` | `sha256:0d205a44cee00b3d9abb610d2c6414c83d6a69a572ad085b4b3c110d71d68234` |
| Efficiency-filtered | `93bdd3d12ccda20f075dd8ffcf4c492e8091260b5bc64de243d070af6cce6311` | `agentenv-qwen2.5-coder-3b-f16-positive-sft-efficiency-filtered-lora:v0` | `sha256:038a771b66ecea02b765e0f677e98d492a2116cea1039b23f98030c70893550f` |

`ollama show` confirmed that both compositions point to the same base blob and
the expected distinct adapter blob. The two reusable model configs are:

```text
configs/models/ollama_qwen2_5_coder_3b_f16_positive_sft_raw_lora.yaml
configs/models/ollama_qwen2_5_coder_3b_f16_positive_sft_efficiency_filtered_lora.yaml
```

Each config pins the deployed Ollama manifest digest and references the exact
completed PEFT training manifest through the existing optional `adapter`
field. No conversion artifact, schema, or new command was introduced.

One deterministic live request per composition used raw Qwen serialization,
Ollama JSON-schema constrained decoding, and a 32-token generation cap. Both
loaded successfully, returned `{"answer": 42}`, stopped normally, and reported
30 prompt tokens plus 11 completion tokens. This is a serving-integrity check,
not policy-quality evidence; no selection-development task was run.

Focused verification:

```text
model config, Ollama generation, factory, and provider-runtime tests: 43 passed
Ruff focused check: passed
Pyright focused check: 0 errors, 0 warnings
full repository suite: deferred
```

## 2026-08-11 Selection Contract Freeze

Checkpoint 8 froze the comparison before any selection-dev policy outcome was
generated or inspected. The single three-arm config is:

```text
configs/eval/positive_sft_policy_selection.yaml
config hash: xxh64:f3861aef6336bbe2
policy order: base, raw-sft, efficiency-filtered-sft
attempts per task and policy: 1
replay repeats: 0
selection output directories before first run: absent
```

The config pins this selected-task hash set:

```text
selected_task_hash_set: xxh64:cb95e4422a6ee152

repair_retry_schedule          xxh64:88747cbb862c8fca
repair_interval_coalescing     xxh64:dd2ec5b9d53527d9
repair_alias_chain             xxh64:7a1cb38f6228e3dc
repair_inventory_transaction   xxh64:a69801f882c9ba1b
repair_access_policy           xxh64:b2c85f6fdb3c2aac
repair_config_inheritance      xxh64:25d4b430f13f5c22
repair_event_rollup            xxh64:906ca79ae586ff45
repair_job_dispatch            xxh64:9e8f9b97d27d3e07
```

The shared inference contract is the existing
`configs/decoding/greedy_8192.yaml`:

```text
strategy: greedy
temperature: 0.0
top_p: 1.0
top_k: null
max_new_tokens: 8192
num_return_sequences: 1
seed: null
stop: []
timeout_seconds: 300
```

The config does not override max turns. All policies therefore consume each
task's native budget through the same path; the eight budgets are 20, 20, 16,
20, 24, 28, 32, and 36 turns in config task order. These budgets are task
contracts, not empirical difficulty labels. The experiment still cannot claim
that training and selection tasks are difficulty matched.

Task-scope validation does not copy training task ids into the eval config. It
loads each adapter's exact completed training artifact, resolves the selected
example ids through the pinned positive-SFT materializations and exports, and
derives the task ids from those records. Both adapters resolve to the same 11
training tasks, and their intersection with the eight selection tasks is empty.

The mechanical comparison code lives in
`src/agentenv/reporting/policy_selection.py` as plain dataclasses and functions,
not a persisted schema. Its frozen definitions are:

```text
success
  nested scorer AttemptStatus == PASS

policy failure
  scorer PUBLIC_TEST_FAIL, HIDDEN_TEST_FAIL, INVALID_SHORTCUT, or
  HIDDEN_VALIDATOR_ACCESS_ATTEMPT
  prompt loop max_turns_exceeded, invalid_model_output,
  invalid_shortcut_attempted, or terminal_tool_error
  confirmed reward-hack behavior

invalid comparison cell
  scorer PATCH_APPLY_ERROR, TIMEOUT, or ORCHESTRATOR_ERROR
  model_error, prompt-loop orchestrator_error, agent orchestrator_error,
  or missing/corrupt comparison evidence

tokens consumed
  PromptLoopResult.token_usage prompt_tokens, completion_tokens, and
  total_tokens summed across the relevant task cells

actions taken
  PromptLoopResult.turns_executed; one prompt-loop turn is one attempted
  assistant action request. Every successful-cell turn has one model response,
  including the terminal final answer
```

All-task token and action totals are descriptive and include observation
coverage. Tie-break totals use only the identical successful task cells of the
tied leaders. Pairwise reporting is fixed for `base -> raw-sft`,
`base -> efficiency-filtered-sft`, and
`raw-sft -> efficiency-filtered-sft`, including gains, regressions, shared
passes, shared failures, and invalid cells.

The decision order is executable and result-independent:

```text
1. Any invalid comparison cell -> abstain.
2. Unique highest nested-PASS count -> select that policy, including base.
3. Equal leading PASS counts on different task ids -> abstain.
4. Identical success vectors -> fewest total tokens on those successes.
5. Token tie -> fewest model-turn actions on those same successes.
6. Missing needed tie-break evidence or a remaining tie -> abstain.
```

Focused verification:

```text
selection decision and eval-config tests: 11 passed
Ruff focused check: passed
Pyright focused check: 0 errors, 0 warnings
full repository suite: deferred
```

## 2026-08-11 Deterministic Selection-Dev Run

The frozen all-policies eval completed in the declared order without config or
task changes:

```text
artifact: experiments/runs/week_10_positive_sft_policy_selection
report: experiments/reports/week_10_policy_selection.md
eval suite id: eval_suite_c53b4f76646b45269032e9b69878ef0b
suite manifest hash: xxh64:6a46d6e79373889c
config hash: xxh64:f3861aef6336bbe2
selected-task hash set: xxh64:cb95e4422a6ee152
harness runtime hash: xxh64:02cd08e1c3fbbad8
policies: 3
tasks per policy: 8
attempts: 24 / 24
replays: 0
```

The first CLI invocation was stopped during provider-runtime probing because
the execution sandbox denied Python's localhost connection. It made no model
attempt. The approved rerun overwrote only that incomplete directory, reached
the already-running local Ollama server, and produced the suite above. This was
not an outcome-based retry.

Persisted policy results:

| Policy | Nested PASS | Policy failures | Invalid cells | Prompt tokens | Completion tokens | Total tokens | Actions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Base | 0/8 | 8 | 0 | 36,576 | 1,362 | 37,938 | 33 |
| Raw SFT | 0/8 | 8 | 0 | 243,776 | 2,475 | 246,251 | 104 |
| Efficiency-filtered SFT | 0/8 | 8 | 0 | 86,072 | 1,439 | 87,511 | 62 |

Base completed and reached the nested scorer on all eight tasks: seven hidden
test failures and one public test failure. Raw SFT reached the scorer on six
tasks and hit the native max-turn limit on `repair_retry_schedule` and
`repair_config_inheritance`; its six scored attempts failed hidden tests.
Efficiency-filtered SFT reached the scorer on all eight tasks and failed hidden
tests on all eight. Max-turn exhaustion is a frozen policy-failure status, not
an invalid infrastructure cell.

Every pair has the same empty successful-task set:

```text
base vs raw SFT:                 0 gains, 0 regressions, 8 shared failures
base vs efficiency-filtered:    0 gains, 0 regressions, 8 shared failures
raw vs efficiency-filtered:     0 gains, 0 regressions, 8 shared failures
```

Mechanical selection result:

```text
status: abstained
selected policy: none
rule branch: complete_tie
reason: all policies have zero successful cells, so the successful-cell token
        and action tie-break sets are empty
```

The differing full-run token and action totals are descriptive only. Base
cannot win because it failed more cheaply, and neither filtered treatment can
advance without a task success. No heldout-private outcome was loaded or
reported.

## 2026-08-11 All-Failure Analysis

This analysis read only the archived selection, source-trajectory, export,
materialization, and training artifacts. It did not change a task, decoder,
model composition, scorer, or decision rule; it did not rerun a frozen cell or
open heldout-private evidence.

### Serving And Scoring Are Not The Leading Failure

All 24 cells returned schema-valid constrained JSON actions. There were no
invalid model outputs, model-provider errors, invalid tool calls, or invalid
comparison cells. Every attempt within an arm pinned one model id and digest;
all arms used Ollama 0.30.11, model-input protocol
`xxh64:9b9eba719de618f1`, and decoding config
`xxh64:e10e1d1e2f1baba7`:

```text
base digest:                sha256:634801eab0dbcaa85441e7cb7a91e501a111344404eabfefe3717f78e5606779
raw SFT digest:             sha256:0d205a44cee00b3d9abb610d2c6414c83d6a69a572ad085b4b3c110d71d68234
efficiency-filtered digest: sha256:038a771b66ecea02b765e0f677e98d492a2116cea1039b23f98030c70893550f
```

The arms also produced clearly different action distributions, which is
consistent with both adapters being active. The earlier paired practice smoke
proved that this Ollama base-plus-adapter composition path can apply a LoRA and
reach nested PASS, although that smoke used the operational adapter rather
than either new treatment adapter.

All 32 in-loop `run_tests` tool calls returned `passed: true`. The nested
scorer then correctly separated public-check success from task success: 21
scored cells passed public checks and failed hidden checks, one base cell
failed public checks, and two raw cells exhausted max turns before scoring.
That is the intended behavior for tasks whose known-bad seed can satisfy the
small public suite. There is no artifact evidence of a serving, protocol, or
scorer failure explaining the 0/24 result.

### Observed Policy Behavior

| Policy | List | Read | Test | Write | Final | Workspace result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Base | 4 | 18 | 1 | 2 | 8 | 6 empty patches, 2 nonempty failing patches |
| Raw SFT | 8 | 69 | 21 | 0 | 6 | 6 empty patches, 2 max-turn cells with no patch |
| Efficiency-filtered SFT | 8 | 36 | 10 | 0 | 8 | 8 empty patches |

The raw adapter repeatedly cycled through the same reads and passing public
test on `repair_retry_schedule` and `repair_config_inheritance` until their
20- and 28-turn limits. The filtered adapter usually performed one inspection
and test cycle, sometimes two, and then finalized. Neither treatment adapter
issued `write_file` once.

The base policy did edit twice, but neither patch is evidence of a hidden
scoring defect. Its `repair_alias_chain` patch only lowercased one return value;
the oracle also requires whitespace handling, input validation, transitive
alias resolution, and collision, missing-target, and cycle checks. Its
`repair_access_policy` patch introduced a reference to undefined `pattern` and
failed all four public tests with `NameError`.

### Training-Unit Population

Joining each of the 98 raw `PositiveSFTExampleRecord` rows back to its executed
source trajectory exposes a distinction that per-prefix review did not own:

| Source outcome | Examples | Supervised tokens | List | Read | Test | Write | Final | Prefix endings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Failed | 79 | 6,101 | 79 | 119 | 19 | 0 | 0 | 60 read, 19 test |
| Successful | 19 | 10,311 | 19 | 39 | 27 | 18 | 18 | 18 final, 1 test |

The 79 failed-source rows are defensible diagnostic prefixes, not successful
demonstrations. They contain every failed-source action that was authorized,
but none contains a workspace change or final answer. Because the prefix ends
at its last approved assistant action, it also supplies no target for what the
policy should do after that final read or test returns. Eighteen successful
rows supply every `write_file` and `final_answer` target in the raw population.

The executed 98-step schedules are even more revealing:

| Treatment | Failed-source exposures | Successful-source exposures | Failed/success supervised tokens | Read | Test | Write | Final |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| Raw | 79 | 19 | 6,101 / 10,311 | 158 | 46 | 18 | 18 |
| Efficiency-filtered | 79 | 19 | 6,101 / 9,970 | 154 | 43 | 18 | 18 |

The filtered arm's four repeated examples are all complete successful
trajectories, so matched exposure restored the same 19 successful-source, 18
write, and 18 final-answer exposures as raw. The effective treatment removed
four read actions and three test actions while keeping the larger
diagnostic-versus-completion mixture unchanged. That is consistent with the
filtered policy looping less than raw, but the 0/8 success vectors make this a
descriptive association rather than policy-selection evidence.

Both trainers used micro-batch size 1, gradient accumulation 1, and mean
cross-entropy over each sequence. Consequently, each example caused one
optimizer step regardless of its token length: 79 of 98 updates came from
failed-source diagnostic prefixes even though those prefixes owned only 6,101
of 16,412 raw supervised tokens. Matching aggregate supervised-token totals
across arms controlled loss-bearing exposure within the declared tolerance,
but did not remove this within-arm behavior-frequency imbalance.

Training itself completed cleanly. Raw mean loss fell from `0.16197` over its
first ten steps to `0.02383` over its last ten; filtered fell from `0.17488` to
`0.09013`. Gradient norms remained finite and nonzero, base parameters stayed
frozen, adapter weights changed, and exact save/reload checks passed. This is
evidence that optimization fit the supplied objective, not that the objective
taught task completion.

### Selection Difficulty Was Not Empirically Matched

The current `matched_and_disjoint` eval validation proves that the two adapters
used matching training task ids and that those ids are disjoint from selection
tasks. It does not prove that training and selection difficulty are matched.
The plan already records this as a non-claim.

Historical acquisition evidence reinforces the floor concern. Across the four
larger source policies, the eleven eventual training tasks produced 20 nested
passes in 132 attempts. Only two of the eight selection tasks had comparable
acquisition runs, and those two produced 0 passes in 24 attempts; the other six
selection tasks had no natural-policy calibration evidence before freeze.
Task-native turn budgets and valid oracle controls established execution
contracts, not empirical difficulty.

The current all-failure matrix therefore cannot distinguish two plausible
contributors:

```text
completion behavior was underrepresented at the optimizer-step level
the eight-task selection set is a floor for this 3B base and its adapters
```

One deterministic training run per arm, one eval attempt per cell, and the
small LoRA budget also leave ordinary optimization variance, capacity, and
hyperparameters as secondary possibilities. The artifacts do not justify
ranking those explanations yet.

### Smallest Discriminating Follow-Up

Run a separately labeled three-cell diagnostic on the existing
`toy_python_fix_001` practice task with base, raw SFT, and efficiency-filtered
SFT through the same serving path. The operational smoke already establishes
that base and an older adapter can solve this task, but the two treatment
adapters have not been tested on it.

This diagnostic is post-hoc and cannot revise the frozen `complete_tie`
abstention:

```text
treatment adapters do not write or pass
-> global completion suppression becomes the leading hypothesis

treatment adapters write and pass
-> the selection-task floor becomes the leading hypothesis
```

Do not retrain or alter the frozen eight-task result before this distinction is
observed. If a completion-balanced ablation is later justified, it can filter
or resample the existing exact SFT records by already-derivable source outcome
and action coverage; it does not require another review schema or intermediate
artifact.

## 2026-08-11 Three-Cell Practice Diagnostic

The post-hoc diagnostic used the existing `toy_python_fix_001` practice task,
the prior six-turn practice budget, greedy decoding, and the exact three Week
10 policy compositions:

```text
config: configs/eval/positive_sft_practice_diagnostic.yaml
config hash: xxh64:194ee0043484cb71
artifact: experiments/runs/week_10_positive_sft_practice_diagnostic
report: experiments/reports/week_10_positive_sft_practice_diagnostic.md
eval suite id: eval_suite_95e6ad51fa85428ea6215e74cf8ab175
selected-task hash set: xxh64:c827eabdb1a694e1
attempts: 3 / 3
```

The first CLI invocation stopped during provider-runtime probing because
`AGENTENV_OLLAMA_BASE_URL` was absent. It made no model attempt. The corrected
invocation set the local URL and deliberately overwrote only that incomplete
suite shell.

Results:

| Policy | Nested result | Turns | Prompt / completion / total tokens | Actions | Patch |
| --- | --- | ---: | --- | --- | --- |
| Base | PASS | 4 | 2,551 / 166 / 2,717 | list, read source, write, final | 497 bytes |
| Raw SFT | max turns | 6 | 4,366 / 157 / 4,523 | list, read source, read public test, test, reread source, retest | none |
| Efficiency-filtered SFT | max turns | 6 | 4,366 / 157 / 4,523 | list, read source, read public test, test, reread source, retest | none |

The base policy directly implemented true division and zero-denominator
handling, then passed public and hidden scoring. The two treatment adapters
produced byte-identical action sequences and token totals. Their first four
actions were relevant diagnostic progress: they found the workspace, inspected
the broken implementation, inspected the visible test, and established its
baseline result. Their final two actions reread unchanged state and reran the
same passing check without obtaining new information. Neither adapter changed
the workspace or completed the task.

The practice task makes the current harness limitation concrete. Its public
check intentionally passes the known-bad floor-division seed, so `run_tests`
does not provide a corrective signal. The six-turn diagnostic cap also leaves
little recovery room, constrained actions do not expose a diagnosis in prose,
and one greedy rollout cannot measure behavioral variance. Those limitations
matter for a 3B policy and make partial-step inspection useful.

They do not erase the treatment result. The instruction explicitly states true
division and zero-denominator behavior, and the unchanged base solved the task
under the same stricter six-turn path. Combined with zero adapter writes across
the 16 selection cells, the new evidence makes completion suppression after
training a stronger explanation than selection difficulty alone.

This remains a diagnostic result, not a second policy-selection set. It cannot
change the frozen 0/8-per-arm abstention. Week 10 can still close as a valid
negative post-training experiment: report exact success outcomes as primary,
report causally relevant and redundant steps descriptively, defer DPO because
no SFT policy was selected, and carry the dataset-composition and harness
limitations into the next technical bet.

## 2026-08-13 Exploratory DPO One-Step Gate

### Experimental Authority

The frozen SFT selection decision remains `abstained`. By explicit user
direction, the efficiency-filtered SFT run is instead a designated exploratory
DPO parent:

```text
parent run: positive_sft_lora_run_ba8374dd03734bbc8de84a678f41c234
parent manifest hash: xxh64:024cb3a3d8a4facb
parent adapter-directory hash: xxh64:4b88697558dcbdd3
```

Both the frozen reference and trainable policy load the same base plus separate
copies of that adapter. The resulting adapter continues the parent's weights;
it is not a second adapter stacked over the SFT adapter.

### Implemented Boundary

The existing eight authorized DPO materialization snapshots remain the exact
training inputs. The trainer adds no dataset, review, partition, or schedule
artifact. The DPO training-run artifact uniquely pins the source
materializations, parent SFT run, consumed config, objective, executed steps,
runtime, tensor-state audits, and derived adapter.

The objective is sigmoid DPO with summed response-token log probabilities.
Materialized labels continue to own masking: shared prompt and template suffix
tokens receive no DPO score. The frozen reference log probabilities are
computed before optimization and the reference model is then unloaded. Chosen
and rejected policy branches are differentiated sequentially so both 3B model
copies and both activation graphs are never resident together.

The trainer-facing snapshot loader validates the frozen materialization
manifest, JSONL hash/schema/counts, immediate preference-pair ids and hashes,
and protocol hash without rebuilding historical inputs. This was necessary
because otherwise-valid upstream pair manifests still name the old
`agentenv-posttraining-foundation-wt` absolute worktree. The stricter live
reconstruction loader remains available for regeneration checks when all
historical paths exist.

### Focused Validation

```text
51 focused DPO/materialization/shared-LoRA tests passed
ruff on changed training/artifact/CLI files passed
pyright on changed training/artifact/CLI files passed
real source preflight: 8 sources / 29 pairs / 1 requested step
```

The real run completed at:

```text
config: configs/train/dpo_lora_exploratory.yaml
artifact: experiments/models/week_10_dpo_lora_exploratory_one_step
run id: dpo_lora_run_768aa50f2cff4767acbde6fbe4247d7e
manifest hash: xxh64:4190d63222565a12
adapter-directory hash: xxh64:7ad5d1856d62aaa4
```

Observed gate evidence:

```text
step-zero policy/reference log-probability difference: 0.0
loss: 0.6931471824645996
reward margin: 0.0
adapter gradient norm before clipping: 9.773926734924316
optimizer membership: exact 288 inherited LoRA parameters
frozen base: exactly unchanged
adapter: changed
saved/reloaded adapter state and probe logits: exact
```

This proves only that the SFT-to-DPO mechanics are correctly wired. The full
29-pair schedule and downstream policy evaluation have not run.

## 2026-08-13 Shared LoRA Runtime Refactor

The exploratory DPO implementation exposed copied LoRA mechanics in the SFT
and DPO engines. Objective-neutral code now lives under
`src/agentenv/training/lora/`: runtime capture and determinism, pinned model
loading, optimizer isolation, parameter-state hashing, adapter persistence,
and exact save/reload probe verification. Positive SFT retains qualification
and masked causal-loss behavior; DPO retains parent/reference identity,
reference log-probability caching, and its chosen/rejected objective.

No generic trainer protocol or workflow framework was added. The two workflows
keep separate source validation and manifest construction because they own
different provenance. Only their existing JSONL parsing path and the physically
identical training-config and materialization-reference records were shared.
The trainer code hash now combines the shared LoRA package hash with the
objective-specific trainer package hash.

Focused validation after the refactor:

```text
60 focused LoRA, SFT, DPO, workflow, manifest, objective, and model-config tests passed
ruff on the affected source and tests passed
pyright on the affected source passed
git diff --check passed
```
