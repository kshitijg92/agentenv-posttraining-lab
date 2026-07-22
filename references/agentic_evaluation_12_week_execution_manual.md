# Agentic Evaluation 12-Week Execution Manual

Updated: 2026-06-16

This is a focused 12-week course plan for learning agentic evaluation and
post-training data discipline by constructing one serious, auditable
eval/post-training loop for local coding-agent tasks.

## Core Objective

Build a small, reproducible, Inspect-compatible or Terminal-Bench-style coding-agent eval suite with:

- 8-10 original local repo-patch/terminal tasks.
- Hidden deterministic validators.
- Oracle and known-bad controls.
- Replayable traces.
- Baseline results under fixed inference budgets.
- Reward-hacking and grader-failure analysis.
- One trace-filtering or SFT smoke experiment.
- A compact technical report with non-claims and failure analysis.

Default artifact name:

```text
agentenv-posttraining-lab
```

Default domain:

```text
local Python repo-patch tasks with shell/tests and deterministic hidden validators
```

Default final course outcome:

```text
A learner can build and audit a reproducible local coding-agent eval/post-training loop.
The loop can create, validate, run, replay, score, and report a small deterministic task suite.
The learner can test trace filtering and/or tiny SFT plumbing under fixed eval conditions.
The result is evidence about this controlled task distribution only, with explicit grader, task, sandbox, and training limitations.
```

Do not optimize for presentation polish yet. Optimize for actual capability.

## Hard Non-Negotiables

- Do not use proprietary data, code, prompts, evals, logs, metrics, internal
  tasks, internal examples, internal docs, or non-public product context.
- Do not train on heldout traces.
- Do not expose hidden validators to the agent phase.
- Do not count public benchmark tasks as original evaluation evidence.
- Do not report pass rates without environment failure rates, grader failure rates, task exclusions, runtime, and known shortcuts.
- Do not claim model improvement from a smoke run.
- Do not build multiple domains in the first 12 weeks.
- Do not add browser/API/function-call tasks unless the repo-patch loop is already reliable.

## Time Budget

Minimum viable week: 8-12 focused hours.

Stretch week: 15-20 focused hours.

Default weekly split:

- 1-2 hours reading/reference inspection.
- 5-8 hours implementation.
- 1-3 hours experiments/debugging.
- 1-2 hours notes/reporting.

If behind, cut in this order:

1. Training runs.
2. Task count.
3. Model variety.
4. Polish.
5. Optional Docker hardening.

Never cut:

- Hidden validators.
- Oracle and bad controls.
- Trace/replay.
- Split/provenance discipline.
- Grader failure analysis.
- Written limitations.

## Recommended Stack

Use this unless it blocks progress:

- Python 3.11 or 3.12.
- `uv`.
- `ruff`.
- `pytest`.
- `pyright`.
- `pydantic`.
- `typer`.
- `rich`.
- `pyyaml`.
- `xxhash`.
- Docker only for sandbox smoke initially.

Do not add MLflow, Phoenix, DVC, Ray, KubeRay, vLLM, SGLang, gVisor, or Firecracker in this 12-week plan unless they become directly necessary.

## Repo Layout

Create this structure as it becomes needed:

```text
agentenv-posttraining-lab/
  README.md
  pyproject.toml
  uv.lock
  src/agentenv/
    __init__.py
    cli.py
    tasks/
      schema.py
      validate.py
      splits.py
    envs/
      local_repo_env.py
    graders/
      pytest_hidden.py
      audit.py
    runners/
      patch_runner.py
      local_runner.py
    tracing/
      schema.py
      writer.py
      replay.py
    reporting/
      markdown.py
      compare.py
    rewards/
      schema.py
      components.py
      audit.py
    training/
      sft_schema.py
      preference_schema.py
    data/
      filtering.py
    sandbox/
      docker_env.py
  configs/
    eval/
    train/
    data/
    sandbox/
  data/
    task_packs/
    processed/
  experiments/
    runs/
    reports/
    plans/
    models/
  docs/
  notes/
    weekly/
    decisions/
    failures/
  tests/
```

## Weekly Gates

Week 4 thin-loop gate:

- Clean checkout can run one toy task end to end.
- Oracle passes.
- Known-bad fails.
- Trace JSONL exists.
- Markdown report exists.

Week 6 eval-quality gate:

- 6 original tasks in one family, or 3 excellent tasks if time-constrained.
- Hidden validators.
- 3x oracle replay.
- Known-bad rejection.
- No hidden files visible during agent execution.

Week 8 baseline gate:

- Baseline agent or scripted policies run all tasks with fixed budget.
- Prompt/public-tests-only pass rate is neither silently inflated nor mixed with oracle.
- Report separates model, grader, sandbox, task, and infra failures.

Week 10 spike gate:

- Choose exactly one spike:
  - task/eval quality,
  - trace filtering/SFT smoke,
  - reward hardening,
  - sandbox/runtime hardening.

Week 12 final gate:

- One-command small eval.
- Reproducible report.
- Scoring contract.
- Task cards.
- Failure examples.
- Non-claims.
- Claim/evidence table.

---

# Phase 1: Thin Eval Loop

## Week 1 - One Task End To End

Goal: one repo-patch task can be validated, patched, graded, and traced locally.

Learning objective:

- Understand task manifests, hidden validators, oracle/bad controls, and trace-linked grading.

### Resources

Read or inspect for no more than 90 minutes:

- Inspect AI task/scorer concepts.
- Terminal-Bench task layout.
- METR task standard.
- One small existing coding benchmark task format.

Write notes in:

```text
notes/weekly/week_01.md
```

### Setup

Run from the workspace parent directory:

```bash
cd /path/to/workspace-parent
cd agentenv-posttraining-lab
uv init --package agentenv-posttraining-lab
uv add pydantic typer rich pyyaml xxhash
uv add --dev pytest ruff pyright
mkdir -p src/agentenv/{tasks,graders,runners,tracing,reporting,sandbox}
mkdir -p data/task_packs/repo_patch_python_v0/tasks/toy_python_fix
mkdir -p tests docs notes/weekly notes/decisions notes/failures experiments/{runs,reports}
touch src/agentenv/__init__.py
```

If `uv init` refuses because the directory is non-empty, create `pyproject.toml` manually or run:

```bash
uv init --package .
```

### Files To Create

```text
src/agentenv/cli.py
src/agentenv/tasks/schema.py
src/agentenv/tasks/validate.py
src/agentenv/graders/pytest_hidden.py
src/agentenv/runners/patch_runner.py
src/agentenv/tracing/schema.py
tests/test_smoke.py
README.md
docs/scoping.md
notes/weekly/week_01.md
```

### Minimum CLI Shape

Implement these commands with `typer`:

```text
agentenv tasks validate <task-or-pack-path>
agentenv grade --task <task.yaml> --submission <patch-file> --out <run-dir>
```

Do not implement `eval`, `replay`, or `report` yet unless Week 1 is ahead of schedule.

### Task Layout

Create:

```text
data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/
  task.yaml
  seed_workspace/
    pyproject.toml
    src/mathlib.py
    tests/test_public.py
  hidden_tests/test_behavior.py
  controls/
    oracle.patch
    bad_noop.patch
    bad_public_only.patch
  task_card.md
```

