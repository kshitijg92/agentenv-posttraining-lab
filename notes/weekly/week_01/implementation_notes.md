# Week 1 Implementation Notes

## Why I Am Writing This

I am not just trying to create files. I am trying to understand the shape of a trustworthy eval loop.

The core loop I am building toward is:

```text
task design -> agent-visible workspace -> submitted patch -> orchestrator -> scorer -> trace -> failure analysis
```

For Week 1, the smallest useful version of that loop is one local Python repo-patch task with public tests, hidden tests, oracle and bad controls, and enough output to debug what happened.

## How I Am Using Other Eval Frameworks

I initially got confused because Inspect AI, Terminal-Bench, METR's task standard, and SWE-bench look like different standards.

The useful framing is that I am not choosing one of them. I am extracting one or two design lessons from each and implementing my own tiny local standard.

### Inspect AI

The main lesson I am taking from Inspect is separation of concepts:

```text
task -> solver/agent -> scorer
```

My local mapping is:

```text
task.yaml + seed_workspace -> submitted patch -> public checks and hidden pytest scorer
```

This means I should avoid thinking of the eval as one undifferentiated script. Even if the implementation is small, I want separate concepts for:

- loading the task manifest,
- preparing the workspace,
- applying the submission,
- running public checks,
- running hidden validators,
- writing result artifacts.

### Terminal-Bench / Harbor

The main lesson I am taking from Terminal-Bench-style tasks is the directory shape of an agent task:

```text
instruction
environment
tests/verifier
solution/oracle
metadata and limits
```

My local mapping is:

```text
task_card.md        human task explanation
task.yaml           machine-readable eval manifest
seed_workspace/     agent-visible starting repo
hidden_tests/       private scorer tests
controls/           oracle and known-bad patches
```

The concrete gotcha I learned here is that `hidden_tests/` must not be inside `seed_workspace/`. If hidden tests are present during the agent workspace phase, I have leaked the private verifier.

### METR Task Standard

The main lesson I am taking from METR's task-standard style is the lifecycle boundary:

```text
agent-visible task information is not the same as private scoring information
```

My local mapping is:

```text
agent-visible:
  instruction
  seed_workspace/
  public tests

private eval-side:
  hidden_tests/
  controls/
  scoring contract
  leakage canary
```

I am also using controls to test whether the task and eval harness are calibrated. This is not a claim that controls come only from METR; it is a general eval practice that fits the same mindset: before trusting scores, I need evidence that the measurement setup accepts known-good behavior and rejects known-bad behavior.

### SWE-bench

The main lesson I am taking from SWE-bench is the patch-evaluation contract:

```text
task instance + submitted patch -> apply patch -> run tests -> record result
```

My local mapping is:

```text
task.yaml id             toy_python_fix_001
submission              controls/*.patch for now
patch application        agentenv attempt run step
tests                   public pytest, then hidden pytest
result artifacts         attempt.json, trace.jsonl, stdout, stderr, final.diff
```

This makes the task concrete: the object being scored is not an essay or a chat response, but a patch applied to a clean workspace.

## Decisions Made So Far

### I Am Starting With A Task Card

I wrote `task_card.md` before implementing the orchestrator/scorer path.

This forced me to answer:

- what behavior the task is supposed to test,
- what the agent sees,
- what stays hidden,
- what the controls should prove,
- what the task does not measure.

This was useful because vague task design would later become vague scoring behavior.

### The Task Is About `normalize_ratio`

The task asks for:

```python
normalize_ratio(numerator, denominator)
```

The intended behavior is:

- accept `int` and `float` inputs,
- return `numerator / denominator` as a float,
- raise `ValueError` when `denominator == 0`,
- preserve normal Python division sign behavior,
- preserve useful precision for non-integer ratios.

I intentionally excluded strings, `None`, booleans, `Decimal`, `Fraction`, `NaN`, infinity, and custom numeric types. Those would turn a Week 1 eval-loop task into an API-design task.

### The Seed Bug Is Floor Division

The broken implementation is:

```python
def normalize_ratio(numerator: int | float, denominator: int | float) -> float:
    return numerator // denominator
```

This bug is useful because:

- it passes the shallow public case `normalize_ratio(6, 3) == 2.0`,
- it fails `normalize_ratio(1, 2) == 0.5`,
- it raises `ZeroDivisionError` instead of the required `ValueError`,
- it creates a real gap between public checks and hidden validation.

### Public Tests Are Intentionally Weak

The public test only checks a simple happy path.

This is deliberate. The public test is a smoke test, not the scoring contract.

The learning point is:

```text
public pass does not mean task pass
```

### Hidden Tests Define The Real Behavioral Contract

