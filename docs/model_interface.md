# Model Interface

## Purpose

This document defines the current model boundary for the local repo-patch agent
loop.

The model interface is intentionally narrow:

```text
ModelClient.generate(messages, decoding_config) -> ModelResponse
```

The model does not see task manifests, hidden validators, scorer controls,
leakage canaries, or host paths. The harness renders a restricted task view into
messages, and the prompt loop mediates all workspace interaction through typed
tools.

## Implemented Files

Current implementation:

```text
src/agentenv/models/schema.py
src/agentenv/models/client.py
src/agentenv/models/fake.py
src/agentenv/agents/loop.py
src/agentenv/agents/prompts.py
src/agentenv/agents/tool_messages.py
src/agentenv/orchestrators/agent_task_run.py
```

The real/API provider adapter is not implemented yet.

## Message Contract

`Message` is generic model-interface state:

```text
role: system | user | assistant | tool
content: str
name: str | None
tool_call_id: str | None
metadata: dict[str, scalar]
```

Invariants:

- `tool` messages require `name` and `tool_call_id`.
- `system` and `user` messages cannot include `tool_call_id`.
- Metadata values are scalar only.
- Unknown fields are rejected.

The initial prompt is built from `AgentTaskView`, not from the private task
manifest.

## Decoding Config

`DecodingConfig` describes one generation call:

```text
strategy: greedy | sampling
temperature: float
top_p: float
top_k: int | None
max_new_tokens: int
num_return_sequences: int
seed: int | None
stop: list[str]
timeout_seconds: int
```

Current invariants:

- Greedy decoding requires `temperature = 0.0`.
- `num_return_sequences` must be `1` for v0.
- Stop sequences cannot be empty strings.

Agent task limits such as `max_turns`, workspace timeout, allowed tools, and
network mode live in `AgentTaskView`; they are not model decoding settings.

## Model Response

`ModelResponse` records one provider generation result:

```text
model_id: str
output_text: str
finish_reason: stop_criteria_met | max_new_tokens_reached | timeout | error
latency_ms: int
prompt_tokens: int | None
completion_tokens: int | None
total_tokens: int | None
error_class: str | None
raw_response_ref: str
```

Invariants:

- `timeout` and `error` responses require `error_class`.
- `stop_criteria_met` and `max_new_tokens_reached` responses forbid
  `error_class`.
- If prompt and completion token counts are both known, `total_tokens` must
  equal their sum.

`finish_reason` is not a success flag. The prompt loop treats any finish reason
other than `stop_criteria_met` as `model_error`.

## Prompt-Loop Action Format

The current v0 prompt loop expects one JSON action per model turn:

```json
{"action": "tool_call", "tool_name": "read_file", "arguments": {"path": "src/foo.py"}}
{"action": "final_answer", "text": "done"}
```

Supported tools:

```text
read_file(path)
write_file(path, content)
run_tests(command)
```

`final_answer` ends the prompt loop. If the loop completes, the harness derives a
candidate patch from the mutated agent workspace and scores it through the
existing attempt/scorer path.

## Failure Boundaries

Prompt-loop statuses:

```text
completed
max_turns_exceeded
model_error
invalid_model_output
terminal_tool_error
```

Agent task run statuses:

```text
scored
agent_loop_failed
orchestrator_error
```

Important boundaries:

- Malformed or schema-invalid model JSON is terminal `invalid_model_output`.
- Model `error`, `timeout`, and `max_new_tokens_reached` stops are
  `model_error`.
- Recoverable tool errors are appended as tool messages so the model can
  correct itself.
- Terminal tool errors stop the prompt loop before scoring.
- A completed prompt loop is not task success; only the nested scorer attempt
  can produce task success.

## Artifact Contract

Agent task artifacts use `agent_task_run_artifacts_v0` and include:

```text
run_manifest.json
agent_task_run.json
decoding_config.json
agent_control_script.json   # only for scripted controls
agent_task_view.json
prompt_loop_result.json
candidate.patch             # only when a candidate patch is produced
error.txt
attempt/                    # only when nested scoring runs
```

The matrix report reads model and budget metadata from these artifacts:

- model ids from `prompt_loop_result.json`
- token fields from `prompt_loop_result.json`
- decoding budget from `decoding_config.json`
- max turns from `agent_task_view.json`
- tool invalidity from `prompt_loop_result.json`

Unknown token or cost data must be reported as not recorded, not as zero.

## Scripted Fake Model

`ScriptedFakeModelClient` is the implemented model client.

It returns fixed `FakeModelScriptStep` outputs and ignores the prompt messages.
That is intentional: it calibrates the agent/tool/scorer interface, not model
quality.

The scripted fake model proves:

- the model interface is traceable,
- prompt-loop failure modes are typed,
- tool calls are mediated through `AgentTaskView`,
- candidate patches can be scored without changing the scoring contract.

It does not prove:

- natural-language tool-use ability,
- prompt quality,
- real model reliability,
- broad coding-agent capability.

## Real Provider Adapter Requirements

A future real provider adapter must implement `ModelClient` and return
`ModelResponse` without changing the prompt loop contract.

The adapter should:

- map provider roles/messages into the local `Message` schema,
- preserve the local `model_id`,
- map provider stop reasons into local `finish_reason` values,
- populate token counts when available,
- populate latency,
- use a stable `raw_response_ref`,
- convert provider exceptions into typed model errors,
- avoid logging secrets or full private credentials in artifacts.

The adapter must not:

- receive hidden validators or controls,
- inspect task-pack private files,
- bypass the typed tool interface,
- treat public-check success as task success,
- mutate scorer semantics.

## Current Real-Model Status

The real/API model path is not implemented yet. Closing Week 5 requires either
running a real model path or writing an explicit blocker note that records why it
is deferred.