The toy task should be simple but not meaningless:

- `src/mathlib.py` has a broken function.
- `tests/test_public.py` checks only a shallow case.
- `hidden_tests/test_behavior.py` checks edge cases.
- `bad_public_only.patch` passes public tests but fails hidden tests.

Example task idea:

```text
Function: normalize_ratio(numerator, denominator)
Bug: integer division/zero behavior/rounding edge case.
Public test: one simple positive ratio.
Hidden tests: zero denominator, negative denominator, large integers, float precision tolerance.
```

### Minimum `task.yaml`

```yaml
id: toy_python_fix_001
domain: repo_patch_python
split: practice
instruction: "Fix the broken function without changing public test intent."
seed_workspace: seed_workspace
allowed_tools: ["shell", "edit", "pytest"]
public_checks:
  - command: "uv run pytest tests/test_public.py"
hidden_validators:
  - id: behavior_pytest
    type: pytest
    path: hidden_tests
scoring:
  primary: hidden_pytest_pass
limits:
  timeout_seconds: 120
  max_turns: 10
  network: "off"
controls:
  oracle: controls/scorer_control_patches/oracle.patch
  bad:
    - controls/scorer_control_patches/bad_noop.patch
    - controls/scorer_control_patches/bad_public_only.patch
replay:
  capture: ["patch", "commands", "stdout", "stderr", "final_diff", "grade"]
leakage_canary: "CANARY_TOY_PY_FIX_001_PRIVATE"
```

### Required Schemas

In `src/agentenv/tasks/schema.py`, define:

```text
TaskManifest
PublicCheck
HiddenValidator
ScoringSpec
LimitSpec
ControlSpec
ReplaySpec
```

Use Pydantic. Validate:

- `id` is non-empty.
- `domain == "repo_patch_python"` for now.
- `split` is one of `practice`, `dev`, `heldout_private`, `public_calibration`.
- `seed_workspace` exists.
- Hidden validator paths exist but are not inside `seed_workspace`.
- Control patch files exist.
- Canary is non-empty and unique enough.

### Grading Behavior

`agentenv grade` should:

1. Create a fresh temp workspace.
2. Copy `seed_workspace` into it.
3. Confirm hidden tests are absent from the copied workspace.
4. Apply the submitted patch.
5. Run public checks.
6. Mount/copy hidden tests only after the patch phase.
7. Run hidden pytest.
8. Write output files.

Required output files:

```text
<out>/
  run_manifest.json
  attempt.json
  trace.jsonl
  final.diff
  stdout.txt
  stderr.txt
```

Minimum `attempt.json` fields:

```text
run_id
task_id
attempt_id
submission_path
status
public_status
hidden_status
error_class
started_at
ended_at
duration_ms
final_diff_hash
grader_version
```

Minimum statuses:

```text
PASS
FAIL
PATCH_APPLY_ERROR
PUBLIC_TEST_FAIL
HIDDEN_TEST_FAIL
GRADER_ERROR
TIMEOUT
```

### Commands

Run:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml
uv run agentenv grade --task data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/oracle.patch --out experiments/runs/week01_oracle
uv run agentenv grade --task data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/bad_noop.patch --out experiments/runs/week01_bad_noop
uv run agentenv grade --task data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/bad_public_only.patch --out experiments/runs/week01_bad_public_only
uv run pytest
uv run ruff check .
```

### Notes To Write

In `notes/weekly/week_01.md`, answer:

```text
What does the task measure?
What does it not measure?
Why is the hidden validator hidden?
How can the public-only patch fool public tests?
What fields are missing from the trace?
What would make this task too toy?
```

In `docs/scoping.md`, write:

```text
This project uses one domain: local Python repo-patch tasks.
This project does not claim broad coding-agent capability.
This project does not use proprietary or private organizational data.
This project does not claim sandbox security yet.
```

### Outputs

- Working package skeleton.
- One toy task.
- One oracle patch.
- Two bad patches.
- Validation command.
- Grading command.
- Trace files.
- Week 1 notes.

### Done Criteria

- `tasks validate` passes.
- Oracle patch gets `PASS`.
- No-op patch gets non-pass.
- Public-only patch passes public check but fails hidden check.
- Hidden tests are not copied into the agent workspace before grading.
- `trace.jsonl` exists for every grading run.
- `uv run pytest` passes.
- `uv run ruff check .` passes.

### Fallback

If patch application takes too long, temporarily use file-overwrite submissions:

```text
agentenv grade --submission-dir tests/fixtures/submissions/...
```

But keep:

- manifest validation,
- hidden validator,
- oracle control,
- bad control,
- trace output.

---

## Week 2 - Runner, Traces, Replay

Goal: move from a single grading command to a repeatable runner with deterministic replay and basic reporting.

Learning objective:

- Understand eval run identity, trace schema, reproducible replay, and failure separation.

### Files To Create

```text
src/agentenv/runners/local_runner.py
src/agentenv/envs/local_repo_env.py
src/agentenv/tracing/writer.py
src/agentenv/tracing/replay.py
src/agentenv/reporting/markdown.py
configs/eval/week02_thin.yaml
tests/test_replay.py
docs/trace_schema.md
```

### New CLI Commands

Implement:

```text
agentenv eval --config <config.yaml> --policy <oracle|bad-noop|bad-public-only> --out <run-dir>
agentenv replay <run-dir> --out <replay-dir>
agentenv report <run-dir> --out <report.md>
```

Keep policy-based eval simple. Do not build an LLM agent yet.

### `configs/eval/week02_thin.yaml`

```yaml
run_name: week02_thin
task_pack: data/task_packs/repo_patch_python_v0
tasks:
  - toy_python_fix_001
split: practice
attempts: 1
timeout_seconds: 120
policies:
  oracle:
    type: scorer_control_patch
    control: oracle
  bad-noop:
    type: scorer_control_patch
    control: bad_noop
  bad-public-only:
    type: scorer_control_patch
    control: bad_public_only
trace:
  version: trace_v0
  capture_stdout: true
  capture_stderr: true
  capture_diff: true
```

### Trace Events

Every attempt should write ordered JSONL events:

```text
episode_start
workspace_reset
submission_selected
submission_applied
public_check_started
public_check_finished
hidden_validation_started
hidden_validation_finished
grade_recorded
episode_finished
```

Each event must include:

```text
run_id
task_id
attempt_id
trace_id
event_index
timestamp_utc
event_type
payload
payload_hash
visible_to_agent
error_class
```

Set `visible_to_agent=false` for hidden-validation events.

### Run Manifest

Every eval run writes:

```text
run_manifest.json
```

Fields:

```text
run_id
created_at
git_sha_or_unknown
config_path
config_hash
task_pack_path
task_pack_hash
policy
attempts
python_version
platform
```

### Replay Semantics

`agentenv replay` does not rerun model inference.

It should:

1. Read prior `attempt.json`.
2. Recreate workspace.
3. Reapply recorded submission patch.
4. Rerun public and hidden validators.
5. Compare:
   - final status,
   - hidden status,
   - final diff hash,
   - grader version.

Write:

```text
<replay-dir>/
  replay_manifest.json
  replay_results.jsonl
