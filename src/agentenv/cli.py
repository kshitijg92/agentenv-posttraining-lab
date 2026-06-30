from pathlib import Path

import typer
from rich.console import Console

from agentenv.agents.audit import run_agent_task_audit
from agentenv.artifacts import ArtifactDirectoryError
from agentenv.controls.controls_run import run_controls
from agentenv.local_model_setup.ollama import (
    DEFAULT_MODEL_ID,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_SERVER_URL,
    DEFAULT_SMOKE_PROMPT,
    DEFAULT_SMOKE_SYSTEM_SUFFIX,
    FALLBACK_MODEL_ID,
    pull_model,
    render_setup_result,
    render_setup_plan,
    run_chat_smoke,
    serve_command,
    setup_ollama_model,
)
from agentenv.orchestrators.eval_run import (
    EvalMatrixRun,
    EvalRun,
    run_eval_config,
    run_eval_config_all_policies,
)
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.replay.runner import run_replay
from agentenv.reporting.markdown import write_markdown_report
from agentenv.sandbox.docker_smoke import run_docker_smoke
from agentenv.scorers.audit import run_scorer_audit
from agentenv.tasks.validate import (
    load_task_manifest,
    validate_task_manifest_paths,
    validate_task_pack,
)


app = typer.Typer(no_args_is_help=True)
tasks_app = typer.Typer(no_args_is_help=True)
attempt_app = typer.Typer(no_args_is_help=True)
agents_app = typer.Typer(no_args_is_help=True)
controls_app = typer.Typer(no_args_is_help=True)
sandbox_app = typer.Typer(no_args_is_help=True)
scorers_app = typer.Typer(no_args_is_help=True)
local_model_app = typer.Typer(no_args_is_help=True)
ollama_app = typer.Typer(no_args_is_help=True)
app.add_typer(tasks_app, name="tasks")
app.add_typer(attempt_app, name="attempt")
app.add_typer(agents_app, name="agents")
app.add_typer(controls_app, name="controls")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(scorers_app, name="scorers")
app.add_typer(local_model_app, name="local-model")
local_model_app.add_typer(ollama_app, name="ollama")

console = Console()


@tasks_app.command("validate")
def validate_task(path: Path) -> None:
    if path.is_dir():
        result = validate_task_pack(path)
        console.print(
            f"[green]valid[/green] {result.task_pack_id} "
            f"tasks={result.task_count}"
        )
        return

    manifest = load_task_manifest(path)
    validate_task_manifest_paths(manifest, path)
    console.print(f"[green]valid[/green] {manifest.id}")


@attempt_app.command("run")
def run_attempt(
    task_manifest: Path = typer.Option(
        ...,
        "--task-manifest",
        "--task",
        help="Path to task.yaml.",
    ),
    submission: Path = typer.Option(..., "--submission", help="Path to patch file."),
    out: Path = typer.Option(..., "--out", help="Directory for attempt artifacts."),
) -> None:
    attempt_run = run_and_persist_patch_attempt_to_dir(task_manifest, submission, out)
    style = "green" if attempt_run.result.status == "PASS" else "red"
    console.print(
        f"[{style}]{attempt_run.result.status}[/{style}] "
        f"{attempt_run.result.task_id}"
    )
    console.print(f"wrote {out / 'attempt.json'}")


@scorers_app.command("audit")
def audit_scorers(
    cases: Path = typer.Option(..., "--cases", help="Directory of scorer cases."),
    out: Path = typer.Option(..., "--out", help="Directory for audit artifacts."),
) -> None:
    results = run_scorer_audit(cases, out)
    failed = sum(not result.overall_match for result in results)
    style = "green" if failed == 0 else "red"
    console.print(
        f"[{style}]scorer audit complete[/{style}] "
        f"cases={len(results)} failed={failed}"
    )
    console.print(f"wrote {out / 'scorer_audit.md'}")


@agents_app.command("audit")
def audit_agent_tasks(
    cases: Path = typer.Option(..., "--cases", help="Directory of agent task cases."),
    out: Path = typer.Option(..., "--out", help="Directory for audit artifacts."),
) -> None:
    results = run_agent_task_audit(cases, out)
    failed = sum(not result.overall_match for result in results)
    style = "green" if failed == 0 else "red"
    console.print(
        f"[{style}]agent task audit complete[/{style}] "
        f"cases={len(results)} failed={failed}"
    )
    console.print(f"wrote {out / 'agent_task_audit.md'}")


@controls_app.command("run")
def run_control_calibration(
    task_pack: Path = typer.Option(..., "--task-pack", help="Path to task pack."),
    repeats: int = typer.Option(3, "--repeats", help="Attempts per control."),
    out: Path = typer.Option(..., "--out", help="Directory for control artifacts."),
) -> None:
    control_run = run_controls(task_pack, repeats, out)
    failed = sum(not record.match for record in control_run.records)
    style = "green" if failed == 0 else "red"
    console.print(
        f"[{style}]controls complete[/{style}] "
        f"records={len(control_run.records)} failed={failed}"
    )
    console.print(f"wrote {control_run.out_dir / 'control_report.md'}")


