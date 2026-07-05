# Typed Artifact Manifest And Payload Refactor Plan

## Purpose

We are introducing typed readers and writers for persisted manifests and
artifact payloads so later trajectory export and training-data filtering do not
depend on loose `dict[str, Any]` parsing at provenance boundaries.

The core rule: every persisted artifact manifest that identifies a run,
attempt, replay, or calibration artifact should have a Pydantic schema and a
typed loader. Every persisted payload that a manifest points to and that can
influence replay, reporting, reward components, leakage, or training eligibility
should also have a typed writer/loader contract. The trajectory builder should
consume those typed schemas instead of re-validating persisted JSON shape by
hand.

This refactor is not about changing eval behavior. It is about making the
artifact boundary explicit enough that we can trust status, ID, split,
provenance, replay, leakage, and training-eligibility decisions built from
those artifacts.

## Scope Boundary

In scope:

- Root artifact manifests named `manifest.json`.
- Manifest records nested inside root artifact manifests.
- Artifact payloads that are embedded in or consumed through root manifests,
  especially task-hash, flake-detection, replay-result, prompt-loop, task-view,
  scorer-result, and config-provenance payloads.
- Typed loaders for artifact manifests used by replay, reporting, task hash
  comparison, leakage scanning, and trajectory building.

Already typed source inputs, but important to inventory:

- `TaskManifest` from task `task.yaml`.
- `TaskPackManifest` from task-pack `manifest.yaml`.
- `TaskSplitsLock` from `splits.lock.json`.

Out of scope for this refactor:

- Trace event schemas; these already use `TRACE_SCHEMA_VERSION` and are payload
  schemas, not root manifests.
- Eval config schemas; these are config inputs, not artifact manifests.
- Markdown reports.
- Any backward-compatibility alias, shim, or reader for stale manifest layouts.
  Stale manifests should fail validation clearly.
- Changing artifact filenames, IDs, status semantics, scoring behavior, replay
  semantics, or training-eligibility rules.

## Manifest Inventory

### Root Artifact Manifests

These must all get Pydantic models and typed loaders:

| Artifact type | File | Current writer | Reader/users |
| --- | --- | --- | --- |
| `scorer_attempt` | `manifest.json` | `src/agentenv/orchestrators/attempt_io.py` | eval runs, replay, reporting, trajectory builder |
| `agent_attempt` | `manifest.json` | `src/agentenv/orchestrators/agent_task_run.py` | eval runs, replay, leakage scanner, reporting, trajectory builder |
| `eval_run` | `manifest.json` | `src/agentenv/orchestrators/eval_run.py` | replay, reporting, task-hash compare, trajectory builder |
| `eval_suite` | `manifest.json` | `src/agentenv/orchestrators/eval_run.py` | reporting, task-hash compare |
| `control_calibration` | `manifest.json` | `src/agentenv/controls/controls_run.py` | tests, future export gate evidence |
| `replay_run` | `manifest.json` | `src/agentenv/replay/runner.py` | eval suite manifests, reporting, future export gate evidence |

### Nested Manifest Records

These are not root files, but they are part of manifest contracts and should be
typed:

- `EvalRunAttemptManifestRecord`
  - carries `eval_attempt_id`, `task_id`, `attempt_index`, `artifact_dir`,
    child `artifact_type`, child `artifact_schema_version`, scorer summary, and
    agent summary.
- `EvalRunScorerAttemptSummary`
  - carries `scorer_attempt_id`, `status`, `public_status`, `hidden_status`,
    `error_class`, `final_diff_hash`, `duration_ms`.
- `EvalRunAgentAttemptSummary`
  - carries `agent_attempt_id`, agent run status, `prompt_loop_status`,
    `error_class`, `candidate_patch_hash`, `duration_ms`, and nested scorer
    summary.
- `EvalSuitePolicyRunManifestRecord`
  - carries policy identity, policy metadata, `eval_run_id`, artifact refs,
    attempt counts, and layer counts.
