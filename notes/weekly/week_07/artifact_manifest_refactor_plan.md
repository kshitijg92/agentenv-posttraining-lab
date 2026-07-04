# Artifact Manifest Refactor Plan

> Superseded note: this plan predates
> [id_vocabulary_refactor_plan.md](id_vocabulary_refactor_plan.md). Its
> historical examples may use older generic id names such as `run_id`,
> `attempt_id`, and `replay_id`; the current artifact contract uses typed ids
> such as `scorer_attempt_id`, `agent_attempt_id`, `eval_attempt_id`, and
> `replay_run_id`.

## Why This Refactor Exists

The current artifact layout mixes several different meanings into similar names:

- root artifact manifests are named differently by subsystem:
  - `run_manifest.json`
  - `eval_matrix_manifest.json`
  - `control_run_manifest.json`
  - `replay_manifest.json`
- root artifact identity is stored as `artifact_version`, even though the value
  is really doing two jobs:
  - identifying the kind of artifact directory
  - identifying the schema contract for that artifact directory
- producer/procedure provenance is stored as `orchestrator_version`, but the
  current constant names and values are too close to artifact schema values:
  - `ORCHESTRATOR_VERSION = "attempt_v0"`
  - `AGENT_RUN_ORCHESTRATOR_VERSION = "agent_task_run_v0"`
- unrelated payload schemas also use `schema_version`, which is correct for
  those payloads but makes generic artifact `schema_version` ambiguous.

The goal is not to make the system more elaborate. The goal is to make the
artifact contract easy to reason about when we later export trajectories and
derive training/reward signals from eval outputs.

## Core Vocabulary

There are three version axes. A constant name must make its axis explicit.

| Axis | Constant pattern | JSON field | Example value | Meaning |
| --- | --- | --- | --- | --- |
| Artifact root schema | `*_ARTIFACT_SCHEMA_VERSION` | `artifact_schema_version` | `scorer_attempt_artifact_v0` | Reader contract for a root artifact directory and its root manifest |
| Orchestrator/procedure | `*_ORCHESTRATOR_VERSION` | `orchestrator_version` | `scorer_attempt_orchestrator_v0` | Producer/procedure provenance for a run result |
| Payload schema | `*_SCHEMA_VERSION` | `schema_version` | `trace_v0` | Reader contract for a non-root payload such as trace events, task hashes, or control scripts |

Root artifact manifests use both semantic type and artifact schema:

```json
{
  "artifact_type": "scorer_attempt",
  "artifact_schema_version": "scorer_attempt_artifact_v0",
  "orchestrator_version": "scorer_attempt_orchestrator_v0"
}
```

Nested payloads keep `schema_version`. For example, trace events, task hash
payloads, control scripts, trajectory records, reward components, and flake
detection records are not root artifact manifests.

## Non-Goals

- Do not change scoring behavior.
- Do not change replay semantics.
- Do not change prompt-loop behavior.
- Do not change task success definition.
- Do not remove any output artifact files other than replacing old root
  manifest filenames with `manifest.json`.
- Do not add backward-compatibility readers for stale artifact layouts.
- Do not broaden replay to support eval-suite inputs.
- Do not rename broad internal symbols such as `EvalMatrixRun` unless a later
  checkpoint explicitly does a mechanical internal rename.
- Do not put `artifact_type` on non-root payload files such as
  `replay_result.json`.

## Artifact Types

Add a central semantic artifact-type enum in `src/agentenv/artifacts.py`:

```python
class ArtifactType(StrEnum):
    SCORER_ATTEMPT = "scorer_attempt"
    AGENT_ATTEMPT = "agent_attempt"
    EVAL_RUN = "eval_run"
    EVAL_SUITE = "eval_suite"
    CONTROL_CALIBRATION = "control_calibration"
    REPLAY_RUN = "replay_run"
```