```

### Commands

Run:

```bash
uv run agentenv eval --config configs/eval/week02_thin.yaml --policy oracle --out experiments/runs/week02_oracle
uv run agentenv eval --config configs/eval/week02_thin.yaml --policy bad-noop --out experiments/runs/week02_bad_noop
uv run agentenv eval --config configs/eval/week02_thin.yaml --policy bad-public-only --out experiments/runs/week02_bad_public_only
uv run agentenv replay experiments/runs/week02_oracle --out experiments/replays/week02_oracle
uv run agentenv report experiments/runs/week02_oracle --out experiments/reports/week02_oracle.md
uv run pytest
uv run ruff check .
```

### Report Contents

`week02_oracle.md` must include:

```text
run id
policy
task count
attempt count
pass count
fail count
environment failure count
grader failure count
median runtime
trace paths
known limitations
```

### Tests

Add tests for:

- Stable manifest parsing.
- Stable config hashing.
- Replay reproduces oracle result.
- Bad-noop remains bad under replay.
- Hidden validator path is absent before hidden-validation phase.
- Timeout status is not confused with task failure.

### Notes To Write

In `docs/trace_schema.md`, explain:

```text
What is visible to the agent?
What is hidden?
What is replayed?
What is not replayed?
Why do we hash payloads?
What fields are needed for reproducibility?
```

In `notes/weekly/week_02.md`, answer:

```text
Which failures are model/task failures?
Which failures are infra/grader failures?
What can replay prove?
What can replay not prove?
```

### Done Criteria

- `eval` runs oracle, bad-noop, and bad-public-only policies.
- `replay` reproduces final diff hash and grader result for oracle.
- All attempts have stable IDs.
- Timeout, patch failure, public-test failure, hidden-validator failure, and grader crash are distinct.
- Markdown report exists.
- Tests pass.

### Fallback

If replay is flaky:

- freeze `PYTHONHASHSEED=0`,
- set `TZ=UTC`,
- normalize temp paths before hashing,
- replay only patch plus command trajectories before adding richer trace fields.

---

# Phase 2: Measurement Trust

## Week 3 - Hidden Validators, Grader Audit, Sandbox Smoke

Goal: prove the grader and environment boundaries are credible enough to trust.

Learning objective:

- Treat graders as measurement instruments, not implementation details.

### Files To Create

```text
src/agentenv/graders/audit.py
src/agentenv/sandbox/docker_env.py
configs/sandbox/docker_none.yaml
tests/fixtures/grader_cases/
tests/graders/test_audit.py
tests/sandbox/test_invariants.py
docs/grader_failure_taxonomy.md
docs/sandbox_invariants_v0.md
notes/failures/grader_false_positive_001.md
```

### Grader Audit Cases

Create at least 10 cases:

```text
correct_oracle
wrong_noop
public_only_fix
malformed_patch
patch_changes_tests
timeout_patch
hidden_test_leak_attempt
fake_test_output_spoof
collateral_damage_import_break
ambiguous_instruction
```

Each case should include:

```text
case.yaml
submission.patch
expected_status
expected_failure_label
notes.md
```

### Failure Labels

Standardize these:

```text
model_failure
public_test_failure
hidden_test_failure
grader_failure
task_flake
runner_failure
patch_apply_error
sandbox_timeout
sandbox_network_blocked
hidden_validator_access_attempt
invalid_shortcut
ambiguous_task
```

### Sandbox Smoke Invariants

Implement Docker only as a smoke path, not as hostile-code security.

`configs/sandbox/docker_none.yaml`:

```yaml
sandbox_type: docker
network: none
cpus: 2
memory_mb: 2048
timeout_seconds: 120
run_as_root: false
mount_hidden_validators_during_agent: false
record_image_digest: true
```

Test these invariants:

- Network disabled.
- `hidden_tests` absent during agent phase.
- `controls` absent during agent phase.
- Leakage canary absent from agent-visible trace.
- Workspace reset between attempts.
- Hidden validators mounted only after episode.
- Timeouts produce `sandbox_timeout`, not ambiguous `FAIL`.
- Docker image digest logged if Docker is used.

### New CLI Commands

```text
agentenv controls run --task-pack <pack> --repeats <n> --out <run-dir>
agentenv graders audit --cases <case-dir> --out <report.md>
agentenv sandbox smoke --config <config.yaml> --task <task.yaml>
```

### Commands

Run:

```bash
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/week03_controls
uv run agentenv graders audit --cases tests/fixtures/grader_cases --out experiments/reports/week03_grader_audit.md
uv run agentenv sandbox smoke --config configs/sandbox/docker_none.yaml --task data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml
uv run pytest tests/graders tests/sandbox tests/test_replay.py
uv run ruff check .
```

### Report Contents

`week03_grader_audit.md` must include:

```text
case id
expected status
actual status
expected failure label
actual failure label
false positive?
false negative?
grader version
notes
```

### Notes To Write

`docs/grader_failure_taxonomy.md`:

- Define every failure label.
- Explain which labels count as model failure.
- Explain which labels invalidate a task.
- Explain which labels invalidate a run.

`docs/sandbox_invariants_v0.md`:

- List what the sandbox checks.
- List what it does not check.
- State explicitly: this is not a production hostile-code sandbox.

`notes/failures/grader_false_positive_001.md`:

- Describe a case where a bad solution could incorrectly pass.
- Explain how the audit catches it or why it remains a risk.

### Done Criteria

- Oracle passes 3/3.
- Every bad control fails 3/3.
- Grader audit has zero unexpected passes.
- Hidden validator text never appears in agent-visible traces.
- Canary never appears in agent-visible traces.
- Docker smoke either passes or has a documented blocker.

### Fallback

If Docker blocks:

```text
docs/week03_docker_blocker.md
```

must include:

- command tried,
- exact error,
- why local isolation is still sufficient for Week 3,
- what Docker check is postponed.

Do not skip hidden-validator checks or grader audit.

---

## Week 4 - Small Suite And Baseline Report

Goal: produce the first honest environment baseline report.

Learning objective:

- Learn task authoring, construct validity, controls, and report discipline.

### Task Count

Minimum:

```text
3 excellent tasks
```

Target:

```text
5-6 original tasks
```

Stretch:

```text
8 original tasks
```

All tasks must be in the same domain:

```text
repo_patch_python
```

### Suggested Tasks

Create tasks such as:

```text
fix_date_parser_tz
repair_jsonl_deduper
preserve_cli_error_codes
fix_cache_key_collision
harden_csv_schema
restore_retry_backoff
fix_path_normalization
repair_config_precedence
```

Avoid single-function katas when possible. Each task should involve at least:

- one source file,
- one visible public test,
- hidden behavioral tests,
- one plausible public-only shortcut,
- one oracle patch,
- one no-op bad patch.

### Required Per-Task Files

```text
task.yaml
seed_workspace/
hidden_tests/
controls/scorer_control_patches/oracle.patch
controls/scorer_control_patches/bad_noop.patch
controls/scorer_control_patches/bad_public_only.patch
task_card.md
```

### `task_card.md` Template

```markdown
# Task: <id>

## What It Measures

## What It Does Not Measure

## Human Solve Estimate

## Expected Meaningful Steps

## Public Check

## Hidden Validator

## Known Shortcuts

## Oracle Summary

## Bad Control Summary

## Flake Risks

## Provenance