- `EvalSuiteReplayRunManifestRecord`
  - carries policy, replay index, `replay_run_id`, status, artifact refs, match
    counts, and error counts.
- `ControlCalibrationRecord`
  - carries task/control/repeat identity, artifact ref, expected outcome,
    actual outcome, and match.

### Artifact Payloads

These should be typed because root manifests embed or depend on them:

- `EvalTaskHashes`
  - currently nested under `task_hashes` in eval run and eval suite manifests.
  - schema version: `eval_task_hashes_v0`.
  - includes `task_pack_id`, `selected_task_hash_set`, and selected task hash
    records.
- `TaskHashReport`
  - produced by task hashing CLI as a standalone report, not a root artifact
    manifest.
  - schema version: `task_hash_report_v0`.
  - useful for future export gating and provenance checks.
- `ControlFlakeDetection`
  - nested under `flake_detection` in control calibration manifests.
  - schema version: `control_flake_detection_v0`.
  - useful for future export gating because it indicates harness stability.
- `ReplayResult`
  - pointed to by replay run manifests as `replay_result.json`.
  - schema version: `replay_result_v0`.
  - useful for reporting and future export gating because it records replay
    pass/mismatch/error counts.
- `ReplayComparisonRecord`
  - pointed to by replay run manifests through `replay_results.jsonl`.
  - current records do not carry a `schema_version`; model the current payload
    shape without adding one unless we explicitly choose a payload schema
    migration.
- `ControlCalibrationResultRecord`
  - pointed to by control calibration manifests through `control_results.jsonl`.
  - useful for future export gating because it links controls, expected outcomes,
    actual outcomes, and artifact dirs.
- `AttemptResult`
  - persisted as scorer attempt `attempt.json`.
  - already has a Pydantic model, but readers should use a typed loader instead
    of raw JSON.
- `AgentTaskRunResult`
  - persisted as agent attempt `agent_task_run.json`.
  - already has a Pydantic model, but readers should use a typed loader instead
    of raw JSON.
- `AgentTaskView`
  - persisted as agent attempt `agent_task_view.json`.
  - already has a Pydantic model.
- `PromptLoopResult`
  - persisted as agent attempt `prompt_loop_result.json`.
  - already has a Pydantic model.
- `ModelConfigProvenance`
  - persisted as `model_config.json` for model-backed agent attempts.
  - should wrap the typed model config plus `source_path` and `source_hash`.
- `DecodingConfigProvenance`
  - persisted as `decoding_config.json`.
  - should wrap the typed decoding config plus nullable source provenance for
    generated decoding configs.
- `AgentControlScriptCase`
  - persisted as `agent_control_script.json`.
  - already has a Pydantic model and schema version.

### Manifest-Like Files Not In Scope As Artifact Manifests

- `manifest_override.json` in scorer audit output.
  - This records temporary task-manifest overrides for audit cases.
  - It is explicitly not a replay or artifact manifest.
- `agent_control_script.json`.
  - This is not an artifact manifest. It is in scope as a typed artifact
    payload because attempt manifests can point to it.


## Target Module Shape

Create a central artifact package:

```text
src/agentenv/artifacts/
  __init__.py
    public re-exports for existing imports

  base.py
    MANIFEST_FILENAME
    ArtifactType
    ArtifactDirectoryError
    prepare_artifact_output_dir(...)

  manifests.py
  artifact schema version constants
  root manifest models
  nested manifest record models
  load_*_manifest(...) functions
  load_supported_*_manifest(...) functions where a caller accepts more than one type

  payloads.py
  payload schema version constants
  payload models
  typed payload loaders
  typed payload writer helpers where useful
```

Rationale:

- `src/agentenv/artifacts.py` is already the artifact namespace. Converting it
  into an `artifacts/` package avoids adding root-level one-off modules and keeps
  artifact contracts together.
- `artifacts/base.py` stays small and generic.
- `artifacts/__init__.py` should re-export stable names such as
  `MANIFEST_FILENAME`, `ArtifactType`, and `prepare_artifact_output_dir` so
  existing imports can be updated gradually without stale compatibility logic.