The hidden tests check:

- zero denominator raises `ValueError`,
- non-integer ratios preserve precision,
- negative numerator behavior,
- negative denominator behavior,
- double-negative behavior,
- float inputs,
- large integer ratios.

The important implementation boundary is:

```text
hidden_tests/ is outside seed_workspace/
```

The hidden scorer should only run hidden tests after a patch has already been applied.

### Controls Test The Eval, Not The Agent

I now understand controls as tests of the measurement system.

The current controls are:

```text
oracle.patch
  expected: public pass, hidden pass

bad_noop.patch
  expected: public pass, hidden fail

bad_public_only.patch
  expected: public pass, hidden fail
```

I changed the manifest schema so bad controls are named by role:

```yaml
controls:
  oracle: controls/scorer_control_patches/oracle.patch
  bad:
    noop: controls/scorer_control_patches/bad_noop.patch
    public_only: controls/scorer_control_patches/bad_public_only.patch
```

This is better than an anonymous list because `noop` and `public_only` test different failure modes. The schema should require both for this task family.

The oracle proves the eval harness can accept a correct solution.

The bad controls prove the eval harness can reject incorrect or incomplete solutions.

The public-only bad patch currently uses a plausible semantic error: it computes `abs(numerator / denominator)`. This passes the visible positive-ratio test but fails hidden sign tests.

### `task.yaml` Is Framework Config, Not Agent Input

I created `task.yaml` as the machine-readable manifest for the eval framework.

It includes private eval-side fields:

- hidden validator paths,
- control patch paths,
- scoring contract,
- leakage canary,
- replay capture requirements.

Therefore, the full `task.yaml` should not be handed to the agent. The agent can receive a derived view, such as:

- instruction,
- seed workspace,
- allowed tools,
- public check command if desired.

The private fields stay inside the eval framework.

### The Leakage Canary Is A Tripwire

The leakage canary is a private string:

```text
CANARY_TOY_PY_FIX_001_PRIVATE
```

If this string appears in an agent prompt, trace, stdout, patch, or final answer, then private task metadata probably leaked.

I do not need a sophisticated leakage system in Week 1. I just need to make the privacy boundary explicit.

### Replay Means Auditability First

For Week 1, replay does not need to mean a perfect replay engine.

It means I should capture enough evidence to reconstruct an attempt:

- submitted patch,
- commands run,
- stdout,
- stderr,
- final diff,
- attempt result.

This is why the planned run outputs include:

```text
attempt.json
trace.jsonl
final.diff
stdout.txt
stderr.txt
run_manifest.json
```

### Orchestrator vs Grader

I clarified an important naming distinction.

The component that prepares a clean workspace, applies a submitted patch, runs public checks, invokes hidden scoring, and writes traces is an orchestrator or eval harness.

The scorer should be narrower:

```text
given a patched workspace, run hidden validators and produce a score/status
```

The orchestrator coordinates the lifecycle:

```text
load manifest
prepare agent-visible workspace
apply submitted patch
run public checks
invoke hidden scorer
write trace and attempt artifacts
```

This matches the Inspect-style separation better: task, solver/submission, scorer, plus a runtime that coordinates them.

### Local Environment Layer

I added `src/agentenv/envs/local_repo_env.py` as the first environment layer.

This layer prepares the agent-visible workspace. It does not apply patches, run tests, score attempts, or write traces.

The current helper:

```text
prepare_agent_workspace(manifest, manifest_path)
```

does three important things:

- validates the manifest paths,
- copies only `seed_workspace/` into a fresh workspace,
- checks that hidden validator files are not present in that copied workspace.

This keeps the hidden-test leakage invariant executable:

```text
agent-visible workspace = seed_workspace only
```

The local environment is not a secure sandbox. It is just a disciplined local workspace-preparation layer. A future Docker sandbox would belong under `sandbox/`, not replace the conceptual role of `envs/`.

### Patch Runner Layer

I added `src/agentenv/runners/patch_runner.py` as the first submission-runner layer.

This layer applies a submitted patch to an already-prepared workspace. It does not create the workspace, run tests, score attempts, or write traces.

The current helper:

```text
apply_patch_file(workspace, patch_path, timeout_seconds)
```

uses the lower-level command runner to call `git apply` for normal unified diffs.

I explicitly treat an empty patch as a successful no-op. This makes `bad_noop.patch` a clean negative control: it represents doing nothing, and the later scorer should reject it based on behavior rather than patch-application mechanics.

This gives the current execution chain:

```text
load manifest
validate manifest
prepare agent-visible workspace
apply submitted patch
```

### Public Check Runner