@sandbox_app.command("smoke")
def smoke_sandbox(
    config: Path = typer.Option(..., "--config", help="Path to sandbox config YAML."),
    out: Path = typer.Option(..., "--out", help="Directory for smoke artifacts."),
) -> None:
    result = run_docker_smoke(config, out)
    style = "green" if result.status == "PASS" else "red"
    console.print(f"[{style}]docker smoke {result.status}[/{style}]")
    console.print(f"wrote {result.out_dir / 'docker_smoke.md'}")


@ollama_app.command("plan")
def plan_ollama(
    model_id: str = typer.Option(
        DEFAULT_MODEL_ID,
        "--model-id",
        "--model",
        help="Ollama/Hugging Face model id.",
    ),
    fallback_model_id: str = typer.Option(
        FALLBACK_MODEL_ID,
        "--fallback-model-id",
        help="Fallback model id shown in the setup plan.",
    ),
) -> None:
    console.print(
        render_setup_plan(
            model_id=model_id,
            fallback_model_id=fallback_model_id,
        )
    )


@ollama_app.command("probe")
def probe_ollama_server(
    server_url: str = typer.Option(
        DEFAULT_SERVER_URL,
        "--server-url",
        help="Ollama server URL.",
    ),
) -> None:
    from agentenv.local_model_setup.ollama import probe_ollama

    probe = probe_ollama(server_url=server_url)
    installed = "yes" if probe.ollama_path is not None else "no"
    running = "yes" if probe.server_running else "no"
    console.print(f"ollama_installed={installed}")
    if probe.ollama_path is not None:
        console.print(f"ollama_path={probe.ollama_path}")
    console.print(f"server_url={probe.server_url}")
    console.print(f"server_running={running}")
    if probe.version is not None:
        console.print(f"version={probe.version}")
    if probe.model_ids:
        console.print("models=" + ",".join(probe.model_ids))
    if probe.error_class is not None:
        console.print(f"error_class={probe.error_class}")
        console.print(f"error_message={probe.error_message}")


@ollama_app.command("pull")
def pull_ollama_model(
    model_id: str = typer.Option(
        DEFAULT_MODEL_ID,
        "--model-id",
        "--model",
        help="Ollama/Hugging Face model id.",
    ),
    timeout_seconds: int = typer.Option(
        3600,
        "--timeout-seconds",
        help="Download timeout.",
    ),
) -> None:
    result = pull_model(model_id=model_id, timeout_seconds=timeout_seconds)
    style = "green" if result.returncode == 0 else "red"
    console.print(f"[{style}]ollama pull exited {result.returncode}[/{style}]")
    console.print("command=" + " ".join(result.command))
    if result.stdout:
        console.print(result.stdout)
    if result.stderr:
        console.print(result.stderr)