- Manifest schema versions live with the models that enforce them.
- Runtime dataclasses such as `EvalRun`, `ReplayRun`, and `ControlRun` remain
  procedure/runtime objects. Persisted manifest models represent serialized
  contracts.
- Consumers stop importing writer modules just to reuse version constants.
- Payload models are allowed to import existing pure schema models such as
  `AttemptResult`, `AgentTaskView`, `PromptLoopResult`, `ModelConfig`, and
  `DecodingConfig`. They should not import writer functions.

Import-boundary rule:

- `artifacts/manifests.py` must not import writer/orchestrator modules that also
  import manifest models. If a status alias or contract type currently lives in
  a writer module, move the pure contract type to a non-writer schema module
  first, or define the manifest field with an equivalent literal in the manifest
  module and test that it accepts the writer's emitted values.
- The obvious current risk is `AgentTaskRunStatus` and `AgentTaskRunManifest`,
  which live in `src/agentenv/orchestrators/agent_task_run.py`. Do not create an
  `artifacts/manifests.py <-> agent_task_run.py` import cycle while moving that
  manifest model.

## Schema Design Rules

- Root models use `extra="forbid"`.
- Root models validate exact `artifact_type` and exact
  `artifact_schema_version`.
- Nested payload models validate exact `schema_version` when they own one.
- Existing persisted payloads that do not carry `schema_version` should receive
  one when that gives us a cleaner current contract. We do not need backward
  compatibility for old payloads.
- Use existing status literal aliases and Pydantic result schemas where they
  already define the contract.
- Use `ArtifactType` values for artifact identity instead of duplicate string
  literals.
- Keep path fields as serialized strings in manifest models. Convert to `Path`
  at call sites that resolve paths.
- Keep artifact maps typed as `dict[str, str]` unless the set is naturally
  stable enough to justify a stricter model.
- Do not model every optional policy-specific field as one loose object if a
  discriminated shape is clearer.
- Typed artifact refs are not path safety by themselves. Readers that resolve
  artifact refs must keep or centralize validation that refs are relative,
  non-empty, and do not escape the artifact root.
- Eval policy metadata should be modeled as discriminated variants:
  scorer-control policies require scorer control metadata, agent-control
  policies require agent control metadata, and agent-model policies require
  model/decoding config refs.
- Replay run manifests must represent both successful source loading and
  `REPLAY_ERROR` cases. Source fields that are absent today on replay-source
  validation failure must remain intentionally optional unless we make a
  separate replay behavior change.
- Do not add `artifact_type` to non-root payloads. Payloads should use
  `schema_version` when they need a versioned contract.

## Proposed Models

Root models:

- `ScorerAttemptManifest`
- `AgentAttemptManifest`
- `EvalRunManifest`
- `EvalSuiteManifest`
- `ControlCalibrationManifest`
- `ReplayRunManifest`

Nested eval models:

- `EvalRunAttemptManifestRecord`
- `EvalRunScorerAttemptSummary`
- `EvalRunAgentAttemptSummary`
- `EvalSuitePolicyRunManifestRecord`
- `EvalSuiteReplayRunManifestRecord`

Nested control models:

- `ControlCalibrationManifestRecord`
- `ControlFlakeDetection`
- `ControlFlakeDetectionGroup`

Task hash payload models:

- `RequiredTaskFileHash`
- `SelectedEvalTaskHash`
- `EvalTaskHashes`
- `TaskHashReportRecord`
- `TaskHashReport`

Replay payload models:

- `ReplayResult`
- `ReplayComparisonRecord`

Control payload models:

- `ControlCalibrationResultRecord`

Agent/scorer payload models:

- `ModelConfigProvenance`
- `DecodingConfigProvenance`

Existing payload models reused through typed loaders:

- `AttemptResult`
- `AgentTaskRunResult`
- `AgentTaskView`
- `PromptLoopResult`
- `AgentControlScriptCase`

Shared helpers:

