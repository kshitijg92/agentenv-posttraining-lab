# Local Model Setup

This package holds repeatable setup helpers for running local models behind an
OpenAI-compatible endpoint. The current supported path is Ollama.

## Prerequisites

Install Ollama first. The setup script does not run the official installer or
use sudo.

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

If Ollama is installed in a user-local location, make sure `ollama` is on
`PATH`.

## One-Shot Ollama Setup

Download a model and smoke test the local chat endpoint:

```bash
uv run python -m agentenv.local_model_setup.setup_ollama_model \
  --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
```

The script:

- checks that the `ollama` binary exists
- starts `ollama serve` if the server is not already running
- runs `ollama pull <model-id>`
- calls `http://localhost:11434/v1/chat/completions`
- prints a compact setup summary

By default, if the script starts the server, it leaves the server running so the
same session can immediately run evals. To stop a server started by the script:

```bash
uv run python -m agentenv.local_model_setup.setup_ollama_model \
  --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M \
  --stop-started-server
```

For non-Qwen models, disable the Qwen-specific no-thinking system message:

```bash
uv run python -m agentenv.local_model_setup.setup_ollama_model \
  --model-id llama3.1:8b \
  --system-suffix ""
```

## CLI Commands

The same setup flow is exposed through the main CLI:

```bash
uv run agentenv local-model ollama setup \
  --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
```

Useful lower-level commands:

```bash
uv run agentenv local-model ollama plan --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
uv run agentenv local-model ollama probe
uv run agentenv local-model ollama pull --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
uv run agentenv local-model ollama smoke --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
uv run agentenv local-model ollama serve-command
```

The default model is currently `hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M`, but every
command accepts `--model-id`.

## Eval Smoke

After setup succeeds:

```bash
export AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1

uv run agentenv eval \
  --config configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml \
  --policy local-qwen-smoke \
  --out experiments/runs/agent_model_smoke_ollama_qwen3_14b
```
