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
ToolDefinition(name, description, input_model, output_model, example_arguments)
```

### Reasoning

Tool definitions describe what a tool is and which schemas define its input and
output. They also carry example arguments for prompt rendering so the prompt
builder does not hardcode per-tool invocation examples.

Tool example arguments must validate against the tool's input schema.

`write_file.content` means full replacement file contents, not a patch. The
harness will later derive the submitted patch by diffing the original prepared
workspace against the final modified workspace.

Tool definitions do not represent one concrete execution.

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

## Local Tool Executor Decision

### Decision

Implement local tool execution as:

```text
execute_tool(tool_call_action, agent_task_view) -> ToolResult
```

Use explicit variable names such as `tool_call_action` and `agent_task_view` to
avoid ambiguous code like `action.action`.

### Validation Order

Executor validation order is:

```text
1. tool_name in AgentTaskView.allowed_tools
2. tool_name in TOOL_REGISTRY
3. arguments validate against the tool input schema
4. file paths stay inside AgentTaskView.workspace_path
5. run_tests command exactly matches one public check command
6. execute the local operation
```

The first matching failure returns a `ToolResult(status="error")`; invalid model
tool calls should not crash the agent loop.

### Error Classes

```text
ToolNotAllowed
UnknownTool
InvalidToolInput
UnsafePath
CommandNotAllowed
ToolExecutionError
ToolTimeout
```

`ToolNotAllowed` is checked before `UnknownTool` because model invalidity should
be measured against the restricted task view first.

### Safety Boundaries

- `read_file` and `write_file` reject absolute paths and path traversal outside
  the prepared workspace.
- `write_file` only writes inside existing directories for v0.
- `run_tests` only executes commands that exactly match `public_checks`.
- subprocess `exit_code != 0` is an `ok` tool execution with
  `RunTestsOutput(passed=False)`, not a tool execution error.
- `ToolResult.tool_name` preserves the raw requested tool name so invalid calls
  such as `delete_file` remain auditable.
- Successful known-tool results still validate that the output type matches the
  tool name.
- For validated tool calls, `input_hash` hashes the validated input payload. For
  permission, unknown-tool, and invalid-input failures, it hashes the raw model
  arguments because no validated input exists yet.

### Next Small Step

Design how a `ToolResult` is rendered back into a bounded `Message(role="tool")`
for the next model turn.

## Tool Observation Rendering Decision

### Decision

Render `ToolResult` into compact model-facing `Message(role="tool")` objects
rather than dumping the full execution envelope.

Success observation:

```json
{
  "tool_name": "read_file",
  "status": "ok",
  "output": {}
}
```

Error observation:

```json
{
  "tool_name": "read_file",
  "status": "error",
  "stdout": "",
  "stderr": "",
  "exit_code": null,
  "error_class": "ToolExecutionError",
  "error_message": "..."
}
```

### Reasoning

The model needs an observation, not the full audit envelope. Successful tool
messages should avoid a large set of null error fields. Error messages should
include the bounded diagnostic information the model can use to recover.

Full `ToolResult` objects remain evaluator-side evidence for traces/artifacts.

### Invariants

- Do not include `duration_ms` in model-facing content.
- Do not include private tracebacks in model-facing content.
- Do not include raw host paths or private artifact refs in model-facing
  content.
- `tool_call_id` is generated by the future agent loop and passed into the
  renderer. The model is not trusted to create linkage IDs.
- Message metadata carries `input_hash` for trace linking. `tool_name`,
  `status`, and `tool_call_id` already exist as first-class message fields or
  model-facing content and should not be duplicated in metadata.

### Next Small Step

Design the prompt-loop state machine now that model calls, action parsing, tool
execution, and tool-observation rendering have narrow contracts.

## Prompt Loop Result Schema Decision

### Decision

Define the prompt-loop result as a summary plus direct evidence objects:

```text
task_id
status
turns_executed
duration_ms
token_usage
messages
model_responses
tool_results
error_class
error_message
```

### Statuses

v0 terminal statuses:

```text
completed
max_turns_exceeded
model_error
invalid_model_output
terminal_tool_error
```

No separate overall loop timeout is included in v0. Per-call model timeouts are
represented as `model_error` with the model response's error class. Tool
timeouts are recoverable tool observations unless the loop later terminates for
another reason.

### Reasoning

The result carries full `messages`, `model_responses`, and `tool_results`
directly for now. This is simpler to unit test and preserves the data needed for
future trajectory export. Artifact references can be added later when the prompt
loop is integrated with eval-run persistence.

The result does not include a separate `final_answer` summary field because the
final answer action is already present in `messages` and `model_responses`.

`status` and `error_class` stay separate:

```text
status = top-level terminal category
error_class = specific diagnostic
```

### Invariants

- `completed` cannot include error fields.
- non-completed results require `error_class`.
- `turns_executed` counts model calls, not tool calls.
- simple `TokenUsage` aggregates prompt, completion, and total tokens, each
  nullable when unknown. Fake model loops will usually report unknown token
  usage.

### Next Small Step

Implement the minimal prompt-loop runner using the existing scripted fake model,
agent action parser, local tool executor, and tool-message renderer.

## Initial Prompt Message Decision

### Decision

Build initial prompt-loop messages with:

```text
system message = protocol, JSON action rules, and allowed tool interface
user message = visible task instruction, public checks, workspace wording, limits
```

The model-facing content includes:

```text
task instruction
allowed tools and descriptions
public check commands
max_turns
timeout_seconds
network
prepared-workspace wording
```

The model-facing content excludes:

```text
raw workspace_path
task_id
hidden validators
controls
leakage canary
task manifest path
private scoring/replay expectations
```

### Reasoning

`task_id` is useful for trace linkage and eval joins, but it does not help the
model solve the task. It is stored in message metadata, not prompt content.

The system message is dynamic for each `AgentTaskView` because allowed tools are
part of the action interface the model must follow. It must only mention tools
that are allowed for the current task. Tool-call examples are rendered from
`ToolDefinition.example_arguments`, not hardcoded in the prompt builder.

The system prompt explicitly says the model may only interact through
`tool_call` or `final_answer` actions; free-form chat and markdown are invalid
model output for v0.

The system message persists at the front of the transcript and is sent on every
model call because the prompt loop resends the full message list each turn.

The user message describes files as available through tools in the prepared
workspace without exposing raw host paths.

### Next Small Step

Implement the minimal prompt-loop runner state machine.

## Model Client Protocol Decision

### Decision

Define a minimal `ModelClient` protocol for the prompt loop:

```text
model_id: str
generate(messages, decoding_config) -> ModelResponse
```

### Reasoning

The prompt loop should depend on a model interface, not on the scripted fake
implementation. `model_id` is exposed on the client, not only on
`ModelResponse`, so traces can identify the attempted model even if generation
raises later or returns an error response.

The interface stays intentionally small for v0. Provider metadata, endpoint
details, pricing, and model-family capabilities can be added only when a real
model integration needs them.

### Next Small Step

Implement the prompt-loop runner against `AgentTaskView`, `ModelClient`,
`DecodingConfig`, local tool execution, and tool-message rendering.

## Prompt Loop Runner Decision

### Decision

Implement the v0 prompt loop as:

```text
run_prompt_loop(agent_task_view, model_client, decoding_config)
  -> PromptLoopResult
