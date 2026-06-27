import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from agentenv.controls.agent_control_scripts import (
    AgentControlScriptCase,
    ExpectedAgentControlResult,
    load_agent_control_script_case,
)
from agentenv.evals.resolve import scorer_control_patch_path
from agentenv.evals.schema import ScorerControlName
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_task_run import (
    AgentTaskRun,
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.attempt import AttemptResult, AttemptStatus, CheckStatus
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest, validate_task_manifest_paths


CONTROL_RUN_ARTIFACT_VERSION = "control_run_v0"
ControlLayer = Literal["scorer", "agent"]
MatchStatus = Literal["PASS", "FAIL"]
JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ScorerControlExpectation:
    control: ScorerControlName
    expected_attempt_status: AttemptStatus
    expected_public_status: CheckStatus
    expected_hidden_status: CheckStatus


@dataclass(frozen=True)
class ControlTask:
    task_id: str
    manifest_path: Path
    manifest: TaskManifest


@dataclass(frozen=True)
class ControlRecord:
    task_id: str
    control_layer: ControlLayer
    control_name: str
    repeat_index: int
    artifact_dir: Path
    expected: JsonObject
    actual: JsonObject
    match: bool


@dataclass(frozen=True)
class ControlRun:
    control_run_id: str
    task_pack_path: Path
    out_dir: Path
    repeats: int
    created_at: str
    records: list[ControlRecord]

    @property
    def overall_match(self) -> bool:
        return all(record.match for record in self.records)


def run_controls(task_pack: Path, repeats: int, out_dir: Path) -> ControlRun:
    if repeats <= 0:
        raise ValueError("repeats must be greater than 0")

    task_pack_path = task_pack.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    scorer_control_dir = out_dir / "scorer_control_patches"
    agent_control_dir = out_dir / "agent_control_scripts"
    scorer_control_dir.mkdir(parents=True, exist_ok=True)
    agent_control_dir.mkdir(parents=True, exist_ok=True)

    tasks = _discover_control_tasks(task_pack_path)
    control_run = ControlRun(
        control_run_id=f"controls_{uuid4().hex}",
        task_pack_path=task_pack_path,
        out_dir=out_dir,
        repeats=repeats,
        created_at=_utc_now(),
        records=[],
    )

    for task in tasks:
        for control, submission_path in _scorer_control_paths(task):
            for repeat_index in range(repeats):
                control_run.records.append(
                    _run_scorer_control(
                        task=task,
                        control=control,
                        submission_path=submission_path,
                        repeat_index=repeat_index,
                        out_dir=scorer_control_dir,
                    )
                )

        for control_name, control_path in _agent_control_script_paths(task):
            control_case = load_agent_control_script_case(control_path)
            for repeat_index in range(repeats):
                control_run.records.append(
                    _run_agent_control(
                        task=task,
                        control_name=control_name,
                        control_case=control_case,
                        repeat_index=repeat_index,
                        out_dir=agent_control_dir,
                    )
                )

    _write_jsonl(control_run)
    _write_manifest(control_run)
    _write_markdown(control_run)
    return control_run


def expected_control_outcome(control: ScorerControlName) -> ScorerControlExpectation:
    if control == "oracle":
        return ScorerControlExpectation(
            control=control,
            expected_attempt_status="PASS",
            expected_public_status="PASS",
            expected_hidden_status="PASS",
        )
    if control == "bad.noop":
        return ScorerControlExpectation(
            control=control,
            expected_attempt_status="HIDDEN_TEST_FAIL",
            expected_public_status="PASS",
            expected_hidden_status="FAIL",
        )
    if control == "bad.public_only":
        return ScorerControlExpectation(
            control=control,
            expected_attempt_status="HIDDEN_TEST_FAIL",
            expected_public_status="PASS",
            expected_hidden_status="FAIL",
        )
    raise ValueError(f"Unknown control: {control}")


def _run_scorer_control(
    *,
    task: ControlTask,
    control: ScorerControlName,
    submission_path: Path,
    repeat_index: int,
    out_dir: Path,
) -> ControlRecord:
    expectation = expected_control_outcome(control)
    artifact_dir = (
        out_dir
        / f"{task.task_id}__{_control_slug(control)}__repeat_{repeat_index + 1:03d}"
    )
    attempt_run = run_and_persist_patch_attempt_to_dir(
        task.manifest_path,
        submission_path,
        artifact_dir,
    )
    expected = _scorer_expected_json(expectation)
    actual = _scorer_actual_json(attempt_run.result)
    return ControlRecord(
        task_id=task.task_id,
        control_layer="scorer",
        control_name=control,
        repeat_index=repeat_index,
        artifact_dir=artifact_dir,
        expected=expected,
        actual=actual,
        match=_scorer_match(expectation, attempt_run.result),
    )


def _run_agent_control(
    *,
    task: ControlTask,
    control_name: str,
    control_case: AgentControlScriptCase,
    repeat_index: int,
    out_dir: Path,
) -> ControlRecord:
    artifact_dir = (
        out_dir / f"{task.task_id}__{control_name}__repeat_{repeat_index + 1:03d}"
    )
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )
    decoding_config = model_client.default_decoding_config()
    agent_task_run = run_and_persist_agent_task_attempt_to_dir(
        task.manifest_path,
        model_client,
        decoding_config,
        artifact_dir,
        agent_control_script=control_case,
    )

    expected = _agent_expected_json(control_case.expected_result)
    actual = _agent_actual_json(agent_task_run)
    return ControlRecord(
        task_id=task.task_id,
        control_layer="agent",
        control_name=control_name,
        repeat_index=repeat_index,
        artifact_dir=artifact_dir,
        expected=expected,
        actual=actual,
        match=_agent_match(control_case.expected_result, agent_task_run),
    )


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


