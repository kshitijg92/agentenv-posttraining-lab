from pathlib import Path

import typer
from rich.console import Console

from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.controls.controls_run import run_controls
from agentenv.orchestrators.eval_run import (
    EvalMatrixRun,
    EvalRun,
    run_eval_config,
    run_eval_config_all_policies,
)
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
controls_app = typer.Typer(no_args_is_help=True)
sandbox_app = typer.Typer(no_args_is_help=True)
scorers_app = typer.Typer(no_args_is_help=True)
app.add_typer(tasks_app, name="tasks")
app.add_typer(attempt_app, name="attempt")
app.add_typer(controls_app, name="controls")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(scorers_app, name="scorers")

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
) -> None:
    if all_policies:
        if policy is not None:
            raise typer.BadParameter("--all-policies cannot be combined with --policy")
        eval_matrix = run_eval_config_all_policies(
            config,
            out,
        )
        status_counts = ", ".join(
            f"{status}={count}"
            for status, count in sorted(
                _matrix_status_counts(eval_matrix).items(),
            )
        )
        console.print(
            f"[green]eval complete[/green] {eval_matrix.config.name} "
            f"policies={len(eval_matrix.policy_runs)} "
            f"attempts={sum(len(run.attempts) for run in eval_matrix.policy_runs)} "
            f"replays={len(eval_matrix.replay_runs)} "
            f"{status_counts}"
        )
        console.print(f"wrote {eval_matrix.out_dir / 'eval_matrix_manifest.json'}")
        return

    if policy is None:
        raise typer.BadParameter("Provide --policy or --all-policies")

    eval_run = run_eval_config(config, policy, out)
    status_counts = ", ".join(
        f"{status}={count}"
        for status, count in sorted(
            _status_counts(eval_run).items(),
        )
    )
    console.print(
        f"[green]eval complete[/green] {eval_run.config.name} "
        f"policy={eval_run.policy} attempts={len(eval_run.attempts)} "
        f"{status_counts}"
    )
    console.print(f"wrote {eval_run.out_dir / 'run_manifest.json'}")


@app.command("replay")
def replay_run(
    source_run_dir: Path = typer.Argument(
        ...,
        help="Source artifact directory to replay.",
    ),
    out: Path = typer.Option(..., "--out", help="Directory for replay artifacts."),
) -> None:
    replay = run_replay(source_run_dir, out)
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


def _status_counts(eval_run: EvalRun) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in eval_run.attempts:
        counts[attempt.result.status] = counts.get(attempt.result.status, 0) + 1
    return counts


def _matrix_status_counts(eval_matrix: EvalMatrixRun) -> dict[str, int]:
    counts: dict[str, int] = {}
    for eval_run in eval_matrix.policy_runs:
        for status, count in _status_counts(eval_run).items():
            counts[status] = counts.get(status, 0) + count
    return counts
