# Eval Quality Gate

## Purpose

This checklist defines what must be true before a `repo_patch_python_v0` eval
result is trusted for analysis, reporting, trajectory export, or reward/data
filtering work.

This is a human checklist for v0. It is not yet a single enforced CLI contract.

The gate is intentionally conservative: a model score is not meaningful unless
the task pack, splits, controls, replay, scorer, and artifact provenance are all
healthy enough to support the claim being made.

## Scope

This gate applies to the current local repo-patch task family:

```text
data/task_packs/repo_patch_python_v0
```

The construct validity statement for this task pack is:

```text
docs/construct_validity_v0.md
```

The current measured construct is:

```text
small localized Python repair under a strict JSON-action tool interface
```

## Gate Checklist

### 1. Task Pack Validates

- [ ] `agentenv tasks validate <task-pack>` passes.
- [ ] Every task manifest loads under the current schema.
- [ ] Every required task file exists.
- [ ] Every task leakage canary is unique within the task pack.
- [ ] Hidden validator paths stay inside task-local hidden validator locations.
- [ ] Agent-visible workspaces do not include hidden validators or hidden assets.

Block the eval if:

- a task manifest is invalid;
- two tasks share the same leakage canary;
- hidden validators are missing;
- hidden validator paths escape expected task boundaries;
- hidden files are visible to the agent.

### 2. Splits Are Locked And Consistent

- [ ] `splits.lock.json` exists for the task pack.
- [ ] Every discovered task appears in exactly one split.
- [ ] No task appears in two splits.
- [ ] Each task YAML `split` matches `splits.lock.json`.
- [ ] `splits.lock.json` does not reference unknown task IDs.

Block the eval if:

- any task is unassigned;
- any task is assigned twice;
- task YAML and split lock disagree;
- heldout/private claims are made without a real heldout-private split.

### 3. Task Input Hashes Are Recorded

- [ ] The task-pack hash report can be generated.
- [ ] Eval manifests include selected-task hashes.
- [ ] Eval comparability is based on selected tasks, not the whole task pack.
- [ ] Per-task records include required task files and `full_task_dir_hash`.
- [ ] Any hash comparison report is `matched` before comparing eval scores.

Block the eval if:

- selected task hashes are missing;
- selected task hashes drift unexpectedly;
- a task input changed after the run and the result is still being treated as
  comparable.

### 4. Hidden Validators Measure More Than Public Checks

- [ ] Public checks are treated as diagnostic feedback, not the score.
- [ ] Hidden validators encode behavior missing from public checks.
- [ ] Public-only bad controls pass public checks but fail hidden validators.
- [ ] Known-bad controls fail for the expected reason, not because of harness
  or patch-apply errors.

Block the eval if:

- a public-only bad control passes hidden validation;
- hidden tests are effectively duplicates of public checks;
- hidden tests introduce requirements not stated clearly enough in the task
  instruction.

### 5. Scorer Controls Calibrate Correctly

For every task:

- [ ] `oracle` scorer control passes:
  - `attempt_status: PASS`
  - `public_status: PASS`
  - `hidden_status: PASS`
- [ ] `bad.noop` scorer control fails hidden validation:
  - `attempt_status: HIDDEN_TEST_FAIL`
  - `public_status: PASS`
  - `hidden_status: FAIL`
- [ ] `bad.public_only` scorer control fails hidden validation:
  - `attempt_status: HIDDEN_TEST_FAIL`
  - `public_status: PASS`
  - `hidden_status: FAIL`

Block the eval if:

- any oracle fails;
- any known-bad scorer control passes;
- any known-bad scorer control fails for an unexpected reason.

### 6. Agent Controls Calibrate Correctly

For every task:

- [ ] `happy` agent control completes the prompt loop and reaches scoring.
- [ ] `malformed` agent control fails with `invalid_model_output`.
- [ ] `recoverable` agent control observes the expected recoverable tool error
  and then completes.
- [ ] Prompt-loop completion is not confused with task success.
- [ ] Task success is taken only from the nested scorer attempt.

Block the eval if:

- the agent loop accepts malformed model output;
- recoverable tool errors are treated as terminal;
- prompt-loop completion is reported as task success without nested scoring.

### 7. Controls Are Repeat-Stable

- [ ] Controls are run with repeated attempts.
- [ ] `control_run_manifest.json` includes `flake_detection`.
- [ ] Overall flake status is `stable`.
- [ ] Scorer artifact stability is `stable`.
- [ ] Agent artifact stability is `stable`.
- [ ] Any drifted group is investigated using manifest drift details.

Block the eval if:

- a deterministic control drifts across repeats;
- artifact drift is normalized away without justification;
- per-file drift details are missing when drift is detected.

### 8. Controls Are Replayable

- [ ] Control attempts can be replayed from persisted artifacts.
- [ ] Replay reproduces scorer outcomes.
- [ ] Replay reproduces final diff hashes for scorer attempts.
- [ ] Replay reproduces agent-control artifact outcomes where agent artifacts
  are replayed.
- [ ] Replay reports show zero mismatched attempts for trusted controls.

Block the eval if:

- control replay cannot be run;
- replay result is `MISMATCH` or `REPLAY_ERROR`;
- replay mismatches are unexplained;
- replay compares a different task input version than the source attempt.

### 9. Reports Separate Failure Sources

- [ ] Reports separate public status, hidden status, and final attempt status.
- [ ] Reports separate scorer controls, agent controls, and model policies.
- [ ] Reports show replay status when replay is configured.
- [ ] Reports show flake status for scorer and agent artifacts.
- [ ] Model/protocol failures are not collapsed into coding failures.
- [ ] Scorer, sandbox, task, model, and infrastructure failures are distinguishable.

Block the eval if:

- a single pass rate hides public-only success;
- scorer failures and model failures are mixed together;
- strict JSON-action protocol failures are presented as pure coding failures.

### 10. Construct Validity Limitations Are Stated

- [ ] The report links or refers to `docs/construct_validity_v0.md`.
- [ ] The measured construct is stated narrowly.
- [ ] Non-claims are stated explicitly.
- [ ] The strict JSON-action tool-interface caveat is visible.
- [ ] The small task distribution limitation is visible.

Block broad claims if:

- the result is described as broad coding-agent capability;
- the result is described as heldout generalization without a heldout-private
  split;
- trajectory or reward data is treated as training-ready without filtering.

## Minimum Evidence Bundle

A trusted Week 6-style eval-quality run should leave behind:

```text
task-pack validation output
split-lock validation output
task hash report
eval manifest with selected-task hashes
control run manifest with flake_detection
control report with flake summary
replay manifest/result for replayed controls
construct-validity doc
eval-quality report or notes
```

## Current Command Shape

Example commands for the current task pack:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv tasks check-splits data/task_packs/repo_patch_python_v0/splits.lock.json
uv run agentenv tasks hash data/task_packs/repo_patch_python_v0 --out experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/eval_quality_controls_repo_patch_python_v0
uv run agentenv eval --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml --all-policies --out experiments/runs/eval_quality_gate_repo_patch_python_v0 --report-out experiments/reports/eval_matrices/eval_quality_gate_repo_patch_python_v0.md --overwrite
```

Replay command shape depends on the source artifact being replayed:

```bash
uv run agentenv replay <source-run-or-artifact-dir> --out <replay-dir>
```

## Gate Outcome

Use one of these labels when summarizing a run:

```text
PASS
BLOCKED_TASK_VALIDATION
BLOCKED_SPLITS
BLOCKED_HASH_DRIFT
BLOCKED_HIDDEN_LEAKAGE
BLOCKED_CONTROL_CALIBRATION
BLOCKED_FLAKE
BLOCKED_REPLAY
BLOCKED_REPORTING
BLOCKED_CONSTRUCT_CLAIM
```

`PASS` means the run is trustworthy for narrow analysis under the stated
construct. It does not mean the task pack supports broad model-quality claims.

## Version

The current eval-quality gate is:

```text
eval_quality_gate_v0
```

Promoting this checklist into a strict machine-checked gate should create a new
version.
