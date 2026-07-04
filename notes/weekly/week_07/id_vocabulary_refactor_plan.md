# ID Vocabulary Refactor Plan

## Why This Refactor Exists

The artifact manifest refactor clarified artifact *types* and artifact *schema
versions*, but the id vocabulary is still mixed:

- scorer artifacts expose both `run_id` and `attempt_id`,
- agent artifacts expose `run_id`, even though the artifact type is
  `agent_attempt`,
- eval traces store a generic `attempt_id` that means either a scorer
  `attempt_id` or an agent `run_id`,
- replay has a top-level `replay_id` and comparison-level `replay_id` with
  different meanings,
- trajectory identity has generic `run_id` and `attempt_id`, even though a
  trajectory needs to connect eval, agent, scorer, and replay artifacts.

This makes the current records hard to reason about. It also makes future
trajectory export and training eligibility more error-prone because a field name
does not tell us which layer owns the id.

## Core Rule

Use typed ids at cross-artifact boundaries.

Avoid generic `run_id`, `attempt_id`, `source_id`, and `replay_id` in records
that combine multiple layers. If a generic id remains inside an implementation
helper, it must not be serialized into artifacts, traces, reports, controls, or
trajectory records.

## Target Vocabulary

| Field | Owner | Meaning |
| --- | --- | --- |
| `eval_suite_id` | eval suite artifact | One multi-policy eval suite artifact |
| `eval_run_id` | eval run artifact | One policy evaluated over selected tasks |
| `eval_attempt_id` | eval run artifact | One eval harness slot: one policy, one task, one attempt index |
| `agent_attempt_id` | agent attempt artifact | One model/prompt-loop attempt against one task, optionally scored |
| `scorer_attempt_id` | scorer attempt artifact | One scoring attempt for one candidate patch against one task |
| `replay_run_id` | replay run artifact | One replay invocation over one source artifact |
| `trajectory_id` | trajectory record | One trajectory record assembled from eval artifacts |

Do not introduce `scorer_run_id`. A scorer artifact is already the durable
scorer attempt. The previous `run_id` in `AttemptResult` and previous
`attempt_id` in `AttemptResult` are two ids for one semantic unit. They should
collapse to `scorer_attempt_id`.

Do not keep `agent_run_id` in artifact contracts. The previous agent `run_id`
is the durable id for one agent attempt, so it should become
`agent_attempt_id`.

`attempt_index` remains an ordinal within a task/policy eval run. It is useful
for ordering and deterministic artifact paths, but it is not an id.

## Value Prefixes

Serialized id values should make their owner obvious:

```text
eval_suite_<uuid>
eval_run_<uuid>
eval_attempt_<uuid>
agent_attempt_<uuid>
scorer_attempt_<uuid>
replay_run_<uuid>
trajectory_<uuid-or-derived>
```

Current values such as `eval_<uuid>`, `run_<uuid>`, `attempt_<uuid>`,
`agent_task_run_<uuid>`, and `replay_<uuid>` should not survive in new artifact
outputs.

## Meaning Of `eval_attempt_id`

`eval_attempt_id` is the eval harness row id. It identifies the slot:

```text
eval_run_id + policy + task_id + attempt_index
```

It is not a scorer id and not an agent id.

It is a serialized surrogate for that natural key, not a replacement for it.
The eval run manifest should keep the natural-key fields present, and should
validate that `eval_attempt_id` is unique within an eval run.

Example:

```json
{
  "eval_run_id": "eval_run_abc",
  "eval_attempt_id": "eval_attempt_def",
  "task_id": "toy_python_fix_001",
  "policy": "agent-happy",
  "attempt_index": 0,
  "artifact_type": "agent_attempt",
  "agent_attempt_id": "agent_attempt_xyz",
  "scorer_attempt_id": "scorer_attempt_123"
}
```

For scorer-control policies:

```json
{
  "eval_run_id": "eval_run_abc",
  "eval_attempt_id": "eval_attempt_def",
  "artifact_type": "scorer_attempt",
  "scorer_attempt_id": "scorer_attempt_123",
  "agent_attempt_id": null
}
```

For agent policies that fail before scoring:

```json
{
  "eval_run_id": "eval_run_abc",
  "eval_attempt_id": "eval_attempt_def",
  "artifact_type": "agent_attempt",
  "agent_attempt_id": "agent_attempt_xyz",
  "scorer_attempt_id": null
}
```

## Current Inventory

### Scorer Attempt

Files:

- `src/agentenv/orchestrators/attempt.py`
- `src/agentenv/orchestrators/attempt_io.py`
- `src/agentenv/orchestrators/attempt_runner.py`

Current fields:

- `AttemptResult.run_id`
- `AttemptResult.attempt_id`
- `AttemptContext.run_id`
- `AttemptContext.attempt_id`
- scorer root `manifest.json` writes both `run_id` and `attempt_id`
- `attempt.json` writes both `run_id` and `attempt_id`
- attempt trace provenance writes both `run_id` and `attempt_id`

Target:

- `AttemptResult.scorer_attempt_id`
- `AttemptContext.scorer_attempt_id`
- scorer root manifest writes `scorer_attempt_id`
- `attempt.json` writes `scorer_attempt_id`
- attempt trace provenance writes `scorer_attempt_id` and `task_id`

### Agent Attempt

Files:

- `src/agentenv/orchestrators/agent_task_run.py`
- `src/agentenv/agents/audit.py`
- `src/agentenv/controls/controls_run.py`

Current fields:

- `AgentTaskRunResult.run_id`
- `AgentTaskRunManifest.run_id`
- audit/control outputs use `agent_run_id`
- temp workspace helper names use `run_id`

Target:

- `AgentTaskRunResult.agent_attempt_id`
- `AgentTaskRunManifest.agent_attempt_id`
- audit/control outputs use `agent_attempt_id`
- helper variable names may use `agent_attempt_id`; temp path prefixes should
  use the same value

### Eval Run And Eval Attempts

Files:

- `src/agentenv/orchestrators/eval_run.py`
- `src/agentenv/reporting/markdown.py`
- `src/agentenv/evals/task_hash_compare.py`

Current fields:

- `EvalRun.eval_run_id` with value prefix `eval_`
- `EvalAttemptRecord` has no id; it has `attempt_index`
- eval trace provenance has generic `attempt_id`
- scorer summaries contain `run_id` and `attempt_id`
- agent summaries contain `run_id`
- eval run manifest embeds these generic summary ids

Target:

- `EvalRun.eval_run_id` with value prefix `eval_run_`
- `EvalAttemptRecord.eval_attempt_id`
- `ScorerAttemptSummary.scorer_attempt_id`
- `AgentAttemptSummary.agent_attempt_id`
- nested agent scorer summary uses `scorer_attempt_id`
- eval trace provenance uses `eval_attempt_id` and optional typed child ids:
  - `scorer_attempt_id`
  - `agent_attempt_id`

### Eval Suite

Files:

- `src/agentenv/orchestrators/eval_run.py`
- `src/agentenv/reporting/markdown.py`

Current fields:

- `eval_suite_id` is already clear
- replay records do not include the nested replay run id

Target:

- keep `eval_suite_id`
- add `replay_run_id` to `replay_runs[*]` if replay records are present
- keep `eval_run_id` in `policy_runs[*]`

### Replay

Files:

- `src/agentenv/replay/runner.py`
- `src/agentenv/reporting/markdown.py`
- `src/agentenv/tracing/schema.py`
- `docs/trace_schema.md`

Current fields:

- top-level `ReplayRun.replay_id`
- replay root manifest writes `replay_id`
- replay result writes `replay_id`
- `ReplayComparison.source_id`
- `ReplayComparison.replay_id`
- replay comparison JSON writes `source_id` and `replay_id`
- trace provenance uses `replay_id`, `source_artifact_id`,
  `replay_artifact_id`, `source_attempt_id`, and `replay_attempt_id`

Target:

- top-level replay invocation becomes `replay_run_id`
- replay root manifest writes `replay_run_id`
- replay result writes `replay_run_id`
- comparison records use typed ids:
  - for scorer comparisons:
    - `source_eval_attempt_id` when the source is an eval run
    - `source_scorer_attempt_id`
    - `replayed_scorer_attempt_id`
  - for agent comparisons:
    - `source_eval_attempt_id` when the source is an eval run
    - `source_agent_attempt_id`
    - `replayed_agent_attempt_id`
- replay trace provenance uses:
  - `replay_run_id`
  - `source_eval_run_id`
  - `source_eval_attempt_id`
  - `source_agent_attempt_id`
  - `replayed_agent_attempt_id`
  - `source_scorer_attempt_id`
  - `replayed_scorer_attempt_id`

Do not use `replay_id` for both the replay run and a replayed attempt.

### Trace Schema

File:

- `src/agentenv/tracing/schema.py`

Target models:

```text
AttemptTraceProvenance:
  scorer_attempt_id
  task_id
  phase?
  name?

EvalTraceProvenance:
  eval_run_id
  config_hash
  config_name
  policy?
  task_id?
  task_index?
  attempt_index?
  eval_attempt_id?
  scorer_attempt_id?
  agent_attempt_id?

ReplayTraceProvenance:
  replay_run_id
  source_eval_run_id?
  source_eval_attempt_id?
  task_id?
  source_scorer_attempt_id?
  replayed_scorer_attempt_id?
  source_agent_attempt_id?
  replayed_agent_attempt_id?
```

Keep the trace schema version value unchanged for now; the current `trace_v0`
contract is still a mutable lab contract.

Event-level invariants:

- attempt events require `scorer_attempt_id` and `task_id`.
- `command_finished` additionally requires `phase` and `name`.
- `eval_attempt_started` requires `eval_attempt_id`, `policy`, `task_id`,
  `task_index`, and `attempt_index`.
- `eval_attempt_finished` requires the same eval-slot fields plus the relevant
  child typed id:
  - scorer-control attempts require `scorer_attempt_id`;
  - agent attempts require `agent_attempt_id`;
  - scored agent attempts should include the nested `scorer_attempt_id`.
- replay `source_manifest_loaded` requires `replay_run_id` plus either
  `source_eval_run_id`, `source_agent_attempt_id`, or
  `source_scorer_attempt_id`.
- replay events for eval-run sources should carry `source_eval_attempt_id` once
  an individual source attempt has been selected.
- replay source/fresh/comparison events require the appropriate source and
  replayed typed id pair for the comparison type.

### Trajectory Record

File:

- `src/agentenv/trajectories/schema.py`

Current identity:

```text
trajectory_id
run_id
task_id
policy_id
attempt_index
attempt_id
```

Target identity:

```text
trajectory_id
eval_suite_id | None
eval_run_id
eval_attempt_id
task_id
policy_id
attempt_index
agent_attempt_id | None
scorer_attempt_id | None
replay_run_id | None
```

Keep the trajectory schema version value unchanged for now; the current
`trajectory_record_v0` contract is still a mutable lab contract.

## Schema Version Policy For This Lab

This is unreleased learning-lab code. We do not need backward compatibility for
old local artifacts, and we do not need to bump schema version values just
because we are improving a contract before it has stabilized.

Default policy:

- Keep the current `*_v0` schema version values unless there is a separate
  design reason to mark a boundary.
- Do not add backward-compatibility readers for old local artifacts.
- Do not preserve old field names as aliases.
- Update tests and docs to define the current `v0` contract after the refactor.
- Treat stale generated artifacts as disposable.