Do not add `TRAJECTORY_EXPORT` yet. There is no trajectory artifact writer yet,
and speculative enum members make the current contract less crisp.

## Target Root Manifest Schemas

### Scorer Attempt Artifact

Owner: `src/agentenv/orchestrators/attempt_io.py`

```python
SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION = "scorer_attempt_artifact_v0"
```

Root manifest:

```json
{
  "artifact_type": "scorer_attempt",
  "artifact_schema_version": "scorer_attempt_artifact_v0",
  "orchestrator_version": "scorer_attempt_orchestrator_v0",
  "run_id": "...",
  "attempt_id": "...",
  "task_id": "...",
  "task_manifest_path": "...",
  "submission_path": "...",
  "status": "...",
  "artifacts": {
    "attempt": "attempt.json",
    "stdout": "stdout.txt",
    "stderr": "stderr.txt",
    "error": "error.txt",
    "trace": "trace.jsonl",
    "final_diff": "final.diff"
  }
}
```

### Agent Attempt Artifact

Owner: `src/agentenv/orchestrators/agent_task_run.py`

```python
AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION = "agent_attempt_artifact_v0"
```

Root manifest:

```json
{
  "artifact_type": "agent_attempt",
  "artifact_schema_version": "agent_attempt_artifact_v0",
  "orchestrator_version": "agent_task_run_orchestrator_v0",
  "run_id": "...",
  "task_id": "...",
  "task_manifest_path": "...",
  "status": "...",
  "prompt_loop_status": "...",
  "attempt_status": "...",
  "artifacts": {
    "agent_task_run": "agent_task_run.json",
    "error": "error.txt"
  }
}
```

### Eval Run Artifact

Owner: `src/agentenv/orchestrators/eval_run.py`

```python
EVAL_RUN_ARTIFACT_SCHEMA_VERSION = "eval_run_artifact_v0"
```

Root manifest:

```json
{
  "artifact_type": "eval_run",
  "artifact_schema_version": "eval_run_artifact_v0",
  "eval_run_id": "...",
  "created_at": "...",
  "config_path": "...",
  "config_hash": "...",
  "config_name": "...",
  "task_pack": "...",
  "split": "...",
  "task_hashes": {
    "schema_version": "eval_task_hashes_v0"
  },
  "policy": "...",
  "attempts": [
    {
      "task_id": "...",
      "attempt_index": 0,
      "artifact_dir": "attempts/...",
      "artifact_type": "scorer_attempt",
      "artifact_schema_version": "scorer_attempt_artifact_v0"
    }
  ]
}
```

The nested `task_hashes.schema_version` is intentionally still a payload
schema version, not an artifact schema version.

### Eval Suite Artifact

Owner: `src/agentenv/orchestrators/eval_run.py`

```python
EVAL_SUITE_ARTIFACT_SCHEMA_VERSION = "eval_suite_artifact_v0"
```

Root manifest:

```json
{
  "artifact_type": "eval_suite",
  "artifact_schema_version": "eval_suite_artifact_v0",
  "eval_suite_id": "...",
  "created_at": "...",
  "config_path": "...",
  "policy_runs": [
    {
      "policy": "...",
      "eval_run_id": "...",
      "artifact_dir": "policies/oracle",
      "manifest": "policies/oracle/manifest.json"
    }
  ],
  "replay_runs": [
    {
      "policy": "...",
      "replay_index": 0,
      "artifact_dir": "replays/oracle__replay_001",
      "manifest": "replays/oracle__replay_001/manifest.json"
    }
  ]
}
```

Artifact-facing names become `eval_suite`. Broad internal class/function names
such as `EvalMatrixRun` can remain until a separate mechanical cleanup.

### Control Calibration Artifact

Owner: `src/agentenv/controls/controls_run.py`

```python
CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION = "control_calibration_artifact_v0"
```

Root manifest:

```json
{
  "artifact_type": "control_calibration",
  "artifact_schema_version": "control_calibration_artifact_v0",
  "control_run_id": "...",
  "created_at": "...",
  "task_pack_path": "...",
  "flake_detection": {
    "schema_version": "control_flake_detection_v0"
  }
}
```

The nested `flake_detection.schema_version` stays a payload schema.

### Replay Run Artifact

Owner: `src/agentenv/replay/runner.py`

```python
REPLAY_RUN_ARTIFACT_SCHEMA_VERSION = "replay_run_artifact_v0"
```

Root manifest:

```json
{
  "artifact_type": "replay_run",
  "artifact_schema_version": "replay_run_artifact_v0",
  "replay_id": "...",
  "created_at": "...",
  "source_run_dir": "...",
  "source_eval_run_id": "...",
  "source_artifact_type": "eval_run",
  "source_artifact_schema_version": "eval_run_artifact_v0",
  "artifacts": {
    "replay_result": "replay_result.json",
    "replay_results": "replay_results.jsonl",
    "trace": "trace.jsonl"
  }
}
```

`replay_result.json` is not a root artifact manifest. It should not receive
`artifact_type`. If it needs a schema field, use a replay-result payload schema
constant.

## Orchestrator Version Targets

### Scorer Attempt Orchestrator

Owner: `src/agentenv/orchestrators/attempt.py`

Starting state:

```python
ORCHESTRATOR_VERSION = "attempt_v0"
```

Target:

```python
SCORER_ATTEMPT_ORCHESTRATOR_VERSION = "scorer_attempt_orchestrator_v0"
```

### Agent Task Run Orchestrator

Owner: `src/agentenv/orchestrators/agent_task_run.py`

Starting state:

```python
AGENT_RUN_ORCHESTRATOR_VERSION = "agent_task_run_v0"
```

Target:

```python
AGENT_TASK_RUN_ORCHESTRATOR_VERSION = "agent_task_run_orchestrator_v0"
```

Readers must never dispatch artifact layout from `orchestrator_version`.

## Payload Schema Constant Cleanup

These are not artifact schema versions. They stay payload-level
`schema_version` values.

| Current constant | Target constant | Value |
| --- | --- | --- |
| `HASH_SCHEMA_VERSION` | `TASK_HASH_REPORT_SCHEMA_VERSION` | `task_hash_report_v0` |
| `EVAL_TASK_HASH_SCHEMA_VERSION` | `EVAL_TASK_HASHES_SCHEMA_VERSION` | `eval_task_hashes_v0` |
| `FLAKE_DETECTION_SCHEMA_VERSION` | `CONTROL_FLAKE_DETECTION_SCHEMA_VERSION` | `control_flake_detection_v0` |

These constants are already clear enough and are not part of this cleanup:

- `TRACE_SCHEMA_VERSION`
- `AGENT_CONTROL_SCRIPT_SCHEMA_VERSION`
- `TRAJECTORY_SCHEMA_VERSION`
- `REWARD_COMPONENTS_VERSION`

`TRAJECTORY_SCHEMA_VERSION` can become `TRAJECTORY_RECORD_SCHEMA_VERSION` in the
trajectory-specific checkpoint, not during the artifact-manifest refactor.

## Checkpoints

## Execution Status

Status as of implementation completion:

- Checkpoint 0 complete: plan file created before implementation.
- Checkpoint 1 complete: canonical root manifest filename is `manifest.json`;
  targeted tests passed; review findings were fixed.
- Checkpoint 2 complete: orchestrator constants and emitted values are explicit;
  targeted tests passed; review findings were fixed.
- Checkpoint 3 complete: root artifact identity is split into `artifact_type`
  and `artifact_schema_version`; targeted tests passed; review findings were
  fixed.
- Checkpoint 4 complete: artifact-facing eval suite vocabulary is in place;
  targeted tests passed; review findings were fixed.
