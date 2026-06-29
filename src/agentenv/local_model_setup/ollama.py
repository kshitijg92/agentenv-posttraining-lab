import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

import httpx

from agentenv.security.secrets import redact_secrets, scrubbed_subprocess_env


DEFAULT_MODEL_ID = "hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M"
FALLBACK_MODEL_ID = "hf.co/Qwen/Qwen3-8B-GGUF:Q4_K_M"
DEFAULT_SERVER_URL = "http://localhost:11434"
DEFAULT_OPENAI_BASE_URL = f"{DEFAULT_SERVER_URL}/v1"
DEFAULT_SMOKE_PROMPT = (
    'Return exactly this JSON and nothing else: {"action":"final_answer","text":"ok"} '
    "/no_think"
)


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class OllamaProbe:
    ollama_path: str | None
    server_url: str
    server_running: bool
    version: str | None
    model_ids: list[str]
    error_class: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ChatSmokeResult:
    model_id: str
    base_url: str
    status: str
    output_text: str
    finish_reason: str | None
    error_class: str | None = None
    error_message: str | None = None


def render_setup_plan(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    fallback_model_id: str = FALLBACK_MODEL_ID,
) -> str:
    return "\n".join([
        "Install Ollama:",
        "  curl -fsSL https://ollama.com/install.sh | sh",
        "",
        "Start or pull the first-choice model:",
        f"  ollama run {model_id}",
        "",
        "If VRAM is too tight, use the fallback model:",
        f"  ollama run {fallback_model_id}",
        "",
        "Use the OpenAI-compatible local endpoint for evals:",
        f"  export AGENTENV_MODEL_BASE_URL={DEFAULT_OPENAI_BASE_URL}",
        "",
        "Probe the local server:",
        "  uv run agentenv local-model ollama probe",
        "",
        "Run a direct chat-completions smoke:",
        "  uv run agentenv local-model ollama smoke",
        "",
        "Run the eval smoke after the server is healthy:",
        "  uv run agentenv eval \\",
        "    --config configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml \\",
        "    --policy local-qwen-smoke \\",
        "    --out experiments/runs/agent_model_smoke_ollama_qwen3_14b",
    ]) + "\n"


def install_command() -> str:
    return "curl -fsSL https://ollama.com/install.sh | sh"


def serve_command() -> list[str]:
    return ["ollama", "serve"]


def pull_command(model_id: str = DEFAULT_MODEL_ID) -> list[str]:
    return ["ollama", "pull", model_id]


def run_command(model_id: str = DEFAULT_MODEL_ID) -> list[str]:
    return ["ollama", "run", model_id]


def probe_ollama(
    *,
    server_url: str = DEFAULT_SERVER_URL,
    timeout_seconds: float = 2.0,
    http_client: httpx.Client | None = None,
) -> OllamaProbe:
    ollama_path = shutil.which("ollama")
    client = http_client or httpx.Client(timeout=timeout_seconds)
    close_client = http_client is None
    try:
        version_payload = _get_json(client, f"{server_url.rstrip('/')}/api/version")
        model_payload = _get_json(client, f"{server_url.rstrip('/')}/v1/models")
    except (httpx.HTTPError, ValueError) as exc:
        return OllamaProbe(
            ollama_path=ollama_path,
            server_url=server_url,
            server_running=False,
            version=None,
            model_ids=[],
            error_class=exc.__class__.__name__,
            error_message=redact_secrets(str(exc)),
        )
    finally:
        if close_client:
            client.close()

    return OllamaProbe(
        ollama_path=ollama_path,
        server_url=server_url,
        server_running=True,
        version=_optional_str(version_payload.get("version")),
        model_ids=_model_ids(model_payload),
    )


def pull_model(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    timeout_seconds: int = 3600,
) -> CommandResult:
    return _run_local_command(pull_command(model_id), timeout_seconds=timeout_seconds)


def run_chat_smoke(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    prompt: str = DEFAULT_SMOKE_PROMPT,
    timeout_seconds: float = 120.0,
    http_client: httpx.Client | None = None,
) -> ChatSmokeResult:
    payload: dict[str, object] = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 128,
    }
    client = http_client or httpx.Client(timeout=timeout_seconds)
    close_client = http_client is None
    try:
        response = client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            json=payload,
            timeout=timeout_seconds,
        )
    except httpx.RequestError as exc:
        return ChatSmokeResult(
            model_id=model_id,
            base_url=base_url,
            status="request_error",
            output_text="",
            finish_reason=None,
            error_class=exc.__class__.__name__,
            error_message=redact_secrets(str(exc)),
        )
    finally:
        if close_client:
            client.close()

    try:
        response_payload = response.json()
    except ValueError:
        return ChatSmokeResult(
            model_id=model_id,
            base_url=base_url,
            status="malformed_response",
            output_text="",
            finish_reason=None,
            error_class="MalformedProviderResponse",
            error_message=f"HTTP {response.status_code} non-JSON response",
        )

    if response.status_code >= 400:
        return ChatSmokeResult(
            model_id=model_id,
            base_url=base_url,
            status="provider_error",
            output_text="",
            finish_reason=None,
            error_class="ProviderHTTPError",
            error_message=_provider_error_message(response.status_code, response_payload),
        )

    choice = _first_choice(response_payload)
    if choice is None:
        return ChatSmokeResult(
            model_id=model_id,
            base_url=base_url,
            status="malformed_response",
            output_text="",
            finish_reason=None,
            error_class="MalformedProviderResponse",
            error_message="Missing choices[0].message.content",
        )

    return ChatSmokeResult(
        model_id=model_id,
        base_url=base_url,
        status="ok",
        output_text=redact_secrets(choice["output_text"]),
        finish_reason=choice["finish_reason"],
    )


def _run_local_command(
    command: list[str],
    *,
    timeout_seconds: int,
) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=scrubbed_subprocess_env(),
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=[redact_secrets(part) for part in command],
            returncode=124,
            stdout=redact_secrets(_stream_text(exc.stdout)),
            stderr=redact_secrets(_stream_text(exc.stderr)),
        )

    return CommandResult(
        command=[redact_secrets(part) for part in command],
        returncode=completed.returncode,
        stdout=redact_secrets(completed.stdout),
        stderr=redact_secrets(completed.stderr),
    )


def _get_json(client: httpx.Client, url: str) -> dict[str, Any]:
    response = client.get(url)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object")
    return payload


def _model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    model_ids: list[str] = []
    for item in data:
        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str):
                model_ids.append(model_id)
    return sorted(model_ids)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _provider_error_message(status_code: int, payload: object) -> str:
    message = f"HTTP {status_code}"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            details = {
                key: value
                for key in ("type", "code", "message")
                if (value := error.get(key)) is not None
            }
            if details:
                message = f"{message} {json.dumps(details, sort_keys=True)}"
    return redact_secrets(message)


def _first_choice(payload: object) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        return None
    finish_reason = first_choice.get("finish_reason")
    return {
        "output_text": content,
        "finish_reason": finish_reason if isinstance(finish_reason, str) else "",
    }


def _stream_text(stream: object) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return str(stream)
