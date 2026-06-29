import subprocess
from pathlib import Path

import httpx
import pytest

from agentenv.local_model_setup import ollama
from agentenv.security.secrets import REDACTED_SECRET


CANARY = "agentenv-canary-secret-000000000000"


def test_render_setup_plan_contains_eval_smoke_command() -> None:
    plan = ollama.render_setup_plan()

    assert "ollama run hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M" in plan
    assert "AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1" in plan
    assert "configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml" in plan


def test_probe_ollama_reads_version_and_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ollama.shutil, "which", lambda command: "/usr/bin/ollama")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "1.2.3"})
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M"},
                        {"id": "other-model"},
                    ]
                },
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    probe = ollama.probe_ollama(http_client=client)

    assert probe.ollama_path == "/usr/bin/ollama"
    assert probe.server_running is True
    assert probe.version == "1.2.3"
    assert probe.model_ids == [
        "hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M",
        "other-model",
    ]


def test_pull_model_scrubs_sensitive_env_and_redacts_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    del tmp_path
    monkeypatch.setenv("HF_TOKEN", CANARY)
    captured_env: dict[str, str] = {}

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        env: dict[str, str],
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del check
        del capture_output
        del text
        del timeout
        captured_env.update(env)
        assert command == ["ollama", "pull", ollama.DEFAULT_MODEL_ID]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"downloaded {CANARY}\n",
            stderr="",
        )

    monkeypatch.setattr(ollama.subprocess, "run", fake_run)

    result = ollama.pull_model()

    assert "HF_TOKEN" not in captured_env
    assert result.returncode == 0
    assert result.stdout == f"downloaded {REDACTED_SECRET}\n"


def test_run_chat_smoke_uses_openai_compatible_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"action":"final_answer","text":"ok"}'},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = ollama.run_chat_smoke(http_client=client)

    assert result.status == "ok"
    assert result.output_text == '{"action":"final_answer","text":"ok"}'
    assert requests[0].url.path == "/v1/chat/completions"
    assert httpx.Request(
        "POST",
        "http://localhost:11434/v1/chat/completions",
    ).url == requests[0].url


def test_run_chat_smoke_redacts_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HF_TOKEN", CANARY)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            500,
            json={"error": {"message": f"provider echoed {CANARY}"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = ollama.run_chat_smoke(http_client=client)

    assert result.status == "provider_error"
    assert result.error_message is not None
    assert CANARY not in result.error_message
    assert REDACTED_SECRET in result.error_message
