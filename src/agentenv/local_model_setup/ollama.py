import json
import shutil
import subprocess
from dataclasses import dataclass
from time import perf_counter, sleep
from typing import Any
from urllib.parse import urlparse

import httpx

from agentenv.security.secrets import redact_secrets, scrubbed_subprocess_env


DEFAULT_MODEL_ID = "hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M"
DEEPSEEK_R1_DISTILL_QWEN_14B_MODEL_ID = (
    "hf.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF:Q4_K_M"
)
FALLBACK_MODEL_ID = "hf.co/Qwen/Qwen3-8B-GGUF:Q4_K_M"
DEFAULT_SERVER_URL = "http://localhost:11434"
DEFAULT_OPENAI_BASE_URL = f"{DEFAULT_SERVER_URL}/v1"
DEFAULT_SMOKE_PROMPT = (
    'Return exactly this JSON and nothing else: {"action":"final_answer","text":"ok"}'
)
DEFAULT_SMOKE_SYSTEM_SUFFIX = "/no_think"


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


@dataclass(frozen=True)
class OllamaModelSetupResult:
    model_id: str
    server_url: str
    base_url: str
    started_server: bool
    server_kept_running: bool
    probe_before: OllamaProbe
    probe_after: OllamaProbe | None
    pull_result: CommandResult | None
    smoke_result: ChatSmokeResult | None
    error_class: str | None = None
    error_message: str | None = None

    @property
    def status(self) -> str:
        return "ok" if self.error_class is None else "error"


@dataclass(frozen=True)
class EvalSmokeProfile:
    config_path: str
    policy: str
    out_dir: str
    smoke_system_suffix: str | None = None


EVAL_SMOKE_PROFILES: dict[str, EvalSmokeProfile] = {
    DEFAULT_MODEL_ID: EvalSmokeProfile(
        config_path="configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml",
        policy="local-qwen-smoke",
        out_dir="experiments/runs/agent_model_smoke_ollama_qwen3_14b",
    ),
    DEEPSEEK_R1_DISTILL_QWEN_14B_MODEL_ID: EvalSmokeProfile(
        config_path=(
            "configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml"
        ),
        policy="local-deepseek-r1-distill-qwen-smoke",
        out_dir=(
            "experiments/runs/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b"
        ),
        smoke_system_suffix="",
    ),
}


def render_setup_plan(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    fallback_model_id: str = FALLBACK_MODEL_ID,
) -> str:
    profile = EVAL_SMOKE_PROFILES.get(model_id)
    lines = [
        "Install Ollama:",
        "  curl -fsSL https://ollama.com/install.sh | sh",
        "",
        "Download and smoke test a model:",
        *_model_command_lines("setup", model_id, profile),
        "",
        "If VRAM is too tight, use the fallback model:",
        "  uv run agentenv local-model ollama setup \\",
        f"    --model-id {fallback_model_id}",
        "",
        "Use the OpenAI-compatible local endpoint for evals:",
        f"  export AGENTENV_MODEL_BASE_URL={DEFAULT_OPENAI_BASE_URL}",
        "",
        "Probe the local server:",
        "  uv run agentenv local-model ollama probe",
        "",
        "Run a direct chat-completions smoke:",
        *_model_command_lines("smoke", model_id, profile),
        "",
        "Run the eval smoke after the server is healthy:",
    ]
    if profile is None:
        lines.extend(
            [
                "  # Add or choose a matching config under configs/eval/",
                "  # agent_model_smoke_ollama_*.yaml, then run:",
                "  uv run agentenv eval \\",
                "    --config <matching-eval-config.yaml> \\",
                "    --policy <matching-policy> \\",
                "    --out experiments/runs/<matching-run-name>",
            ]
        )
    else:
        lines.extend(
            [
                "  uv run agentenv eval \\",
                f"    --config {profile.config_path} \\",
                f"    --policy {profile.policy} \\",
                f"    --out {profile.out_dir}",
            ]
        )
    return "\n".join(lines) + "\n"


