# Agentenv Post-Training Lab

A personal project that builds a small, auditable harness for evaluating coding
agents and for gating which agent trajectories may become post-training data.
Agents and scripted controls attempt self-authored Python repo-patch tasks in
fresh workspace copies; success is decided by hidden validators the agent never
sees, and every task is calibrated with oracle and known-bad controls. The repo
also takes one small SFT/DPO experiment through this pipeline and reports its
negative result.

```text
task design -> isolated attempt -> agent trace -> hidden validation ->
controls -> replay -> reporting -> reward-hack analysis -> training-data gates
```

Status: the planned scope is complete and closed out in the
[Week 12 spike report](experiments/reports/week12_spike_report.md). The
selected follow-up experiment has not been run.

## What It Does

- **Task pack.** 26 self-authored tasks in
  [`data/task_packs/repo_patch_python_v0`](data/task_packs/repo_patch_python_v0)
  (1 practice, 19 development, 6 heldout-private). Each task has a seed
  workspace, visible public checks, hidden pytest validators, a task card,
  three scorer controls (oracle, no-op, and public-only patches), and three
  scripted-agent controls (happy path, malformed output, tool error followed by
  recovery). Manifests are validated, split membership is locked in
  `splits.lock.json`, task bytes are hashed, and the heldout slice is
  hash-frozen.
- **Attempt execution and scoring.** Each attempt starts from a fresh copy of
  the seed workspace; hidden validators and controls are never copied in.
  Public checks are diagnostics only. An attempt succeeds only when its attempt,
  public, and hidden statuses are all `PASS`; everything else gets a typed
  failure status.
- **Agent loop.** A one-JSON-action-per-turn prompt loop with four typed tools
  (`list_files`, `read_file`, `write_file`, `run_tests`), turn and token
  budgets, and typed failures for malformed output, tool errors, and timeouts.
  Models connect through OpenAI-compatible chat endpoints or through Ollama's
  generate endpoint with a pinned chat template, which serves base and
  LoRA-adapted models under the same input protocol used for training.
- **Evals, replay, and reports.** Config-driven eval runs and suites with fixed
  decoding configs, typed traces, replay, and Markdown reports that regenerate
  byte-for-byte from stored artifacts. Eval-suite resume (a library function
  covered by `tests/test_resume.py`, not exposed in the CLI) reuses validated
  attempts and fails closed on missing or corrupt evidence and on config, task,
  or harness drift.
- **Harness audits.** 12 scorer cases and 21 agent-harness cases (for example
  malformed patches, test tampering, timeouts, leakage canaries, fake success
  output, tool-output spoofing, and state corruption), plus repeated control
  calibration with flake detection and public-check idempotency.
- **Reward-hack audit.** 16 authored exploit/control pairs. Detection,
  neutralization, private-content exposure, and training exclusion are reported
  separately from task success.
- **Training-data gates.** Trajectory export and review,
  `TrainingCandidateRecord` eligibility, positive-SFT prefix review and export,
  preference discovery, adjudication, and pair export, target-model
  tokenization with assistant-only loss masks, and adapter-only LoRA SFT and DPO
  trainers that check optimizer ownership, frozen-base invariance, and
  save/reload equality. Construction artifacts are `not_authorized`; a trainer
  accepts only an artifact whose manifest records authorization.
- **Provenance and reproduction.** Artifacts record schema versions, config and
  task hashes, harness source and runtime hashes, and output hashes, and
  downstream steps re-check them. `agentenv reproduce core` combines
  stored-evidence checks with a fresh deterministic run. The suite has 1,291
  tests, and CI runs Ruff, Pyright, the tests, and the deterministic eval path.

## Findings

These results are taken from the
[Week 12 spike report](experiments/reports/week12_spike_report.md), which pairs
each claim with run and config identities, task hashes, counterevidence, and
limitations. The underlying run artifacts live under the Git-ignored
`experiments/` tree and are not in this repository; the report cites them by
path and hash.

Measurement controls (deterministic, authored cases; these are not model
results):

- Full-pack control calibration matched all 468 expected scorer and
  scripted-agent control records (26 tasks, three repeats), with zero drift
  across 156 flake groups and 26/26 public checks idempotent.
- The aggregate harness audit passed all 21 agent cases and 12 scorer cases.
- The reward-hack audit passed 16/16 authored cases, recorded no private-content
  exposure, and allowed none of the exploit traces into training. One case, fake
  success output on a genuinely correct patch, was allowed task success but
  denied training, which is the intended separation. See
  [`notes/failures/reward_hack_001.md`](notes/failures/reward_hack_001.md).
