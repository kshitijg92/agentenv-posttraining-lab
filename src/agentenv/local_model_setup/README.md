# Local Model Setup

This package holds repeatable setup helpers for running local models through
Ollama. Existing model configs use Ollama's OpenAI-compatible endpoint; the
Qwen2.5-Coder-3B config instead uses AgentEnv-owned prompt rendering through
Ollama's native generate endpoint.

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

## Additional Local Models

DeepSeek R1 Distill Qwen 14B can be pulled and smoke tested through the same
Ollama setup path:

```bash
uv run agentenv local-model ollama setup \
  --model-id hf.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF:Q4_K_M \
  --system-suffix ""
```

The matching model and eval configs are:

```text
configs/models/ollama_deepseek_r1_distill_qwen_14b_q4_k_m.yaml
configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml
configs/eval/agent_model_dev_ollama_deepseek_r1_distill_qwen_14b.yaml
```

The DeepSeek config does not add the Qwen3 `/no_think` prompt adapter. Week 6
should probe whether this reasoning model needs a larger decoding budget or a
separate prompt adapter before using it as a serious eval baseline.

## Eval Smoke

After setup succeeds:

```bash
export AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1

uv run agentenv eval \
  --config configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml \
  --policy local-qwen-smoke \
  --out experiments/runs/agent_model_smoke_ollama_qwen3_14b
```

For the DeepSeek R1 Distill Qwen smoke:

```bash
uv run agentenv eval \
  --config configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml \
  --policy local-deepseek-r1-distill-qwen-smoke \
  --out experiments/runs/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b
```

The protocol-owned Qwen2.5-Coder-3B path requires the native Ollama server root
without an OpenAI-compatible `/v1` suffix:

```bash
export AGENTENV_OLLAMA_BASE_URL=http://localhost:11434
```

Its model config is
`configs/models/ollama_qwen2_5_coder_3b.yaml`. The separate environment
variable makes it explicit whether a policy is using provider-owned
OpenAI-compatible chat serialization or AgentEnv-owned raw generation.

## Qwen2.5 Base-Plus-LoRA Serving

Ollama can serve the exact pinned Qwen2.5 base and a PEFT adapter after both
are converted to separate GGUF files. The adapter is not merged into the base.
This remains a local setup operation: the existing LoRA training manifest owns
the source adapter provenance, while the model config pins the registered
Ollama model id and manifest digest.

Use a pinned `llama.cpp` checkout. The compatibility path was verified at:

```text
ggml-org/llama.cpp commit:
030ebb558a5820b444a8f836ed5cdd46c9b4bd7a
```

Convert the exact Hugging Face snapshot and the adapter published by a
completed LoRA training run:

```bash
uv run --project <llama-cpp> python <llama-cpp>/convert_hf_to_gguf.py \
  <exact-hugging-face-snapshot> \
  --outfile <serving-dir>/base-f16.gguf \
  --outtype f16

uv run --project <llama-cpp> python <llama-cpp>/convert_lora_to_gguf.py \
  <completed-training-run>/adapter \
  --base <exact-hugging-face-snapshot> \
  --outfile <serving-dir>/adapter-f16.gguf \
  --outtype f16
```

The base Modelfile contains:

```text
FROM /absolute/path/to/base-f16.gguf
```

The adapted Modelfile contains:

```text
FROM /absolute/path/to/base-f16.gguf
ADAPTER /absolute/path/to/adapter-f16.gguf
```

Register separate immutable identities:

```bash
ollama create <base-model-id> -f <base-Modelfile>
ollama create <adapted-model-id> -f <adapted-Modelfile>
curl -sS http://127.0.0.1:11434/api/tags
```

Copy each observed manifest digest into its `ollama_generate` model config.
Set `adapter: null` for the base. For an adapted policy, set `adapter` to the
hash-pinned completed LoRA training manifest. Loading the config then validates
that the source adapter package, base checkpoint, and model-input protocol still
match before evaluation begins.