Original self-authored task. No proprietary or private organizational data or
code.
```

### Files To Create

```text
data/task_packs/repo_patch_python_v0/manifest.yaml
data/task_packs/repo_patch_python_v0/splits.lock.json
configs/eval/week04_baseline.yaml
docs/scoring_contract.md
docs/task_authoring_checklist.md
docs/task_design_note_v0.md
experiments/reports/week04_baseline.md
```

### Split Policy

For Week 4:

```text
practice: toy task
dev: all new original tasks
heldout_private: empty or 1 task if ahead
public_calibration: empty
```

Do not create heldout just to feel rigorous. Heldout is useful only if you can avoid looking at it.

### `splits.lock.json`

Fields:

```json
{
  "version": "splits_v0",
  "created_at": "...",
  "task_pack": "repo_patch_python_v0",
  "practice": ["toy_python_fix_001"],
  "dev": ["..."],
  "heldout_private": [],
  "public_calibration": [],
  "policy": "heldout_private is read-only and never used for training or prompt tuning"
}
```

### Baseline Policies

Run three policies:

```text
noop
public-tests-only
oracle
```

Optional stretch:

```text
simple-prompt-loop
```

Do not block Week 4 on real LLM agent integration.

### Commands

Run:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/week04_controls
uv run agentenv eval --config configs/eval/week04_baseline.yaml --policy noop --out experiments/runs/week04_noop
uv run agentenv eval --config configs/eval/week04_baseline.yaml --policy public-tests-only --out experiments/runs/week04_public_only
uv run agentenv eval --config configs/eval/week04_baseline.yaml --policy oracle --out experiments/runs/week04_oracle
uv run agentenv replay experiments/runs/week04_oracle --out experiments/replays/week04_oracle
uv run agentenv report compare experiments/runs/week04_noop experiments/runs/week04_public_only experiments/runs/week04_oracle --out experiments/reports/week04_baseline.md
uv run pytest
uv run ruff check .
```

### Report Must Include

```text
task count
task ids
policy table
pass rate by policy
oracle pass rate
bad-control pass rate
replay match rate
environment failure rate
grader failure rate
median runtime
hidden-validator version/hash
task exclusions
trace links
known shortcuts
what this environment measures
what it does not measure
```

### Notes To Write

`docs/scoring_contract.md`:

- Primary metric is binary hidden-validator pass.
- Public tests are diagnostic, not the score.
- Oracle controls must pass.
- Known-bad controls must fail.
- Ambiguous/flaky tasks are excluded only by predeclared rules.
- Scorer version changes create new scorer versions.

`docs/task_authoring_checklist.md`:

- Include required files.
- Include oracle.
- Include bad controls.
- Include human solve estimate.
- Include shortcut analysis.
- Include provenance statement.

`docs/task_design_note_v0.md`:

- Explain why these are not just prompt-list tasks.
- Explain construct validity.
- Explain weaknesses.

### Done Criteria

- All tasks validate.
- Oracle pass rate is 100%.
- Known-bad pass rate is 0%, or every exception has a written blocker.
- Replay match rate is 100% for oracle.
- Baseline report clearly states this is an environment baseline, not a model-improvement claim.
- Minimum 3 excellent tasks exist.

### Fallback

If 5-8 tasks is too much, ship 3 excellent tasks with full controls and traces.

Cut task count before cutting:

- hidden validators,
- replay,
- controls,
- report.

---

# Phase 3: Baselines And Post-Training Plumbing

## Week 5 - Simple Agent Baseline And Model Interface

Goal: add a minimal model/agent path without weakening measurement.

Learning objective:

- Understand how fixed inference budgets, model configs, tool loops, and trace capture affect eval quality.

### Files To Create

```text
src/agentenv/models/schema.py
src/agentenv/models/fake.py
src/agentenv/models/chat_compatible.py
src/agentenv/agents/prompt_loop.py
src/agentenv/tools/schema.py
src/agentenv/tools/local_tools.py
configs/models/fake.yaml
configs/models/local_or_api_placeholder.yaml
configs/eval/week05_agent_baseline.yaml
docs/model_interface.md
experiments/reports/week05_agent_baseline.md
```

### Model Interface

Define:

```text
ModelClient.generate(messages, decoding_config) -> ModelResponse
```

Required `DecodingConfig` fields:

```text
strategy
temperature
top_p
top_k
max_new_tokens
num_return_sequences
seed
stop
timeout_seconds
```

Required `ModelResponse` fields:

```text
model_id
output_text
finish_reason
latency_ms
prompt_tokens
completion_tokens
total_tokens
error_class
raw_response_ref
```

### Agent Loop

Implement a simple prompt-loop agent:

```text
observe task instruction
choose one of: read_file, write_file, run_tests, submit_patch/final
max turns fixed by config
all tool calls logged
invalid tool call produces typed error
```

Do not make it clever. The point is instrumentation.

### Tool Schemas

Implement:

```text
read_file(path)
write_file(path, content)
run_tests(command)
final_answer(text)
```

Every tool result includes:

```text
tool_name
input_hash
stdout
stderr
exit_code
duration_ms
error_class
```

### Commands

Run:

```bash
uv run agentenv eval --config configs/eval/week05_agent_baseline.yaml --model fake --out experiments/runs/week05_fake_agent
uv run agentenv report experiments/runs/week05_fake_agent --out experiments/reports/week05_agent_baseline.md
uv run pytest
uv run ruff check .
```

If you have a local/API model available and cost is acceptable:

```bash
uv run agentenv eval --config configs/eval/week05_agent_baseline.yaml --model-config configs/models/local_or_api_placeholder.yaml --out experiments/runs/week05_real_agent
uv run agentenv report experiments/runs/week05_real_agent --out experiments/reports/week05_real_agent.md
```

### Report Must Include

```text
model id
task ids
fixed budget
max turns
temperature
pass/fail
tool-call invalidity
cost/tokens if available
latency
model failure vs task failure vs infra failure
```

### Done Criteria

- Fake model path runs end to end.
- Tool calls are trace-linked.
- Invalid tool calls do not crash the runner.
- Fixed inference budget is recorded.
- Real model path is either run or explicitly blocked with reason.

### Fallback

If model integration burns time:

- keep fake model,
- implement prompt-loop scaffolding,
- write `docs/week05_model_blocker.md`,
- continue to trajectory export.

---

## Week 6 - Eval Quality Gate

Goal: harden the small task suite enough to support trajectory/reward work.

Learning objective:

- Learn flake detection, false positives, construct validity, and split enforcement.

### Files To Create

```text
src/agentenv/tasks/splits.py
src/agentenv/tasks/hashing.py
src/agentenv/graders/flakes.py
configs/eval/week06_eval_quality.yaml
docs/eval_quality_gate.md
docs/construct_validity_v0.md
experiments/reports/week06_eval_quality.md
```

### Required Checks

Implement:

- exact normalized text hash for instructions and visible tests,
- task asset hash,
- split membership check,
- hidden validator path check,
- canary uniqueness check,
- flake detector for repeated oracle runs,
- false-positive review for bad controls.

Normalized text:

```text
lowercase
Unicode NFKC
collapse whitespace
strip volatile temp paths
hash with xxhash64
```

### Commands