- `load_json_object(path: Path) -> dict[str, Any]`
- `load_scorer_attempt_manifest(path: Path) -> ScorerAttemptManifest`
- `load_agent_attempt_manifest(path: Path) -> AgentAttemptManifest`
- `load_eval_run_manifest(path: Path) -> EvalRunManifest`
- `load_eval_suite_manifest(path: Path) -> EvalSuiteManifest`
- `load_control_calibration_manifest(path: Path) -> ControlCalibrationManifest`
- `load_replay_run_manifest(path: Path) -> ReplayRunManifest`
- `load_attempt_manifest(path: Path) -> ScorerAttemptManifest | AgentAttemptManifest`
- `load_eval_artifact_manifest(path: Path) -> EvalRunManifest | EvalSuiteManifest`
- `load_replay_source_manifest(path: Path) -> EvalRunManifest | AgentAttemptManifest`
- `load_task_hash_report(path: Path) -> TaskHashReport`
- `load_replay_result(path: Path) -> ReplayResult`
- `load_replay_comparison_records(path: Path) -> tuple[ReplayComparisonRecord, ...]`
- `load_control_calibration_result_records(path: Path) -> tuple[ControlCalibrationResultRecord, ...]`
- `load_attempt_result(path: Path) -> AttemptResult`
- `load_agent_task_run_result(path: Path) -> AgentTaskRunResult`
- `load_agent_task_view(path: Path) -> AgentTaskView`
- `load_prompt_loop_result(path: Path) -> PromptLoopResult`
- `load_model_config_provenance(path: Path) -> ModelConfigProvenance`
- `load_decoding_config_provenance(path: Path) -> DecodingConfigProvenance`
- `load_agent_control_script_artifact(path: Path) -> AgentControlScriptCase`

## Checkpoint Plan

### Checkpoint 1: Establish Import-Safe Contract Types

Before creating a central manifest module, remove obvious import-cycle traps.

Targets:

- Convert `src/agentenv/artifacts.py` into an `src/agentenv/artifacts/` package:
  move generic artifact utilities into `artifacts/base.py`, and re-export the
  stable public API from `artifacts/__init__.py`.
- Move `AgentTaskRunManifest` out of `agent_task_run.py`, or plan the exact
  import direction so the writer depends on the manifest module and the manifest
  module does not depend on the writer.
- Keep pure status aliases in schema/contract modules rather than writer modules
  when both manifests and writers need them.
- Keep runtime dataclasses such as `EvalRun`, `ReplayRun`, and `ControlRun` out
  of persisted manifest schemas.

Done criteria:

- Existing `from agentenv.artifacts import ...` imports still work through
  `artifacts/__init__.py`.
- The dependency direction is acyclic and documented in code structure.
- Manifest schemas can import all field types they need without importing
  writer functions.
- No emitted JSON shape changes in this checkpoint.

Validation:

```bash
uv run pyright src/agentenv
uv run ruff check src/agentenv
```

### Checkpoint 2: Introduce Manifest Schemas Without Rewiring Writers

Add `src/agentenv/artifacts/manifests.py` and
`src/agentenv/artifacts/payloads.py` with models and typed loaders.

Use the current emitted JSON as the contract. Do not change emitted fields in
this checkpoint.

Done criteria:

- All six root artifact manifest types load through typed loaders.
- Bad `artifact_type` and bad `artifact_schema_version` are rejected.
- Nested eval attempt records validate child artifact identity.
- `EvalTaskHashes` validates `schema_version`.
- `ReplayResult`, `TaskHashReport`, `ControlFlakeDetection`, and new
  config-provenance payloads validate their payload schema versions.
- Existing Pydantic payloads have typed loaders and malformed-payload tests.
- `ReplayRunManifest` accepts the current `REPLAY_ERROR` shape where source
  artifact fields can be absent or null.
- Eval policy metadata rejects invalid cross-combinations, such as an
  `agent_model` manifest without model/decoding config refs or a control policy
  with the wrong `control_layer`.