```

The loop builds initial messages, calls `model_client.generate(...)`, records
the `ModelResponse`, appends the assistant message containing
`ModelResponse.output_text`, and only then checks finish reason or parses the
output into an `AgentAction`.

### Reasoning

The assistant message is recorded before parsing or error handling so invalid
JSON, schema-invalid actions, and model budget stops remain visible in the
transcript. This keeps trace reconstruction deterministic and avoids losing the
exact text that caused a failure.

### State Machine

- `final_answer` stops the loop with `completed`.
- model `error`, `timeout`, or `max_new_tokens_reached` stops the loop with
  `model_error` after recording the assistant output.
- malformed JSON or schema-invalid actions stop the loop with
  `invalid_model_output`.
- successful tool calls execute locally, append a bounded tool message, and
  continue.
- recoverable tool errors (`InvalidToolInput`, `ToolExecutionError`,
  `ToolTimeout`) are rendered back to the model and the loop continues.
- terminal tool errors stop the loop with `terminal_tool_error` after appending
  the tool message.
- reaching `AgentTaskView.max_turns` without completion returns
  `max_turns_exceeded`.

### Trace Details

- assistant messages use `name = model_response.model_id`.
- the loop generates `tool_call_id` values and attaches them to the assistant
  tool-call message and matching tool message.
- if `generate(...)` raises before returning a `ModelResponse`, the result uses
  `model_error` and includes `model_client.model_id` in the diagnostic.

### Next Small Step

Run a small end-to-end fake-agent attempt against a prepared workspace to verify
that read/write/test/final-answer turns produce the expected final workspace and
trace.

## Fake-Agent E2E Test Placement Decision

### Decision

Put the first fake-agent end-to-end prompt-loop proof in a separate test file:

```text
tests/agents/test_prompt_loop_e2e.py
```

### Reasoning

`tests/agents/test_prompt_loop.py` already covers unit-level prompt-loop state
machine behavior such as final-answer completion, malformed model output,
model-generation errors, recoverable tool errors, terminal tool errors, and
max-turn handling.

The new checkpoint proves a different boundary: the scripted fake model, JSON
action parser, local tool executor, tool-message renderer, and prompt-loop
transcript all compose correctly across a real temporary workspace.

### Invariants

- the fake agent reads a source file, writes full replacement contents, runs the
  exact allowed public-check command, and then emits `final_answer`;
- the source file is actually changed on disk;
- the `run_tests` result reports `RunTestsOutput(passed=True)`;
- assistant/tool message pairs share generated `tool_call_id` values;
- the transcript preserves the expected system/user/assistant/tool ordering;
- raw host workspace paths do not appear in model-facing message content.

### Non-Goals

Do not use this checkpoint to add eval config, CLI integration, scoring, report
generation, trace export, or real model APIs. Those remain later Week 5
checkpoints.

## Recoverable Tool-Input E2E Decision

### Decision

Add one end-to-end self-correction test for a valid JSON `tool_call` whose
arguments fail tool-input validation:

```json
{"action":"tool_call","tool_name":"read_file","arguments":{}}
```

The prompt loop should render the resulting `InvalidToolInput` as a tool
observation, continue to the next model turn, and allow the scripted fake model
to correct the call before completing the read/write/test/final-answer path.

### Reasoning

This exercises a real recovery path across the model/action parser, local tool
executor, tool-message renderer, and prompt-loop transcript.

Malformed JSON or schema-invalid model output remains terminal
`invalid_model_output` in v0. That failure happens before the model has crossed
the action boundary, so treating it as a recoverable tool observation would
blur protocol failure with workspace/tool failure.

### Invariants

- invalid tool arguments produce a `ToolResult(status="error",
  error_class="InvalidToolInput")`;
- the invalid-input result is rendered into a model-facing tool message;
- the next model turn can issue a corrected `read_file` call;
- the loop can still complete after the corrected read, write, public check,
  and final answer;
- malformed JSON remains covered by unit-level prompt-loop tests rather than
  promoted to an e2e recovery path.

## Task Manifest Tool Vocabulary Decision

### Decision

Use concrete Week 5 tool names in canonical task manifests:

```text
read_file
write_file
run_tests
```

Do not add a legacy adapter from old Week 1-4 manifest vocabulary such as:

```text
shell
edit
pytest
```

### Reasoning

`allowed_tools` is part of the task-to-agent contract. If the manifest supplies
the allowed tool list and `AgentTaskView` passes that list to the prompt loop,
then the manifest should use the actual executable agent tool names.

Adding a compatibility adapter would make the harness silently reinterpret task
permissions and create ambiguity at the exact boundary Week 5 is trying to make
explicit.

### Implementation

- Updated all `repo_patch_python_v0` task manifests to use
  `["read_file", "write_file", "run_tests"]`.
- Tightened the task manifest schema so `allowed_tools` validates against the
  concrete tool registry names.
- Added a regression test that rejects the old legacy tool vocabulary.

### Non-Goals

This is not a new task-pack baseline claim, not a new task, and not an eval
policy integration. It is a vocabulary migration so the next agent-attempt
bridge can pass manifest `allowed_tools` into `AgentTaskView` without hidden
translation.

## Agent Task Run Harness Decision

### Decision

Add a minimal harness-side agent task run:

```text
src/agentenv/orchestrators/agent_task_run.py
```

with:

```text
run_agent_task_attempt(...)
write_agent_task_run_artifacts(...)
```

### Boundary

The agent loop still receives only:

```text
AgentTaskView
ModelClient
DecodingConfig
local tools
```

The harness owns:

```text
load full task manifest
prepare agent_interaction_workspace
construct AgentTaskView from visible fields
run prompt loop
derive candidate.patch from workspace diff
submit candidate.patch through run_patch_attempt(...) in a fresh
scoring_workspace
persist agent-side and attempt-side artifacts
```

### Statuses

`AgentTaskRunResult.status` is intentionally narrow:

```text
scored
agent_loop_failed
orchestrator_error
```

`scored` means the prompt loop completed, the harness derived a candidate patch,
and the existing patch-attempt path was invoked. It does not mean task success;
task success remains `AttemptRun.result.status == PASS`.

`agent_loop_failed` means the model/agent protocol did not reach
`final_answer`, so the harness does not derive a patch or invoke hidden
scoring.

`orchestrator_error` is reserved for harness failures such as workspace setup,
patch derivation, artifact writing, or unexpected scoring invocation errors.

### Artifacts

Agent task run artifacts are separate from the existing attempt artifacts:

```text
run_manifest.json
agent_task_run.json
agent_task_view.json
prompt_loop_result.json
candidate.patch
error.txt
attempt/
```

The nested `attempt/` directory uses the existing `write_attempt_artifacts(...)`
contract unchanged.

### Invariants

- `agent_task_view.json` is harness evidence, not model-facing content.
- `agent_task_run.json` carries the full nested `AttemptResult` when scoring was
  invoked, not only a lossy attempt status.
- `manifest.allowed_tools` is passed directly into `AgentTaskView`.
- prompt-loop failure does not become an `AttemptStatus`.
- candidate patch content is opaque to the bridge: correct, wrong, partial, and
  no-op patches all belong to the existing scoring path once the loop completes.
- hidden validators remain reachable only through `run_patch_attempt(...)`.

### Workspace Vocabulary

The agent task run uses three distinct workspace concepts:

```text
seed workspace = immutable task starting files from seed_workspace
agent_interaction_workspace = workspace exposed to model-mediated tools
scoring workspace = fresh workspace prepared inside run_patch_attempt(...)
```

The harness does not score the mutated `agent_interaction_workspace` directly.
It derives `candidate.patch` from the seed workspace versus the interaction
workspace, then scores that patch in a fresh scoring workspace through the
existing patch-attempt path.

## Agent Diff Hygiene Decision

### Decision

Teach `render_directory_diff(...)` to ignore generated `.venv` directories and
after-only `uv.lock` files.

### Reasoning

The agent loop can run public checks before the harness derives
`candidate.patch`. In `uv`-based seed workspaces, that can create `.venv/`,
`.pytest_cache/`, `__pycache__/`, and a generated `uv.lock`. These are tool
side effects, not candidate source edits.

The existing attempt path captures `final.diff` before public checks, so it did
not previously see these side effects. Agent-produced patches need equivalent
artifact hygiene after tool execution.

### Invariant

Seeded `uv.lock` changes are still diffed. Only after-only `uv.lock` files are
ignored, so the diff runner does not hide lockfile changes when a task actually
ships a lockfile in `seed_workspace`.

## Scorer Control Policy Naming Decision

### Decision

Rename the existing eval policy type:

```text
control_patch -> scorer_control_patch
```

and rename the corresponding schema object:

```text
ControlPatchPolicy -> ScorerControlPatchPolicy
```

### Reasoning

The existing controls bypass the agent loop and submit known patches directly to
the patch-attempt/scoring path. They calibrate the scorer/orchestrator layer,
not the model-agent loop.

Now that Week 5 has an agent task run harness, policy names need to identify
which layer is being calibrated. `scorer_control_patch` makes the old control
path explicit and leaves room for a separate agent-loop control policy such as
an agent fake-model script.

### Non-Goals

This migration does not add an agent policy type yet. It only makes the current
scorer-control policy vocabulary precise before adding agent-loop controls.

## Scorer Control Patch Directory Decision

### Decision

Move direct patch controls under a layer-specific controls subdirectory:

```text
controls/scorer_control_patches/
```

The task manifest now records:

```yaml
controls:
  scorer_control_patches:
    oracle: controls/scorer_control_patches/oracle.patch
    bad:
      noop: controls/scorer_control_patches/bad_noop.patch
      public_only: controls/scorer_control_patches/bad_public_only.patch