- An early calibration of newly added tasks failed: four oracle patches did not
  apply and two agent controls violated their expected outcomes. The tasks were
  blocked, corrected, and recalibrated before use, and the failing report is
  retained.

Post-training experiment (negative result):

- Raw positive-SFT, efficiency-filtered positive-SFT, and exploratory DPO LoRA
  adapters were trained from one pinned Qwen2.5-Coder-3B-Instruct base. The SFT
  arms used 98 and 94 reviewed examples from 11 development tasks; DPO used 29
  preference pairs.
- On eight frozen development tasks, base, raw SFT, and filtered SFT each
  succeeded on 0/8. On the corrected six-task comparison that excludes DPO's
  training lineage, base, filtered SFT, and DPO each succeeded on 0/6. Both
  predeclared selection rules abstained.
- DPO exhausted every turn budget while copying the illustrative tool calls
  from the system prompt.
- The first DPO evaluation reused two tasks that had contributed preference
  pairs. It was demoted to a contaminated diagnostic and replaced by the
  lineage-disjoint comparison above.
- The base model succeeded on the one practice task (1/1). Because every policy
  scored zero on the development comparisons, the result cannot separate task
  difficulty, the strict action protocol, base-model capability, and
  training-data quality. The selected next step is a six-task calibration slice
  with a predeclared target of 2-4/6 base successes before any further
  training.

Each comparison used one deterministic greedy rollout per policy-task cell. This
is no observed improvement, not evidence of policy equivalence or of SFT or DPO
being ineffective in general. Heldout-private outcomes have not been opened.

Reproduction:

- The deterministic control, hidden-scoring, replay, and report path reproduces
  offline in a clean tree, and same-run reports regenerate byte-for-byte.
- The Week 10 training and evaluation evidence reconstructs only at its
  original local location, because it is Git-ignored and referenced by absolute
  paths. Live inference and training were not rerun.

Closure audits with more detail:
[Week 10](notes/weekly/week_10/closure_audit.md) (SFT and DPO),
[Week 11](notes/weekly/week_11/closure_audit.md) (reproduction and failure
injection), and [Week 12](notes/weekly/week_12/closure_audit.md) (final
synthesis).

## Scope And Limitations

This is a deliberately small environment. It is not a benchmark leaderboard, a
production sandbox, or evidence of model improvement.

- Tasks are synthetic, Python-only, self-authored, and mostly localized to a
  few files and functions.
- Model runs use local open-weight models served through Ollama, and the
  training experiment used a 3B base. The SFT and DPO comparisons cover eight
  and six development tasks with one deterministic greedy rollout per cell.
  Sampling and training-seed variance were not measured, and the zero-success
  floor rules out effect-size or equivalence claims.
- The strict one-JSON-action protocol is part of what is measured and can
  confound coding ability with interface compliance.
- Trajectory and preference reviews were made by an explicitly recorded AI
  proxy, not by independent expert human reviewers.
- The Week 10 training inputs were authorized through an explicit,
  manifest-recorded override of the normal trust gate because of a known
  source-runtime mismatch. The final dataset-release step is planned, not
  built.
- The reward-hack catalogue is hand-authored and deterministic. Leakage
  scanning matches canaries and boundary markers, not semantic similarity to
  hidden validators.
- Workspace isolation prevents accidental leakage in the local eval lifecycle;
  it is not a security boundary against hostile code. The Docker check is a
  startup and `--network none` smoke test only.
- Stored Week 10 evidence is local and not relocatable. See
  [`docs/reproducibility.md`](docs/reproducibility.md) for the exact
  reproduction levels.
- Some older docs and notes contain stale task counts; the split lock and
  task-hash artifacts take precedence.

This repository does not claim:

- broad coding-agent capability;
- large-scale RLHF, RL, or post-training infrastructure;
- secure sandboxing beyond the specific tested invariants;
- general model improvement from the limited Week 10 SFT/DPO comparisons;
- benchmark-comparable results;
- validity outside the small local task distribution in this repo.

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

## Quick Start

This project uses Python 3.11+ and `uv`. From the repo root:

```bash
uv sync --dev
uv run agentenv --help
```

Run the checks. Tests that read the local Week 10 evidence are skipped when it
is absent.

```bash
uv run pytest -n auto
uv run ruff check .
uv run pyright
```