- A focused `tests/test_artifact_manifests.py` covers all root loaders, wrong
  `artifact_type`, wrong `artifact_schema_version`, extra root fields, duplicate
  `eval_attempt_id`, bad nested payload schema versions, replay error manifests,
  and invalid policy metadata combinations.
- A focused `tests/test_artifact_payloads.py` covers payload loaders, missing or
  wrong `schema_version` where required, malformed existing payloads, and
  config-provenance wrapper validation.
- Existing writers still produce byte-compatible shapes except for formatting
  differences only if a writer is touched later.

Validation:

```bash
uv run pytest tests/test_artifact_manifests.py tests/test_artifact_payloads.py tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_controls_run.py tests/test_eval_task_hash_compare.py tests/trajectories/test_builder.py
uv run ruff check src/agentenv/artifacts tests/test_artifact_manifests.py tests/test_artifact_payloads.py
uv run pyright src/agentenv/artifacts tests/test_artifact_manifests.py tests/test_artifact_payloads.py
```

### Checkpoint 3: Move Writers To Manifest Models

Update root manifest writers to instantiate models and serialize
`model_dump(mode="json")`.

Writers:

- scorer attempt writer in `attempt_io.py`.
- agent attempt writer in `agent_task_run.py`.
- eval run and eval suite writers in `eval_run.py`.
- control calibration writer in `controls_run.py`.
- replay run writer in `replay/runner.py`.

Done criteria:

- No writer manually assembles a root manifest dict as its final serialized
  object.
- `AgentTaskRunManifest` has one definition, and writer imports do not create a
  cycle.
- Artifact schema version constants are imported from the manifest module.
- Tests still assert current JSON field names and typed IDs.
- Payload writer helpers are introduced only when needed by the payload
  checkpoint; root manifest writer migration should not hide payload schema
  changes.

Validation:

```bash
uv run pytest tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_controls_run.py tests/test_controls_reporting.py tests/test_reporting.py tests/test_cli.py
uv run ruff check src/agentenv tests
uv run pyright src/agentenv tests
```

### Checkpoint 4: Move Readers To Typed Loaders

Replace hand-written manifest parsing in consumers.

Consumers:

- `src/agentenv/replay/runner.py`
  - source manifests, child attempt manifests, and replay/scorer/agent payloads
    it reads.
- `src/agentenv/reporting/markdown.py`
  - eval run, eval suite, replay run, nested policy run manifests, and replay
    payloads it reads.
- `src/agentenv/evals/task_hash_compare.py`
  - eval run/eval suite manifests and nested `task_hashes`.
- `src/agentenv/security/leakage.py`
  - agent attempt manifest artifacts map.
- `src/agentenv/trajectories/builder.py`
  - eval run manifest, selected attempt, attempt manifest, nested scorer attempt
    manifest, and payloads needed for consistency checks.

Done criteria:

- No consumer uses `manifest.get("artifact_type")` for root manifest dispatch
  when a typed loader can do it.
- `TrajectoryRecord` construction no longer uses raw manifest dictionaries for
  eval run or attempt manifests.
- Replay validates parent eval attempt record and child manifest identity through
  shared typed code.
- Replay validates parent eval attempt summaries against child artifact payloads
  before using them as trusted status/ID/hash signals.
- Negative tests cover parent PASS / child FAIL drift and parent/child ID drift.
- Reporting and task-hash compare no longer duplicate eval artifact identity
  checks.
- Artifact ref resolution preserves relative, non-escaping path checks.
- Control calibration manifest readback is covered by tests even though current
  control markdown rendering uses the runtime `ControlRun` object.
- Raw `json.loads(...)` remains only for payloads that are explicitly outside
  the artifact contract.

Validation:

```bash
uv run pytest tests/test_artifact_manifests.py tests/test_artifact_payloads.py tests/test_replay.py tests/test_reporting.py tests/test_eval_task_hash_compare.py tests/security/test_leakage.py tests/trajectories/test_builder.py
uv run ruff check src/agentenv/replay src/agentenv/reporting src/agentenv/evals src/agentenv/security src/agentenv/trajectories src/agentenv/artifacts
uv run pyright src/agentenv/replay src/agentenv/reporting src/agentenv/evals src/agentenv/security src/agentenv/trajectories src/agentenv/artifacts
```

