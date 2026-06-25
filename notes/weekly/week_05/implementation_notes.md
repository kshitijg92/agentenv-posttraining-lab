# Week 5 Implementation Notes

## Fake Model Output Contract

### Decision

Start with a fake model that emits a fixed structured tool-call script.

### Reasoning

Week 5 is primarily about instrumentation, traceability, and failure boundaries.
A structured fake-model output gives deterministic parsing and keeps the first
agent loop from becoming a brittle free-form text parser.

This does not mean the prompt loop should trust the fake model blindly. The
structured script should still cross the model boundary as model output and be
validated by the agent layer. Malformed or invalid tool calls should produce
typed errors rather than crashing the runner.

### Non-Claim

This does not test natural-language tool-call parsing. That can be added later
as a separate capability once the deterministic agent/tool path is measured.

## Message Schema Decision

### Decision

Use a generic model-message schema rather than baking task fields directly into
the message object.

```text
role: system | user | assistant | tool
content: str
name: str | None
tool_call_id: str | None
metadata: dict[str, scalar]
```

### Reasoning

Task manifest fields such as instruction, allowed tools, public checks, and
limits should be rendered into initial prompt messages by a prompt builder.
`Message` itself should stay model-interface-level so it can also represent
assistant outputs and tool observations.

`name` is included directly for readability and tool attribution. `tool_call_id`
is included for future agent-loop trace linking. Metadata is limited to simple
scalar JSON-like values so prompts remain deterministic and do not become a
place to hide large outputs, timestamps, host paths, or private evaluator data.

### Invariants

- `tool` messages require `name` and `tool_call_id`.
- `system` and `user` messages cannot include `tool_call_id`.
- `name` and `tool_call_id`, when present, must be non-empty.
- unknown fields are rejected.
- metadata values must be scalar; nested lists and objects are rejected.

### Next Small Step

Design `DecodingConfig` before adding more model client code.

## Decoding Config Decision

### Decision

`DecodingConfig` represents the generation settings for one
`ModelClient.generate(...)` call, not the full agent attempt budget.

```text
strategy: greedy | sampling
temperature: 0.0 to 2.0
top_p: >0.0 to 1.0
top_k: positive int | None
max_new_tokens: positive int
num_return_sequences: 1 for v0
seed: non-negative int | None
stop: list[str]
timeout_seconds: positive int
```

### Reasoning

This keeps model-call behavior separate from agent-loop behavior. Token budget,
sampling controls, stop strings, and per-call timeout belong to decoding.
`max_turns`, tool-call limits, and test-run limits belong to the future
agent-loop config.

### Invariants

- `greedy` decoding requires `temperature == 0.0`.
- `num_return_sequences` is restricted to `1` for v0.
- stop sequences cannot be empty strings.
- unknown fields are rejected so agent-loop settings do not silently leak into
  model-call settings.

### Next Small Step

Design `ModelResponse` before implementing the fake model client.

## Model Response Decision

### Decision

`ModelResponse` records the result of one model generation call before the
agent loop interprets the output as a tool action.

```text
model_id: str
output_text: str
finish_reason: stop_criteria_met | max_new_tokens_reached | timeout | error
latency_ms: non-negative int
prompt_tokens: non-negative int | None
completion_tokens: non-negative int | None
total_tokens: non-negative int | None
error_class: str | None
raw_response_ref: str
```

### Reasoning

The response object should preserve what the model emitted, not whether the
agent thinks it is a valid action. Parsing structured output into tool calls
belongs to the future agent layer.

`finish_reason` explains why generation stopped. It is not a success flag.
`max_new_tokens_reached` is a budget stop, not a provider or infrastructure
error. Timeout and provider errors require an `error_class`.

Token counts are nullable because fake, local, and API-backed models may expose
different usage accounting. When both prompt and completion token counts are
known, `total_tokens` must match their sum.

### Invariants

- `raw_response_ref` is required so every model response has an artifact handle.
- `timeout` and `error` responses require `error_class`.
- normal stop responses cannot include `error_class`.
- if prompt and completion token counts are present, `total_tokens` must equal
  their sum.

### Next Small Step

Design the fake model client interface and fixed structured output format.

## Agent Action Parsing Decision

### Decision

Represent one model-to-agent action as JSON text inside
`ModelResponse.output_text`, then parse it into an agent-layer action object.

Tool call example:

```json
{
  "action": "tool_call",
  "tool_name": "read_file",
  "arguments": {
    "path": "src/foo.py"
  }
}
```

Final answer example:

```json
{
  "action": "final_answer",
  "text": "done"
}
```

### Reasoning

The model interface remains realistic because model output is still text. The
agent loop owns JSON parsing and schema validation.

The parsed action schema is intentionally only a local parsing contract. It
checks whether the model emitted an action-shaped object, not whether the action
is allowed for the current task or safe to execute.

### Boundary

Parsing layer:

```text
model output_text -> JSON -> ToolCallAction | FinalAnswerAction
```

Future enforcement layers:

```text
task-aware validator: allowed tool names and argument requirements
local tool layer: workspace path containment and command execution boundaries
```

### Invariants

- v0 supports one action per model turn.
- `tool_call` requires a non-empty `tool_name`.
- `tool_call.arguments` defaults to `{}` and only allows scalar JSON values.
- `final_answer` requires non-empty `text`.
- malformed JSON is distinct from schema-invalid JSON.
- extra fields are rejected.

### Next Small Step

Design the fake model client behavior once its fixed script is exhausted.
