# DeepSeek R1 Local Decision

## Question

Can `hf.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF:Q4_K_M` be used as a
local Week 6 agent-model baseline under the current strict JSON action protocol?

## Result

Not yet.

The model and endpoint are reachable, but this reasoning model does not reliably
produce exactly one JSON action per turn after tool observations.

## Evidence

Setup/probe succeeded:

```text
ollama_setup=ok
pull_exit=0
smoke_status=ok
server_url=http://localhost:11434
base_url=http://localhost:11434/v1
```

The first eval attempt initially failed operationally because Ollama was not
running:

```text
ProviderRequestError
ConnectError: [Errno 111] Connection refused
```

After starting `ollama serve`, the toy smoke reached the model. The first model
turn emitted a valid `write_file` JSON tool call and the harness executed it.

The second turn emitted prose plus a reasoning close tag before the next JSON
tool call:

```text
The file was written successfully. Now, I need to test it.
</think>

{"action":"tool_call","arguments":{"command":"uv run pytest tests/test_public.py"},"tool_name":"run_tests"}
```

The harness correctly classified this as:

```text
prompt_loop_status=invalid_model_output
error_class=MalformedModelOutput
```

## Thinking Disable Probe

The Qwen local config uses:

```yaml
prompt_adapter:
  system_suffix: /no_think
```

Equivalent DeepSeek probes did not disable reasoning:

- `/no_think` as a system message still produced a `reasoning` field.
- OpenAI-compatible `think: false` still produced a `reasoning` field.
- Native Ollama `/api/chat` with `think: false` still produced a `thinking`
  field.

## Decision

Do not weaken the global parser or prompt for Week 6.

Do not add a DeepSeek-specific adapter yet.

Treat DeepSeek R1 Distill Qwen as unsupported under the current strict JSON
action protocol. Revisit it later as an explicit thinking-model adapter design
problem, likely after trajectory/protocol observability work.

## Non-Claim

This is not evidence that DeepSeek is bad at coding tasks. It is evidence that
this local reasoning-model endpoint is not currently compatible with this lab's
strict one-JSON-action agent protocol.
