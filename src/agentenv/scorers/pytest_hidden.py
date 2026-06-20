import shutil
from dataclasses import dataclass
from pathlib import Path

from agentenv.runners.command_runner import CommandResult, run_process
from agentenv.tasks.schema import HiddenValidator


@dataclass(frozen=True)
class HiddenScoreResult:
    validator_id: str
    passed: bool
    command_result: CommandResult


def run_hidden_pytest_validator(
    workspace: Path,
    task_dir: Path,
    validator: HiddenValidator,
    timeout_seconds: int,
) -> HiddenScoreResult:
    source = (task_dir / validator.path).resolve()
    target = (workspace / validator.path).resolve()

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    command_result = run_process(
        ["uv", "run", "pytest", validator.path],
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
    return HiddenScoreResult(
        validator_id=validator.id,
        passed=command_result.returncode == 0,
        command_result=command_result,
    )


def run_hidden_pytest_validators(
    workspace: Path,
    task_dir: Path,
    validators: list[HiddenValidator],
    timeout_seconds: int,
) -> list[HiddenScoreResult]:
    return [
        run_hidden_pytest_validator(
            workspace,
            task_dir,
            validator,
            timeout_seconds,
        )
        for validator in validators
    ]