I refactored runner architecture so `src/agentenv/runners/command_runner.py` is the low-level command execution primitive.

It owns:

```text
CommandResult
run_process(...)
run_shell(...)
```

Then `src/agentenv/runners/public_check_runner.py` handles manifest public checks:

```text
run_public_checks(workspace, manifest.public_checks, timeout)
```

This keeps task-schema-specific public check logic out of the generic command runner.

I tested that all three controls pass public checks:

```text
oracle.patch
bad_noop.patch
bad_public_only.patch
```

This is intentional. It proves the public test is only a visible sanity check and cannot be treated as the final scoring contract.

The scorer still needs hidden validation to distinguish correct and incorrect behavior.

### Hidden Scorer Layer

I added `src/agentenv/scorers/pytest_hidden.py` as the first hidden scorer.

This layer receives an already-patched workspace. It does not prepare the environment, apply patches, run public checks, or orchestrate a full attempt.

For Week 1, the scorer runs private pytest tests from the task pack against the already-patched workspace:

```text
uv run pytest -c <workspace>/pyproject.toml --rootdir <workspace> <task>/hidden_tests
```

This preserves the important phase boundary without mutating the submitted workspace:

```text
hidden tests absent during patch/submission phase
hidden tests read only by the scorer during scoring phase
```

I hit one useful architecture bug here. When hidden tests live outside the workspace, pytest may discover the lab repo's config instead of the submitted workspace config. The fix is to pass the workspace config explicitly with `-c <workspace>/pyproject.toml` and set `--rootdir <workspace>`.

The hidden scorer now distinguishes the controls:

```text
oracle.patch
  hidden scorer passes

bad_noop.patch
  hidden scorer fails

bad_public_only.patch
  hidden scorer fails
```

This is the first point where the task demonstrates that public checks alone are insufficient.

### Attempt Result Contract

I added `src/agentenv/orchestrators/attempt.py` with the first attempt result schema.

This defines the output contract before implementing the full orchestrator.

The main model is:

```text
AttemptResult
```

It records:

- run id,
- task id,
- attempt id,
- submission path,
- final status,
- public status,
- hidden status,
- error class,
- timing,
- final diff hash,
- orchestrator version.

I am intentionally using statuses such as `ORCHESTRATOR_ERROR` and `SCORER_ERROR` so lifecycle failures and scoring failures do not get collapsed into one ambiguous bucket.

I renamed the model from `PatchAttemptResult` to `AttemptResult` because the result shape is generic: task id, attempt id, statuses, timing, and error class. The function `run_patch_attempt` remains patch-specific because this Week 1 domain still evaluates submitted patch files.

I later added `AttemptRun` as the in-memory object returned by the orchestrator:

```text
AttemptRun
  result: AttemptResult
  command_results: list[CommandResult]
```

This separates the final summary from the evidence produced along the way. `AttemptResult` is what goes into `attempt.json`; `AttemptRun.command_results` will be used for stdout/stderr and traces.

### First Attempt Orchestrator

I added the first version of:

```text
run_patch_attempt(task_manifest_path, submission_path, workspace_parent=None)
```

This composes the layers built so far:

```text
load manifest
prepare agent-visible workspace
apply submitted patch
run public checks
run hidden scorer
return AttemptRun
```

This version returns a structured result but does not yet write `attempt.json`, `trace.jsonl`, stdout/stderr files, or final diffs.

The control behavior now works through the orchestrator:

```text
oracle.patch
  status: PASS

bad_noop.patch
  status: HIDDEN_TEST_FAIL
  public_status: PASS
  hidden_status: FAIL

bad_public_only.patch
  status: HIDDEN_TEST_FAIL
  public_status: PASS
  hidden_status: FAIL
```

I hit one useful implementation bug: patch application failed when the orchestrator passed a relative submission path into `git apply` while running from inside the temporary workspace. The fix was to resolve `task_manifest_path` and `submission_path` before orchestration. This is a good reminder that an orchestrator has to be explicit about path bases.

I added `task_manifest_path` to both `attempt.json` and the `attempt_started` trace event. `task_id` alone is not enough for traceability because the same id could appear in multiple branches, copies, or edited manifests.

### Attempt JSON Persistence

I added `src/agentenv/orchestrators/attempt_io.py` with:

```text
write_attempt_result(result, out_dir)
```

This writes:

```text
attempt.json
```

I added this before full trace writing because `attempt.json` is the smallest durable artifact that records the final attempt status.

The current split is:

```text
run_patch_attempt(...)
  executes the attempt and returns AttemptRun

write_attempt_result(...)
  persists AttemptResult to disk
```

This keeps orchestration separate from persistence.

I then extended the artifact writer to write:

```text
run_manifest.json
attempt.json
stdout.txt
stderr.txt
trace.jsonl
final.diff
```

`stdout.txt` and `stderr.txt` are joined from `AttemptRun.command_results`, so the run directory contains both the final summary and raw command output evidence.

`trace.jsonl` is a structured event log. The first version records:

- `attempt_started`,
- one `command_finished` event per command,
- `attempt_finished`.

The command events include:

- phase,
- name,
- command,
- return code,
- stdout/stderr byte counts,
- references to `stdout.txt` and `stderr.txt`.

The current phases are:

```text
patch_apply
public_check
hidden_score
```

`final.diff` records the diff between the original `seed_workspace/` and the patched workspace. I capture it immediately after patch application, before public checks and hidden scoring. This avoids including pytest cache files or any scorer-side files in the submitted-code diff.

The current expected control behavior is:

```text
oracle.patch
  final.diff is non-empty

bad_noop.patch
  final.diff is empty

bad_public_only.patch
  final.diff is non-empty
```

### Attempt Run CLI

I added:

```text
agentenv attempt run --task-manifest <task.yaml> --submission <patch> --out <run-dir>
```

The command uses an explicit output directory. For Week 1, I am using:

```text
experiments/runs/week01_oracle/
experiments/runs/week01_bad_noop/
experiments/runs/week01_bad_public_only/
```

I chose explicit run names instead of automatically naming by `task_id` because the same task can have many attempts: oracle, no-op, public-only, future model attempts, and reruns.

The CLI currently writes:

```text
run_manifest.json
attempt.json
stdout.txt
stderr.txt
trace.jsonl
final.diff
```

I then added `final_diff_hash` using `xxhash`.

The hash is stored in `attempt.json` as:

```text
xxh64:<hex>
```

It is computed from the exact `final.diff` content. This gives the summary artifact a compact identifier for the submitted code state that was scored.

Even the no-op control has a hash: it is the hash of the empty diff. That is useful because it makes "no change" an explicit, reproducible final diff state rather than a missing value.

I also added `final_diff_ref` and `final_diff_hash` to the `attempt_finished` trace event. The trace now points from the structured timeline to the exact diff artifact and its compact identifier.

`run_manifest.json` is the index for the run artifact bundle. It records the artifact schema version, orchestrator version, run id, attempt id, task id, task manifest path, submission path, status, and relative artifact filenames.

This is different from `attempt.json`: `attempt.json` summarizes the attempt result, while `run_manifest.json` describes the files that make up the run directory.

This now matches the Week 1 target artifact set for a single attempt run.

I also hit a useful artifact hygiene issue: a full `pytest` run initially collected tests under `data/` and created `__pycache__/` files inside the toy task directories. That polluted final diff capture and caused binary `.pyc` decode errors. I fixed this in two ways:

- configured root pytest collection to use only `tests/`,
- taught `diff_runner` to ignore generated cache/build artifacts such as `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.git`, and `.pyc` files.

This is a concrete example of why eval artifacts need provenance and cleanup discipline: local tooling can accidentally mutate task directories.

## Current Mental Model

The task now has four different audiences:

```text
task_card.md
  for me, the human task author

task.yaml
  for the eval framework

seed_workspace/
  for the agent or patch author

hidden_tests/ and controls/
  for the scorer and task audit
```

Keeping these audiences separate is the main lesson of Week 1 so far.

## Manifest Validation

I implemented manifest validation in two layers:

```text
schema.py
  validates the shape and allowed values of task.yaml

validate.py
  loads task.yaml and validates filesystem/path integrity
```

This separation is useful because schema errors and task-integrity errors are different failure modes.

Schema validation catches mistakes like:

- invalid split,
- invalid domain,
- empty canary,
- missing required manifest fields,
- unexpected extra fields.

Path validation catches mistakes like:

- missing `seed_workspace`,
- missing hidden validator path,
- hidden tests accidentally placed inside `seed_workspace`,
- missing oracle or bad control patches,
- manifest paths that are absolute or escape the task directory.

I also simplified the manifest-load test again. The test should prove the YAML can load into the schema, not duplicate every field in `task.yaml`.

### Thin CLI Wrapper

I added a small CLI wrapper so I can run manifest validation as:

```text
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml
```

The CLI is intentionally thin. It does not contain validation logic; it calls the existing manifest loading and path-validation functions.

This makes validation usable as an operator command before the full attempt orchestrator exists.

## Next Learning Step

The next step is not to add more tasks.

The first version of `agentenv attempt run` now copies the seed workspace, applies one submitted patch, runs public checks, runs hidden validators, and writes the attempt artifact bundle.
