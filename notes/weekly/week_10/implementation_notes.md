# Week 10 Implementation Notes

Current boundary as of 2026-07-23: action efficiency is an embedded judgment
on the existing `PositiveSFTReviewRecord`. There is no standalone efficiency
review artifact, schema, manifest, or CLI. The earlier standalone implementation
below is retained only as design history and is explicitly superseded.

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

The eight existing positive-SFT review artifacts contain 100 prefix-review
rows:

```text
prefix accepted / efficiency pending: 18
prefix rejected or needs_followup / efficiency not applicable: 82
```

All rows now contain explicit `efficiency_judgment: null`. The existing queue
files were refreshed so the 18 eligible rows show:

- the combined review row;
- the frozen efficiency rubric id;
- the exact retained prefix messages;
- exact assistant message ids and action count.

The old recursive review provenance contains absolute paths to a retired
worktree. The one-time queue refresh therefore used the adjacent hash-pinned
positive-SFT exports, whose messages are exactly the previously approved
prefixes. No compatibility path resolver was added.

The existing positive-SFT exports and token materializations are intentionally
not regenerated while judgments remain editable. They will be regenerated
once, after all 18 judgments are complete, so review edits do not cause
repeated artifact churn. No trajectory, harness-audit, or agent execution must
be rerun.

### Current Invariants

- Efficiency applies only when the prefix decision is `accepted`.
- Every completed judgment pins
  `positive_sft_action_efficiency_v0`.
- A rejected judgment requires at least one unique assistant message id.
- Evidence must identify an assistant message inside the retained prefix.
- Accepted and `needs_followup` judgments cannot claim avoidable actions.
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
combined artifact accounting: 8 artifacts, 100 rows, 18 pending
standalone efficiency artifact absent
full repository suite: deferred until the Week 10 integration boundary
```

### Next Small Step

Populate the 18 embedded judgments, starting with the four calibration
candidates. Then validate complete accounting and regenerate dependent exports
and token materializations exactly once.
