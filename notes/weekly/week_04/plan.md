# Week 4 Plan

## Theme

Week 4 is about moving from one calibrated toy task to a small, honest task
suite baseline.

Weeks 1-3 built and audited the harness:

```text
single task -> attempt runner -> eval runner -> replay -> reports
status taxonomy -> scorer audit -> repeated controls -> sandbox invariants
```

Week 4 should not jump to model agents, training, or system-level tasks. The
useful question now is:

```text
Can I author several small but real repo-patch tasks whose controls, hidden
validators, splits, and baseline report are trustworthy enough to build on?
```

## Task Difficulty Target

The new tasks should be more realistic than `toy_python_fix_001`, but not large
multi-file system tasks.

Target shape:

```text
one focused behavioral bug
one source file, sometimes two
one visible public test that is intentionally incomplete
hidden tests that encode the real contract
oracle patch
no-op bad patch
public-only bad patch
task card with shortcut and limitation analysis
```

Avoid for Week 4:

```text
large app refactors
multi-service integration
database-backed tasks
async orchestration tasks
broad architecture cleanup
tasks that need a real LLM agent to evaluate
```

The right human solve estimate is roughly 10-30 minutes for a strong engineer.
Three excellent controlled tasks are better than six weak or ambiguous tasks.

## What Was Missing After Week 3

Week 3 closed the measurement-trust layer, but several suite-level pieces are
still missing:

- There is only one practice task.
- There is no task-pack manifest.
- There is no split lock file.
- `agentenv tasks validate` validates one `task.yaml`, not a full task pack.
- There is no dev-baseline eval config.
- There is no compare report command for multiple baseline policies.
- The scoring contract is implicit in code and notes, not a dedicated doc.
- There is no task-authoring checklist.
- There is no design note explaining construct validity and weaknesses for the
  task family.
- No new dev tasks have been calibrated with oracle/no-op/public-only controls.

## Planned Artifacts

Task-pack metadata:

```text
data/task_packs/repo_patch_python_v0/manifest.yaml
data/task_packs/repo_patch_python_v0/splits.lock.json
```

New task directories:

```text
data/task_packs/repo_patch_python_v0/tasks/<task_slug>/
  task.yaml
  task_card.md
  workspace_seed/
  hidden_tests/
  controls/oracle.patch
  controls/bad_noop.patch
  controls/bad_public_only.patch
```

Default candidate task set:

```text
repair_jsonl_deduper
preserve_cli_error_codes
fix_cache_key_collision
```

Stretch candidates, only if the first three are solid:

```text
fix_date_parser_tz
repair_config_precedence
fix_path_normalization
```

Config and docs:

```text
configs/eval/dev_baseline.yaml
docs/scoring_contract.md
docs/task_authoring_checklist.md
docs/task_design_note_v0.md
notes/weekly/week_04/implementation_notes.md
notes/weekly/week_04/learnings.md
```

Generated evidence:

```text
experiments/runs/dev_controls/
experiments/runs/dev_noop/
experiments/runs/dev_public_only/
experiments/runs/dev_oracle/
experiments/replays/dev_oracle/
experiments/reports/dev_baseline.md
```

Possible code changes, only as needed:

```text
src/agentenv/tasks/validate.py
src/agentenv/cli.py
src/agentenv/reporting/
tests/
```

## Baseline Policies

Week 4 should run three scripted policies:

```text
noop
public-tests-only
oracle
```

Current naming in the codebase uses:

```text
bad.noop
bad.public_only
oracle
```

The dev-baseline eval config can expose user-facing policy names as:

```text
noop -> bad.noop
public-tests-only -> bad.public_only
oracle -> oracle
```

No real LLM agent integration is required this week.

## Execution Plan

1. Write the scoring contract and task-authoring checklist.
   This gives task authoring a concrete bar before adding new tasks.

2. Add task-pack metadata and split lock.
   Keep `toy_python_fix_001` in `practice`; put new tasks in `dev`.
   Leave `heldout_private` empty unless a truly untouched task can be preserved.

3. Decide the first new task's behavioral contract.
   Before writing files, answer:

   ```text
   What does the task measure, and what public-only shortcut should hidden tests catch?
   ```

