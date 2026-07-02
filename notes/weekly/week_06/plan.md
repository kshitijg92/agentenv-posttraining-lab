# Week 6 Plan

## Theme

Week 6 hardens the small repo-patch task suite enough to support trajectory,
reward, and data-filtering work.

The manual's Week 6 goal is:

```text
harden the small task suite enough to support trajectory/reward work
```

The learning objective is:

```text
flake detection, false positives, construct validity, and split enforcement
```

Before starting that gate, we will close one Week 5 carryover: run the local
DeepSeek R1 Distill Qwen path to completion through the existing agent-model
eval harness.

## Starting Point

Weeks 1-5 are closed.

Trusted scoring path:

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

Current dev task pack:

```text
data/task_packs/repo_patch_python_v0
```

Current dev tasks:

```text
repair_jsonl_deduper
preserve_cli_error_codes
repair_config_precedence
```

Current real-model baseline:

```text
configs/eval/agent_model_dev_ollama_qwen3_14b.yaml
experiments/runs/agent_model_dev_ollama_qwen3_14b
experiments/reports/eval_matrices/agent_model_dev_ollama_qwen3_14b.md
```

That Qwen baseline is an integration baseline, not a broad model benchmark.

## Checkpoint 0: Finish DeepSeek Local Model Wiring

Purpose:

```text
Prove the DeepSeek local model can run through the same typed-tool,
candidate-patch, hidden-scorer, and report path as the prior Qwen run.
```

Existing configs:

```text
configs/models/ollama_deepseek_r1_distill_qwen_14b_q4_k_m.yaml
configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml
configs/eval/agent_model_dev_ollama_deepseek_r1_distill_qwen_14b.yaml
configs/decoding/greedy_1024.yaml
```

Planned commands:

```bash
uv run agentenv local-model ollama setup \
  --model-id hf.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF:Q4_K_M \
  --system-suffix ""

AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1 uv run agentenv eval \
  --config configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml \
  --policy local-deepseek-r1-distill-qwen-smoke \
  --out experiments/runs/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b \
  --report-out experiments/reports/eval_matrices/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.md \
  --overwrite

AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1 uv run agentenv eval \
  --config configs/eval/agent_model_dev_ollama_deepseek_r1_distill_qwen_14b.yaml \
  --all-policies \
  --out experiments/runs/agent_model_dev_ollama_deepseek_r1_distill_qwen_14b \
  --report-out experiments/reports/eval_matrices/agent_model_dev_ollama_deepseek_r1_distill_qwen_14b.md \
  --overwrite
```

Evidence to record:

- whether setup/probe/smoke reached the local OpenAI-compatible endpoint;
- whether the smoke task completes through the prompt loop;
- whether the dev matrix runs all control and model policies;
- candidate patch presence, empty-patch count, max-turn count, invalid tool-call
  count, public pass count, hidden pass count;
- trace validation results;
- whether decoding or prompt behavior blocks a serious DeepSeek baseline.

Non-claim:

```text
DeepSeek pass rate on three dev tasks is not a broad model-quality result.
It is only a local integration and diagnostic baseline.
```

Checkpoint decision after probe:

```text
DeepSeek R1 Distill Qwen is not supported yet under the current strict JSON
action protocol.
```

Reason:

- the local Ollama endpoint and model are reachable;
- the model can emit a valid tool call on the first turn;
- after a tool result, the model emits reasoning/prose artifacts before the next
  JSON action;
- `/no_think`, OpenAI-compatible `think: false`, and native Ollama
  `think: false` did not disable the reasoning channel for this model;
- weakening the parser or global prompt would change the harness contract.

Decision:

```text
Do not add DeepSeek-specific protocol repair in Week 6.
Move on to the eval-quality gate and revisit thinking-model adapters later as a
deliberate model-interface/protocol design task.
```

## Week 6 Gate Work

After DeepSeek is closed or explicitly blocked, implement the manual's Week 6
eval-quality gate.

Required artifact concepts from the manual:

```text
task split enforcement
task input hashing
repeat-control flake detection
eval-quality gate config
eval-quality gate documentation
construct-validity documentation
weekly eval-quality report
```

Implemented artifact mapping:

```text
src/agentenv/tasks/splits.py
src/agentenv/tasks/hashing.py
src/agentenv/controls/controls_run.py
src/agentenv/controls/reporting.py
configs/eval/eval_quality_gate_repo_patch_python_v0.yaml
docs/eval_quality_gate.md
docs/construct_validity_v0.md
experiments/reports/week06_eval_quality.md
```

Notes:

- The flake detector lives with control-run execution/reporting instead of a
  separate `graders/flakes.py` module, because it compares complete repeated
  control artifacts, including scorer and agent groups.
- The eval config and run paths are schedule-neutral because repo code and
  config should not know about the learning-week calendar.
- The weekly report keeps `week06` in the filename because it is a learning
  artifact, not a reusable repo contract.

## Required Checks

Implement or verify:

- exact normalized text hash for instructions and visible tests;
- task asset hash;
- split membership check;
- hidden validator path check;
- canary uniqueness check;
- flake detector for repeated oracle runs;
- false-positive review for bad controls.

Normalized text contract:

```text
lowercase
Unicode NFKC
collapse whitespace
strip volatile temp paths
hash with xxhash64
```

## Planned Commands

The manual listed placeholder command names with `week06_*` paths. Use the
schedule-neutral command shape below for the current repo:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
uv run agentenv tasks check-splits data/task_packs/repo_patch_python_v0/splits.lock.json
uv run agentenv tasks hash data/task_packs/repo_patch_python_v0 --out experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
uv run agentenv controls run --task-pack data/task_packs/repo_patch_python_v0 --repeats 3 --out experiments/runs/eval_quality_controls_repo_patch_python_v0
uv run agentenv eval --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml --all-policies --out experiments/runs/eval_quality_gate_repo_patch_python_v0 --report-out experiments/reports/eval_matrices/eval_quality_gate_repo_patch_python_v0.md --overwrite
```

The control run now writes flake detection into `control_run_manifest.json` and
summarizes it in `control_report.md`; there is no separate flake-check command.
The eval report plus `experiments/reports/week06_eval_quality.md` provide the
human-facing gate summary.

## Construct Validity Notes

Write `docs/construct_validity_v0.md` around these questions:

- What capability is being measured?
- What task families are excluded?
- What shortcuts exist?
- Why are hidden tests appropriate?
- How hard are tasks for a skilled human?
- What does public-tests-only success mean?
- What would make this task distribution invalid?

## Done Criteria

Minimum:

- three existing dev tasks remain validated;
- all controls pass/fail correctly;
- flake risks are documented;
- split checks are enforced by code;
- task asset hashes are recorded;
- Week 6 report separates model, scorer, sandbox, task, and infra failures.

Target:

- oracle replay/checks run 3x;
- bad solutions remain rejected;
- no hidden files are visible during agent execution;
- no unexplained flake above 3%;
- weakest task is identified before authoring any new tasks.

## Fallback

If task count lags, do not add rushed tasks. Fix the weakest existing task.

Do not proceed to trajectory filtering if:

- oracle controls are failing;
- hidden validators leak;
- bad controls pass;
- task flakiness is unexplained.

## Initial Design Question

Before implementing the first Week 6 subsystem, decide:

```text
Should the first checkpoint target split/hash enforcement, or repeated-control
flake detection?
```

The answer determines whether we start by protecting data boundaries or by
measuring runtime reliability.
