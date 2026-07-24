# Week 10 Implementation Notes

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