```

### Reasoning

The top-level `controls/` directory will hold private eval-side calibration
artifacts for multiple harness layers. Direct patch controls calibrate the
scorer path. Future scripted fake-model controls will calibrate the agent loop.

Putting scorer controls in `controls/scorer_control_patches/` prevents the
current patch controls from occupying the generic controls namespace and leaves
a clean place for future `controls/agent_control_scripts/`.

### Non-Goals

This step does not add `agent_control_scripts/` or define the script JSON
contract. It only moves the existing direct patch controls and updates the task
manifest schema to name them precisely.

## Agent Control Script Case Decision

### Decision

Add the first task-local scripted agent control as a single nested JSON file:

```text
controls/agent_control_scripts/happy_path.json
```

The file contains:

```text
script
expected_result
```

For the first checkpoint, `expected_result` asserts only
`prompt_loop_status`.

### Reasoning

Agent control scripts calibrate the model-agent loop, not the scorer. The fake
model script and its expectation belong together because they form one
calibration case; splitting them across two files creates drift risk.

The happy-path script may still produce a valid patch and therefore flow through
the scoring harness, but the agent-control expectation intentionally does not
assert `attempt_status`, `public_status`, or `hidden_status` yet. Those outcomes
are already calibrated by scorer control patches.

### Non-Goals

This step does not add controls CLI discovery or task-manifest references for
agent control scripts. It only defines and exercises one concrete control-case
artifact.

## Malformed JSON Agent Control Decision

### Decision

Add a second task-local agent control script:

```text
controls/agent_control_scripts/malformed_json.json
```

This script emits malformed JSON from the fake model and expects:

```text
prompt_loop_status = invalid_model_output
```

### Reasoning

Malformed model JSON fails before the tool boundary. It is not recoverable
through tool feedback in the current loop contract, so the expected loop result
is terminal `invalid_model_output`.

This control uses the existing `script` plus `expected_result` shape and does
not expand the expectation schema.

## Agent Control Tool Result Expectation Decision

### Decision

Extend agent control `expected_result` with an optional structured
`tool_results` list.

Each expected tool result records:

```text
tool_name
status
error_class
```

`error_class` is required when `status = error` and forbidden when
`status = ok`.

### Reasoning

`prompt_loop_status = completed` is too weak for recovery controls. A bad-tool
input script could complete without proving that the loop surfaced a recoverable
tool error and then continued correctly.

A structured list avoids parallel-array drift and lets controls assert the
behavioral path while staying less brittle than full transcript role/content
matching.

### Non-Goals

This step only defines the expectation shape. It does not add the bad-tool-input
recovery script yet.

## Bad Tool Input Recovery Control Decision

### Decision

Add a third task-local agent control script:

```text
controls/agent_control_scripts/bad_tool_input_then_recovery.json
```

The script first emits a valid `read_file` tool action with invalid arguments,
then corrects the call, writes the fix, runs public tests, and finalizes.

The expected result asserts:

```text
prompt_loop_status = completed
tool_results = [
  read_file error InvalidToolInput
  read_file ok
  write_file ok
  run_tests ok
]
```

### Reasoning

This distinguishes recoverable tool-boundary errors from malformed model JSON.
Malformed JSON is terminal `invalid_model_output` because parsing fails before
tool execution. Invalid tool input is recoverable because the loop can return a
tool observation to the model and allow a corrected next turn.

The structured `tool_results` expectation proves the recovery path occurred
without asserting the full transcript shape.

## Required Agent Controls Decision

### Decision

Make the three initial agent control scripts required for every task in the
`repo_patch_python_v0` task pack:

```text
controls/agent_control_scripts/happy_path.json
controls/agent_control_scripts/malformed_json.json
controls/agent_control_scripts/bad_tool_input_then_recovery.json
```

The task-pack manifest now lists these paths in `required_task_files`, and
task-pack validation loads each required agent-control JSON.

The agent-control schema and loader live under:

```text
agentenv.controls.agent_control_scripts
```

### Reasoning

Agent controls calibrate the model-agent loop. If they are optional by default,
a controls report or validation pass could silently skip tasks that lack
agent-loop calibration. Making them required avoids that self-deception risk
for this pack.

The schema/loader moved out of `orchestrators/` because task validation needs to
parse the control artifacts. `tasks.validate` should not depend on an
orchestrator module just to validate task-pack files.

### Non-Goals

This step still does not add controls CLI discovery or reporting for agent
controls. It makes the artifacts required and validates/runs them in tests.

## Controls Module Boundary Decision

### Decision

Move scorer-control run code from:

```text
agentenv.orchestrators.controls_run
```

to:

```text
agentenv.controls.controls_run
```

Keep agent-control schema/loading in:

```text
agentenv.controls.agent_control_scripts
```

When `controls run` executes agent controls, it should use a harness-owned
default `DecodingConfig` rather than adding decoding fields to the task
manifest.

### Reasoning

Controls now span multiple calibration layers: scorer control patches and
agent-loop scripts. Keeping control-specific loading and run logic under a
`controls` package gives that concept an explicit home instead of scattering it
across orchestrators.

`DecodingConfig` is run policy, not task definition. Scripted fake models ignore
sampling settings, but the prompt-loop interface requires the object. A
controls-run default is enough for calibration and avoids making task manifests
model-run configuration files.
