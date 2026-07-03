# Week 7 Plan

## Theme

Week 7 turns trusted eval artifacts into auditable trajectory and reward
records.

The manual's Week 7 goal is:

```text
turn eval traces into auditable post-training artifacts
```

The learning objective is:

```text
trajectory schemas, reward components, training eligibility, and leakage
boundaries
```

The goal this week is observability and data discipline, not training or reward
validity. We should be able to inspect an exported trajectory, explain where it
came from, explain why it is or is not training-eligible, and see each reward
component separately from any scalar score.

## Starting Point

Weeks 1-6 are closed.

Current trusted scoring path:

```text
task manifest + seed_workspace -> patch/control/agent policy -> orchestrator ->
public checks -> hidden scorer -> attempt artifacts -> replay/report
```

Core scoring invariant:

```text
task success = nested AttemptStatus PASS
public checks = diagnostic only
prompt-loop completion = not task success
```

Current eval-quality gate artifacts:

```text
configs/eval/eval_quality_gate_repo_patch_python_v0.yaml
experiments/runs/eval_quality_gate_repo_patch_python_v0
experiments/reports/eval_matrices/eval_quality_gate_repo_patch_python_v0.md
experiments/runs/eval_quality_controls_repo_patch_python_v0
experiments/runs/eval_quality_controls_repo_patch_python_v0/control_report.md
experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
docs/eval_quality_gate.md
docs/construct_validity_v0.md
```

Current construct claim:

```text
small localized Python repair under a strict JSON-action tool interface
```

Current limitations that matter for Week 7:

- only three dev tasks;
- no heldout-private tasks;
- raw provider responses are not persisted;
- cost is reported as `not_recorded`;
- public checks are intentionally weak on some dev tasks;
- reward components and trajectory export are not implemented yet.

## Design Priority

Preserve measurement boundaries:

- exported trajectories must not redefine task success;
- hidden validators must remain private;
- split and task-hash provenance must travel with exported records;
- environment failures must not become positive training examples;
- reward components must be inspectable separately from any aggregate reward;
- heldout-private and public-calibration records must never become
  training-eligible.

## Initial Design Question

Before implementing the exporter, decide:

```text
What is the smallest trustworthy TrajectoryRecord boundary for this repo:
one eval attempt, one model prompt-loop turn, one scorer attempt, or a
higher-level task/policy aggregate?
```

Do not implement the full exporter before answering this. The boundary controls
provenance, replayability, training eligibility, reward attribution, and failure
source separation.

## Planned Checkpoints

### Checkpoint 1: Trajectory Boundary

Purpose:

```text
Choose the unit of export and write down why that unit preserves provenance and
failure attribution.
```

Done when:

- the trajectory unit is chosen;
- rejected alternatives are named briefly;
- the decision explains how the record links back to trace, task, split, run,
  scorer, and config evidence;
- the main self-deception risk is written down.

### Checkpoint 2: Minimal Trajectory Schema

Purpose:

```text
Define the smallest schema that can represent trusted eval attempts without
leaking hidden information or hiding failure modes.
```

Likely artifact:

```text
src/agentenv/trajectories/schema.py
```

Done when:

- schema validation rejects records without provenance;
- schema validation rejects ambiguous training eligibility;
- hidden-validation details are represented only through allowed result
  references or summaries;
- tests cover at least one successful attempt, one hidden failure, and one
  prompt-loop failure.

### Checkpoint 3: Reward Components

Purpose:

```text
Represent reward evidence as components instead of immediately collapsing it
into one scalar.
```

Likely artifacts:

```text
src/agentenv/rewards/schema.py
src/agentenv/rewards/components.py
docs/reward_design_v0.md
```

Done when:

- hidden success and public-test success are separate;
- format/tool failures are separate from task failure;
- environment failure is explicit;
- reward-hack flags can be represented;
- reward version, config hash, code hash, and scorer version are recorded.

### Checkpoint 4: Export Path

Purpose:

```text
Export trajectories from an existing eval run into JSONL without rerunning
model inference or changing scoring.
```

Likely artifacts:

```text
scripts/export_trajectories.py
data/processed/trajectories/
```

Prefer schedule-neutral output names, for example:

```text
data/processed/trajectories/dev_eval_quality_gate_repo_patch_python_v0.jsonl
```

Done when:

- exported JSONL validates;
- every record links back to source artifacts;
- split rules are enforced in code;
- environment failures are marked non-training-eligible;
- heldout-private and public-calibration examples cannot be exported as
  training-eligible.

### Checkpoint 5: Manual Review

Purpose:

```text
Inspect trajectories before treating them as possible training data.
```

Likely artifact:

```text
data/processed/trajectories/dev_eval_quality_gate_repo_patch_python_v0_review_notes.jsonl
```

Done when:

- successful and failed traces are reviewed;
- review labels are machine-readable;
- shortcut, leakage, environment, and ambiguity issues can be recorded;
- manual overrides do not bypass split rules.

## Planned Commands

Start by refreshing trusted input evidence:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv tasks check-splits data/task_packs/repo_patch_python_v0/splits.lock.json
uv run agentenv tasks hash data/task_packs/repo_patch_python_v0 \
  --out experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
```

Use the existing eval-quality gate as the first export source:

```bash
uv run agentenv eval \
  --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml \
  --all-policies \
  --out experiments/runs/eval_quality_gate_repo_patch_python_v0 \
  --report-out experiments/reports/eval_matrices/eval_quality_gate_repo_patch_python_v0.md \
  --overwrite
```

Exporter command shape to converge on:

```bash
uv run python scripts/export_trajectories.py \
  experiments/runs/eval_quality_gate_repo_patch_python_v0 \
  --out data/processed/trajectories/dev_eval_quality_gate_repo_patch_python_v0.jsonl
```

Verification commands:

```bash
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

## Notes To Keep

Write implementation notes as decisions are made:

```text
notes/weekly/week_07/implementation_notes.md
notes/weekly/week_07/learnings.md
```

Important questions to answer in notes:

- What exactly is one trajectory record?
- What provenance is required before a record is trustworthy?
- Which records are analysis-only?
- Which records are training-eligible?
- What reward components are untrusted or easy to hack?
- What would make this export unsafe for SFT filtering later?

## Done Criteria

Week 7 is done when:

- trajectory records can be exported from a trusted eval run;
- every exported record validates against a schema;
- every exported record links to task, split, run, config, scorer, and reward
  version evidence;
- reward components are visible individually;
- training eligibility is enforced by code, not reviewer discipline;
- heldout-private and public-calibration examples cannot become
  training-eligible;
- manual review notes exist;
- `docs/reward_design_v0.md` states when the reward is untrusted;
- tests and static checks pass.

## Explicit Non-Claims

Do not claim:

- reward validity;
- model improvement;
- training readiness for all traces;
- heldout generalization;
- broad coding-agent capability;
- production-grade sandbox security.

This week proves that eval traces can become auditable post-training artifacts
with explicit provenance, reward components, and training eligibility rules.

## Main Risks

- Exporting too much hidden-scorer detail and weakening the privacy boundary.
- Treating public-test success as task success.
- Mixing prompt-loop failure, task failure, scorer failure, and environment
  failure into one vague label.
- Allowing split rules to live only in documentation.
- Creating a scalar reward before the components are inspectable.
- Optimizing for a training dataset before the exported records are auditable.

## Next Small Step

Answer the initial design question:

```text
What should one TrajectoryRecord represent in this repo?
```

After that decision, implement only the schema skeleton and its validation tests
before building the exporter.