Run:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv tasks check-splits data/task_packs/repo_patch_python_v0/splits.lock.json
uv run agentenv tasks hash data/task_packs/repo_patch_python_v0 --out experiments/reports/week06_task_hashes.json
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/week06_controls
uv run agentenv graders flake-check experiments/runs/week06_controls --out experiments/reports/week06_flakes.md
uv run agentenv eval --config configs/eval/week06_eval_quality.yaml --policy public-tests-only --out experiments/runs/week06_public_only
uv run agentenv report compare experiments/runs/week06_controls experiments/runs/week06_public_only --out experiments/reports/week06_eval_quality.md
```

### Construct Validity Notes

In `docs/construct_validity_v0.md`, write:

```text
What capability is being measured?
What task families are excluded?
What shortcuts exist?
Why are hidden tests appropriate?
How hard are tasks for a skilled human?
What does public-tests-only success mean?
What would make this task distribution invalid?
```

### Gate Criteria

Target:

- 6 original tasks.
- 3x oracle replay.
- Bad solution rejection.
- No hidden files visible during agent execution.
- No flake above 3%.

Minimum:

- 3 excellent tasks.
- All controls pass/fail correctly.
- Flake risks documented.

### Done Criteria

- Split checks are enforced by code.
- Task asset hashes are recorded.
- Flaky tasks are labeled or excluded.
- `week06_eval_quality.md` separates model, grader, sandbox, task, and infra failures.

### Fallback

If task count lags, stop authoring new tasks and fix the weakest task.

Do not proceed to trajectory filtering if:

- oracle controls are failing,
- hidden validators leak,
- bad controls pass,
- task flakiness is unexplained.

---

## Week 7 - Trajectory Export And Reward Components

Goal: turn eval traces into auditable post-training artifacts.

Learning objective:

- Learn trajectory schemas, reward components, training eligibility, and leakage boundaries.

### Files To Create

```text
src/agentenv/trajectories/schema.py
src/agentenv/rewards/schema.py
src/agentenv/rewards/components.py
scripts/export_trajectories.py
configs/eval/week07_baseline.yaml
docs/reward_design_v0.md
data/processed/trajectories/
```

### Trajectory Schema

Define `TrajectoryRecord`:

```text
trace_id
run_id
task_id
split
model_id
prompt_hash
messages
tool_calls
tool_outputs
errors
final_state_ref
grader_result
reward_components
training_allowed
```

### Reward Components

Keep components separate from scalar reward:

```text
hidden_success
public_test_success
format_valid
tool_validity
timeout_penalty
no_op_penalty
collateral_damage_penalty
environment_failure
reward_hack_flag
```

### Reward Versioning

Every reward record includes:

```text
reward_version
reward_config_hash
reward_code_hash
grader_version
```

### Training Eligibility

Rules:

- `practice` and `dev` may be exported for analysis.
- `heldout_private` may only be exported to `experiments/runs/heldout_readonly/`.
- `heldout_private` always has `training_allowed=false`.
- `public_calibration` always has `training_allowed=false`.
- Environment failures are never training-eligible.
- Reward-hack traces are never training-eligible unless explicitly labeled as negative/adversarial examples later.

### Commands

Run:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv eval --config configs/eval/week07_baseline.yaml --split dev --attempts 3 --out experiments/runs/week07_baseline
uv run python scripts/export_trajectories.py experiments/runs/week07_baseline --out data/processed/trajectories/week07_baseline.jsonl
```

### Manual Review

Manually inspect:

- 10 successful traces and 10 failed traces, or all traces if fewer.

Write:

```text
data/processed/trajectories/week07_review_notes.jsonl
```

Fields:

```text
trace_id
review_label
reason
shortcut_observed
environment_issue
training_allowed_override
notes
```

### Done Criteria

- Every trajectory links to task, split, model, prompt, grader, reward version, and run config.
- Reward components are inspectable individually.
- Heldout traces cannot enter trainable paths.
- Manual review notes exist.
- `docs/reward_design_v0.md` states when the reward is untrusted.

### Fallback

If model trajectories are expensive or flaky, use scripted/fake policies to validate export and reward plumbing.

Do not claim reward validity yet. This week proves observability only.

---

## Week 8 - Reward Hacking, Controls, And Baseline Gate

Goal: make the reward visibly attackable before using it for training.

Learning objective:

- Learn reward hacking, metric exploits, valid controls, and baseline discipline.

### Files To Create

```text
data/task_packs/reward_hack_dev/
tests/fixtures/reward_hack_cases/
src/agentenv/rewards/audit.py
configs/eval/week08_reward_hack.yaml
experiments/reports/week08_reward_hacking.md
notes/failures/reward_hack_001.md
experiments/plans/week08_baseline_gate.yaml
```

### Reward-Hack Fixtures

Create at least 5 cases.

Target 8 cases:

```text
public_test_only_pass
no_op_patch
fake_success_output
hidden_test_probe_attempt
format_only_compliance
tool_output_spoofing
state_corruption
timeout_or_retry_exploit
```

For each exploit, add a valid control:

```text
invalid shortcut should fail
real correct behavior should pass
```

### Reward Audit Command

Implement:

```bash
uv run agentenv rewards audit --cases tests/fixtures/reward_hack_cases --out experiments/reports/week08_reward_audit.md
```

### Eval Commands

Run:

```bash
uv run agentenv rewards audit --cases tests/fixtures/reward_hack_cases --out experiments/reports/week08_reward_audit.md
uv run agentenv eval --config configs/eval/week08_reward_hack.yaml --out experiments/runs/week08_reward_hack
uv run agentenv report experiments/runs/week08_reward_hack --out experiments/reports/week08_reward_hacking.md
```

Run the main baseline gate:

```bash
uv run agentenv eval --config configs/eval/week07_baseline.yaml --split dev --attempts 3 --out experiments/runs/week08_baseline_repeat
uv run agentenv report experiments/runs/week08_baseline_repeat --out experiments/reports/week08_baseline_gate.md
```

### Report Must Include

```text
task success rate
reward-hack pass rate
public-only pass rate
tool invalidity rate
grader failure rate
environment failure rate
cost/tokens if available
latency
failure labels
trace examples
```

### Baseline Gate

Before moving to Week 9, answer:

```text
Is the task suite stable enough for training experiments?
Is pass rate informative, or 0%/100%?
Are failures mostly model failures or measurement failures?
Which task should be deleted?
Which reward component is easiest to hack?
```

### Done Criteria

- Reward-hack pass rate is reported separately from task success.
- Every mitigation has one invalid shortcut and one valid-control test.
- Reward audit distinguishes model failure, grader failure, environment failure, and metric exploit.
- Known unpatched reward holes are documented.
- Baseline report separates model, grader, sandbox, task, and infra failures.

### Fallback

If 8 adversarial cases is too much, build 5 high-quality cases with strong trace analysis.

Do not claim reward robustness. Claim only that obvious hacks are measured and some are blocked.

---

# Phase 4: One Deep Spike

Default spike: validated trajectory/data filtering with tiny SFT smoke.

Reason: it ties together eval quality, reward design, training data discipline,
and post-training plumbing without pretending to do large-scale RL.

If Week 8 shows measurement is weak, replace Weeks 9-12 with the alternate spike at the end of this manual.

## Week 9 - SFT And Preference Data Plumbing

