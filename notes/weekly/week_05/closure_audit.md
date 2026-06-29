# Week 5 Closure Audit

## Sources

This audit checks the current repo against:

- `notes/weekly/week_05/plan.md`
- `references/frontier_upskilling_12_week_execution_manual.md`
- `references/handoff.md`

## Verdict

Week 5 is functionally close, but not closed.

The fake/scripted model-agent path now runs end to end through eval, replay,
reporting, and agent-task harness audit. The remaining closure gaps are the
explicit real-model decision required by the Week 5 done criteria and the final
week-close learnings/limitations.

## Fresh Evidence

Regenerated canonical dev-baseline eval matrix:

```bash
uv run agentenv eval \
  --config configs/eval/dev_baseline.yaml \
  --all-policies \
  --out experiments/runs/dev_baseline
```

Observed:

```text
policies=6
attempts=18
replays=6
```

Regenerated canonical matrix report:

```bash
uv run agentenv report \
  experiments/runs/dev_baseline \
  --out experiments/reports/eval_matrices/dev_baseline.md
```

The report now shows:

```text
Task count: 3
Policy count: 6
Attempt count: 18
Replay match rate: 18/18 (100%)
Agent Model And Budget Summary
```

Validated generated dev-baseline traces:

```text
validated 42 trace files under experiments/runs/dev_baseline
```

Regenerated agent-task harness audit:

```bash
uv run agentenv agents audit \
  --cases data/harness_audit/agent_task_cases \
  --out experiments/harness_audit/agent_task_audit
```

Observed:

```text
cases=12
failed=0
```

Repo checks:

```text
uv run ruff check . -> passed
uv run pyright -> 0 errors
git diff --check -> passed
uv run pytest -n auto -> 264 passed
```

## Passing Criteria

The current implementation satisfies these Week 5 criteria:

- Fake/scripted model path runs end to end through eval.
- Agent controls interact with restricted task workspaces through typed tools.
- Completed agent prompt loops materialize candidate patches.
- Candidate patches are scored through the existing attempt/scorer path.
- Prompt-loop failures stay separate from nested scorer outcomes.
- Invalid model JSON, model errors, max-token stops, timeouts, max turns,
  terminal tool errors, recoverable tool errors, public failures, hidden
  failures, invalid shortcuts, and orchestrator errors are covered by
  agent-task harness audit cases.
- Fixed decoding budget is persisted in each agent task artifact through
  `decoding_config.json`.
- Agent task limits and allowed tools are persisted in `agent_task_view.json`.
- Dev-baseline matrix separates scorer control policies from agent control
  policies.
- Dev-baseline replay now covers all six control policies and reports `18/18`
  artifact comparisons matched.
- The matrix report surfaces model id, decoding strategy, temperature,
  max-new-token budget, model timeout, max turns, token/cost availability, and
  tool invalidity counts for agent policies.
- `docs/model_interface.md` documents the current model boundary and the
  requirements for a future real provider adapter.
- Scorer control behavior remains calibrated: oracle passes, known-bad controls
  pass public checks and fail hidden validators.

## Remaining Gaps

1. Real model path is not yet run or explicitly blocked.

   Week 5 done criteria require the real model path to be either run or blocked
   with a reason. There is no `docs/week05_model_blocker.md`, and there is no
   real model run artifact.

2. Real/API model config files and implementation are absent.

   `src/agentenv/models/openai_compatible.py`,
   `configs/models/fake.yaml`, and
   `configs/models/local_or_api_placeholder.yaml` do not exist. This is only a
   closure blocker if we choose to run a real model path. If we choose the
   fallback, the blocker doc should explicitly say these are deferred.

3. Week 5 learnings and limitations are not closed.

   `notes/weekly/week_05/learnings.md` does not exist yet. The implementation
   notes are detailed, but the week still needs a short closure summary with
   non-claims and limitations.

## Not Gaps

These differ from the original manual names but are intentional:

- There is no `configs/eval/week05_agent_baseline.yaml`; reusable configs use
  schedule-agnostic names such as `configs/eval/agent_control_policies.yaml`
  and `configs/eval/dev_baseline.yaml`.
- There is no `src/agentenv/agents/prompt_loop.py`; the implemented prompt loop
  lives in `src/agentenv/agents/loop.py`.
- The current Week 5 fake-agent baseline is deterministic agent-control based,
  not a non-control model-quality baseline. The reports correctly state that it
  is not evidence of broad coding-agent capability.

## Recommended Closure Path

1. Decide whether to run a real model path now.
2. If not, write `docs/week05_model_blocker.md` with the exact reason and what
   remains deferred.
3. Write `notes/weekly/week_05/learnings.md` and close Week 5.
