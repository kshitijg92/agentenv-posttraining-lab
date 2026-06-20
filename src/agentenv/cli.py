from pathlib import Path

import typer
from rich.console import Console

from agentenv.orchestrators.attempt import run_patch_attempt
from agentenv.orchestrators.attempt_io import write_attempt_artifacts
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
    attempt_run = run_patch_attempt(task_manifest, submission)
    artifact_paths = write_attempt_artifacts(attempt_run, out)
    style = "green" if attempt_run.result.status == "PASS" else "red"
    console.print(
        f"[{style}]{attempt_run.result.status}[/{style}] "
        f"{attempt_run.result.task_id}"
    )
    console.print(f"wrote {artifact_paths.attempt_json}")
