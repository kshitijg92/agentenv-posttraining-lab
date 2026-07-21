import json
from pathlib import Path

import typer
from rich.console import Console

from agentenv.audits.agent_task import run_agent_task_audit_layer
from agentenv.audits.runner import run_harness_audit
from agentenv.audits.scorer import run_scorer_audit_layer
from agentenv.artifacts import MANIFEST_FILENAME, ArtifactDirectoryError
from agentenv.controls.controls_run import run_controls
from agentenv.controls.public_check_idempotency_runner import (
    DEFAULT_PUBLIC_CHECK_IDEMPOTENCY_REPEATS,
)
from agentenv.evals.task_hash_compare import (
    compare_eval_task_hashes,
    render_eval_task_hash_comparison_summary,
)
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
    count_eval_matrix_layers,
    count_eval_run_layers,
    run_eval_config,
    run_eval_config_all_policies,
)
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.replay.runner import run_replay
from agentenv.reporting.markdown import write_markdown_report
from agentenv.rewards.export import run_and_persist_reward_hack_audit
from agentenv.sandbox.docker_smoke import run_docker_smoke
from agentenv.tasks.validate import (
    load_task_manifest,
    validate_task_manifest_paths,
    validate_task_pack,
)
from agentenv.tasks.hashing import write_task_hash_report
from agentenv.tasks.splits import check_splits_lock
from agentenv.training.candidates.export import (
    export_training_candidate_records,
)
from agentenv.training.positive_sft.export import export_positive_sft_examples
from agentenv.training.positive_sft.materialization.export import (
    export_positive_sft_training_materializations,
)
from agentenv.training.positive_sft.review import (
    initialize_positive_sft_review_artifact,
    validate_positive_sft_review_artifact,
)
from agentenv.training.preferences.export import (
    export_preference_comparison_candidates,
)
from agentenv.training.preferences.review import (
    initialize_preference_adjudication_review_artifact,
    validate_preference_adjudication_review_artifact,
)
from agentenv.trajectories.export import export_trajectory_records_from_eval_artifact
from agentenv.trajectories.review import (
    initialize_trajectory_review_artifact,
    validate_trajectory_review_artifact,
)


app = typer.Typer(no_args_is_help=True)
tasks_app = typer.Typer(no_args_is_help=True)
attempt_app = typer.Typer(no_args_is_help=True)
agents_app = typer.Typer(no_args_is_help=True)
controls_app = typer.Typer(no_args_is_help=True)
eval_app = typer.Typer(no_args_is_help=False)
trajectories_app = typer.Typer(no_args_is_help=True)
training_app = typer.Typer(no_args_is_help=True)
training_candidates_app = typer.Typer(no_args_is_help=True)
training_positive_sft_app = typer.Typer(no_args_is_help=True)
training_preferences_app = typer.Typer(no_args_is_help=True)
sandbox_app = typer.Typer(no_args_is_help=True)
scorers_app = typer.Typer(no_args_is_help=True)
harness_app = typer.Typer(no_args_is_help=True)
rewards_app = typer.Typer(no_args_is_help=True)
local_model_app = typer.Typer(no_args_is_help=True)
ollama_app = typer.Typer(no_args_is_help=True)
app.add_typer(tasks_app, name="tasks")
app.add_typer(attempt_app, name="attempt")
app.add_typer(agents_app, name="agents")
app.add_typer(controls_app, name="controls")
app.add_typer(eval_app, name="eval")
app.add_typer(trajectories_app, name="trajectories")
app.add_typer(training_app, name="training")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(scorers_app, name="scorers")
app.add_typer(harness_app, name="harness")
app.add_typer(rewards_app, name="rewards")
app.add_typer(local_model_app, name="local-model")
training_app.add_typer(training_candidates_app, name="candidates")
training_app.add_typer(training_positive_sft_app, name="positive-sft")
training_app.add_typer(training_preferences_app, name="preferences")
local_model_app.add_typer(ollama_app, name="ollama")

console = Console()


@tasks_app.command("validate")
def validate_task(path: Path) -> None:
    if path.is_dir():
        result = validate_task_pack(path)
        console.print(
            f"[green]valid[/green] {result.task_pack_id} tasks={result.task_count}"
        )
        return

    manifest = load_task_manifest(path)
    validate_task_manifest_paths(manifest, path)
    console.print(f"[green]valid[/green] {manifest.id}")