### Checkpoint 5: Type Artifact Payloads At Production Sites

Update task hashing, replay, and control calibration production sites to return
typed payload models instead of generic payload dicts where practical.

Targets:

- `build_eval_task_hashes(...) -> EvalTaskHashes`
- `TaskHashReport.payload` replaced or wrapped by a typed model.
- `write_task_hash_report(...)` has a matching `load_task_hash_report(...)`.
- Eval run/eval suite manifest writers serialize `EvalTaskHashes` through the
  manifest model.
- Replay writer serializes `ReplayResult` through its payload model.
- Replay reporting loads `ReplayResult` and replay comparison records through
  typed payload loaders where it reads those files.
- Control calibration JSONL records are written and read through a typed payload
  model when used as export-gate evidence.
- Scorer attempt `attempt.json` is written/read through `AttemptResult`.
- Agent attempt `agent_task_run.json`, `agent_task_view.json`, and
  `prompt_loop_result.json` are written/read through their Pydantic models.
- Model and decoding config provenance wrappers become typed payloads with
  explicit schema versions.
- `agent_control_script.json` is read through the existing typed control-script
  loader wherever consumed as an artifact.

Done criteria:

- Selected task hash records are validated once when built.
- Task-hash compare consumes `EvalTaskHashes` directly from typed manifests.
- Standalone `TaskHashReport` can be loaded and validated, or the plan is
  explicitly revised to keep it write-only until export gating.
- Replay result payloads are typed without adding `artifact_type` to them.
- Existing agent/scorer Pydantic payloads have typed artifact loaders.
- Config provenance payloads are typed and versioned.
- The serialized task hash payload remains compatible with current tests unless
  we explicitly choose a schema change.

Validation:

```bash
uv run pytest tests/test_artifact_payloads.py tests/test_task_hashing.py tests/test_eval_task_hash_compare.py tests/test_eval_run.py tests/test_replay.py tests/test_reporting.py tests/test_controls_run.py tests/trajectories/test_builder.py
uv run ruff check src/agentenv/artifacts src/agentenv/tasks src/agentenv/evals src/agentenv/orchestrators src/agentenv/replay src/agentenv/reporting src/agentenv/controls src/agentenv/trajectories
uv run pyright src/agentenv/artifacts src/agentenv/tasks src/agentenv/evals src/agentenv/orchestrators src/agentenv/replay src/agentenv/reporting src/agentenv/controls src/agentenv/trajectories
```

### Checkpoint 6: Remove Duplicate JSON Boundary Helpers

After consumers use typed loaders, remove or narrow local helpers that manually
parse root manifests.

Targets:

- `_load_json_object` copies in replay/reporting/task-hash compare/trajectory
  builder where they only exist for manifests.
- `_load_json_object` copies in replay/reporting/trajectory builder where they
  only exist for artifact payloads now covered by typed loaders.
- Local artifact identity validators duplicated across replay, reporting, and
  task-hash compare.
- Local selected task hash parsing duplicated in task-hash compare if the
  payload model owns it.
- Local replay result parsing in reporting once payload loaders own it.
- Local model/decoding provenance parsing once payload loaders own it.

Done criteria:

- Generic JSON helpers remain only for JSON files outside the artifact contract.
- Root artifact identity is validated by manifest models, and in-scope payload
  shape is validated by payload models.
- Reader error messages still include the manifest path.
- Artifact ref path validation remains present after local helpers are removed.

Validation:

```bash
uv run pytest tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_reporting.py tests/test_eval_task_hash_compare.py tests/test_controls_run.py tests/security/test_leakage.py tests/trajectories
uv run ruff check src/agentenv tests
uv run pyright src/agentenv tests
uv run ruff format --check src/agentenv tests
git diff --check
```

## Trajectory Builder Impact

The trajectory builder should become a consumer of typed manifests, not the
place where manifest structure is redefined.

