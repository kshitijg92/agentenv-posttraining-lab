from pathlib import Path

from agentenv.orchestrators.attempt import AttemptRun, run_patch_attempt
from agentenv.orchestrators.attempt_io import write_attempt_artifacts


def run_and_persist_patch_attempt_to_dir(
    task_manifest_path: Path,
    submission_path: Path,
    out_dir: Path,
) -> AttemptRun:
    attempt_run = run_patch_attempt(task_manifest_path, submission_path)
    write_attempt_artifacts(attempt_run, out_dir)
    return attempt_run