def _model_command_lines(
    command: str,
    model_id: str,
    profile: EvalSmokeProfile | None,
) -> list[str]:
    lines = [
        f"  uv run agentenv local-model ollama {command} \\",
        f"    --model-id {model_id}",
    ]
    if profile is not None and profile.smoke_system_suffix is not None:
        lines[-1] += " \\"
        lines.append(f"    --system-suffix {json.dumps(profile.smoke_system_suffix)}")
    return lines


def install_command() -> str:
    return "curl -fsSL https://ollama.com/install.sh | sh"


def serve_command() -> list[str]:
    return ["ollama", "serve"]


def pull_command(model_id: str = DEFAULT_MODEL_ID) -> list[str]:
    return ["ollama", "pull", model_id]


def run_command(model_id: str = DEFAULT_MODEL_ID) -> list[str]:
    return ["ollama", "run", model_id]


def start_ollama_server(
    *,
    server_url: str = DEFAULT_SERVER_URL,
) -> subprocess.Popen[bytes]:
    env = scrubbed_subprocess_env()
    ollama_host = _ollama_host_from_server_url(server_url)
    if ollama_host is not None:
        env["OLLAMA_HOST"] = ollama_host
    return subprocess.Popen(
        serve_command(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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


def setup_ollama_model(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    server_url: str = DEFAULT_SERVER_URL,
    base_url: str | None = None,
    smoke_prompt: str = DEFAULT_SMOKE_PROMPT,
    smoke_system_suffix: str | None = DEFAULT_SMOKE_SYSTEM_SUFFIX,
    pull_timeout_seconds: int = 3600,
    smoke_timeout_seconds: float = 120.0,
    start_server: bool = True,
    keep_server_running: bool = True,
    server_start_timeout_seconds: float = 30.0,
) -> OllamaModelSetupResult:
    resolved_base_url = base_url or f"{server_url.rstrip('/')}/v1"
    probe_before = probe_ollama(server_url=server_url)
    if probe_before.ollama_path is None:
        return _setup_error(
            model_id=model_id,
            server_url=server_url,
            base_url=resolved_base_url,
            probe_before=probe_before,
            error_class="MissingOllamaBinary",
            error_message="ollama was not found on PATH",
        )

    server_process: subprocess.Popen[bytes] | None = None
    started_server = False
    try:
        ready_probe = probe_before
        if not ready_probe.server_running:
            if not start_server:
                return _setup_error(
                    model_id=model_id,
                    server_url=server_url,
                    base_url=resolved_base_url,
                    probe_before=probe_before,
                    error_class="OllamaServerNotRunning",
                    error_message="ollama server is not running",
                )
            try:
                server_process = start_ollama_server(server_url=server_url)
            except OSError as exc:
                return _setup_error(
                    model_id=model_id,
                    server_url=server_url,
                    base_url=resolved_base_url,
                    probe_before=probe_before,
                    error_class=exc.__class__.__name__,
                    error_message=redact_secrets(str(exc)),
                )
            started_server = True
            ready_probe = wait_for_ollama(
                server_url=server_url,
                timeout_seconds=server_start_timeout_seconds,
            )
            if not ready_probe.server_running:
                return _setup_error(
                    model_id=model_id,
                    server_url=server_url,
                    base_url=resolved_base_url,
                    probe_before=probe_before,
                    error_class="OllamaServerStartTimeout",
                    error_message=ready_probe.error_message,
                )

        pull_result = pull_model(
            model_id=model_id,
            timeout_seconds=pull_timeout_seconds,
        )
        if pull_result.returncode != 0:
            return _setup_error(
                model_id=model_id,
                server_url=server_url,
                base_url=resolved_base_url,
                probe_before=probe_before,
                probe_after=ready_probe,
                pull_result=pull_result,
                started_server=started_server,
                server_kept_running=started_server and keep_server_running,
                error_class="OllamaPullFailed",
                error_message=pull_result.stderr or pull_result.stdout,
            )

        smoke_result = run_chat_smoke(
            model_id=model_id,
            base_url=resolved_base_url,
            prompt=smoke_prompt,
            system_suffix=smoke_system_suffix,
            timeout_seconds=smoke_timeout_seconds,
        )
        probe_after = probe_ollama(server_url=server_url)
        if smoke_result.status != "ok":
            return _setup_error(
                model_id=model_id,
                server_url=server_url,
                base_url=resolved_base_url,
                probe_before=probe_before,
                probe_after=probe_after,
                pull_result=pull_result,
                smoke_result=smoke_result,
                started_server=started_server,
                server_kept_running=started_server and keep_server_running,
                error_class="OllamaSmokeFailed",
                error_message=smoke_result.error_message,
            )

        return OllamaModelSetupResult(
            model_id=model_id,
            server_url=server_url,
            base_url=resolved_base_url,
            started_server=started_server,
            server_kept_running=started_server and keep_server_running,
            probe_before=probe_before,
            probe_after=probe_after,
            pull_result=pull_result,
            smoke_result=smoke_result,
        )
    finally:
        if server_process is not None and not keep_server_running:
            _terminate_process(server_process)


def wait_for_ollama(
    *,
    server_url: str = DEFAULT_SERVER_URL,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.5,
) -> OllamaProbe:
    deadline = perf_counter() + timeout_seconds
    last_probe = probe_ollama(server_url=server_url)
    while perf_counter() < deadline:
        if last_probe.server_running:
            return last_probe
        sleep(poll_interval_seconds)
        last_probe = probe_ollama(server_url=server_url)
    return last_probe


def run_chat_smoke(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    prompt: str = DEFAULT_SMOKE_PROMPT,
    system_suffix: str | None = None,
    timeout_seconds: float = 120.0,
    http_client: httpx.Client | None = None,
) -> ChatSmokeResult:
    messages: list[dict[str, str]] = []
    if system_suffix:
        messages.append({"role": "system", "content": system_suffix})
    messages.append({"role": "user", "content": prompt})
    payload: dict[str, object] = {
        "model": model_id,
        "messages": messages,
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
            error_message=_provider_error_message(
                response.status_code, response_payload
            ),
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


def render_setup_result(result: OllamaModelSetupResult) -> str:
    lines = [
        f"ollama_setup={result.status}",
        f"model_id={result.model_id}",
        f"server_url={result.server_url}",
        f"base_url={result.base_url}",
        f"started_server={'yes' if result.started_server else 'no'}",
        f"server_kept_running={'yes' if result.server_kept_running else 'no'}",
    ]
    if result.pull_result is not None:
        lines.append(f"pull_exit={result.pull_result.returncode}")
    if result.smoke_result is not None:
        lines.append(f"smoke_status={result.smoke_result.status}")
        if result.smoke_result.finish_reason is not None:
            lines.append(f"smoke_finish_reason={result.smoke_result.finish_reason}")
        if result.smoke_result.output_text:
            lines.append(f"smoke_output={result.smoke_result.output_text}")
    if result.probe_after is not None and result.probe_after.model_ids:
        lines.append("models=" + ",".join(result.probe_after.model_ids))
    if result.error_class is not None:
        lines.append(f"error_class={result.error_class}")
    if result.error_message is not None:
        lines.append(f"error_message={result.error_message}")
    return "\n".join(lines) + "\n"


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
    except OSError as exc:
        return CommandResult(
            command=[redact_secrets(part) for part in command],
            returncode=127,
            stdout="",
            stderr=redact_secrets(str(exc)),
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


def _setup_error(
    *,
    model_id: str,
    server_url: str,
    base_url: str,
    probe_before: OllamaProbe,
    error_class: str,
    error_message: str | None,
    probe_after: OllamaProbe | None = None,
    pull_result: CommandResult | None = None,
    smoke_result: ChatSmokeResult | None = None,
    started_server: bool = False,
    server_kept_running: bool = False,
) -> OllamaModelSetupResult:
    return OllamaModelSetupResult(
        model_id=model_id,
        server_url=server_url,
        base_url=base_url,
        started_server=started_server,
        server_kept_running=server_kept_running,
        probe_before=probe_before,
        probe_after=probe_after,
        pull_result=pull_result,
        smoke_result=smoke_result,
        error_class=error_class,
        error_message=redact_secrets(error_message) if error_message else None,
    )


def _ollama_host_from_server_url(server_url: str) -> str | None:
    parsed = urlparse(server_url)
    if parsed.hostname is None:
        return None
    if parsed.port is None:
        return parsed.hostname
    return f"{parsed.hostname}:{parsed.port}"


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


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
