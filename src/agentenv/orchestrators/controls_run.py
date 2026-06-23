import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from agentenv.evals.resolve import control_patch_path
from agentenv.evals.schema import ControlName
from agentenv.orchestrators.attempt import AttemptResult, AttemptStatus, CheckStatus
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest, validate_task_manifest_paths


CONTROL_RUN_ARTIFACT_VERSION = "control_run_v0"
CONTROL_NAMES: tuple[ControlName, ...] = ("oracle", "bad.noop", "bad.public_only")
MatchStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class ControlExpectation:
    control: ControlName
    expected_attempt_status: AttemptStatus
    expected_public_status: CheckStatus
    expected_hidden_status: CheckStatus


@dataclass(frozen=True)
class ControlTask:
    task_id: str
    manifest_path: Path
    manifest: TaskManifest


@dataclass(frozen=True)
class ControlAttemptRecord:
    task_id: str
    control: ControlName
    repeat_index: int
    attempt_dir: Path
    result: AttemptResult
    expectation: ControlExpectation

    @property
    def match(self) -> bool:
        return (
            self.result.status == self.expectation.expected_attempt_status
            and self.result.public_status == self.expectation.expected_public_status
            and self.result.hidden_status == self.expectation.expected_hidden_status
        )


@dataclass(frozen=True)
class ControlRun:
    control_run_id: str
    task_pack_path: Path
    out_dir: Path
    repeats: int
    created_at: str
    attempts: list[ControlAttemptRecord]

    @property
    def overall_match(self) -> bool:
        return all(attempt.match for attempt in self.attempts)


def run_controls(task_pack: Path, repeats: int, out_dir: Path) -> ControlRun:
    if repeats <= 0:
        raise ValueError("repeats must be greater than 0")

    task_pack_path = task_pack.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir = out_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    tasks = _discover_control_tasks(task_pack_path)
    control_run = ControlRun(
        control_run_id=f"controls_{uuid4().hex}",
        task_pack_path=task_pack_path,
        out_dir=out_dir,
        repeats=repeats,
        created_at=_utc_now(),
        attempts=[],
    )

    for task in tasks:
        for control in CONTROL_NAMES:
            expectation = expected_control_outcome(control)
            submission_path = control_patch_path(
                task.manifest_path.parent,
                task.manifest,
                control,
            )
            for repeat_index in range(repeats):
                attempt_dir = (
                    attempts_dir
                    / f"{task.task_id}__{_control_slug(control)}__repeat_{repeat_index + 1:03d}"
                )
                attempt_run = run_and_persist_patch_attempt_to_dir(
                    task.manifest_path,
                    submission_path,
                    attempt_dir,
                )
                control_run.attempts.append(
                    ControlAttemptRecord(
                        task_id=task.task_id,
                        control=control,
                        repeat_index=repeat_index,
                        attempt_dir=attempt_dir,
                        result=attempt_run.result,
                        expectation=expectation,
                    )
                )

    _write_jsonl(control_run)
    _write_manifest(control_run)
    _write_markdown(control_run)
    return control_run


def expected_control_outcome(control: ControlName) -> ControlExpectation:
    if control == "oracle":
        return ControlExpectation(
            control=control,
            expected_attempt_status="PASS",
            expected_public_status="PASS",
            expected_hidden_status="PASS",
        )
    if control == "bad.noop":
        return ControlExpectation(
            control=control,
            expected_attempt_status="HIDDEN_TEST_FAIL",
            expected_public_status="PASS",
            expected_hidden_status="FAIL",
        )
    if control == "bad.public_only":
        return ControlExpectation(
            control=control,
            expected_attempt_status="HIDDEN_TEST_FAIL",
            expected_public_status="PASS",
            expected_hidden_status="FAIL",
        )
    raise ValueError(f"Unknown control: {control}")


def _discover_control_tasks(task_pack_path: Path) -> list[ControlTask]:
    task_manifests = sorted((task_pack_path / "tasks").glob("*/task.yaml"))
    if not task_manifests:
        raise ValueError(f"No task manifests found in task pack: {task_pack_path}")

    tasks: list[ControlTask] = []
    for manifest_path in task_manifests:
        manifest = load_task_manifest(manifest_path)
        validate_task_manifest_paths(manifest, manifest_path)
        tasks.append(
            ControlTask(
                task_id=manifest.id,
                manifest_path=manifest_path.resolve(),
                manifest=manifest,
            )
        )
    return tasks


