from __future__ import annotations

import typer

from agentenv.local_model_setup.ollama import (
    DEFAULT_MODEL_ID,
    DEFAULT_SERVER_URL,
    DEFAULT_SMOKE_PROMPT,
    DEFAULT_SMOKE_SYSTEM_SUFFIX,
    render_setup_result,
    setup_ollama_model,
)


app = typer.Typer(add_completion=False, no_args_is_help=False)


@app.command()
def main(
    model_id: str = typer.Option(
        DEFAULT_MODEL_ID,
        "--model-id",
        "--model",
        help="Ollama or Hugging Face model id.",
    ),
    server_url: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server-url",
        help="Ollama server URL.",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="OpenAI-compatible base URL. Defaults to SERVER_URL/v1.",
    ),
    smoke_prompt: str = typer.Option(
        DEFAULT_SMOKE_PROMPT,
        "--smoke-prompt",
        help="Prompt used for the chat-completions smoke test.",
    ),
    system_suffix: str = typer.Option(
        DEFAULT_SMOKE_SYSTEM_SUFFIX,
        "--system-suffix",
        help='Optional system message for smoke testing. Use "" to disable.',
    ),
    pull_timeout_seconds: int = typer.Option(
        3600,
        "--pull-timeout-seconds",
        help="Timeout for model download.",
    ),
    smoke_timeout_seconds: float = typer.Option(
        120.0,
        "--smoke-timeout-seconds",
        help="Timeout for the smoke request.",
    ),
    server_start_timeout_seconds: float = typer.Option(
        30.0,
        "--server-start-timeout-seconds",
        help="Time to wait after starting ollama serve.",
    ),
    start_server: bool = typer.Option(
        True,
        "--start-server/--no-start-server",
        help="Start ollama serve if the server is not already running.",
    ),
    keep_server_running: bool = typer.Option(
        True,
        "--keep-server-running/--stop-started-server",
        help="Keep a server started by this script running after setup.",
    ),
) -> None:
    result = setup_ollama_model(
        model_id=model_id,
        server_url=server_url,
        base_url=base_url,
        smoke_prompt=smoke_prompt,
        smoke_system_suffix=system_suffix or None,
        pull_timeout_seconds=pull_timeout_seconds,
        smoke_timeout_seconds=smoke_timeout_seconds,
        start_server=start_server,
        keep_server_running=keep_server_running,
        server_start_timeout_seconds=server_start_timeout_seconds,
    )
    typer.echo(render_setup_result(result), nl=False)
    if result.status != "ok":
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