- Checkpoint 5 complete: non-root payload schema constant names are explicit;
  targeted tests passed; review found no blocking issue.
- Checkpoint 6 complete: trajectory and replay trace vocabulary is aligned;
  targeted tests passed; review findings were fixed.
- Checkpoint 7 complete: current docs and final audit were updated.

Final verification:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

All final verification commands passed after the review fixes.

### Checkpoint 0: Plan File

Tasks:

- Write this plan.
- Confirm worktree status.

Acceptance:

- Plan exists under `notes/weekly/week_07/`.
- No source code has changed.

Review:

- No review agent required. This is pre-implementation planning.

### Checkpoint 1: Canonical Manifest Filename And Filename-Derived References

Tasks:

- Add `MANIFEST_FILENAME = "manifest.json"` in `src/agentenv/artifacts.py`.
- Write root manifests to `manifest.json` in:
  - `src/agentenv/orchestrators/attempt_io.py`
  - `src/agentenv/orchestrators/agent_task_run.py`
  - `src/agentenv/orchestrators/eval_run.py`
  - `src/agentenv/controls/controls_run.py`
  - `src/agentenv/replay/runner.py`
- Read root manifests from `manifest.json` in:
  - eval child-attempt reads
  - replay source reads
  - replay child-attempt reads
  - report discovery
  - task-hash compare manifest resolution
- Update manifest refs:
  - `policy_runs[*].run_manifest` -> `policy_runs[*].manifest`
  - `replay_runs[*].replay_manifest` -> `replay_runs[*].manifest`
  - trace payload ref key `run_manifest` -> `manifest`
- Update path-holder APIs:
  - `run_manifest_json` -> `manifest_json`
  - `run_manifest_path` -> `manifest_path`
- Update replay artifact comparison allowlists:
  - old root manifest filename entries -> `manifest.json`
- Update CLI output, reports, tests, and current docs to say `manifest.json`.
- Keep `artifact_version` unchanged.

Acceptance:

- Existing non-manifest artifact files are still produced.
- Old root manifest filenames are not produced.
- Tests that assert paths now use `manifest.json`.

Targeted tests:

```bash
uv run pytest tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_reporting.py tests/test_eval_task_hash_compare.py tests/test_controls_run.py tests/test_controls_reporting.py tests/test_cli.py tests/test_trace_schema.py tests/trajectories/test_schema.py tests/agents/test_agent_audit.py
```

Review:

- Run one review agent after tests.
- Reviewer checks that this checkpoint did not change artifact identity fields.

### Checkpoint 2: Explicit Orchestrator Version Names

Tasks:

- Rename `ORCHESTRATOR_VERSION` to `SCORER_ATTEMPT_ORCHESTRATOR_VERSION`.
- Change value from `attempt_v0` to `scorer_attempt_orchestrator_v0`.
- Rename `AGENT_RUN_ORCHESTRATOR_VERSION` to
  `AGENT_TASK_RUN_ORCHESTRATOR_VERSION`.
- Change value from `agent_task_run_v0` to
  `agent_task_run_orchestrator_v0`.
- Update tests and docs that assert old values.
- Do not change artifact manifests except for the emitted
  `orchestrator_version` values.

Acceptance:

- `orchestrator_version` remains present in attempt and agent task run result
  payloads.
- No reader dispatches on `orchestrator_version`.

Targeted tests:

```bash
uv run pytest tests/test_attempt.py tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py
```

Review:

- Run one review agent after tests.
- Reviewer checks that producer/provenance version naming is now explicit and
  not mixed with artifact schemas.

### Checkpoint 3: Root Artifact Identity Split

Tasks:

- Add `ArtifactType(StrEnum)` to `src/agentenv/artifacts.py`.
- Add artifact-schema constants in owning writer modules:
  - `SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION`
  - `AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION`
  - `EVAL_RUN_ARTIFACT_SCHEMA_VERSION`
  - `EVAL_SUITE_ARTIFACT_SCHEMA_VERSION`
  - `CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION`
  - `REPLAY_RUN_ARTIFACT_SCHEMA_VERSION`