If we later decide a contract is stable enough to publish or compare across
weeks, then version bumps become meaningful. This refactor is not that moment.

## Non-Goals

- Do not change scoring behavior.
- Do not change prompt-loop behavior.
- Do not change replay comparison semantics.
- Do not rename broad implementation classes such as `AgentTaskRunResult` just
  because their serialized id field changes. Class renames can be a later
  mechanical cleanup.
- Do not introduce generic `artifact_id` as a replacement for generic `run_id`.
  It recreates the same ambiguity at a different layer.
- Do not change artifact directory names unless needed for test clarity. The id
  contract is in JSON fields; paths can remain deterministic and human-readable.
- Do not rename non-id status, count, or prose fields merely because they
  contain the word `run`. Examples that are out of scope unless separately
  redesigned:
  - `agent_run_status`
  - `expected_agent_run_status`
  - `actual_agent_run`
  - `agent_scorer_run_count`

## Checkpoints

### Checkpoint 0: Plan And Review

Tasks:

- Write this plan.
- Run two review agents on the plan.
- Incorporate review feedback before implementation.

Acceptance:

- The target vocabulary is explicit enough to implement without inventing names
  mid-refactor.

### Checkpoint 1: Central ID Helpers

Tasks:

- Add a small id helper module, probably `src/agentenv/ids.py`.
- Provide typed constructors:
  - `new_eval_suite_id()`
  - `new_eval_run_id()`
  - `new_eval_attempt_id()`
  - `new_agent_attempt_id()`
  - `new_scorer_attempt_id()`
  - `new_replay_run_id()`
  - optionally `new_trajectory_id()` when trajectory export exists
- Use the helpers only for new id creation. Do not make a broad id abstraction.

Acceptance:

- New ids have typed prefixes.
- No new code calls `uuid4()` directly for these artifact/run ids.

Targeted tests:

```bash
uv run pytest tests/test_ids.py
```

### Checkpoint 2: Scorer Attempt ID Vertical Slice

Tasks:

- Replace `AttemptResult.run_id` and `AttemptResult.attempt_id` with
  `AttemptResult.scorer_attempt_id`.
- Replace `AttemptContext.run_id` and `AttemptContext.attempt_id` with
  `AttemptContext.scorer_attempt_id`.
- Update scorer artifact `manifest.json`.
- Update `attempt.json`.
- Update attempt trace provenance.
- Update scorer audit and scorer control outputs.
- Update every direct scorer-attempt consumer in the same checkpoint:
  - eval `ScorerAttemptSummary`
  - eval run manifest scorer summaries
  - eval trace child-id fields
  - agent nested `attempt_result` serialization
  - replay scorer comparisons
  - replay scorer trace provenance
  - replay volatile-id comparison allowlist
- Keep `SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION` value unchanged.

Acceptance:

- Scorer attempt artifacts serialize one id: `scorer_attempt_id`.
- No scorer artifact serializes `run_id` or generic `attempt_id`.
- Eval scorer summaries and replay scorer comparison records use
  `scorer_attempt_id`.
- Attempt trace provenance uses `scorer_attempt_id`.

Targeted tests:

```bash
uv run pytest tests/test_attempt.py tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_controls_run.py tests/test_controls_reporting.py tests/scorers/test_audit.py tests/test_trace_schema.py
```

### Checkpoint 3: Agent Attempt ID Vertical Slice

Tasks:

- Replace serialized `AgentTaskRunResult.run_id` with
  `AgentTaskRunResult.agent_attempt_id`.
- Update `AgentTaskRunManifest`.
- Update agent attempt root `manifest.json`.
- Update agent audit and controls from `agent_run_id` to `agent_attempt_id`.
- Update replay direct-agent source provenance.
- Update every direct agent-attempt consumer in the same checkpoint:
  - eval `AgentAttemptSummary`
  - eval run manifest agent summaries
  - eval trace child-id fields
  - replay agent comparisons
  - replay agent trace provenance
  - replay volatile-id comparison allowlist