Expected cleanup:

- `select_eval_attempt_record(...)` returns `EvalRunAttemptManifestRecord`.
- `select_eval_task_hash_record(...)` returns `SelectedEvalTaskHash`.
- attempt manifest loading returns `AgentAttemptManifest |
  ScorerAttemptManifest`.
- nested scorer manifest loading returns `ScorerAttemptManifest`.
- artifact refs are built from typed `artifacts` maps.
- status derivation reads typed summaries rather than raw dictionaries.
- parent eval summary fields are checked against child payloads before they
  influence task success, reward components, or training eligibility.
- prompt-loop, task-view, scorer-result, agent-result, and config-provenance
  payloads are consumed through typed loaders.

This keeps the trajectory record focused on post-training semantics: identity,
source provenance, policy, statuses, reward components, leakage, eligibility,
artifacts, and review.

## Self-Deception Traps

- A typed `EvalRunManifest` alone is not enough. If nested attempt records and
  child attempt manifests remain raw dictionaries, the export boundary is still
  weak.
- A manifest model that allows arbitrary extras can hide contract drift. Root
  artifact manifests should forbid extras unless there is a deliberate schema
  migration.
- A model named after the runtime object can blur boundaries. Runtime
  `EvalRun` is not the same thing as persisted `EvalRunManifest`.
- Payload schema versions are not artifact schema versions. `schema_version`
  belongs to nested payloads; `artifact_schema_version` belongs to root artifact
  manifests.
- Treating non-manifest artifact payloads as "out of scope" creates a second
  refactor later. If a payload can influence replay, reward, leakage, reporting,
  or training eligibility, it needs a clean contract now.
- A typed parent eval manifest can still lie about child outcomes if the parent
  summary is not checked against child payloads. Training eligibility must not
  trust parent summaries alone.
- Import cycles are a schema-boundary smell. If manifest models need writer
  modules to import, the contract is still too entangled with execution code.
- A strict replay manifest that cannot represent `REPLAY_ERROR` would silently
  change replay semantics. Error artifacts are still artifacts and need a typed
  shape.
- Artifact path strings can be well-typed and still unsafe. Ref resolution must
  separately reject absolute paths and `..` escapes.
- Passing tests that only inspect happy-path JSON is insufficient. We need
  negative tests for wrong artifact type, wrong schema version, missing nested
  records, duplicate eval attempt IDs, invalid policy metadata, replay error
  manifests, unsafe artifact refs, parent/child artifact identity drift, and
  parent/child status drift.

## Final Done Criteria

- Every active `manifest.json` root artifact has one Pydantic model and one
  typed loader.
- Every writer serializes root manifests through those models.
- Every reader dispatches root manifests through typed loaders instead of raw
  dictionaries.
- Trajectory builder consumes typed eval and attempt manifests.
- Replay parent/child attempt identity checks are shared with manifest typing.
- Eval parent summaries are consistency-checked against child attempt payloads
  before training/export decisions use them.
- Eval policy metadata is validated as discriminated policy variants.
- Task hash payloads embedded in eval manifests are typed.
- Standalone task hash reports have a typed loader or are explicitly deferred as
  write-only until export gating.
- Replay result payloads pointed to by replay manifests are typed, without
  turning them into root artifact manifests.
- Agent/scorer payloads pointed to by attempt manifests are typed.
- Model/decoding config provenance payloads are typed and versioned.
- Control flake detection payload embedded in control calibration manifests is
  typed.
- Artifact ref resolution keeps non-escaping relative path validation.
- No backward-compatibility aliases, shims, or stale-layout readers are added.
- Full targeted suite passes:

```bash
uv run pytest tests/test_artifact_manifests.py tests/test_artifact_payloads.py tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_reporting.py tests/test_eval_task_hash_compare.py tests/test_controls_run.py tests/test_controls_reporting.py tests/security/test_leakage.py tests/trajectories
uv run ruff check src/agentenv tests
uv run pyright src/agentenv tests
uv run ruff format --check src/agentenv tests
git diff --check
```