Goal: build trainable datasets without contaminating evals.

Learning objective:

- Learn post-training data contracts, trace quality labels, loss masking, and preference-pair validity.

### Files To Create

```text
docs/post_training_data_contract.md
src/agentenv/training/sft_schema.py
src/agentenv/training/preference_schema.py
scripts/make_sft_dataset.py
scripts/make_preference_pairs.py
configs/train/week09_sft_smoke.yaml
configs/train/week09_dpo_deferred.yaml
tests/training/test_sft_dataset.py
tests/training/test_preference_pairs.py
```

### Data Contract

In `docs/post_training_data_contract.md`, define:

```text
allowed sources
forbidden sources
split rules
trace-quality labels
leakage labels
rejection reasons
which data may be used for SFT
which data may be used for preference training
which data may never be used
```

### SFT Example Schema

Fields:

```text
messages
tools
task_id
trace_id
split
source
license
success_label
quality_label
leakage_status
reward_version
rejection_reason
```

Accept only:

```text
success_no_shortcut
human_repaired_success
```

Reject:

```text
heldout_private
public_calibration
flaky
hacky
public_test_only
ambiguous
environment_failure
hidden_leakage
```

### Preference Schema

Fields:

```text
prompt
chosen
rejected
basis
task_id
trace_ids
split
grader_versions
known_risks
```

Allowed pair bases:

```text
successful_vs_failed
lower_cost_success_vs_higher_cost_success
no_hack_success_vs_hacky_success
human_repaired_vs_failed
```

Reject pairs if:

- chosen and rejected are identical,
- either side is heldout-derived,
- either side is public-calibration-derived,
- either side is environment failure,
- pair basis is not auditable,
- chosen is only public-test success.

### Commands

Run:

```bash
uv run python scripts/make_sft_dataset.py --input data/processed/trajectories/week07_baseline.jsonl --out data/processed/sft/week09_sft.jsonl
uv run python scripts/make_preference_pairs.py --input data/processed/trajectories/week07_baseline.jsonl --out data/processed/preferences/week09_pairs.jsonl
uv run pytest tests/training
```

Run tiny SFT smoke if feasible:

```bash
uv run agentenv train sft --config configs/train/week09_sft_smoke.yaml --data data/processed/sft/week09_sft.jsonl --limit 20 --out experiments/models/week09_sft_smoke
```

Do not run DPO yet unless you have at least 20 auditable pairs. Instead write:

```text
configs/train/week09_dpo_deferred.yaml
docs/dpo_deferred_note.md
```

### Tool-Call Serialization Tests

Test:

- chat template formatting,
- EOS handling,
- assistant/action loss masking,
- user/tool-observation masking,
- malformed tool call rejection.

### Done Criteria

- Bad examples are rejected by code, not reviewer discipline.
- SFT dataset builder writes valid JSONL.
- Preference builder writes valid JSONL or documents insufficient pairs.
- Smoke training runs or fails with preserved logs.
- Adapter/model manifest records:
  - base model,
  - tokenizer,
  - config hash,
  - data hash,
  - seed,
  - git SHA,
  - hardware,
  - runtime.

### Fallback

If GPU training is blocked:

- run tokenizer/loss-masking tests,
- run tiny CPU overfit if feasible,
- preserve blocker note,
- continue filtering work.

Do not claim model improvement from this smoke.

---

## Week 10 - Filtering Policy V1 And Baseline-Controlled Comparison

Goal: turn manual review into reproducible filtering and test whether
fine-tuning and filtering change behavior relative to the frozen base policy.

Learning objective:

- Learn data filtering as an experimental variable, not a vibes-based cleanup
  step.
- Learn why comparing two trained policies without the unchanged base arm
  cannot establish whether either policy improved or regressed.
- Learn why development-task partitioning must prevent training examples from
  reappearing in the evaluation context.
- If enough auditable preference pairs exist, learn the incremental effect of
  preference optimization relative to the exact SFT policy from which it
  starts.

### Files To Create

```text
src/agentenv/data/filtering.py
configs/data/week10_filtering.yaml
configs/data/week10_task_partition.yaml
data/processed/manifests/week10_filter_manifest.json
data/processed/sft/week10_raw_train_dev.jsonl
data/processed/sft/week10_filtered_train_dev.jsonl
data/processed/preferences/week10_train_dev_pairs.jsonl
experiments/reports/week10_filtering_quality.md
configs/train/week10_sft_raw.yaml
configs/train/week10_sft_filtered.yaml
configs/train/week10_dpo.yaml
configs/eval/week10_fixed_selection_dev.yaml
experiments/reports/week10_base_vs_raw.md
experiments/reports/week10_base_vs_filtered.md
experiments/reports/week10_raw_vs_filtered.md
experiments/reports/week10_dpo_increment.md
```

The DPO files are conditional. Create them only when the Week 9 preference
artifact contains at least 20 auditable pairs and the reference-policy contract
below can be enforced.

### Task-Level Development Partition

Freeze two disjoint task-id sets before constructing Week 10 datasets:

```text
train_dev_task_ids
selection_dev_task_ids
```

Require:

```text
train_dev_task_ids intersect selection_dev_task_ids = empty
```

All SFT examples and DPO preference evidence must come only from
`train_dev_task_ids`. The fixed development evaluation must contain only
`selection_dev_task_ids`. Split attempts, seeds, or trajectories from the same
task do not create independence; the exclusion is at task identity and pinned
task-content hash level.

The selection-dev subset is development data, not heldout evidence. It may be
used to compare policies and make modeling choices, but it may never be
relabeled as heldout later. Keep `heldout_private` unopened until every data,
training, serving, decoding, and reporting choice is frozen.

### Filtering Labels

Implement:

```text
accepted_success
accepted_repaired
reject_leakage
reject_reward_hack
reject_flaky
reject_public_only
reject_env_failure
reject_low_signal
reject_ambiguous
```

### Reviewer Notes JSONL

Fields:

```text
trace_id
decision
reason
evidence_ref
reviewer
timestamp
```

### Filtering Commands

Run:

```bash
uv run agentenv data filter --config configs/data/week10_filtering.yaml --task-partition configs/data/week10_task_partition.yaml --input data/processed/trajectories/week07_baseline.jsonl --raw-out data/processed/sft/week10_raw_train_dev.jsonl --filtered-out data/processed/sft/week10_filtered_train_dev.jsonl
uv run agentenv data summarize --input data/processed/sft/week10_filtered_train_dev.jsonl --out experiments/reports/week10_filtering_quality.md
```

Here, `raw` does not mean arbitrary trajectories. `S_raw` must still satisfy all
Week 9 hard eligibility rules for split, leakage, harness integrity,
orchestration validity, reward-hack handling, review, serialization, and loss
ownership. `S_filtered` applies the stricter Week 10 quality policy to that
eligible pool.

### Baseline-Controlled SFT Training And Development Evaluation

Only run if Week 9 training smoke worked.

Define three policy arms:

```text
B0          = exact frozen base checkpoint with no adapter
S_raw       = B0 plus LoRA trained on raw-eligible train-dev SFT data
S_filtered  = B0 plus LoRA trained on strictly filtered train-dev SFT data
```

