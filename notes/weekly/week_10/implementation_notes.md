# Week 10 Implementation Notes

Current boundary as of 2026-07-23: action efficiency is an embedded judgment
on the existing `PositiveSFTReviewRecord`. There is no standalone efficiency
review artifact, schema, manifest, or CLI. The earlier standalone implementation
below is retained only as design history and is explicitly superseded. The
100-row review universe is complete at 98 prefix accepted, 2 prefix rejected,
94 efficiency accepted, 4 efficiency rejected, and no unresolved or abstained
decisions. Because training and policy evaluation have not started, the Week
10 experiment will use all 98 accepted prefixes and all 94
efficiency-accepted prefixes. The earlier 18-row exports and materializations
are stale working artifacts and will be regenerated.

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
| `positive_sft_example_a5ef0f3a430cc454` | `preserve_cli_error_codes` | `message_f01ad86192404fa1b0a14db56e31f54e` | Second unchanged `src/validate_records.py` read before any write |
| `positive_sft_example_aab1e627500f226b` | `preserve_cli_error_codes` | `message_ada15f297b3148249f33dd2b3c81f55e` | Second unchanged `src/validate_records.py` read before any write |
| `positive_sft_example_b535bb9c0f7ca71b` | `preserve_cli_error_codes` | `message_41d73bea570c42efbd8dba27b01a69b2` | Unused `pyproject.toml` inspection before a standard-library-only repair |
| `positive_sft_example_bf8626bdcb21216d` | `repair_jsonl_deduper` | `message_9e942f8f981644f2ae676732282a2003` | Unused `pyproject.toml` inspection before a standard-library-only repair |

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

### Next Small Step

Regenerate the exports and token materializations for all 98 accepted prefixes,
resolve the 94-example filtered subset, validate the resulting 11-task versus
8-task split, and freeze matched supervised-token exposure before launching
either LoRA run.
