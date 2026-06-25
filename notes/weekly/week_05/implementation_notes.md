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

## Fake Model Client Decision

### Decision

Implement a scripted fake model client. Each call to `generate(...)` returns the
next fixed raw string as `ModelResponse.output_text`.

If the agent loop calls the fake model after the script is exhausted, return:

```text
finish_reason: error
error_class: FakeModelScriptExhausted
output_text: ""
```

### Reasoning

The fake model exists to exercise the model/agent boundary deterministically. A
fixed script makes turn order auditable and avoids prompt-quality claims.

The fake model script stores raw text, not parsed `AgentAction` objects. That
keeps the model layer independent from the agent layer:

```text
fake model -> ModelResponse.output_text -> agent parser -> AgentAction
```

This also lets later tests intentionally script malformed JSON or schema-invalid
JSON without changing the fake model.

Script exhaustion is not a normal completion. A well-formed fake script should
emit `final_answer` explicitly when the model is done. If the script runs out
first, that is a fake-model configuration failure and should be visible as a
model error.

### Non-Claims

- The fake model does not inspect messages intelligently.
- The fake model does not execute tools.
- The fake model does not parse or validate agent actions.
- The fake model does not provide real token accounting; token fields are
  unknown unless a future fake configuration explicitly models them.
- The fake model does not know hidden validators, controls, or full task
  manifests.
- Passing through the fake model does not measure model quality.

### Next Small Step

Design the visible task view passed from the all-knowing eval harness to the
restricted agent loop.

## Agent Task View Decision

### Decision

Pass a restricted `AgentTaskView` from the eval harness to the agent loop rather
than passing the full task manifest.

```text
task_id
instruction
workspace_path
allowed_tools
public_checks
max_turns
timeout_seconds
network
```

### Reasoning

The eval harness is the all-knowing side of the system. It can load the full
task manifest, prepare the workspace, and later run hidden scoring.

The agent loop is only the restricted model-environment mediator. It should
receive visible task information and the prepared workspace path needed for tool
execution, but it should not receive private evaluator fields.

### Excluded Fields

Do not include:

```text
hidden_validators
controls
leakage_canary
task_manifest_path
task_pack_path
oracle/bad patches
hidden test paths
scoring/replay expectations
```

### Invariant

`workspace_path` is allowed in `AgentTaskView` for execution coordination, but
prompt rendering must not include the raw host path in messages sent to the
model.

### Next Small Step

Design tool schemas separately from task visibility:

```text
AgentTaskView.allowed_tools = permission list
tool schemas = argument contracts
tool executor = permission checks and workspace containment
```

## Tool Definition And Schema Decision

### Decision

Keep v0 tool input and output schemas minimal and atomic:

```text
read_file(path)
write_file(path, content)
run_tests(command)
```

```text
ReadFileOutput(content, bytes_read, truncated)
WriteFileOutput(bytes_written)
RunTestsOutput(passed)
```

Define tools as reusable capabilities:

```text
ToolDefinition(name, description, input_model, output_model)
```

### Reasoning

Tool definitions describe what a tool is and which schemas define its input and
output. They do not represent one concrete execution.

Concrete model requests remain `ToolCallAction` objects from the agent layer:

```text
tool_name + raw arguments
```

Concrete execution records will later be represented by `ToolResult`.

Tool schemas and definitions do not decide whether a tool is allowed for a task,
whether a path is safe, or whether a command should execute.

Those checks belong to the executor layer:

```text
permission check against AgentTaskView.allowed_tools
argument validation against tool schema
workspace path containment
command execution boundary
ToolResult recording
```

### Boundary

Current concepts:

```text
ToolDefinition = reusable capability metadata
ToolCallAction = one model request
ToolInput/ToolOutput = per-tool payload schemas
```

Future concept:

```text
ToolResult = one execution record with status, timing, error, and output
```

### Non-Goals For This Checkpoint

Do not add optional fields yet:

```text
max_bytes
start_line/end_line
append mode
custom cwd
timeout override
```

Those can be added only when the prompt loop exposes a real need.

### Next Small Step

Design `ToolResult` before implementing local tool execution.

## Tool Result Decision

### Decision

Represent one tool execution with a common `ToolResult` envelope:

```text
tool_name
input_hash
status: ok | error
output: ToolOutput | None
stdout
stderr
exit_code: int | None
duration_ms
error_class: str | None
error_message: str | None
```

### Reasoning

Tool-specific outputs should stay small and typed. Shared execution evidence
belongs in the common envelope.

`exit_code` is nullable because `read_file` and `write_file` are not
subprocesses. `run_tests` can set it once execution is implemented.

Tracebacks are intentionally not part of `ToolResult` v0. Private tracebacks can
be written to evaluator-side artifacts later. The result envelope should remain
safe to render into bounded tool observations after filtering.

### Invariants

- `ok` results require typed `output`.
- `ok` results cannot include error fields.
- `error` results cannot include output.
- `error` results require `error_class`.
- `input_hash` is required and should later hash the validated input payload,
  not raw model JSON.

### Next Small Step

Design local tool execution and permission checks against `AgentTaskView`.