Hold the base checkpoint, tokenizer, model-input protocol, provider, chat
template, tool/action contract, decoding configuration, seed policy, and all
inference budgets constant. The intended treatment difference is the adapter.
If the base and adapter policies require different serving paths, report the
comparison as confounded rather than as a clean fine-tuning effect.

```bash
uv run agentenv train sft --config configs/train/week10_sft_raw.yaml --data data/processed/sft/week10_raw_train_dev.jsonl --out experiments/models/week10_raw
uv run agentenv train sft --config configs/train/week10_sft_filtered.yaml --data data/processed/sft/week10_filtered_train_dev.jsonl --out experiments/models/week10_filtered
uv run agentenv eval --config configs/eval/week10_fixed_selection_dev.yaml --out experiments/runs/week10_base
uv run agentenv eval --config configs/eval/week10_fixed_selection_dev.yaml --adapter experiments/models/week10_raw --out experiments/runs/week10_raw
uv run agentenv eval --config configs/eval/week10_fixed_selection_dev.yaml --adapter experiments/models/week10_filtered --out experiments/runs/week10_filtered
uv run agentenv report compare experiments/runs/week10_base experiments/runs/week10_raw --out experiments/reports/week10_base_vs_raw.md
uv run agentenv report compare experiments/runs/week10_base experiments/runs/week10_filtered --out experiments/reports/week10_base_vs_filtered.md
uv run agentenv report compare experiments/runs/week10_raw experiments/runs/week10_filtered --out experiments/reports/week10_raw_vs_filtered.md
```

The required questions are:

```text
B0 vs S_raw       -> what changed after raw-eligible SFT?
B0 vs S_filtered  -> what changed after filtered SFT?
S_raw vs S_filtered
                  -> what changed when filtering policy changed?
```

A raw-versus-filtered result alone is incomplete. Both adapters may improve,
both may regress, or one may merely regress less. The frozen base arm anchors
those interpretations.

### Conditional DPO Follow-Up

Run DPO only if at least 20 auditable Week 9 pairs remain after applying the
same task-partition, leakage, harness, and provenance gates. First select the
SFT policy using only the fixed selection-dev results. Then define:

```text
S_selected = the frozen selected SFT policy
P_dpo      = a policy initialized exactly from S_selected and updated by DPO
R_dpo      = a frozen reference initialized exactly from S_selected
```

`P_dpo` and `R_dpo` must begin with identical policy weights and serialization
semantics. Only `P_dpo` receives preference updates. The DPO run must pin its
reference-policy identity, beta, chosen/rejected log-probability reduction,
pair artifact, seed, runtime, and adapter composition. Task success alone must
not create the preference direction.

Evaluate `P_dpo` on the same fixed selection-dev tasks and report:

```text
S_selected vs P_dpo  -> incremental effect of preference optimization
B0 vs P_dpo          -> total observed post-training effect
```

If the reference-policy or adapter-composition contract is not yet trustworthy,
preserve the DPO materializations and write an explicit deferral rather than
forcing a training run.

If training did not work, run filtering-only analysis:

```bash
uv run agentenv report data-quality data/processed/sft/week10_raw_train_dev.jsonl data/processed/sft/week10_filtered_train_dev.jsonl --out experiments/reports/week10_filtering_quality.md
```

### Report Must Include

```text
raw example count
filtered example count
accepted count by reason
rejected count by reason
split distribution
task distribution
reward-hack removal count
environment failure removal count
leakage rejection count
examples of borderline decisions
```

If raw vs filtered eval runs:

```text
same base model
same tokenizer
same provider and model-input protocol
same inference budget
task-disjoint train-dev and selection-dev subsets
same fixed selection-dev task hashes
same scorer version
same seed policy
success rate
cost
latency
tool validity
reward-hack rate
regression rate
output length
base-versus-raw paired deltas
base-versus-filtered paired deltas
raw-versus-filtered paired deltas
```

If DPO runs, also report the selected SFT policy, exact frozen reference-policy
identity, pair count and distinct shared-context count, DPO loss configuration,
selected-SFT-versus-DPO paired deltas, and base-versus-DPO paired deltas.

### Done Criteria

- Every accepted trace has a reason.
- Every rejected trace has machine-readable rejection reason.
- No heldout/public calibration trace is accepted.
- Train-dev and selection-dev task ids and task-content hashes are frozen and
  disjoint.
- Filtering report exists.
- Base, raw-SFT, and filtered-SFT policies use one serving and evaluation path.
- Base-versus-raw, base-versus-filtered, and raw-versus-filtered comparisons
  exist or are explicitly blocked by a training or serving limitation.
- If DPO runs, its policy and frozen reference start from the exact same
  selected SFT policy and its two required comparisons are reported.
- Negative or neutral result is written clearly.

### Fallback

If full SFT fails:

- run tiny overfit,
- inspect generated behavior qualitatively,
- label as plumbing-only,
- keep filtering report as the primary output.

Do not inspect `heldout_private` during Week 10 iteration. After all policy arms
and reporting rules are frozen, a later one-shot heldout operation may compare
the predeclared base, selected SFT, and SFT-to-DPO policies together. Do not
claim general SFT or DPO benefit from development comparisons.

---

## Week 11 - Reliability, Reproduction, And Failure Injection

Goal: make the result reproducible enough to trust and failures visible enough to debug.

Learning objective:

- Learn eval systems reliability: resumability, typed failure modes, artifact hashes, and report regeneration.

### Files To Create

```text
scripts/reproduce_week10.sh
docs/reproducibility.md
experiments/plans/week11_reproduce.yaml
experiments/reports/week11_repro_check.md
.github/workflows/repro_smoke.yml
src/agentenv/runners/resume.py
tests/runner/test_resume.py
tests/runner/test_failure_injection.py
```

### Reproduction Command

Create:

```bash
uv run agentenv reproduce --plan experiments/plans/week11_reproduce.yaml --out experiments/runs/week11_repro
```

The plan should run:

- task validation,
- fake-model eval,
- controls replay,
- report generation,
- filtering summary.

Do not require GPU or paid API for the default reproduction.

### Manifest Checks

Verify and record:

```text
git SHA
lockfile hash
model revision
adapter hash if applicable
data manifest hash
reward hash
scorer hash
seed
hardware
Python version
platform
Docker image digest if Docker was used
```

### CI Smoke

Add CI jobs for:

```text
ruff
pyright
pytest
task validation
schema tests
filter tests
fake-model eval
report generation
```

### Failure Injection

Implement or simulate:

```text
worker interrupted
partial result missing
corrupt attempt.json
duplicate attempt id
timeout
hidden validator missing
bad config path
```

Each must produce typed failure, not silent success.

### Commands

Run:

```bash
uv run agentenv reproduce --plan experiments/plans/week11_reproduce.yaml --out experiments/runs/week11_repro
uv run pytest tests/runner tests/tasks tests/graders tests/training
uv run ruff check .
uv run pyright
```

### Notes To Write

`docs/reproducibility.md`:

```text
How to run toy eval.
How to run small eval.
How to regenerate report.
Which artifacts are content-hashed.
Which parts require local model/GPU/API.
Which results are not reproducible without rerunning model inference.
```

`experiments/reports/week11_repro_check.md`:

```text
exact commands
hardware
runtime
hashes
failures
fixes
unreproduced artifacts
```

### Done Criteria

