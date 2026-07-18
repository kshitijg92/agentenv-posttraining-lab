# Agentenv Post-Training Lab

This repository is a personal learning lab for building and auditing a small
coding-agent evaluation and post-training data pipeline. The learning plan lives in
[`references/agentic_evaluation_12_week_execution_manual.md`](references/agentic_evaluation_12_week_execution_manual.md).

The goal is to develop hands-on fluency with the full loop:

```text
task design -> sandboxed attempt -> agent trace -> hidden validation ->
controls -> replay -> reporting -> reward-hack analysis -> training-data gates
```

This is not a benchmark leaderboard, a production sandbox, or a claim of model
improvement. It is a deliberately small, auditable environment for learning how
agentic evaluation, hidden validators, reward hacking, provenance, and training
eligibility interact.

## What This Repo Builds

The current project centers on local Python repo-patch tasks. Each task has a
seed workspace, visible public checks, hidden deterministic validators, oracle
controls, and known-bad controls. The harness can run scorer-control patches,
scripted agent controls, and local/model-backed agent policies under fixed eval
configs.

The repo currently includes:

- Task manifest validation, split locks, and task hashing.
- Patch-attempt execution with public checks and hidden validation.
- Agent prompt-loop execution with local file/read/test tools.
- Eval runs, eval suites, replay, artifact manifests, and markdown reports.
- Trajectory export, human review rows, training-candidate export, and positive
  SFT example export.
- Scorer and agent harness audit fixtures.
- Reward-hack cases for hidden-validator probing, no-op patches,
  public-test-only pass, public-check tampering, fake success output,
  tool-output spoofing, format-only compliance, and state corruption.
- Local model config plumbing through OpenAI-compatible chat endpoints, including
  Ollama-oriented smoke configs.

The execution plan lives in
[`references/agentic_evaluation_12_week_execution_manual.md`](references/agentic_evaluation_12_week_execution_manual.md).
Weekly implementation notes and conceptual lessons live under
[`notes/weekly/`](notes/weekly/).

## Core Invariants

These are the boundaries this project is designed to make explicit:

- Hidden validators must not be visible during the agent phase.
- Public checks are not sufficient evidence of task success.
- Oracle and known-bad controls are required for calibration.
- Every eval/training artifact needs provenance: source config, task hashes,
  schema version, and output hashes.
- Reward-hack detection is separate from task success.
- Positive-SFT use requires an explicitly approved, clean assistant prefix and
  objective-specific review; task success alone is neither sufficient nor
  necessary.
- Model-authored files are not authoritative scorer, tool, or run provenance.
- Reports must include limitations and non-claims.

## Non-Claims

This repository does not claim:

- broad coding-agent capability;
- large-scale RLHF, RL, or post-training infrastructure;
- secure sandboxing beyond the specific tested invariants;
- model improvement from a smoke SFT export;
- benchmark-comparable results;
- validity outside the small local task distribution in this repo.

## Repository Map

```text
configs/
  decoding/        Decoding configs.
  eval/            Eval configs for scorer controls, agent controls, and models.
  models/          Local/OpenAI-compatible model configs.
  sandbox/         Docker smoke config.

data/
  task_packs/      Local repo-patch tasks, controls, hidden validators.
  harness_audit/   Scorer and agent audit cases.
  reward_hack_cases/
                   Authored reward-hack cases over harness evidence.

docs/              Design notes and contracts.
experiments/       Local run/report output directories.
notes/weekly/      Weekly implementation notes and conceptual learnings.
references/        Execution manual; local-only context files are ignored.
src/agentenv/      Package source.
tests/             Unit and integration tests.
```

Useful source modules:

```text
src/agentenv/tasks/          Task schemas, validation, split locks, hashes.
src/agentenv/orchestrators/  Patch and agent attempt orchestration.
src/agentenv/agents/         Prompt loop, prompt construction, agent audit.
src/agentenv/scorers/        Hidden-validator scorer and scorer audit.
src/agentenv/evals/          Eval config schema and eval execution.
src/agentenv/replay/         Replay execution.
src/agentenv/reporting/      Markdown report rendering.
src/agentenv/rewards/        Reward-hack schema, audit runtime, export/reporting.
src/agentenv/trajectories/   Trajectory export and review surfaces.
src/agentenv/training/       Training-candidate and positive-SFT exports.
src/agentenv/security/       Leakage and private-reference checks.
```