- Keep `AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION` value unchanged.

Acceptance:

- Agent attempt artifacts serialize `agent_attempt_id`.
- No agent artifact serializes generic `run_id`.
- Eval agent summaries and replay agent comparison records use
  `agent_attempt_id`.
- Nested scorer result uses `scorer_attempt_id`.

Targeted tests:

```bash
uv run pytest tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_reporting.py tests/agents/test_agent_audit.py tests/test_controls_run.py tests/test_controls_reporting.py
```

### Checkpoint 4: Eval Attempt Identity

Tasks:

- Add `eval_attempt_id` to `EvalAttemptRecord`.
- Generate one `eval_attempt_id` per policy/task/attempt-index slot.
- Keep the natural-key fields (`eval_run_id`, policy, `task_id`,
  `attempt_index`) present.
- Validate `eval_attempt_id` uniqueness within an eval run.
- Update eval trace events:
  - `eval_attempt_started` includes `eval_attempt_id`.
  - `eval_attempt_finished` includes `eval_attempt_id` and the relevant child
    typed id(s).
- Update eval run manifest attempts:
  - add `eval_attempt_id`
  - replace scorer summary ids with `scorer_attempt_id`
  - replace agent summary ids with `agent_attempt_id`
- Change `eval_run_id` value prefix from `eval_` to `eval_run_`.
- Keep `EVAL_RUN_ARTIFACT_SCHEMA_VERSION` value unchanged.

Acceptance:

- Eval manifest attempt records have a durable eval-layer id.
- Eval traces no longer use generic `attempt_id`.
- Eval reports render typed ids if they render ids at all.

Targeted tests:

```bash
uv run pytest tests/test_eval_run.py tests/test_reporting.py tests/test_trace_schema.py
```

### Checkpoint 5: Replay Run And Comparison IDs

Tasks:

- Rename top-level `ReplayRun.replay_id` to `replay_run_id`.
- Change value prefix from `replay_` to `replay_run_`.
- Update replay root manifest and replay result payload.
- Replace comparison `source_id` / `replay_id` with typed fields:
  - scorer comparison: `source_eval_attempt_id` when the source is an eval
    run, `source_scorer_attempt_id`, `replayed_scorer_attempt_id`
  - agent comparison: `source_eval_attempt_id` when the source is an eval run,
    `source_agent_attempt_id`, `replayed_agent_attempt_id`
- Update replay trace provenance to `replay_run_id` and typed source/replayed
  attempt ids.
- Add `replay_run_id` to eval suite replay records if useful for reporting.
- Keep `REPLAY_RUN_ARTIFACT_SCHEMA_VERSION`, `REPLAY_RESULT_SCHEMA_VERSION`,
  `TRACE_SCHEMA_VERSION`, and `EVAL_SUITE_ARTIFACT_SCHEMA_VERSION` values
  unchanged.

Acceptance:

- Top-level replay id and replayed attempt ids cannot be confused.
- Replay result JSON has no `source_id` or generic comparison-level `replay_id`.
- Replay comparisons for eval-run sources include `source_eval_attempt_id`.
- Replay traces validate typed replay provenance.

Targeted tests:

```bash
uv run pytest tests/test_replay.py tests/test_reporting.py tests/test_trace_schema.py tests/test_eval_run.py
```

### Checkpoint 6: Trajectory Identity

Tasks:

- Replace generic trajectory identity fields:
  - `run_id`
  - `attempt_id`
- Add typed identity fields:
  - `eval_suite_id`
  - `eval_run_id`
  - `eval_attempt_id`
  - `agent_attempt_id`
  - `scorer_attempt_id`
  - `replay_run_id`
- Keep `attempt_index` as an ordinal.
- Update cross-section invariants so present ids are coherent with status and
  artifact type.