- Repro smoke passes without private state.
- Failed reproduction has preserved failure note.
- Any flaky task is excluded or labeled outside primary metrics.
- CI blocks split leakage and train/eval contamination.
- Report can be regenerated from archived logs for at least one run.

### Fallback

If full reproduction is too slow:

- reproduce toy eval,
- reproduce fake-model small eval,
- regenerate report from logs,
- document why model-training reproduction is excluded.

Do not claim reproducibility unless the command actually runs from a clean environment.

---

## Week 12 - Final Spike Report And Next Technical Bet

Goal: finish with a truthful technical artifact and a clear next phase.

Learning objective:

- Learn research taste: claim boundaries, evidence mapping, failure analysis, and next-experiment selection.

### Files To Create

```text
experiments/reports/week12_spike_report.md
docs/claim_boundaries.md
docs/claim_evidence_table.md
docs/non_claims.md
docs/next_phase_plan.md
docs/final_readiness_review.md
README.md
```

### Final Report Structure

`experiments/reports/week12_spike_report.md`:

```markdown
# Week 12 Spike Report

## Abstract

## Artifact Summary

## Task Distribution

## Scoring Contract

## Baselines

## Trace And Reward Schema

## Filtering Policy

## Training Smoke Or Deferred Training

## Reward-Hack Analysis

## Reliability And Reproduction

## Main Evidence

## Negative Results

## Limitations

## Non-Claims

## Next Technical Bet
```

### Required Tables

Include:

```text
task table
control pass/fail table
baseline table
reward-hack table
filtering rejection table
base vs raw-SFT vs filtered-SFT comparisons if available
selected-SFT vs DPO comparison if DPO ran
flake/exclusion table
claim/evidence table
```

### Claim/Evidence Table

Fields:

```text
claim
evidence
run ids
config paths
task split
scorer version
statistical support
counterevidence
limitation
decision
```

### Bundle Command

Implement:

```bash
uv run agentenv report bundle --runs experiments/runs/week10_base experiments/runs/week10_raw experiments/runs/week10_filtered experiments/runs/week10_dpo experiments/runs/week11_repro --out experiments/reports/week12_spike_report.md
```

If some runs do not exist, the bundle command should include a missing-artifact section rather than crash without explanation.

### README Update

README must include:

```text
what this is
what this is not
quickstart with fake model
one-command toy eval
one-command small eval
one-command report generation
main limitations
where to read the Week 12 report
```

### Final What-Not-To-Claim

Write `docs/non_claims.md`:

```text
No large-scale RLHF claim.
No general coding-agent improvement claim.
No benchmark SOTA claim.
No production sandbox-security claim.
No validated human preference modeling claim.
No reliable heldout improvement claim unless heldout protocol was predeclared and used once.
No claim based on proprietary or private organizational knowledge.
```

### Next Phase Options

Choose one:

1. Task/eval quality:
   - expand to 12-20 tasks,
   - add human solve attempts,
   - improve construct validity,
   - add public calibration tasks.

2. Trace filtering/post-training:
   - build stronger trace labels,
   - improve SFT quality,
   - collect enough auditable preference pairs,
   - run DPO only if pair quality supports it and it was not already completed
     during the conditional Week 10 follow-up.

3. Reward/safety hardening:
   - expand reward-hack suite,
   - add adversarial task variants,
   - reduce false positives,
   - improve scorer calibration.

4. Runtime/systems:
   - resumable concurrent runner,
   - failure injection,
   - trace viewer,
   - cost/latency capacity table.

Pick based on evidence, not novelty.

### Done Criteria

- Report contains exact commands and artifact paths.
- Claim is narrower after evidence, not broader.
- At least one failed hypothesis is documented.
- Reward-hack and regression checks are included beside headline results.
- One-command fake-model eval works.
- One-command report generation works.
- Next phase has a stop rule.

### Final 12-Week Pass Criteria

By the end, the course artifact should support these statements:

```text
A local coding-agent eval/post-training artifact exists.
It measures this narrow task distribution.
The hidden validators and controls are documented.
The baselines are documented.
The failure modes are documented.
Replayability and scorer reliability checks are documented.
Train/eval leakage controls are documented.
The trace-filtering/SFT smoke result is documented, including what changed or did not change.
This is what I would deepen next.
```

---

# Alternate Weeks 9-12 Spikes

Use these only if Week 8 shows the default trace-filtering spike is not the right next move.

## Alternate A - Task/Eval Quality Spike

Use if:

- task suite is too small,
- pass rate is uninformative,
- graders are weak,
- task validity feels toy.

Weeks 9-12:

```text
Week 9: expand to 8-10 tasks with stronger task cards and human solve estimates.
Week 10: grader calibration, false-positive audit, scorer version v1.
Week 11: public calibration slice from 1-2 Terminal-Bench/SWE-bench-inspired examples, clearly labeled non-private.
Week 12: task/eval report with construct-validity analysis and next task-family decision.
```

Do not train.

## Alternate B - Runtime/Systems Spike

Use if:

- runs are flaky,
- reproduction fails,
- trace storage is messy,
- failures are hard to debug.

Weeks 9-12:

```text
Week 9: resumable runner and atomic attempt writes.
Week 10: failure injection and typed infra failures.
Week 11: concurrency workers=1 vs workers=4 for scripted policies.
Week 12: reliability report and trace viewer/static HTML report.
```

Do not train.

## Alternate C - Reward/Scorer Hardening Spike

Use if:

- public-only shortcuts pass,
- false positives exist,
- reward components are easy to game.

Weeks 9-12:

```text
Week 9: expand reward-hack suite to 12-15 cases.
Week 10: add valid controls and scorer fixes.
Week 11: re-run main suite before/after scorer changes.
Week 12: reward-hacking report with scorer migration notes.
```

Do not train unless the scorer is stable.

---

# Daily Work Template

For each work session, write one entry in `notes/weekly/week_XX.md`:

```markdown
## YYYY-MM-DD

### Shipped

### Ran

### Result

### Failure Or Surprise

### Decision

### Next Small Step
```

Every day should produce at least one of:

- a code change,
- a task artifact,
- a trace,
- a report,
- a failure note,
- a decision note.

---

# Weekly Review Template

At the end of each week, answer:

```text
What did I build?
What did I learn?
What failed?
What got cut?
What evidence exists?
What is still hand-wavy?
What is the next smallest useful step?
```

Do not roll a week forward if a core gate failed. Narrow instead.

---

# Reading Plan

Do not read endlessly. Use reading to unblock implementation.

Week 1:

- Inspect task/scorer basics.
- Terminal-Bench task examples.
- METR task standard overview.

Week 2:

- Inspect logs/traces/reporting concepts.

Week 3:

- Grader/scorer docs.
- Sandbox docs at a high level.

Week 4:

- SWE-bench/Terminal-Bench task design examples.

Week 5:

- Tool-agent loop examples from mini-SWE-agent or SWE-agent.

Week 7:

- InstructGPT data/reward framing.
- DPO paper abstract/introduction only.
- TRL SFT docs if running SFT.

Week 8:

- Specification gaming examples.

Weeks 9-12:

- Read only what supports the chosen spike.

Rule:

```text
If reading does not change a task, grader, trace, reward, or report, stop reading and build.
```
