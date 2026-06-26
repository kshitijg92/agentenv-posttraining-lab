# Week 5 Plan

## Theme

Week 5 adds the first model/agent path on top of the calibrated Week 4
environment baseline.

The goal is not to build a clever coding agent. The useful question is:

```text
Can a model-shaped policy interact with a task workspace through typed tools,
produce a patch artifact, and hand that patch back to the existing public-check
and hidden-scorer path without weakening measurement?
```

## Starting Point

Weeks 1-4 are closed.

Current trusted path:

```text
task manifest + seed_workspace -> submitted patch -> orchestrator ->
public checks -> hidden scorer -> attempt artifacts
```

Current eval path:

```text
eval config -> control_patch policies -> attempts -> eval matrix ->
control-policy replay -> report
```

Week 4 produced a clean dev environment baseline:

```text
dev tasks: 3
oracle: 3/3 PASS
noop: 3/3 HIDDEN_TEST_FAIL with public PASS / hidden FAIL
public-tests-only: 3/3 HIDDEN_TEST_FAIL with public PASS / hidden FAIL
control-policy replay: 9/9 matched
```

That baseline is measurement evidence, not a model baseline.

## Design Priority

Preserve the scoring contract:

```text
attempt success = AttemptStatus PASS
public checks = diagnostics only
hidden validators = private scorer
model/agent failures = separate from task/scorer/infra failures
```

The model/agent layer should produce a candidate patch or a typed failure. It
should not redefine task success.

## Initial Design Question

Before implementing the first model/agent artifact, decide:

```text
Should the first fake model emit a fixed structured tool-call script, or should
it emit free-form text that the prompt loop must parse into tool calls?
```

This decision controls the first contract:

- structured script emphasizes instrumentation and deterministic failure modes;
- free-form text emphasizes parser boundaries and malformed-output handling.

Do not build both at once.

## Planned Artifacts

Model interface:

```text
src/agentenv/models/schema.py
src/agentenv/models/fake.py
src/agentenv/models/openai_compatible.py
configs/models/fake.yaml
configs/models/local_or_api_placeholder.yaml
docs/model_interface.md
```

Tool interface:

```text
src/agentenv/tools/schema.py
src/agentenv/tools/local_tools.py
```

Agent loop:

```text
src/agentenv/agents/prompt_loop.py
```

Eval integration:

```text
configs/eval/week05_agent_baseline.yaml
experiments/runs/week05_fake_agent/
experiments/reports/week05_agent_baseline.md
```

Notes:

```text
notes/weekly/week_05/implementation_notes.md
notes/weekly/week_05/learnings.md
```

## Model Interface Contract

Define:

```text
ModelClient.generate(messages, decoding_config) -> ModelResponse
```

Required decoding fields:

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

Required response fields:

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

Non-claim:

```text
The fake model does not measure model quality.
It only proves the model interface and agent loop are wired and traceable.
```

## Tool Contract

Start with these tools:

```text
read_file(path)
write_file(path, content)
run_tests(command)
final_answer(text)
```

Every tool result should include:

```text
tool_name
input_hash
stdout
stderr
exit_code
duration_ms
error_class
```

Tool boundaries:

- tool paths are relative to the prepared agent workspace;
- hidden validators and task-pack private assets remain unavailable;
- invalid tool names or malformed arguments return typed errors;
- invalid tool calls do not crash the eval runner;
- tool output is trace-linked and bounded enough for reports.

## Agent Loop Contract

Implement the smallest prompt loop:

```text
observe task instruction
call model
interpret one tool action
execute local tool
append tool result to messages
repeat until final_answer or max turns
write candidate patch
score candidate patch through existing attempt path
```

The loop must record:

```text
model_id
model config path or fake model config
decoding config
fixed max turns
tool calls
tool invalidity
latency
token counts when available
model failure vs task failure vs infra failure
```

## Execution Plan

1. Decide the fake-model output contract.
   Do this before writing schema code.

2. Add model schema and fake model.
   Keep this independent of the eval runner at first. Unit-test response
   validation and deterministic fake output.

3. Add tool schema and local tools.
   Unit-test `read_file`, `write_file`, `run_tests`, and invalid tool handling
   in a temporary workspace.

4. Add the prompt-loop skeleton.
   Run it against a prepared workspace and produce either a patch text artifact
   or a typed agent failure. Do not integrate scoring until tool traces are
   inspectable.

5. Connect agent output to the existing scoring path.
   The scorer still sees a submitted patch. Public checks and hidden validators
   remain unchanged.

6. Extend eval config support for one agent policy.
   Keep `control_patch` behavior intact. Add only the smallest policy schema
   needed for `week05_agent_baseline.yaml`.

7. Write the fake-agent baseline report.
   State clearly that this is an interface baseline, not a model-quality result.

8. Close notes.
   Record implementation decisions as they happen, then write Week 5 learnings
   and limitations after the fake-agent path runs end to end.

## Commands To Reach The Gate

Expected fake-agent run:

```bash
uv run agentenv eval \
  --config configs/eval/week05_agent_baseline.yaml \
  --model fake \
  --out experiments/runs/week05_fake_agent

uv run agentenv report \
  experiments/runs/week05_fake_agent \
  --out experiments/reports/week05_agent_baseline.md
```

Repo checks:

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

Trace validation should include the new Week 5 artifacts once the agent trace
event family exists:

```bash
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments/runs/week05_fake_agent").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```

## Report Must Include

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

Also include:

```text
what the fake model proves
what it does not prove
whether a real model path was run or explicitly blocked
```

## Done Criteria

Minimum:

- fake model path runs end to end;
- tool calls are trace-linked;
- invalid tool calls produce typed errors;
- fixed inference budget is recorded;
- candidate patch is scored through the existing attempt path;
- real model path is either run or explicitly blocked with reason.

Quality bar:

- `control_patch` evals still work unchanged;
- existing dev-baseline scoring semantics are not weakened;
- reports separate model failure, task failure, scorer failure, and infra
  failure;
- notes record non-claims and limitations.

## Explicit Non-Goals

Do not spend Week 5 on:

- adding more tasks;
- creating heldout-private tasks;
- changing hidden-validator semantics;
- improving replay for model agents beyond what is needed to avoid false
  claims;
- optimizing prompt quality;
- model selection or benchmark comparison;
- training, filtering, or reward design.

## Fallback

If real model integration burns time:

```text
keep fake model only
finish prompt-loop scaffolding
write docs/week05_model_blocker.md
continue to trajectory export later
```

Do not proceed by weakening the scoring path or calling public-test success a
task pass.