def _write_jsonl(control_run: ControlRun) -> Path:
    path = control_run.out_dir / "control_results.jsonl"
    lines = [
        json.dumps(_attempt_record_json(control_run, attempt), sort_keys=True)
        for attempt in control_run.attempts
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return path


def _write_manifest(control_run: ControlRun) -> Path:
    path = control_run.out_dir / "control_run_manifest.json"
    path.write_text(
        json.dumps(_control_run_manifest(control_run), indent=2, sort_keys=True)
        + "\n"
    )
    return path


def _write_markdown(control_run: ControlRun) -> Path:
    path = control_run.out_dir / "control_report.md"
    lines = [
        "# Control Calibration",
        "",
        "## Summary",
        "",
        f"- Control run ID: {control_run.control_run_id}",
        f"- Task pack: {control_run.task_pack_path}",
        f"- Repeats: {control_run.repeats}",
        f"- Attempts: {len(control_run.attempts)}",
        f"- Overall: {_match_display(control_run.overall_match)}",
        "",
        "## Control Summary",
        "",
        "| task_id | control | repeats | matches | expected |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task_id, control in _summary_keys(control_run):
        attempts = [
            attempt
            for attempt in control_run.attempts
            if attempt.task_id == task_id and attempt.control == control
        ]
        matches = sum(attempt.match for attempt in attempts)
        expectation = expected_control_outcome(control)
        lines.append(
            f"| {task_id} | {control} | {len(attempts)} | "
            f"{matches}/{len(attempts)} | {_expectation_display(expectation)} |"
        )

    lines.extend(
        [
            "",
            "## Attempt Details",
            "",
            "| task_id | control | repeat | expected | actual | match | artifact_dir |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for attempt in control_run.attempts:
        lines.append(
            f"| {attempt.task_id} | {attempt.control} | {attempt.repeat_index + 1} | "
            f"{_expectation_display(attempt.expectation)} | "
            f"{_actual_display(attempt.result)} | {_match_display(attempt.match)} | "
            f"{attempt.attempt_dir.relative_to(control_run.out_dir)} |"
        )

    path.write_text("\n".join(lines) + "\n")
    return path


def _control_run_manifest(control_run: ControlRun) -> dict[str, object]:
    return {
        "artifact_version": CONTROL_RUN_ARTIFACT_VERSION,
        "control_run_id": control_run.control_run_id,
        "created_at": control_run.created_at,
        "task_pack_path": str(control_run.task_pack_path),
        "repeats": control_run.repeats,
        "attempt_count": len(control_run.attempts),
        "overall_match": control_run.overall_match,
        "artifacts": {
            "attempts": "attempts",
            "results": "control_results.jsonl",
            "report": "control_report.md",
        },
        "attempts": [
            _attempt_record_json(control_run, attempt) for attempt in control_run.attempts
        ],
    }


def _attempt_record_json(
    control_run: ControlRun,
    attempt: ControlAttemptRecord,
) -> dict[str, object]:
    return {
        "control_run_id": control_run.control_run_id,
        "task_id": attempt.task_id,
        "control": attempt.control,
        "repeat_index": attempt.repeat_index,
        "attempt_id": attempt.result.attempt_id,
        "attempt_artifact_dir": str(attempt.attempt_dir.relative_to(control_run.out_dir)),
        "expected": {
            "attempt_status": attempt.expectation.expected_attempt_status,
            "public_status": attempt.expectation.expected_public_status,
            "hidden_status": attempt.expectation.expected_hidden_status,
        },
        "actual": {
            "attempt_status": attempt.result.status,
            "public_status": attempt.result.public_status,
            "hidden_status": attempt.result.hidden_status,
            "error_class": attempt.result.error_class,
        },
        "match": attempt.match,
    }


def _summary_keys(control_run: ControlRun) -> list[tuple[str, ControlName]]:
    return sorted({(attempt.task_id, attempt.control) for attempt in control_run.attempts})


def _expectation_display(expectation: ControlExpectation) -> str:
    return (
        f"attempt_status: {expectation.expected_attempt_status}; "
        f"public_status: {expectation.expected_public_status}; "
        f"hidden_status: {expectation.expected_hidden_status}"
    )


def _actual_display(result: AttemptResult) -> str:
    return (
        f"attempt_status: {result.status}; "
        f"public_status: {result.public_status}; "
        f"hidden_status: {result.hidden_status}"
    )


def _match_display(match: bool) -> MatchStatus:
    return "PASS" if match else "FAIL"


def _control_slug(control: ControlName) -> str:
    return control.replace(".", "_")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