4. Create one new dev task end to end.
   Build `workspace_seed`, public tests, hidden tests, controls, manifest, and
   task card. Do not batch-create all tasks before calibrating the first one.

5. Calibrate the first task.
   Run task validation, oracle attempt, no-op attempt, public-only attempt, and
   fix either the task or hidden tests until the expected statuses are stable.

6. Repeat for the second and third tasks.
   Keep each task small. If a task becomes ambiguous or too broad, replace it
   rather than salvaging it with an overcomplicated validator.

7. Add or extend task-pack validation if needed.
   Week 4's manual expects:

   ```bash
   uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
   ```

   The implementation should validate every `tasks/*/task.yaml`, required
   task-card files, controls, hidden validators, and split membership.

8. Create `configs/eval/dev_baseline.yaml`.
   Include the new dev tasks and the three scripted policies.

9. Run repeated controls.
   Expected behavior:

   ```text
   oracle: 3/3 PASS
   bad.noop: 3/3 HIDDEN_TEST_FAIL
   bad.public_only: 3/3 HIDDEN_TEST_FAIL
   ```

10. Run baseline evals and oracle replay.
    Generate separate runs for noop, public-tests-only, and oracle, then replay
    the oracle run.

11. Create the dev-baseline report.
    If `agentenv report compare` is not implemented yet, either add the smallest
    compare path or write the report from the generated artifacts without
    overstating automation.

12. Close Week 4 notes.
    Write implementation notes as decisions are made, then write learnings and
    limitations after the baseline report exists.

## Commands To Reach The Gate

Expected final commands:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/dev_controls
uv run agentenv eval --config configs/eval/dev_baseline.yaml --policy noop --out experiments/runs/dev_noop
uv run agentenv eval --config configs/eval/dev_baseline.yaml --policy public-tests-only --out experiments/runs/dev_public_only
uv run agentenv eval --config configs/eval/dev_baseline.yaml --policy oracle --out experiments/runs/dev_oracle
uv run agentenv replay experiments/runs/dev_oracle --out experiments/replays/dev_oracle
uv run agentenv report compare experiments/runs/dev_noop experiments/runs/dev_public_only experiments/runs/dev_oracle --out experiments/reports/dev_baseline.md
uv run pytest
uv run ruff check .
uv run pyright
```

If `report compare` is not implemented by the time the baseline is ready, record
that explicitly and generate `experiments/reports/dev_baseline.md` by the
smallest auditable route available.

## Report Must Include

The dev-baseline report must include:

```text
task count
task ids
policy table
pass rate by policy
oracle pass rate
bad-control pass rate
replay match rate
environment failure rate
grader/scorer failure rate
median runtime
hidden-validator version/hash or explicit current substitute
task exclusions
trace links
known shortcuts
what this environment measures
what it does not measure
```

It must describe the result as an environment baseline, not a model result and
not a post-training improvement.

## Done Criteria

- Minimum 3 excellent dev tasks exist.
- Every task has a task card, hidden validators, oracle control, no-op bad
  control, and public-only bad control.
- All task manifests validate.
- Split lock records `toy_python_fix_001` as `practice` and new tasks as `dev`.
- Oracle pass rate is 100%.
- Known-bad pass rate is 0%, or every exception has a written blocker.
- Oracle replay match rate is 100%.
- Dev-baseline report exists and separates public checks from hidden scoring.
- Written limitations are updated.
- `pytest`, `ruff`, and `pyright` pass, or any blocker is recorded with the exact
  command and error.

## Self-Deception Traps

- Do not treat more tasks as better if the controls are weak.
- Do not make tasks complex to feel more realistic.
- Do not use hidden tests to patch over an ambiguous instruction.
- Do not let public-test-only success look like task success.
- Do not count a bad control failure without checking why it failed.
- Do not create a heldout split if it cannot actually remain unseen.
- Do not call this a model baseline; these are scripted policy baselines.
- Do not proceed to Week 5 model-agent work if oracle controls are failing,
  hidden validators leak, or public-only controls pass hidden scoring.

## First Small Step

Write `docs/scoring_contract.md` and `docs/task_authoring_checklist.md`.

Before implementing the first new task, answer one design question:

```text
For the first new dev task, what behavior should the hidden validator prove that
the public test deliberately does not prove?
```