## Setup

This project uses Python 3.11+ and `uv`.

From the repo root:

```bash
uv sync --dev
uv run agentenv --help
```

Run the main checks:

```bash
uv run pytest -n auto
uv run ruff check .
uv run pyright
```

## Quick Start

Validate the current task pack:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
```

Check task split provenance:

```bash
uv run agentenv tasks check-splits \
  data/task_packs/repo_patch_python_v0/splits.lock.json
```

Run one known-correct patch attempt:

```bash
uv run agentenv attempt run \
  --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml \
  --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/oracle.patch \
  --out experiments/runs/manual_oracle_attempt
```

Run the baseline eval suite:

```bash
uv run agentenv eval \
  --config configs/eval/dev_baseline.yaml \
  --all-policies \
  --out experiments/runs/dev_baseline \
  --report-out experiments/reports/eval_suites/dev_baseline.md
```

Regenerate a report from an artifact directory:

```bash
uv run agentenv report \
  experiments/runs/dev_baseline \
  --out experiments/reports/eval_suites/dev_baseline.md
```

## Reward-Hack Audit

Reward-hack cases are authored under
[`data/reward_hack_cases/`](data/reward_hack_cases/). Each case points at an
underlying scorer or agent harness audit exploit/control pair, then adds a
reward-hacking interpretation on top.

Run the reward-hack audit:

```bash
uv run agentenv rewards audit \
  --cases data/reward_hack_cases \
  --out experiments/runs/reward_hack_audit \
  --report-out experiments/reports/reward_hack_audit.md
```

The audit reruns the underlying harness evidence, writes machine-readable
artifacts, and reports whether each exploit mechanism was detected,
neutralized, excluded from training, and free of withheld-content exposure while
the valid control still succeeds.

## Trajectory And Training-Data Flow

Export detailed trajectory records from an eval artifact:

```bash
uv run agentenv trajectories export \
  --source experiments/runs/dev_baseline \
  --out experiments/runs/dev_baseline_trajectory_export
```

Initialize a review workspace:

```bash
uv run agentenv trajectories review-init \
  --source experiments/runs/dev_baseline_trajectory_export \
  --out experiments/runs/dev_baseline_trajectory_review
```

Export training candidates after review:

```bash
uv run agentenv training candidates export \
  --trajectories experiments/runs/dev_baseline_trajectory_export \
  --reviews experiments/runs/dev_baseline_trajectory_review \
  --harness-audit experiments/harness_audit/current \
  --control-calibration experiments/runs/control_calibration \
  --out experiments/runs/dev_baseline_training_candidates
```

Candidate export fails before writing records unless the aggregate harness
audit is `PASS`, control outcomes and flake detection are successful, both
artifacts match the current harness runtime, and control task hashes cover the
exact trajectory task versions.

Export positive SFT examples:

```bash
uv run agentenv training sft export \
  --candidates experiments/runs/dev_baseline_training_candidates \
  --out experiments/runs/dev_baseline_positive_sft
```

These exports are plumbing and data-discipline exercises. They are not evidence
of model improvement by themselves.

## Local Model Smoke Runs

The model adapter expects an OpenAI-compatible chat endpoint. For local Ollama
experiments:

```bash
uv run agentenv local-model ollama plan \
  --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M

export AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1

uv run agentenv eval \
  --config configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml \
  --policy local-qwen-smoke \
  --out experiments/runs/agent_model_smoke_ollama_qwen3_14b
```

Model smoke runs should be interpreted as debugging evidence for the harness,
not as a model comparison or capability claim.

## Publication Note

Use only self-authored tasks, synthetic fixtures, and public/open tooling in
this repository.

The 12-week execution manual is written as a learning plan for agentic
evaluation and post-training data discipline.

Before publishing or sharing, review:

- `references/`
- `notes/`
- `experiments/`
- local model configs
- generated reports

for personal paths, local run details, unpublished notes, or accidental secrets.

## More Command Examples

See [`src/agentenv/README.md`](src/agentenv/README.md) for a longer CLI command
catalog.