- Replace root manifest `artifact_version` with:
  - `artifact_type`
  - `artifact_schema_version`
- Update eval attempt records:
  - `artifact_version` -> `artifact_type`
  - add `artifact_schema_version`
- Update replay source fields:
  - `source_artifact_version` -> `source_artifact_type`
  - add `source_artifact_schema_version`
- Update replay dispatch to use `artifact_type`, with schema validation after
  dispatch.
- Update reporting dispatch to use `artifact_type`, with schema validation
  after dispatch.
- Update task-hash compare to carry separate `artifact_type` and
  `artifact_schema_version`.
- Remove `SOURCE_EVAL_ARTIFACT_VERSION` and
  `SOURCE_AGENT_TASK_ARTIFACT_VERSION` in favor of `ArtifactType`.
- Do not put `artifact_type` on `replay_result.json`.

Acceptance:

- No active root manifest writes `artifact_version`.
- Root readers reject missing or unsupported `artifact_type`.
- Root readers reject unsupported `artifact_schema_version`.
- Payload schemas still use `schema_version`.

Targeted tests:

```bash
uv run pytest tests/test_attempt_io.py tests/test_agent_task_run.py tests/test_eval_run.py tests/test_replay.py tests/test_reporting.py tests/test_eval_task_hash_compare.py tests/test_controls_run.py tests/test_cli.py
```

Review:

- Run one review agent after tests.
- Reviewer checks that root artifact identity and nested payload schemas remain
  separate.

### Checkpoint 4: Eval Suite Artifact-Facing Vocabulary

Tasks:

- Change artifact-facing eval matrix vocabulary to eval suite:
  - `eval_matrix_id` -> `eval_suite_id`
  - ID prefix `eval_matrix_` -> `eval_suite_`
  - user-facing report title/text from Eval Matrix to Eval Suite
  - CLI output and docs from eval matrix to eval suite where user-facing
- Keep broad internal symbols like `EvalMatrixRun`,
  `_eval_matrix_manifest`, and `run_eval_config_all_policies` unless the code
  becomes more confusing than helpful.
- If function-local names are already being touched and are clearly
  artifact-facing, prefer `eval_suite`; otherwise leave for a mechanical
  cleanup checkpoint.

Acceptance:

- Root eval suite manifest exposes `eval_suite_id`.
- No active manifest exposes `eval_matrix_id`.
- User-facing docs/reports say eval suite.

Targeted tests:

```bash
uv run pytest tests/test_eval_run.py tests/test_reporting.py tests/test_eval_task_hash_compare.py tests/test_cli.py
```

Review:

- Run one review agent after tests.
- Reviewer checks that artifact-facing vocabulary is clean without unnecessary
  broad internal churn.

### Checkpoint 5: Non-Artifact Payload Schema Constant Names

Tasks:

- Rename `HASH_SCHEMA_VERSION` to `TASK_HASH_REPORT_SCHEMA_VERSION`.
- Rename `EVAL_TASK_HASH_SCHEMA_VERSION` to
  `EVAL_TASK_HASHES_SCHEMA_VERSION`.
- Rename `FLAKE_DETECTION_SCHEMA_VERSION` to
  `CONTROL_FLAKE_DETECTION_SCHEMA_VERSION`.
- Update imports and tests.
- Keep JSON field names as `schema_version`.
- Keep values unchanged.

Acceptance:

- Payload schema constants are explicit about the payload they version.
- No root artifact manifests use generic `schema_version`.

Targeted tests:

```bash
uv run pytest tests/test_task_hashing.py tests/test_eval_task_hash_compare.py tests/test_controls_run.py tests/test_controls_reporting.py
```

Review:

- Run one review agent after tests.
- Reviewer checks that only constant names changed, not payload contracts.