@ollama_app.command("smoke")
def smoke_ollama_openai_api(
    model_id: str = typer.Option(
        DEFAULT_MODEL_ID,
        "--model-id",
        "--model",
        help="Ollama/Hugging Face model id.",
    ),
    base_url: str = typer.Option(
        DEFAULT_OPENAI_BASE_URL,
        "--base-url",
        help="OpenAI-compatible base URL.",
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
) -> None:
    result = run_chat_smoke(
        model_id=model_id,
        base_url=base_url,
        prompt=smoke_prompt,
        system_suffix=system_suffix or None,
    )
    style = "green" if result.status == "ok" else "red"
    console.print(f"[{style}]ollama smoke {result.status}[/{style}]")
    console.print(f"model_id={result.model_id}")
    console.print(f"base_url={result.base_url}")
    if result.finish_reason is not None:
        console.print(f"finish_reason={result.finish_reason}")
    if result.output_text:
        console.print(result.output_text)
    if result.error_class is not None:
        console.print(f"error_class={result.error_class}")
        console.print(f"error_message={result.error_message}")


@ollama_app.command("setup")
def setup_ollama_model_command(
    model_id: str = typer.Option(
        DEFAULT_MODEL_ID,
        "--model-id",
        "--model",
        help="Ollama/Hugging Face model id.",
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
        help="Download timeout.",
    ),
    smoke_timeout_seconds: float = typer.Option(
        120.0,
        "--smoke-timeout-seconds",
        help="Smoke request timeout.",
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
        help="Keep a server started by this command running after setup.",
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
    console.print(render_setup_result(result), end="")
    if result.status != "ok":
        raise typer.Exit(1)


@ollama_app.command("serve-command")
def print_ollama_serve_command() -> None:
    console.print(" ".join(serve_command()))


@app.command("eval")
def run_eval(
    config: Path = typer.Option(..., "--config", help="Path to eval config YAML."),
    policy: str | None = typer.Option(
        None,
        "--policy",
        help="Policy name from the config.",
    ),
    all_policies: bool = typer.Option(
        False,
        "--all-policies",
        help="Run every policy defined by the config.",
    ),
    out: Path = typer.Option(..., "--out", help="Directory for eval artifacts."),
    report_out: Path | None = typer.Option(
        None,
        "--report-out",
        help="Optional Markdown report path to write after the eval completes.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before running.",
    ),
) -> None:
    if all_policies:
        if policy is not None:
            raise typer.BadParameter("--all-policies cannot be combined with --policy")
        try:
            eval_matrix = run_eval_config_all_policies(
                config,
                out,
                overwrite=overwrite,
            )
        except ArtifactDirectoryError as exc:
            raise typer.BadParameter(str(exc), param_hint="--out") from exc
        layer_counts = _format_layer_counts(_matrix_layer_counts(eval_matrix))
        console.print(
            f"[green]eval complete[/green] {eval_matrix.config.name} "
            f"policies={len(eval_matrix.policy_runs)} "
            f"attempts={sum(len(run.attempts) for run in eval_matrix.policy_runs)} "
            f"replays={len(eval_matrix.replay_runs)} "
            f"{layer_counts}"
        )
        console.print(f"wrote {eval_matrix.out_dir / 'eval_matrix_manifest.json'}")
        if report_out is not None:
            report_path = write_markdown_report(eval_matrix.out_dir, report_out)
            console.print(f"wrote {report_path}")
        return

    if policy is None:
        raise typer.BadParameter("Provide --policy or --all-policies")

    try:
        eval_run = run_eval_config(config, policy, out, overwrite=overwrite)
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    layer_counts = _format_layer_counts(_layer_counts(eval_run))
    console.print(
        f"[green]eval complete[/green] {eval_run.config.name} "
        f"policy={eval_run.policy} attempts={len(eval_run.attempts)} "
        f"{layer_counts}"
    )
    console.print(f"wrote {eval_run.out_dir / 'run_manifest.json'}")
    if report_out is not None:
        report_path = write_markdown_report(eval_run.out_dir, report_out)
        console.print(f"wrote {report_path}")


@app.command("replay")
def replay_run(
    source_run_dir: Path = typer.Argument(
        ...,
        help="Source artifact directory to replay.",
    ),
    out: Path = typer.Option(..., "--out", help="Directory for replay artifacts."),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before replaying.",
    ),
) -> None:
    try:
        replay = run_replay(source_run_dir, out, overwrite=overwrite)
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    style = "green" if replay.status == "PASS" else "red"
    console.print(
        f"[{style}]{replay.status}[/{style}] "
        f"comparisons={len(replay.comparisons)}"
    )
    console.print(f"wrote {replay.out_dir / 'replay_result.json'}")


@app.command("report")
def report_run(
    artifact_dir: Path = typer.Argument(..., help="Artifact directory to report on."),
    out: Path = typer.Option(..., "--out", help="Markdown report path."),
) -> None:
    report_path = write_markdown_report(artifact_dir, out)
    console.print(f"[green]wrote[/green] {report_path}")


def _layer_counts(eval_run: EvalRun) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for attempt in eval_run.attempts:
        if attempt.scorer is not None:
            _increment_layer_count(counts, "scorer_status", attempt.scorer.status)
            _increment_layer_count(
                counts,
                "scorer_public_status",
                attempt.scorer.public_status,
            )
            _increment_layer_count(
                counts,
                "scorer_hidden_status",
                attempt.scorer.hidden_status,
            )
        if attempt.agent is not None:
            _increment_layer_count(counts, "agent_status", attempt.agent.status)
            if attempt.agent.prompt_loop_status is not None:
                _increment_layer_count(
                    counts,
                    "prompt_loop_status",
                    attempt.agent.prompt_loop_status,
                )
            if attempt.agent.scorer_attempt is not None:
                _increment_layer_count(
                    counts,
                    "agent_scorer_status",
                    attempt.agent.scorer_attempt.status,
                )
                _increment_layer_count(
                    counts,
                    "agent_scorer_public_status",
                    attempt.agent.scorer_attempt.public_status,
                )
                _increment_layer_count(
                    counts,
                    "agent_scorer_hidden_status",
                    attempt.agent.scorer_attempt.hidden_status,
                )
    return counts


def _matrix_layer_counts(eval_matrix: EvalMatrixRun) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for eval_run in eval_matrix.policy_runs:
        for layer_name, status_counts in _layer_counts(eval_run).items():
            layer_count = counts.setdefault(layer_name, {})
            for status, count in status_counts.items():
                layer_count[status] = layer_count.get(status, 0) + count
    return counts


def _increment_layer_count(
    counts: dict[str, dict[str, int]],
    layer_name: str,
    status: str,
) -> None:
    layer_count = counts.setdefault(layer_name, {})
    layer_count[status] = layer_count.get(status, 0) + 1


def _format_layer_counts(layer_counts: dict[str, dict[str, int]]) -> str:
    return " ".join(
        f"{layer_name}.{status}={count}"
        for layer_name, status_counts in sorted(layer_counts.items())
        for status, count in sorted(status_counts.items())
    )