@tasks_app.command("check-splits")
def check_task_splits(
    splits_lock: Path = typer.Argument(..., help="Path to splits.lock.json."),
) -> None:
    result = check_splits_lock(splits_lock)
    counts = " ".join(
        f"{split}={count}" for split, count in result.split_counts.items()
    )
    console.print(
        f"[green]valid[/green] {result.task_pack_id} tasks={result.task_count} {counts}"
    )


@tasks_app.command("hash")
def hash_task_pack(
    task_pack: Path = typer.Argument(..., help="Path to task pack directory."),
    out: Path = typer.Option(..., "--out", help="Path for hash report JSON."),
) -> None:
    report = write_task_hash_report(task_pack, out)
    console.print(
        f"[green]hashed[/green] {report.payload.task_pack_id} "
        f"tasks={report.payload.task_count} "
        f"pack_record_hash={report.pack_record_hash}"
    )
    console.print(f"wrote {out}")


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
        f"[{style}]{attempt_run.result.status}[/{style}] {attempt_run.result.task_id}"
    )
    console.print(f"wrote {out / 'attempt.json'}")


@scorers_app.command("audit")
def audit_scorers(
    cases: Path = typer.Option(..., "--cases", help="Directory of scorer cases."),
    out: Path = typer.Option(..., "--out", help="Directory for audit artifacts."),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    layer = run_scorer_audit_layer(cases, out, overwrite=overwrite)
    style = _audit_status_style(layer.summary.status)
    console.print(
        f"[{style}]scorer audit {layer.summary.status}[/{style}] "
        f"records={layer.summary.record_count} "
        f"mismatched={layer.summary.mismatched_count} "
        f"errors={layer.summary.audit_error_count}"
    )
    console.print(f"wrote {out / MANIFEST_FILENAME}")


@agents_app.command("audit")
def audit_agent_tasks(
    cases: Path = typer.Option(..., "--cases", help="Directory of agent task cases."),
    out: Path = typer.Option(..., "--out", help="Directory for audit artifacts."),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    layer = run_agent_task_audit_layer(cases, out, overwrite=overwrite)
    style = _audit_status_style(layer.summary.status)
    console.print(
        f"[{style}]agent-task audit {layer.summary.status}[/{style}] "
        f"records={layer.summary.record_count} "
        f"mismatched={layer.summary.mismatched_count} "
        f"errors={layer.summary.audit_error_count}"
    )
    console.print(f"wrote {out / MANIFEST_FILENAME}")


@harness_app.command("audit")
def audit_harness(
    agent_cases: Path = typer.Option(
        ...,
        "--agent-cases",
        help="Directory of agent-task audit cases.",
    ),
    scorer_cases: Path = typer.Option(
        ...,
        "--scorer-cases",
        help="Directory of scorer audit cases.",
    ),
    out: Path = typer.Option(..., "--out", help="Root harness audit directory."),
    overwrite: bool = typer.Option(False, "--overwrite"),
) -> None:
    artifact = run_harness_audit(
        agent_case_root=agent_cases,
        scorer_case_root=scorer_cases,
        out_dir=out,
        overwrite=overwrite,
    )
    style = _audit_status_style(artifact.manifest.status)
    console.print(
        f"[{style}]harness audit {artifact.manifest.status}[/{style}] "
        f"agent={artifact.agent_audit.summary.status} "
        f"scorer={artifact.scorer_audit.summary.status}"
    )
    console.print(f"wrote {out / MANIFEST_FILENAME}")
    console.print(f"wrote {out / 'harness_audit.md'}")


@rewards_app.command("audit")
def audit_reward_hacks(
    cases: Path = typer.Option(..., "--cases", help="Directory of reward-hack cases."),
    out: Path = typer.Option(
        ..., "--out", help="Directory for reward audit artifacts."
    ),
    report_out: Path | None = typer.Option(
        None,
        "--report-out",
        help="Optional Markdown report path.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before auditing.",
    ),
) -> None:
    try:
        artifact = run_and_persist_reward_hack_audit(
            cases,
            out,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--cases") from exc

    manifest = artifact.manifest
    style = "green" if manifest.fail_count == 0 else "red"
    console.print(
        f"[{style}]reward-hack audit complete[/{style}] "
        f"records={manifest.record_count} "
        f"passed={manifest.pass_count} failed={manifest.fail_count}"
    )
    console.print(f"wrote {artifact.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {artifact.out_dir / manifest.artifacts['results']}",
        soft_wrap=True,
    )
    if report_out is not None:
        report_path = write_markdown_report(artifact.out_dir, report_out)
        console.print(f"wrote {report_path}", soft_wrap=True)


@controls_app.command("run")
def run_control_calibration(
    task_pack: Path = typer.Option(..., "--task-pack", help="Path to task pack."),
    repeats: int = typer.Option(3, "--repeats", help="Attempts per control."),
    public_check_idempotency_repeats: int = typer.Option(
        DEFAULT_PUBLIC_CHECK_IDEMPOTENCY_REPEATS,
        "--public-check-idempotency-repeats",
        help="Consecutive seed-workspace runs per declared idempotent public check.",
    ),
    out: Path = typer.Option(..., "--out", help="Directory for control artifacts."),
) -> None:
    control_run = run_controls(
        task_pack,
        repeats,
        out,
        public_check_idempotency_repeats=public_check_idempotency_repeats,
    )
    failed = sum(not record.match for record in control_run.records)
    status = "PASS" if control_run.overall_match else "FAIL"
    style = "green" if control_run.overall_match else "red"
    console.print(
        f"[{style}]controls {status}[/{style}] "
        f"records={len(control_run.records)} failed={failed} "
        f"flake={control_run.flake_detection.status}"
    )
    console.print(f"wrote {control_run.out_dir / 'control_report.md'}")
    if not control_run.overall_match:
        raise typer.Exit(1)


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
        ),
        soft_wrap=True,
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
        console.print("models=" + ",".join(probe.model_ids), soft_wrap=True)
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
    console.print(render_setup_result(result), end="", soft_wrap=True)
    if result.status != "ok":
        raise typer.Exit(1)


@ollama_app.command("serve-command")
def print_ollama_serve_command() -> None:
    console.print(" ".join(serve_command()))


@eval_app.callback(invoke_without_command=True)
def run_eval(
    ctx: typer.Context,
    config: Path | None = typer.Option(
        None, "--config", help="Path to eval config YAML."
    ),
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
    out: Path | None = typer.Option(
        None, "--out", help="Directory for eval artifacts."
    ),
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
    if ctx.invoked_subcommand is not None:
        return
    if config is None:
        raise typer.BadParameter("Provide --config", param_hint="--config")
    if out is None:
        raise typer.BadParameter("Provide --out", param_hint="--out")

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
        layer_counts = _format_layer_counts(count_eval_matrix_layers(eval_matrix))
        console.print(
            f"[green]eval complete[/green] {eval_matrix.config.name} "
            f"policies={len(eval_matrix.policy_runs)} "
            f"attempts={sum(len(run.attempts) for run in eval_matrix.policy_runs)} "
            f"replays={len(eval_matrix.replay_runs)} "
            f"{layer_counts}"
        )
        console.print(
            f"wrote {eval_matrix.out_dir / MANIFEST_FILENAME}",
            soft_wrap=True,
        )
        if report_out is not None:
            report_path = write_markdown_report(eval_matrix.out_dir, report_out)
            console.print(f"wrote {report_path}", soft_wrap=True)
        return

    if policy is None:
        raise typer.BadParameter("Provide --policy or --all-policies")

    try:
        eval_run = run_eval_config(config, policy, out, overwrite=overwrite)
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    layer_counts = _format_layer_counts(count_eval_run_layers(eval_run))
    console.print(
        f"[green]eval complete[/green] {eval_run.config.name} "
        f"policy={eval_run.policy} attempts={len(eval_run.attempts)} "
        f"{layer_counts}"
    )
    console.print(f"wrote {eval_run.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    if report_out is not None:
        report_path = write_markdown_report(eval_run.out_dir, report_out)
        console.print(f"wrote {report_path}", soft_wrap=True)


@eval_app.command("compare-task-hashes")
def compare_task_hashes(
    reference: Path = typer.Option(
        ...,
        "--reference",
        help="Reference eval artifact directory or manifest JSON.",
    ),
    candidate: Path = typer.Option(
        ...,
        "--candidate",
        help="Candidate eval artifact directory or manifest JSON.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Optional JSON path for the full comparison result.",
    ),
) -> None:
    try:
        comparison = compare_eval_task_hashes(reference, candidate)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    summary_lines = render_eval_task_hash_comparison_summary(comparison)
    style = "green" if comparison.status == "matched" else "red"
    console.print(f"[{style}]{summary_lines[0]}[/{style}]")
    for line in summary_lines[1:]:
        console.print(line)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(comparison.to_dict(), indent=2, sort_keys=True) + "\n"
        )
        console.print(f"wrote {out}", soft_wrap=True)
    if comparison.status != "matched":
        raise typer.Exit(1)


@trajectories_app.command("export")
def export_trajectories(
    source: Path = typer.Option(
        ...,
        "--source",
        help="Eval run or eval suite artifact directory.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for trajectory export artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before exporting.",
    ),
) -> None:
    try:
        export = export_trajectory_records_from_eval_artifact(
            source,
            out,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--source") from exc

    manifest = export.manifest
    source_id = manifest.source_eval_run_id or manifest.source_eval_suite_id
    console.print(
        "[green]trajectory export complete[/green] "
        f"source={manifest.source_artifact_type} "
        f"source_id={source_id} records={manifest.record_count}"
    )
    console.print(f"wrote {export.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {export.out_dir / manifest.artifacts['trajectories']}",
        soft_wrap=True,
    )


@trajectories_app.command("review-init")
def initialize_trajectory_review(
    source: Path = typer.Option(
        ...,
        "--source",
        help="Trajectory export artifact directory.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for trajectory review artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before initializing.",
    ),
) -> None:
    try:
        review_artifact = initialize_trajectory_review_artifact(
            source,
            out,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--source") from exc

    manifest = review_artifact.manifest
    source_id = manifest.source_eval_run_id or manifest.source_eval_suite_id
    console.print(
        "[green]trajectory review initialized[/green] "
        f"source={manifest.source_artifact_type} "
        f"source_id={source_id} records={manifest.record_count}"
    )
    console.print(
        f"wrote {review_artifact.out_dir / MANIFEST_FILENAME}", soft_wrap=True
    )
    console.print(
        f"wrote {review_artifact.out_dir / manifest.artifacts['reviews']}",
        soft_wrap=True,
    )
    console.print(
        f"wrote {review_artifact.out_dir / manifest.artifacts['review_queue']}",
        soft_wrap=True,
    )


@trajectories_app.command("review-validate")
def validate_trajectory_review(
    source: Path = typer.Option(
        ...,
        "--source",
        help="Trajectory export artifact directory.",
    ),
    reviews: Path = typer.Option(
        ...,
        "--reviews",
        help="Trajectory review artifact directory.",
    ),
) -> None:
    try:
        validation = validate_trajectory_review_artifact(source, reviews)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--reviews") from exc

    status_counts = validation.review_status_counts
    decision_counts = validation.review_decision_counts
    console.print(
        "[green]trajectory review valid[/green] "
        f"records={validation.record_count} "
        f"not_reviewed={status_counts['not_reviewed']} "
        f"reviewed={status_counts['reviewed']} "
        f"accepted={decision_counts['accepted']} "
        f"rejected={decision_counts['rejected']} "
        f"needs_followup={decision_counts['needs_followup']}"
    )


@training_candidates_app.command("export")
def export_training_candidates(
    trajectories: Path = typer.Option(
        ...,
        "--trajectories",
        help="Trajectory export artifact directory.",
    ),
    reviews: Path = typer.Option(
        ...,
        "--reviews",
        help="Trajectory review artifact directory.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for training candidate export artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before exporting.",
    ),
) -> None:
    try:
        export = export_training_candidate_records(
            trajectories,
            reviews,
            out,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except ValueError as exc:
        raise typer.BadParameter(
            str(exc),
            param_hint="--trajectories/--reviews",
        ) from exc

    manifest = export.manifest
    console.print(
        "[green]training candidate export complete[/green] "
        f"records={manifest.record_count} "
        f"training_authorization={manifest.training_authorization} "
        "downstream_construction_eligible="
        f"{manifest.downstream_construction_eligible_count} "
        f"analysis_only={manifest.analysis_only_count} "
        f"fully_ineligible={manifest.fully_ineligible_count} "
        f"positive_sft_review={manifest.positive_sft_review_eligible_count} "
        f"negative_examples={manifest.negative_example_eligible_count} "
        f"preference_discovery={manifest.preference_discovery_eligible_count}"
    )
    console.print(f"wrote {export.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {export.out_dir / manifest.artifacts['training_candidates']}",
        soft_wrap=True,
    )


@training_preferences_app.command("discover")
def discover_training_preferences(
    candidates: Path = typer.Option(
        ...,
        "--candidates",
        help="Training candidate export artifact directory.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for preference comparison export artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before exporting.",
    ),
) -> None:
    try:
        export = export_preference_comparison_candidates(
            candidates,
            out,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--candidates") from exc

    manifest = export.manifest
    console.print(
        "[green]preference comparison discovery complete[/green] "
        f"records={manifest.record_count} "
        f"shared_contexts={manifest.shared_context_count} "
        f"training_authorization={manifest.training_authorization}"
    )
    console.print(f"wrote {export.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {export.out_dir / manifest.artifacts['comparison_candidates']}",
        soft_wrap=True,
    )


@training_preferences_app.command("review-init")
def initialize_training_preference_review(
    comparisons: Path = typer.Option(
        ...,
        "--comparisons",
        help="Preference comparison export artifact directory.",
    ),
    rubric: Path = typer.Option(
        ...,
        "--rubric",
        help="Versioned overall-action preference rubric Markdown file.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for preference adjudication review artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before initializing.",
    ),
) -> None:
    try:
        artifact = initialize_preference_adjudication_review_artifact(
            comparisons,
            rubric,
            out,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(
            str(exc),
            param_hint="--comparisons/--rubric",
        ) from exc

    manifest = artifact.manifest
    console.print(
        "[green]preference adjudication review initialized[/green] "
        f"records={manifest.record_count} "
        f"rubric={manifest.rubric_provenance.rubric_version}"
    )
    console.print(f"wrote {artifact.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {artifact.out_dir / manifest.artifacts['adjudications']}",
        soft_wrap=True,
    )
    console.print(
        f"wrote {artifact.out_dir / manifest.artifacts['review_queue']}",
        soft_wrap=True,
    )


@training_preferences_app.command("review-validate")
def validate_training_preference_review(
    reviews: Path = typer.Option(
        ...,
        "--reviews",
        help="Preference adjudication review artifact directory.",
    ),
) -> None:
    try:
        validation = validate_preference_adjudication_review_artifact(reviews)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--reviews") from exc

    status_counts = validation.review_status_counts
    decision_counts = validation.review_decision_counts
    console.print(
        "[green]preference adjudication review valid[/green] "
        f"records={len(validation.review_artifact.adjudications)} "
        f"not_reviewed={status_counts['not_reviewed']} "
        f"reviewed={status_counts['reviewed']} "
        f"preferred={decision_counts['preferred']} "
        f"tie={decision_counts['tie']} "
        f"ambiguous={decision_counts['ambiguous']} "
        f"invalid={decision_counts['invalid']}"
    )


@training_positive_sft_app.command("review-init")
def initialize_training_positive_sft_review(
    candidates: Path = typer.Option(
        ...,
        "--candidates",
        help="Training candidate export artifact directory.",
    ),
    repairs: Path | None = typer.Option(
        None,
        "--repairs",
        help="Optional training candidate repair export artifact directory.",
    ),
    repair_reviews: Path | None = typer.Option(
        None,
        "--repair-reviews",
        help="Optional accepted repair review artifact directory.",
    ),
    repair_id: list[str] | None = typer.Option(
        None,
        "--repair-id",
        help="Selected repair ID; repeat for multiple candidates.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for positive-SFT prefix review artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before exporting.",
    ),
    ) -> None:
    try:
        artifact = initialize_positive_sft_review_artifact(
            candidates,
            out,
            repair_export_dir=repairs,
            repair_review_dir=repair_reviews,
            selected_repair_ids=tuple(repair_id or ()),
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--candidates") from exc

    manifest = artifact.manifest
    console.print(
        "[green]positive SFT review initialized[/green] "
        f"records={manifest.record_count} "
        f"original={manifest.original_record_count} "
        f"repaired={manifest.repaired_record_count}"
    )
    console.print(f"wrote {artifact.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {artifact.out_dir / manifest.artifacts['reviews']}",
        soft_wrap=True,
    )
    console.print(
        f"wrote {artifact.out_dir / manifest.artifacts['review_queue']}",
        soft_wrap=True,
    )


@training_positive_sft_app.command("review-validate")
def validate_training_positive_sft_review(
    reviews: Path = typer.Option(
        ...,
        "--reviews",
        help="Positive-SFT prefix review artifact directory.",
    ),
) -> None:
    try:
        validation = validate_positive_sft_review_artifact(reviews)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--reviews") from exc
    decisions = [
        review.review_decision
        for review in validation.review_artifact.reviews
        if review.review_decision is not None
    ]
    console.print(
        "[green]positive SFT review valid[/green] "
        f"records={len(validation.review_artifact.reviews)} "
        f"accepted={decisions.count('accepted')} "
        f"rejected={decisions.count('rejected')} "
        f"needs_followup={decisions.count('needs_followup')}"
    )


@training_positive_sft_app.command("export")
def export_training_positive_sft(
    candidates: Path = typer.Option(
        ...,
        "--candidates",
        help="Training candidate export artifact directory.",
    ),
    reviews: Path = typer.Option(
        ...,
        "--reviews",
        help="Validated positive-SFT prefix review artifact directory.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for positive SFT export artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before exporting.",
    ),
) -> None:
    try:
        export = export_positive_sft_examples(
            candidates,
            reviews,
            out,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except ValueError as exc:
        raise typer.BadParameter(
            str(exc),
            param_hint="--candidates/--reviews",
        ) from exc

    manifest = export.manifest
    console.print(
        "[green]positive SFT export complete[/green] "
        f"records={manifest.record_count} "
        f"training_authorization={manifest.training_authorization}"
    )
    console.print(f"wrote {export.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {export.out_dir / manifest.artifacts['positive_sft_examples']}",
        soft_wrap=True,
    )


@training_positive_sft_app.command("materialize")
def materialize_training_positive_sft(
    source: Path = typer.Option(
        ...,
        "--source",
        help="Positive-SFT source export artifact directory.",
    ),
    model_input_protocol: Path = typer.Option(
        ...,
        "--model-input-protocol",
        help="Pinned target-model input protocol YAML.",
    ),
    max_sequence_length: int = typer.Option(
        ...,
        "--max-sequence-length",
        min=1,
        help="Maximum complete token sequence length; overlength rows fail whole.",
    ),
    tokenizer_cache_dir: Path | None = typer.Option(
        None,
        "--tokenizer-cache-dir",
        help="Optional Hugging Face tokenizer cache directory.",
    ),
    local_files_only: bool = typer.Option(
        False,
        "--local-files-only",
        help="Require the pinned tokenizer revision to be present locally.",
    ),
    out: Path = typer.Option(
        ...,
        "--out",
        help="Directory for positive-SFT training materialization artifacts.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Delete and recreate a non-empty --out directory before exporting.",
    ),
) -> None:
    try:
        export = export_positive_sft_training_materializations(
            source,
            model_input_protocol,
            out,
            max_sequence_length=max_sequence_length,
            tokenizer_cache_dir=tokenizer_cache_dir,
            local_files_only=local_files_only,
            overwrite=overwrite,
        )
    except ArtifactDirectoryError as exc:
        raise typer.BadParameter(str(exc), param_hint="--out") from exc
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(
            str(exc),
            param_hint="--source/--model-input-protocol",
        ) from exc

    manifest = export.manifest
    console.print(
        "[green]positive SFT training materialization complete[/green] "
        f"records={manifest.record_count} "
        f"completed={manifest.completed_count} "
        f"failed={manifest.failed_count} "
        f"overlength={manifest.sequence_length_exceeded_count} "
        f"materialization_errors={manifest.materialization_error_count} "
        f"training_authorization={manifest.training_authorization}"
    )
    console.print(f"wrote {export.out_dir / MANIFEST_FILENAME}", soft_wrap=True)
    console.print(
        f"wrote {export.out_dir / manifest.artifacts['materializations']}",
        soft_wrap=True,
    )


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
        f"[{style}]{replay.status}[/{style}] comparisons={len(replay.comparisons)}"
    )
    console.print(f"wrote {replay.out_dir / 'replay_result.json'}")


@app.command("report")
def report_run(
    artifact_dir: Path = typer.Argument(..., help="Artifact directory to report on."),
    out: Path = typer.Option(..., "--out", help="Markdown report path."),
) -> None:
    report_path = write_markdown_report(artifact_dir, out)
    console.print(f"[green]wrote[/green] {report_path}")


def _format_layer_counts(layer_counts: dict[str, dict[str, int]]) -> str:
    return " ".join(
        f"{layer_name}.{status}={count}"
        for layer_name, status_counts in sorted(layer_counts.items())
        for status, count in sorted(status_counts.items())
    )


def _audit_status_style(status: str) -> str:
    if status == "PASS":
        return "green"
    if status == "INCONCLUSIVE":
        return "yellow"
    return "red"