### Checkpoint 6: Trajectory And Trace Vocabulary Decision

Tasks:

- Update trajectory artifact-reference field names if they are in active use:
  - `run_manifest_json` -> `manifest_json`
  - `eval_matrix_json` -> `eval_suite_json`
- Rename `TRAJECTORY_SCHEMA_VERSION` to `TRAJECTORY_RECORD_SCHEMA_VERSION`.
- Consider trace event rename:
  - `source_run_manifest_loaded` -> `source_manifest_loaded`
- If trace event names change, treat it as a trace schema cleanup and update:
  - `src/agentenv/tracing/schema.py`
  - `docs/trace_schema.md`
  - trace tests
  - replay trace event emission
- Do not change trace event fields or provenance semantics.

Acceptance:

- Trajectory schema no longer uses stale manifest/eval-matrix artifact names.
- If trace event is renamed, trace tests and docs agree.

Targeted tests:

```bash
uv run pytest tests/trajectories/test_schema.py tests/test_trace_schema.py tests/test_replay.py
```

Review:

- Run one review agent after tests.
- Reviewer checks that trajectory/trace schema changes are intentional and not
  accidentally mixed into root artifact identity.

### Checkpoint 7: Docs And Final Audit

Tasks:

- Update current docs:
  - `src/agentenv/README.md`
  - `docs/model_interface.md`
  - `docs/eval_quality_gate.md`
  - `docs/trace_schema.md` if trace names changed
  - `notes/weekly/week_07/implementation_notes.md`
- Do not add coding-practice content to `learnings.md`.
- Run final old-vocabulary audit.

Final tests:

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

Final audit:

```bash
rg "artifact_version|ARTIFACT_VERSION|run_artifacts_v0|agent_task_run_artifacts_v0|eval_matrix_v0|attempt_v0|agent_task_run_v0|run_manifest.json|eval_matrix_manifest.json|control_run_manifest.json|replay_manifest.json|run_manifest_json|eval_matrix_json|source_artifact_version|SOURCE_.*ARTIFACT_VERSION|eval_matrix_id|Eval Matrix|eval_matrices|source_run_manifest_loaded|TRAJECTORY_SCHEMA_VERSION|TrajectorySchemaVersion" src tests docs notes/weekly/week_07
```

Expected:

- No active source/test/docs references to stale root artifact identity.
- Historical notes may retain old vocabulary only if clearly historical.
- Explicitly deferred internal symbols such as `EvalMatrixRun` are allowed.
- This plan intentionally retains old vocabulary in before/after examples.
- A negative test assertion may mention `eval_matrix_id` only to prove the
  active manifest no longer emits it.

Review:

- Run one final review agent after tests and audit.
- Reviewer checks for stale vocabulary, accidental behavior changes, and
  incomplete doc updates.

## Review-Agent Prompt Template

After each checkpoint, run a review-only agent with:

```text
Review-only task. Do not edit files.

We completed checkpoint <N> of the artifact manifest refactor.

Checkpoint scope:
<scope>

Please inspect the diff and relevant tests. Check for:
- changes outside the checkpoint scope
- stale vocabulary that should have changed in this checkpoint
- accidental behavior changes
- missing tests
- artifact/schema/orchestrator version-axis confusion

Return findings ordered by severity with file/line references. If no issues,
say so and list residual risks.
```

## Self-Deception Traps

- Claiming the refactor is only a filename change while leaving stale
  `artifact_version` semantics in new readers.
- Claiming `schema_version` means artifact schema when nested payloads also use
  `schema_version`.
- Letting `orchestrator_version` become a reader dispatch key.
- Treating `replay_result.json` like a root artifact manifest.
- Updating generated reports while forgetting replay artifact comparison
  allowlists.
- Renaming eval suite in prose but leaving `eval_matrix_id` in the artifact
  contract.
- Adding future-looking enum values that have no writer.