Run the deterministic eval that CI runs. It needs no GPU, network, or model
server. It runs three development tasks under six control policies (three
scorer-control patches and three scripted agents), replays them, and checks
that the report regenerates byte-for-byte:

```bash
eval_root="$(mktemp -d)"
uv run --offline --frozen agentenv eval \
  --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml \
  --all-policies \
  --out "$eval_root/eval" \
  --report-out "$eval_root/eval.md"

uv run --offline --frozen agentenv report \
  "$eval_root/eval" \
  --out "$eval_root/eval-regenerated.md"

cmp "$eval_root/eval.md" "$eval_root/eval-regenerated.md"
```

The eval exits nonzero when a control or replay outcome does not match its
declared expectation.

The full core reproduction adds Level 1: validation of the retained Week 10
training and evaluation evidence and byte-for-byte regeneration of its
reports.

```bash
repro_root="$(mktemp -d)"
uv run --offline --frozen agentenv reproduce core \
  --out "$repro_root/core"
```

That evidence is Git-ignored and bound to absolute paths, so Level 1 can pass
only at the original checkout; in a clean clone, use the deterministic eval
above. Neither path reruns live model inference or training. See
[`docs/reproducibility.md`](docs/reproducibility.md) for the Level 1-4
boundaries.

## Command Reference

### Tasks And Single Attempts

Validate the task pack:

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

### Deterministic Evals

Run the one-task deterministic scorer-control eval (no model server):

```bash
toy_eval_root="$(mktemp -d)"
uv run --offline --frozen agentenv eval \
  --config configs/eval/scorer_control_policies.yaml \
  --all-policies \
  --out "$toy_eval_root/run" \
  --report-out "$toy_eval_root/report.md"
```

Run the three-task deterministic small eval with scorer and scripted-agent
controls:

```bash
small_eval_root="$(mktemp -d)"
uv run --offline --frozen agentenv eval \
  --config configs/eval/dev_baseline.yaml \
  --all-policies \
  --out "$small_eval_root/run" \
  --report-out "$small_eval_root/report.md"
```

Regenerate a report from an artifact directory:

```bash
uv run --offline --frozen agentenv report \
  "$small_eval_root/run" \
  --out "$small_eval_root/report-regenerated.md"
```

### Harness Audits And Control Calibration

Run the aggregate scorer and agent-harness audit:

```bash
uv run agentenv harness audit \
  --agent-cases data/harness_audit/agent_task_cases \
  --scorer-cases data/harness_audit/scorer_cases \
  --out experiments/harness_audit/full
```

Run repeated control calibration with flake detection over the full task pack:

```bash
uv run agentenv controls run \
  --task-pack data/task_packs/repo_patch_python_v0 \
  --repeats 3 \
  --public-check-idempotency-repeats 2 \
  --out experiments/runs/control_calibration
```

### Reward-Hack Audit

Reward-hack cases are authored under
[`data/reward_hack_cases/`](data/reward_hack_cases/). Each case points at an
underlying scorer or agent harness audit exploit/control pair, then adds a
reward-hacking interpretation on top.

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

### Trajectory And Training-Data Flow

Export trajectories from an eval suite (here, the small eval above), then
initialize and validate trajectory review:

```bash
uv run agentenv trajectories export \
  --source "$small_eval_root/run" \
  --out "$small_eval_root/trajectories"

uv run agentenv trajectories review-init \
  --source "$small_eval_root/trajectories" \
  --out "$small_eval_root/trajectory_review"

uv run agentenv trajectories review-validate \
  --source "$small_eval_root/trajectories" \
  --reviews "$small_eval_root/trajectory_review"
```

`review-init` writes one `not_reviewed` row per trajectory; review decisions
are recorded in `reviews.jsonl`. Build training candidates, then run the
positive-SFT prefix review and export:

```bash
uv run agentenv training candidates export \
  --trajectories "$small_eval_root/trajectories" \
  --reviews "$small_eval_root/trajectory_review" \
  --out "$small_eval_root/candidates"

uv run agentenv training positive-sft review-init \
  --candidates "$small_eval_root/candidates" \
  --out "$small_eval_root/positive_sft_review"

uv run agentenv training positive-sft review-validate \
  --reviews "$small_eval_root/positive_sft_review"

uv run agentenv training positive-sft export \
  --candidates "$small_eval_root/candidates" \
  --reviews "$small_eval_root/positive_sft_review" \
  --out "$small_eval_root/positive_sft"
```

