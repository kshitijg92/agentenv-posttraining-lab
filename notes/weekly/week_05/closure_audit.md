# Week 5 Closure Audit

## Sources

This audit checks the current repo against:

- `notes/weekly/week_05/plan.md`
- `references/agentic_evaluation_12_week_execution_manual.md`

## Verdict

Week 5 is closed.

The scripted-control agent path runs end to end through eval, replay, reporting,
and agent-task harness audit. The real-model path was also run through a local
OpenAI-compatible Ollama endpoint, satisfying the Week 5 "run or explicitly
block real model" criterion.

## Fresh Evidence

Regenerated canonical dev-baseline eval matrix:

```bash
uv run agentenv eval \
  --config configs/eval/dev_baseline.yaml \
  --all-policies \
  --out experiments/runs/dev_baseline \
  --report-out experiments/reports/eval_matrices/dev_baseline.md \
  --overwrite
```

Observed:

```text
config: dev_baseline
tasks: 3
policies: 6
attempts: 18
replay runs: 6
replay run success summary: 6/6
replay match rate: 18/18 (100%)
```

Report:

```text
experiments/reports/eval_matrices/dev_baseline.md
```

The dev-baseline report shows:

- scorer controls are calibrated: oracle `3/3` PASS;
- known-bad scorer controls are `0/6` final PASS with public PASS and hidden
  FAIL;
- agent controls are calibrated: `agent-happy` and `agent-recoverable` score
  `3/3` PASS, while `agent-malformed` fails before scoring as expected;
- all configured control-policy replay runs pass.

Real-model dev matrix:

```text
config: configs/eval/agent_model_dev_ollama_qwen3_14b.yaml
model: hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
run: experiments/runs/agent_model_dev_ollama_qwen3_14b
report: experiments/reports/eval_matrices/agent_model_dev_ollama_qwen3_14b.md
```

Observed:

```text
tasks: 3
policies: 7
attempts: 21
replay runs: 0
control expectations: on track
real-model final pass rate: 0/3
prompt-loop completed: 2/3
nested scorer run: 2/3
public pass: 2/3
hidden pass: 0/3
empty candidate patches: 2
missing candidate patches: 1
max-turn failures: 1
invalid tool calls: 1
```

This is not a model-quality claim. It is evidence that a real model policy can
run through the same typed-tool, artifact, and scorer path as scripted controls.

Trace validation:

```text
validated 42 trace files under experiments/runs/dev_baseline
validated 24 trace files under experiments/runs/agent_model_dev_ollama_qwen3_14b
```

Harness audit coverage:

```text
scorer audit cases: 11
agent task audit cases: 13
```

Repo checks from the final Week 5 implementation pass:

```text
uv run ruff check . -> passed
uv run pyright -> 0 errors
git diff --check -> passed
uv run pytest -n auto -> 340 passed
```

## Passing Criteria

The current implementation satisfies the Week 5 minimum criteria:

- fake/scripted model path runs end to end;
- tool calls are persisted and trace-linked through prompt-loop artifacts;
- invalid tool calls produce typed errors;
- fixed inference budget is recorded in `decoding_config.json`;
- agent task limits and allowed tools are recorded in `agent_task_view.json`;
- completed candidate patches are scored through the existing attempt/scorer
  path;
- real model path was run through `agent_model` using a local
  OpenAI-compatible endpoint.

The implementation also satisfies the quality bar:

- `scorer_control_patch` evals still work and remain calibrated;
- existing dev-baseline scoring semantics are not weakened;
- reports separate control calibration from real agent-model results;
- reports separate prompt-loop failure, task failure, scorer failure, and
  infrastructure/orchestrator failure;
- Week 5 notes record non-claims and limitations.

## Current Artifacts

Model interface documentation:

```text
docs/model_interface.md
```

Week 5 learning summary:

```text
notes/weekly/week_05/learnings.md
```

Canonical control matrix:

```text
experiments/runs/dev_baseline
experiments/reports/eval_matrices/dev_baseline.md
```

Real-model matrix:

```text
configs/eval/agent_model_dev_ollama_qwen3_14b.yaml
experiments/runs/agent_model_dev_ollama_qwen3_14b
experiments/reports/eval_matrices/agent_model_dev_ollama_qwen3_14b.md
```

Local-model setup:

```text
src/agentenv/local_model_setup/
src/agentenv/local_model_setup/README.md
configs/models/ollama_qwen3_14b_q4_k_m.yaml
configs/decoding/greedy_1024.yaml
```

## Not Gaps

These differ from the original plan/manual names but are intentional:

- There is no `configs/eval/week05_agent_baseline.yaml`; reusable configs use
  schedule-agnostic names such as `configs/eval/agent_control_policies.yaml`,
  `configs/eval/dev_baseline.yaml`, and
  `configs/eval/agent_model_dev_ollama_qwen3_14b.yaml`.
- There is no `src/agentenv/agents/prompt_loop.py`; the implemented prompt loop
  lives in `src/agentenv/agents/loop.py`.
- There is no `src/agentenv/models/openai_compatible.py`; the implemented
  adapter is `src/agentenv/models/openai_compatible_chat.py`.
- There is no fake-model YAML config. Scripted controls are persisted per
  artifact as `agent_control_script.json`, which is the relevant replayable
  control artifact.

## Remaining Limitations

These are limitations, not Week 5 blockers:

- hidden-validator file hashes are still not captured in `eval_matrix_v0`;
- raw provider responses are not persisted;
- cost is reported as `not_recorded`;
- the prompt loop supports one JSON action per model turn;
- prompt quality has not been optimized;
- local real-model execution depends on an external Ollama server and local
  machine capacity;
- public checks are weak on some dev tasks, by design, and hidden validators
  remain the task-success authority.

## Closure Decision

Week 5 should be treated as closed. Week 6 can start from a real, inspectable
model-agent baseline rather than from interface scaffolding.
