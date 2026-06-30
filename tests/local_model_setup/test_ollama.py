import json
import subprocess
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from agentenv.local_model_setup import ollama
from agentenv.local_model_setup import setup_ollama_model as setup_script
from agentenv.security.secrets import REDACTED_SECRET


CANARY = "agentenv-canary-secret-000000000000"


def test_render_setup_plan_contains_known_eval_smoke_command() -> None:
    plan = ollama.render_setup_plan(model_id=ollama.DEFAULT_MODEL_ID)

    assert "uv run agentenv local-model ollama setup" in plan
    assert f"--model-id {ollama.DEFAULT_MODEL_ID}" in plan
    assert "AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1" in plan
    assert "configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml" in plan


def test_render_setup_plan_contains_deepseek_eval_smoke_command() -> None:
    plan = ollama.render_setup_plan(
        model_id=ollama.DEEPSEEK_R1_DISTILL_QWEN_14B_MODEL_ID
    )

    assert f"--model-id {ollama.DEEPSEEK_R1_DISTILL_QWEN_14B_MODEL_ID}" in plan
    assert (
        "configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml"
        in plan
    )
    assert '--system-suffix ""' in plan
    assert "local-deepseek-r1-distill-qwen-smoke" in plan


def test_render_setup_plan_uses_generic_eval_smoke_guidance_for_unknown_model() -> None:
    plan = ollama.render_setup_plan(model_id="custom-model")

    assert "--model-id custom-model" in plan
    assert "agent_model_smoke_ollama_*.yaml" in plan
    assert "<matching-policy>" in plan
    assert "configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml" not in plan


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
        assert command == ["ollama", "pull", "custom-model"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=f"downloaded {CANARY}\n",
            stderr="",
        )

    monkeypatch.setattr(ollama.subprocess, "run", fake_run)

    result = ollama.pull_model(model_id="custom-model")

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
    result = ollama.run_chat_smoke(
        model_id="custom-model",
        system_suffix="/no_think",
        http_client=client,
    )

    assert result.status == "ok"
    assert result.output_text == '{"action":"final_answer","text":"ok"}'
    assert requests[0].url.path == "/v1/chat/completions"
    assert httpx.Request(
        "POST",
        "http://localhost:11434/v1/chat/completions",
    ).url == requests[0].url
    payload = json.loads(requests[0].content)
    assert payload["model"] == "custom-model"
    assert payload["messages"] == [
        {"role": "system", "content": "/no_think"},
        {"role": "user", "content": ollama.DEFAULT_SMOKE_PROMPT},
    ]


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


def test_setup_ollama_model_pulls_and_smokes_requested_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = ollama.OllamaProbe(
        ollama_path="/usr/bin/ollama",
        server_url=ollama.DEFAULT_SERVER_URL,
        server_running=True,
        version="1.2.3",
        model_ids=["custom-model"],
    )
    calls: dict[str, object] = {}

    monkeypatch.setattr(ollama, "probe_ollama", lambda **kwargs: probe)

    def fake_pull_model(
        *,
        model_id: str,
        timeout_seconds: int,
    ) -> ollama.CommandResult:
        calls["pull"] = (model_id, timeout_seconds)
        return ollama.CommandResult(
            command=["ollama", "pull", model_id],
            returncode=0,
            stdout="",
            stderr="",
        )

    def fake_run_chat_smoke(
        *,
        model_id: str,
        base_url: str,
        prompt: str,
        system_suffix: str | None,
        timeout_seconds: float,
        http_client: httpx.Client | None = None,
    ) -> ollama.ChatSmokeResult:
        del http_client
        calls["smoke"] = (
            model_id,
            base_url,
            prompt,
            system_suffix,
            timeout_seconds,
        )
        return ollama.ChatSmokeResult(
            model_id=model_id,
            base_url=base_url,
            status="ok",
            output_text='{"action":"final_answer","text":"ok"}',
            finish_reason="stop",
        )

    monkeypatch.setattr(ollama, "pull_model", fake_pull_model)
    monkeypatch.setattr(ollama, "run_chat_smoke", fake_run_chat_smoke)

    result = ollama.setup_ollama_model(
        model_id="custom-model",
        smoke_system_suffix=None,
    )

    assert result.status == "ok"
    assert result.started_server is False
    assert calls["pull"] == ("custom-model", 3600)
    assert calls["smoke"] == (
        "custom-model",
        "http://localhost:11434/v1",
        ollama.DEFAULT_SMOKE_PROMPT,
        None,
        120.0,
    )


def test_setup_ollama_model_reports_missing_server_when_not_starting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = ollama.OllamaProbe(
        ollama_path="/usr/bin/ollama",
        server_url=ollama.DEFAULT_SERVER_URL,
        server_running=False,
        version=None,
        model_ids=[],
        error_class="ConnectError",
        error_message="connection refused",
    )
    monkeypatch.setattr(ollama, "probe_ollama", lambda **kwargs: probe)

    result = ollama.setup_ollama_model(start_server=False)

    assert result.status == "error"
    assert result.error_class == "OllamaServerNotRunning"


def test_setup_script_parses_model_id_and_empty_system_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_setup_ollama_model(**kwargs: object) -> ollama.OllamaModelSetupResult:
        captured.update(kwargs)
        probe = ollama.OllamaProbe(
            ollama_path="/usr/bin/ollama",
            server_url=ollama.DEFAULT_SERVER_URL,
            server_running=True,
            version="1.2.3",
            model_ids=["custom-model"],
        )
        return ollama.OllamaModelSetupResult(
            model_id=str(kwargs["model_id"]),
            server_url=str(kwargs["server_url"]),
            base_url="http://localhost:11434/v1",
            started_server=False,
            server_kept_running=False,
            probe_before=probe,
            probe_after=probe,
            pull_result=None,
            smoke_result=None,
        )

    monkeypatch.setattr(setup_script, "setup_ollama_model", fake_setup_ollama_model)

    result = CliRunner().invoke(
        setup_script.app,
        [
            "--model-id",
            "custom-model",
            "--system-suffix",
            "",
        ],
    )

    assert result.exit_code == 0
    assert captured["model_id"] == "custom-model"
    assert captured["smoke_system_suffix"] is None
    assert "ollama_setup=ok" in result.output
