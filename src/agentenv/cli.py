from pathlib import Path

import typer
from rich.console import Console

from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.orchestrators.eval_run import EvalRun, run_eval_config
from agentenv.replay.runner import run_replay
from agentenv.reporting.markdown import write_markdown_report
from agentenv.tasks.validate import load_task_manifest, validate_task_manifest_paths


app = typer.Typer(no_args_is_help=True)
tasks_app = typer.Typer(no_args_is_help=True)
attempt_app = typer.Typer(no_args_is_help=True)
app.add_typer(tasks_app, name="tasks")
app.add_typer(attempt_app, name="attempt")

console = Console()


@tasks_app.command("validate")
def validate_task(path: Path) -> None:
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


@app.command("eval")
def run_eval(
    config: Path = typer.Option(..., "--config", help="Path to eval config YAML."),
    policy: str = typer.Option(..., "--policy", help="Policy name from the config."),
    out: Path = typer.Option(..., "--out", help="Directory for eval artifacts."),
) -> None:
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
    source_run_dir: Path = typer.Argument(..., help="Eval run directory to replay."),
    out: Path = typer.Option(..., "--out", help="Directory for replay artifacts."),
) -> None:
    replay = run_replay(source_run_dir, out)
    style = "green" if replay.status == "PASS" else "red"
    console.print(
        f"[{style}]{replay.status}[/{style}] "
        f"attempts={len(replay.comparisons)}"
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