def _scorer_control_paths(task: ControlTask) -> list[tuple[ScorerControlName, Path]]:
    return [
        (
            "oracle",
            scorer_control_patch_path(
                task.manifest_path.parent,
                task.manifest,
                "oracle",
            ),
        ),
        (
            "bad.noop",
            scorer_control_patch_path(
                task.manifest_path.parent,
                task.manifest,
                "bad.noop",
            ),
        ),
        (
            "bad.public_only",
            scorer_control_patch_path(
                task.manifest_path.parent,
                task.manifest,
                "bad.public_only",
            ),
        ),
    ]


def _agent_control_script_paths(task: ControlTask) -> list[tuple[str, Path]]:
    agent_controls = task.manifest.controls.agent_control_scripts
    return [
        (
            "happy",
            _resolve_task_control_path(task, agent_controls.happy),
        ),
        (
            "malformed",
            _resolve_task_control_path(task, agent_controls.malformed),
        ),
        (
            "recoverable",
            _resolve_task_control_path(task, agent_controls.recoverable),
        ),
    ]


def _resolve_task_control_path(task: ControlTask, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        raise ValueError(f"Task control paths must be relative: {raw_path}")

    task_dir = task.manifest_path.parent.resolve()
    resolved = (task_dir / path).resolve()
    if not resolved.is_relative_to(task_dir):
        raise ValueError(f"Task control path escapes task directory: {raw_path}")
    if not resolved.is_file():
        raise ValueError(f"Task control file does not exist: {resolved}")
    return resolved


def _write_jsonl(control_run: ControlRun) -> Path:
    path = control_run.out_dir / "control_results.jsonl"
    lines = [
        json.dumps(_record_json(control_run, record), sort_keys=True)
        for record in control_run.records
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return path


def _write_manifest(control_run: ControlRun) -> Path:
    path = control_run.out_dir / "control_run_manifest.json"
    path.write_text(
        json.dumps(_control_run_manifest(control_run), indent=2, sort_keys=True) + "\n"
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
        f"- Records: {len(control_run.records)}",
        f"- Overall: {_match_display(control_run.overall_match)}",
        "",
        "## Control Overview",
        "",
        "| layer | control | tasks | records | matches | failures | status |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for layer, control_name, task_count, record_count, matches in _overview_rows(
        control_run
    ):
        failures = record_count - matches
        lines.append(
            f"| {layer} | {control_name} | {task_count} | {record_count} | "
            f"{matches}/{record_count} | {failures} | "
            f"{_match_badge(matches == record_count)} |"
        )

    lines.extend(
        [
            "",
            "## Control Summary",
            "",
            "| layer | task_id | control | repeats | matches | expected |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for control_layer, task_id, control_name in _summary_keys(control_run):
        records = [
            record
            for record in control_run.records
            if record.control_layer == control_layer
            and record.task_id == task_id
            and record.control_name == control_name
        ]
        matches = sum(record.match for record in records)
        expected = records[0].expected if records else {}
        lines.append(
            f"| {control_layer} | {task_id} | {control_name} | {len(records)} | "
            f"{matches}/{len(records)} | {_json_display(expected)} |"
        )

    lines.extend(
        [
            "",
            "## Record Details",
            "",
            "| layer | task_id | control | repeat | expected | actual | match | artifact_dir |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for record in control_run.records:
        lines.append(
            f"| {record.control_layer} | {record.task_id} | {record.control_name} | "
            f"{record.repeat_index + 1} | {_json_display(record.expected)} | "
            f"{_json_display(record.actual)} | {_match_display(record.match)} | "
            f"{record.artifact_dir.relative_to(control_run.out_dir)} |"
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
        "record_count": len(control_run.records),
        "overall_match": control_run.overall_match,
        "artifacts": {
            "agent_control_scripts": "agent_control_scripts",
            "scorer_control_patches": "scorer_control_patches",
            "report": "control_report.md",
            "results": "control_results.jsonl",
        },
        "records": [
            _record_json(control_run, record) for record in control_run.records
        ],
    }


def _record_json(
    control_run: ControlRun,
    record: ControlRecord,
) -> dict[str, object]:
    return {
        "control_run_id": control_run.control_run_id,
        "task_id": record.task_id,
        "control_layer": record.control_layer,
        "control_name": record.control_name,
        "repeat_index": record.repeat_index,
        "artifact_dir": str(record.artifact_dir.relative_to(control_run.out_dir)),
        "expected": record.expected,
        "actual": record.actual,
        "match": record.match,
    }


def _summary_keys(control_run: ControlRun) -> list[tuple[str, str, str]]:
    return sorted(
        {
            (record.control_layer, record.task_id, record.control_name)
            for record in control_run.records
        }
    )


def _overview_rows(control_run: ControlRun) -> list[tuple[str, str, int, int, int]]:
    rows: list[tuple[str, str, int, int, int]] = []
    for control_layer in sorted(
        {record.control_layer for record in control_run.records}
    ):
        layer_records = [
            record
            for record in control_run.records
            if record.control_layer == control_layer
        ]
        rows.append(_overview_row(control_layer, "all controls", layer_records))
        for control_name in sorted({record.control_name for record in layer_records}):
            control_records = [
                record
                for record in layer_records
                if record.control_name == control_name
            ]
            rows.append(_overview_row(control_layer, control_name, control_records))
    return rows


def _overview_row(
    control_layer: str,
    control_name: str,
    records: list[ControlRecord],
) -> tuple[str, str, int, int, int]:
    return (
        control_layer,
        control_name,
        len({record.task_id for record in records}),
        len(records),
        sum(record.match for record in records),
    )


def _scorer_expected_json(expectation: ScorerControlExpectation) -> JsonObject:
    return {
        "attempt_status": expectation.expected_attempt_status,
        "public_status": expectation.expected_public_status,
        "hidden_status": expectation.expected_hidden_status,
    }


def _scorer_actual_json(result: AttemptResult) -> JsonObject:
    return {
        "attempt_id": result.attempt_id,
        "attempt_status": result.status,
        "public_status": result.public_status,
        "hidden_status": result.hidden_status,
        "final_diff_hash": result.final_diff_hash,
        "error_class": result.error_class,
    }


def _scorer_match(
    expectation: ScorerControlExpectation,
    result: AttemptResult,
) -> bool:
    return (
        result.status == expectation.expected_attempt_status
        and result.public_status == expectation.expected_public_status
        and result.hidden_status == expectation.expected_hidden_status
    )


def _agent_expected_json(expected_result: ExpectedAgentControlResult) -> JsonObject:
    expected: JsonObject = {
        "prompt_loop_status": expected_result.prompt_loop_status,
    }
    if expected_result.tool_results is not None:
        expected["tool_results"] = [
            {
                "tool_name": tool_result.tool_name,
                "status": tool_result.status,
                "error_class": tool_result.error_class,
            }
            for tool_result in expected_result.tool_results
        ]
    return expected


def _agent_actual_json(agent_task_run: AgentTaskRun) -> JsonObject:
    attempt_result = agent_task_run.result.attempt_result
    return {
        "agent_run_id": agent_task_run.result.run_id,
        "agent_run_status": agent_task_run.result.status,
        "prompt_loop_status": agent_task_run.result.prompt_loop_status,
        "tool_results": _actual_tool_results(agent_task_run),
        "attempt_status": attempt_result.status if attempt_result is not None else None,
        "public_status": (
            attempt_result.public_status if attempt_result is not None else None
        ),
        "hidden_status": (
            attempt_result.hidden_status if attempt_result is not None else None
        ),
        "error_class": agent_task_run.result.error_class,
    }


def _actual_tool_results(agent_task_run: AgentTaskRun) -> list[JsonObject]:
    if agent_task_run.prompt_loop_result is None:
        return []
    return [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in agent_task_run.prompt_loop_result.tool_results
    ]


def _agent_match(
    expected_result: ExpectedAgentControlResult,
    agent_task_run: AgentTaskRun,
) -> bool:
    if agent_task_run.result.prompt_loop_status != expected_result.prompt_loop_status:
        return False

    expected_tool_results = expected_result.tool_results
    if expected_tool_results is None:
        return True

    return _actual_tool_results(agent_task_run) == [
        {
            "tool_name": tool_result.tool_name,
            "status": tool_result.status,
            "error_class": tool_result.error_class,
        }
        for tool_result in expected_tool_results
    ]


def _json_display(value: JsonObject) -> str:
    return json.dumps(value, sort_keys=True)


def _match_display(match: bool) -> MatchStatus:
    return "PASS" if match else "FAIL"


def _match_badge(match: bool) -> str:
    if match:
        return (
            '<span style="background-color: #dcfce7; color: #166534; '
            'font-weight: 700; padding: 2px 6px; border-radius: 4px;">PASS</span>'
        )
    return (
        '<span style="background-color: #fee2e2; color: #991b1b; '
        'font-weight: 700; padding: 2px 6px; border-radius: 4px;">FAIL</span>'
    )


def _control_slug(control_name: str) -> str:
    return control_name.replace(".", "_")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
