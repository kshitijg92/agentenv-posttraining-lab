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
src/agentenv/models/config_schema.py
src/agentenv/models/config.py
src/agentenv/models/openai_compatible_chat.py
src/agentenv/models/factory.py
src/agentenv/agents/loop.py
src/agentenv/agents/prompts.py
src/agentenv/agents/tool_messages.py
src/agentenv/orchestrators/agent_task_run.py
src/agentenv/orchestrators/eval_run.py
```

The OpenAI-compatible chat provider adapter is implemented as a `ModelClient`
and is wired into `agent_model` eval policies. The same path supports local
OpenAI-compatible endpoints such as Ollama.

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

Reusable decoding configs live under `configs/decoding/` and use the same
schema as `DecodingConfig`. Eval configs reference them by path from
`agent_model` policies.

## Model Config

Model configs describe provider identity and adapter capabilities, not decoding
behavior:

```text
version: model_config_v0
provider: openai_compatible_chat
model_id: str
api_key_env: str | None
base_url_env: str | None
capabilities:
  token_usage: native | unavailable
  supports_seed: bool
  supports_stop: bool
  supports_top_k: bool
```

The config stores environment variable names, never secret values. Eval configs
reference model configs by path from `agent_model` policies.

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
list_files(path, max_depth, max_files)
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

Agent task artifacts are root manifests with `artifact_type: agent_attempt` and
`artifact_schema_version: agent_attempt_artifact_v0`. They include:

```text
manifest.json
agent_task_run.json
decoding_config.json
model_config.json           # only for real agent_model policies
agent_control_script.json   # only for scripted controls
agent_task_view.json
prompt_loop_result.json
candidate.patch             # only when a candidate patch is produced
error.txt
attempt/                    # only when nested scoring runs
```

The eval suite report reads model and budget metadata from these artifacts:

- model ids from `prompt_loop_result.json`
- token fields from `prompt_loop_result.json`
- decoding budget from `decoding_config.json`
- model config provenance from `model_config.json`
- max turns from `agent_task_view.json`
- candidate patch size from `candidate.patch`
- prompt-loop statuses, nested scorer statuses, and tool invalidity from
  `prompt_loop_result.json` and `agent_task_run.json`

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

A real provider adapter must implement `ModelClient` and return `ModelResponse`
without changing the prompt loop contract.

The adapter should:

- map provider roles/messages into the local `Message` schema,
- preserve the local `model_id`,
- map provider stop reasons into local `finish_reason` values,
- populate token counts when available,
- populate latency,
- use a stable `raw_response_ref`,
- convert provider exceptions into typed model errors,
- avoid logging secrets or full private credentials in artifacts.

The provider adapter is allowed to access network as an inference backend. That
does not grant network access to task tools, public checks, hidden validators,
or scorer execution. Future networked tools such as browser/API tools should be
introduced as explicit tool capabilities with their own audit coverage.

The adapter must not:

- receive hidden validators or controls,
- inspect task-pack private files,
- bypass the typed tool interface,
- treat public-check success as task success,
- mutate scorer semantics.

## Current Real-Model Status

The real-model path has been run through an OpenAI-compatible local Ollama
endpoint with Qwen:

```text
config: configs/eval/agent_model_dev_ollama_qwen3_14b.yaml
model: hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
report: experiments/reports/eval_suites/agent_model_dev_ollama_qwen3_14b.md
```

The run is useful as an integration baseline, not a model-quality claim. The
configured controls stayed on track, while the real model finished with:

```text
final pass rate: 0/3
public-pass/hidden-fail: 2
empty candidate patches: 2
max-turn failures: 1
invalid tool calls: 1
```

This proves the real provider path can execute through typed tools, persist
model/decoding provenance, generate agent-task artifacts, and hand completed
candidate patches to the existing scorer without changing scorer semantics.