- Keep `TRAJECTORY_RECORD_SCHEMA_VERSION` value unchanged.

Acceptance:

- A trajectory record can identify the eval slot and the concrete agent/scorer
  artifacts without overloading `run_id` or `attempt_id`.

Targeted tests:

```bash
uv run pytest tests/trajectories/test_schema.py
```

### Checkpoint 7: Controls, Audits, Reports, Docs

Tasks:

- Update controls outputs and reports:
  - `attempt_id` -> `scorer_attempt_id` for scorer controls.
  - `agent_run_id` -> `agent_attempt_id` for agent controls.
- Update audit outputs:
  - scorer audit uses `scorer_attempt_id`.
  - agent audit uses `agent_attempt_id`.
- Update markdown reports, docs, and weekly implementation notes.
- Explicitly update:
  - `docs/model_interface.md`
  - `docs/trace_schema.md`
  - `src/agentenv/README.md`
  - `notes/weekly/week_07/implementation_notes.md`
- Update volatile replay JSON key allowlist:
  - remove old `run_id` / `attempt_id` where possible.
  - add typed id fields that should be ignored in replay artifact byte/JSON
    comparisons.

Acceptance:

- User-facing reports do not show generic ids for typed attempts.
- Docs define the id vocabulary in one place.

Targeted tests:

```bash
uv run pytest tests/test_controls_run.py tests/test_controls_reporting.py tests/scorers/test_audit.py tests/agents/test_agent_audit.py tests/test_reporting.py tests/test_replay.py
```

### Checkpoint 8: Final Audit

Tasks:

- Run full tests and static checks.
- Run stale-id audit.

Final verification:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

Stale-id audit:

```bash
rg "\\b(run_id|attempt_id|agent_run_id|source_id|replay_id|source_artifact_id|replay_artifact_id|source_attempt_id|replay_attempt_id)\\b" src tests docs notes/weekly/week_07
rg "\\b(eval_[0-9a-fA-F]{8,}|eval_001|run_[0-9a-fA-F]{8,}|run_001|attempt_[0-9a-fA-F]{8,}|attempt_001|agent_task_run_[0-9a-fA-F]{8,}|agent_task_run_001|replay_[0-9a-fA-F]{8,}|replay_001)\\b" src tests docs notes/weekly/week_07
```

Expected:

- `run_id` may remain only in unrelated domains where the owner is obvious and
  not part of eval/scorer/agent/replay artifacts.
- `attempt_id` may remain only in `attempt_index` or historical before/after
  planning text.
- `replay_id` should not remain for replay-run artifacts; use
  `replay_run_id`.
- Old value prefixes such as `eval_<uuid>`, `run_<uuid>`, `attempt_<uuid>`,
  `agent_task_run_<uuid>`, and `replay_<uuid>` should not remain in active
  generated contracts or tests.
- Plan files may retain old vocabulary only as explicitly historical examples.

## Review Questions

Ask review agents to check:

- Is `eval_attempt_id` justified, or should the eval slot remain a compound key
  of `eval_run_id`, `task_id`, and `attempt_index`?
- Are there any places where typed ids make records too sparse or verbose?
- Does the plan correctly avoid unnecessary version bumps for unreleased lab
  contracts?
- Are any generic ids acceptable inside private implementation helpers?
- Does the plan change behavior beyond naming and schema contracts?

## Self-Deception Traps

- Renaming `run_id` to `agent_attempt_id` in one artifact but leaving
  `agent_run_id` in controls or audits.
- Adding `eval_attempt_id` but still writing generic `attempt_id` in eval trace
  provenance.
- Renaming top-level `replay_id` while leaving comparison-level `replay_id` with
  a different meaning.
- Spending effort on compatibility/version bump mechanics before the contract is
  stable enough to preserve.
- Treating `source_artifact_id` as a harmless generic name when it actually
  hides whether the source is an agent attempt or scorer attempt.