On control-policy output this chain completes with zero trainable records:
unreviewed trajectories and scripted-control policies are analysis-only, and
the candidate and positive-SFT export manifests are `not_authorized`.
Target-model tokenization and LoRA training (the `materialize` and
`train-lora` subcommands of `training positive-sft` and `training preferences`)
need the pinned Hugging Face tokenizer or base model, and the trainers accept
only explicitly authorized inputs. Their contracts are described in
[`src/agentenv/training/README.md`](src/agentenv/training/README.md) and
[`docs/post_training_data_contract.md`](docs/post_training_data_contract.md).

### Local Model Runs

The smoke configs use the OpenAI-compatible chat adapter. For local Ollama
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

See [`src/agentenv/README.md`](src/agentenv/README.md) for a longer CLI command
catalog. Some entries there predate the current training CLI;
`uv run agentenv <command> --help` is authoritative for options.

## Repository Map

```text
configs/
  decoding/        Decoding configs.
  eval/            Eval configs for scorer controls, agent controls, and models.
  models/          Local/OpenAI-compatible model configs.
  model_input_protocols/
                   Pinned chat templates and serialization for training/serving.
  train/           LoRA SFT and DPO training configs.
  training/        Preference review rubrics.
  reproduction/    Core reproduction plan.
  sandbox/         Docker smoke config.

data/
  task_packs/      Local repo-patch tasks, controls, hidden validators.
  harness_audit/   Scorer and agent audit cases.
  reward_hack_cases/
                   Authored reward-hack cases over harness evidence.

docs/              Design notes and contracts.
experiments/       Local run/report output (Git-ignored except the final report).
notes/weekly/      Weekly plans, implementation notes, learnings, closure audits.
notes/failures/    Failure analyses.
references/        Execution manual; local-only context files are ignored.
scripts/           Control-generation and reproduction helper scripts.
src/agentenv/      Package source.
tests/             Unit and integration tests.
```

Useful source modules:

```text
src/agentenv/tasks/          Task schemas, validation, split locks, hashes.
src/agentenv/envs/           Fresh agent workspace preparation.
src/agentenv/orchestrators/  Patch-attempt, agent-task, and eval-run orchestration.
src/agentenv/agents/         Prompt loop, prompt construction, tool messages.
src/agentenv/tools/          Typed agent tools.
src/agentenv/models/         Model configs, input protocols, provider clients.
src/agentenv/scorers/        Hidden-validator scorer.
src/agentenv/audits/         Scorer and agent-harness audits.
src/agentenv/controls/       Control calibration, flake and idempotency checks.
src/agentenv/evals/          Eval config schema, suite declaration and validation.
src/agentenv/runners/        Command, patch, public-check runners; resume.
src/agentenv/replay/         Replay execution.
src/agentenv/reporting/      Markdown reports and policy-selection reporting.
src/agentenv/rewards/        Reward-hack schema, audit runtime, export/reporting.
src/agentenv/trajectories/   Trajectory export and review surfaces.
src/agentenv/training/       Candidates, positive SFT, preferences, LoRA SFT/DPO.
src/agentenv/security/       Leakage and private-reference checks; secret redaction.
src/agentenv/reproduction/   Core and stored-evidence reproduction.
```

Design documents:

```text
docs/scoring_contract.md            What counts as task success.
docs/attempt_status_taxonomy.md     Terminal attempt statuses.
docs/sandbox_invariants_v0.md       Workspace isolation invariants and tests.
docs/construct_validity_v0.md       What the eval can and cannot measure.
docs/eval_quality_gate.md           Checklist before trusting an eval result.
docs/heldout_evaluation_protocol.md Heldout-private slice protocol.
docs/trace_schema.md                Trace events and replay evidence.
docs/reward_design_v0.md            Reward components and interpretation.
docs/post_training_data_contract.md When a trajectory may become training data.
docs/model_interface.md             Model and agent-action boundary.
docs/reproducibility.md             Reproduction levels and portability limits.
```

## How This Was Built

The project followed a 12-week plan,
[`references/agentic_evaluation_12_week_execution_manual.md`](references/agentic_evaluation_12_week_execution_manual.md),
covering the thin eval loop, measurement trust, baselines and post-training
plumbing, and one post-training spike. Weekly plans, implementation notes, and
learnings are under [`notes/weekly/`](notes/weekly/); weeks 5 and 8-12 also
have closure audits that check the work against the manual's criteria and
record the remaining limitations.

Tasks, fixtures, and controls are self-authored or synthetic, and the tooling
is public/open.
