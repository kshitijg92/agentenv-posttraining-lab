import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any, Literal
from uuid import uuid4

import xxhash

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
FLAKE_DETECTION_SCHEMA_VERSION = "control_flake_detection_v0"
SCORER_ARTIFACT_NORMALIZATION_VERSION = "scorer_artifact_normalization_v0"
AGENT_ARTIFACT_NORMALIZATION_VERSION = "agent_artifact_normalization_v0"
ControlLayer = Literal["scorer", "agent"]
FlakeDetectionStatus = Literal["stable", "drifted"]
MatchStatus = Literal["PASS", "FAIL"]
JsonObject = dict[str, Any]


_VOLATILE_JSON_KEYS = {
    "attempt_id",
    "control_run_id",
    "created_at",
    "duration_ms",
    "ended_at",
    "latency_ms",
    "run_id",
    "started_at",
    "stderr_bytes",
    "stdout_bytes",
    "timestamp_utc",
}

_TEMP_WORKSPACE_RE = re.compile(r"/tmp/agentenv-[^/\s:\"']+/workspace")
_TEMP_RUN_RE = re.compile(r"/tmp/agentenv-[^/\s:\"']+")
_PYTEST_TMP_RE = re.compile(r"/tmp/pytest-of-[^/\s:\"']+/pytest-\d+")
_PYTEST_TMP_SEGMENT_RE = re.compile(r"(?:(?<=/)|(?<=\.\.\.))pytest-\d+(?=/)")
_SECONDS_DURATION_RE = re.compile(r"\bin \d+(?:\.\d+)?s\b")
_MILLISECONDS_DURATION_RE = re.compile(r"\bin \d+ms\b")


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
    flake_detection: JsonObject | None = None

    @property
    def overall_match(self) -> bool:
        return all(record.match for record in self.records) and (
            self.flake_detection is None
            or self.flake_detection.get("status") == "stable"
        )


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
    control_run_id = f"controls_{uuid4().hex}"
    created_at = _utc_now()
    records: list[ControlRecord] = []

    for task in tasks:
        for control, submission_path in _scorer_control_paths(task):
            for repeat_index in range(repeats):
                records.append(
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
                records.append(
                    _run_agent_control(
                        task=task,
                        control_name=control_name,
                        control_case=control_case,
                        repeat_index=repeat_index,
                        out_dir=agent_control_dir,
                    )
                )

    flake_detection = _build_flake_detection(
        task_pack_path=task_pack_path,
        repeats=repeats,
        records=records,
    )
    control_run = ControlRun(
        control_run_id=control_run_id,
        task_pack_path=task_pack_path,
        out_dir=out_dir,
        repeats=repeats,
        created_at=created_at,
        records=records,
        flake_detection=flake_detection,
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
    scorer_records = _records_for_layer(control_run, "scorer")
    agent_records = _records_for_layer(control_run, "agent")
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
        "## Scorer Control Overview",
        "",
    ]
    lines.extend(_overview_table(scorer_records))
    lines.extend(
        [
            "",
            "## Agent Control Overview",
            "",
        ]
    )
    lines.extend(_overview_table(agent_records))

    lines.extend(
        [
            "",
            "## Scorer Control Summary",
            "",
        ]
    )
    lines.extend(_scorer_summary_table(scorer_records))
    lines.extend(
        [
            "",
            "## Agent Control Summary",
            "",
        ]
    )
    lines.extend(_agent_summary_table(agent_records))

    lines.extend(
        [
            "",
            "## Scorer Record Details",
            "",
        ]
    )
    lines.extend(_scorer_detail_table(control_run, scorer_records))
    lines.extend(
        [
            "",
            "## Agent Record Details",
            "",
        ]
    )
    lines.extend(_agent_detail_table(control_run, agent_records))

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
        "flake_detection": control_run.flake_detection,
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


def _build_flake_detection(
    *,
    task_pack_path: Path,
    repeats: int,
    records: list[ControlRecord],
) -> JsonObject:
    scorer_records = [
        record
        for record in records
        if record.control_layer == "scorer"
    ]
    agent_records = [
        record
        for record in records
        if record.control_layer == "agent"
    ]
    scorer_groups = [
        _scorer_flake_detection_group(
            task_pack_path,
            _record_group(scorer_records, task_id, control_name),
        )
        for task_id, control_name in _summary_keys(scorer_records)
    ]
    agent_groups = [
        _agent_flake_detection_group(
            task_pack_path,
            _record_group(agent_records, task_id, control_name),
        )
        for task_id, control_name in _summary_keys(agent_records)
    ]
    drifted_groups = sum(
        group["status"] == "drifted"
        for group in [*scorer_groups, *agent_groups]
    )
    status: FlakeDetectionStatus = "drifted" if drifted_groups else "stable"
    return {
        "schema_version": FLAKE_DETECTION_SCHEMA_VERSION,
        "status": status,
        "repeats": repeats,
        "groups_checked": len(scorer_groups) + len(agent_groups),
        "drifted_groups": drifted_groups,
        "groups": {
            "scorer": scorer_groups,
            "agent": agent_groups,
        },
    }


def _scorer_flake_detection_group(
    task_pack_path: Path,
    records: list[ControlRecord],
) -> JsonObject:
    return _control_artifact_flake_detection_group(
        task_pack_path,
        records,
        normalization_version=SCORER_ARTIFACT_NORMALIZATION_VERSION,
    )


def _agent_flake_detection_group(
    task_pack_path: Path,
    records: list[ControlRecord],
) -> JsonObject:
    return _control_artifact_flake_detection_group(
        task_pack_path,
        records,
        normalization_version=AGENT_ARTIFACT_NORMALIZATION_VERSION,
    )


def _control_artifact_flake_detection_group(
    task_pack_path: Path,
    records: list[ControlRecord],
    *,
    normalization_version: str,
) -> JsonObject:
    if not records:
        raise ValueError("Expected at least one control record")

    sorted_records = sorted(records, key=lambda record: record.repeat_index)
    reference = sorted_records[0]
    if reference.repeat_index != 0:
        raise ValueError(
            f"Expected repeat_index 0 reference for {reference.task_id} "
            f"{reference.control_name}"
        )

    repo_root = _find_repo_root(task_pack_path)
    reference_hashes = _normalized_artifact_hashes(
        reference.artifact_dir,
        repo_root,
    )
    drifted_repeats: list[int] = []
    individual_drift_details: dict[str, object] = {}
    for record in sorted_records[1:]:
        actual_hashes = _normalized_artifact_hashes(
            record.artifact_dir,
            repo_root,
        )
        file_drifts = _normalized_file_drifts(reference_hashes, actual_hashes)
        if file_drifts:
            drifted_repeats.append(record.repeat_index)
            individual_drift_details[str(record.repeat_index)] = {
                "files": file_drifts,
            }

    status: FlakeDetectionStatus = (
        "drifted" if drifted_repeats else "stable"
    )
    return {
        "task_id": reference.task_id,
        "control_name": reference.control_name,
        "status": status,
        "reference_repeat_index": reference.repeat_index,
        "drifted_repeats": drifted_repeats,
        "items_compared": {
            "normalization": normalization_version,
            "files": [
                {
                    "path": path,
                    "normalized_hash": hash_value,
                }
                for path, hash_value in sorted(reference_hashes.items())
            ],
        },
        "individual_drift_details": individual_drift_details,
    }


def _normalized_artifact_hashes(
    artifact_dir: Path,
    repo_root: Path | None,
) -> dict[str, str]:
    return {
        file_path.relative_to(artifact_dir).as_posix(): _hash_normalized_artifact_file(
            file_path,
            repo_root,
        )
        for file_path in sorted(artifact_dir.rglob("*"))
        if file_path.is_file()
    }


def _normalized_file_drifts(
    reference_hashes: dict[str, str],
    actual_hashes: dict[str, str],
) -> list[JsonObject]:
    drifts: list[JsonObject] = []
    for path in sorted(set(reference_hashes) - set(actual_hashes)):
        drifts.append(
            {
                "path": path,
                "status": "removed",
                "reference_hash": reference_hashes[path],
                "actual_hash": None,
            }
        )
    for path in sorted(set(actual_hashes) - set(reference_hashes)):
        drifts.append(
            {
                "path": path,
                "status": "added",
                "reference_hash": None,
                "actual_hash": actual_hashes[path],
            }
        )
    for path in sorted(set(reference_hashes) & set(actual_hashes)):
        if reference_hashes[path] != actual_hashes[path]:
            drifts.append(
                {
                    "path": path,
                    "status": "changed",
                    "reference_hash": reference_hashes[path],
                    "actual_hash": actual_hashes[path],
                }
            )
    return drifts


def _hash_normalized_artifact_file(path: Path, repo_root: Path | None) -> str:
    if path.suffix == ".json":
        normalized = _normalize_json_value(json.loads(path.read_text()), repo_root)
        return _hash_json(normalized)
    if path.suffix == ".jsonl":
        normalized_lines = [
            json.dumps(
                _normalize_json_value(json.loads(line), repo_root),
                sort_keys=True,
                separators=(",", ":"),
            )
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        return _hash_bytes(("\n".join(normalized_lines) + "\n").encode())
    return _hash_bytes(_normalize_text(path.read_text(), repo_root).encode())


def _normalize_json_value(value: Any, repo_root: Path | None) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_json_value(raw_value, repo_root)
            for key, raw_value in sorted(value.items())
            if key not in _VOLATILE_JSON_KEYS
        }
    if isinstance(value, list):
        return [_normalize_json_value(item, repo_root) for item in value]
    if isinstance(value, str):
        return _normalize_text(value, repo_root)
    return value


def _normalize_text(text: str, repo_root: Path | None) -> str:
    normalized = text.replace("\r\n", "\n")
    if repo_root is not None:
        normalized = normalized.replace(str(repo_root), "<REPO>")
    normalized = _TEMP_WORKSPACE_RE.sub("<WORKSPACE>", normalized)
    normalized = _TEMP_RUN_RE.sub("<TMP_RUN>", normalized)
    normalized = _PYTEST_TMP_RE.sub("<PYTEST_TMP>", normalized)
    normalized = _PYTEST_TMP_SEGMENT_RE.sub("pytest-<N>", normalized)
    normalized = _SECONDS_DURATION_RE.sub("in <DURATION>", normalized)
    normalized = _MILLISECONDS_DURATION_RE.sub("in <DURATION>", normalized)
    return normalized


def _hash_json(value: object) -> str:
    return _hash_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    )


def _hash_bytes(payload: bytes) -> str:
    return f"xxh64:{xxhash.xxh64(payload).hexdigest()}"


def _find_repo_root(path: Path) -> Path | None:
    resolved = path.resolve()
    candidates = [resolved, *resolved.parents]
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src/agentenv"
        ).is_dir():
            return candidate
    return None


def _records_for_layer(
    control_run: ControlRun,
    control_layer: ControlLayer,
) -> list[ControlRecord]:
    return [
        record
        for record in control_run.records
        if record.control_layer == control_layer
    ]


def _overview_table(records: list[ControlRecord]) -> list[str]:
    if not records:
        return ["No controls for this layer."]

    rows = [
        "| control | tasks | records | matches | failures | status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for control_name, task_count, record_count, matches in _overview_rows(records):
        failures = record_count - matches
        rows.append(
            f"| {control_name} | {task_count} | {record_count} | "
            f"{matches}/{record_count} | {failures} | "
            f"{_match_badge(matches == record_count)} |"
        )
    return rows


def _scorer_summary_table(records: list[ControlRecord]) -> list[str]:
    if not records:
        return ["No scorer controls in this run."]

    rows = [
        (
            "| task_id | control | repeats | matches | expected_attempt | "
            "expected_public | expected_hidden |"
        ),
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for task_id, control_name in _summary_keys(records):
        group = _record_group(records, task_id, control_name)
        expected = group[0].expected
        rows.append(
            f"| {task_id} "
            f"| {control_name} "
            f"| {len(group)} "
            f"| {sum(record.match for record in group)}/{len(group)} "
            f"| {_display(expected.get('attempt_status'))} "
            f"| {_display(expected.get('public_status'))} "
            f"| {_display(expected.get('hidden_status'))} |"
        )
    return rows


def _agent_summary_table(records: list[ControlRecord]) -> list[str]:
    if not records:
        return ["No agent controls in this run."]

    rows = [
        (
            "| task_id | control | repeats | matches | expected_prompt_loop | "
            "expected_tool_results |"
        ),
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for task_id, control_name in _summary_keys(records):
        group = _record_group(records, task_id, control_name)
        expected = group[0].expected
        rows.append(
            f"| {task_id} "
            f"| {control_name} "
            f"| {len(group)} "
            f"| {sum(record.match for record in group)}/{len(group)} "
            f"| {_display(expected.get('prompt_loop_status'))} "
            f"| {_json_display(expected.get('tool_results'))} |"
        )
    return rows


def _scorer_detail_table(
    control_run: ControlRun,
    records: list[ControlRecord],
) -> list[str]:
    if not records:
        return ["No scorer records in this run."]

    rows = [
        (
            "| task_id | control | repeat | expected_attempt | actual_attempt | "
            "expected_public | actual_public | expected_hidden | actual_hidden | "
            "error_class | final_diff_hash | match | artifact_dir |"
        ),
        (
            "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- "
            "| --- | --- |"
        ),
    ]
    for record in records:
        expected = record.expected
        actual = record.actual
        rows.append(
            f"| {record.task_id} "
            f"| {record.control_name} "
            f"| {record.repeat_index + 1} "
            f"| {_display(expected.get('attempt_status'))} "
            f"| {_display(actual.get('attempt_status'))} "
            f"| {_display(expected.get('public_status'))} "
            f"| {_display(actual.get('public_status'))} "
            f"| {_display(expected.get('hidden_status'))} "
            f"| {_display(actual.get('hidden_status'))} "
            f"| {_display(actual.get('error_class'))} "
            f"| {_display(actual.get('final_diff_hash'))} "
            f"| {_match_display(record.match)} "
            f"| {record.artifact_dir.relative_to(control_run.out_dir)} |"
        )
    return rows


def _agent_detail_table(
    control_run: ControlRun,
    records: list[ControlRecord],
) -> list[str]:
    if not records:
        return ["No agent records in this run."]

    rows = [
        (
            "| task_id | control | repeat | expected_prompt_loop | "
            "actual_agent_run | actual_prompt_loop | expected_tool_results | "
            "actual_tool_results | nested_attempt | nested_public | "
            "nested_hidden | error_class | match | artifact_dir |"
        ),
        (
            "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- "
            "| --- | --- | --- |"
        ),
    ]
    for record in records:
        expected = record.expected
        actual = record.actual
        rows.append(
            f"| {record.task_id} "
            f"| {record.control_name} "
            f"| {record.repeat_index + 1} "
            f"| {_display(expected.get('prompt_loop_status'))} "
            f"| {_display(actual.get('agent_run_status'))} "
            f"| {_display(actual.get('prompt_loop_status'))} "
            f"| {_json_display(expected.get('tool_results'))} "
            f"| {_json_display(actual.get('tool_results'))} "
            f"| {_display(actual.get('attempt_status'))} "
            f"| {_display(actual.get('public_status'))} "
            f"| {_display(actual.get('hidden_status'))} "
            f"| {_display(actual.get('error_class'))} "
            f"| {_match_display(record.match)} "
            f"| {record.artifact_dir.relative_to(control_run.out_dir)} |"
        )
    return rows


def _summary_keys(records: list[ControlRecord]) -> list[tuple[str, str]]:
    return sorted(
        {
            (record.task_id, record.control_name)
            for record in records
        }
    )


def _record_group(
    records: list[ControlRecord],
    task_id: str,
    control_name: str,
) -> list[ControlRecord]:
    return [
        record
        for record in records
        if record.task_id == task_id and record.control_name == control_name
    ]


def _overview_rows(records: list[ControlRecord]) -> list[tuple[str, int, int, int]]:
    rows: list[tuple[str, int, int, int]] = []
    rows.append(_overview_row("all controls", records))
    for control_name in sorted({record.control_name for record in records}):
        control_records = [
            record
            for record in records
            if record.control_name == control_name
        ]
        rows.append(_overview_row(control_name, control_records))
    return rows


def _overview_row(
    control_name: str,
    records: list[ControlRecord],
) -> tuple[str, int, int, int]:
    return (
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


def _json_display(value: object) -> str:
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True)


def _display(value: object) -> str:
    if value is None:
        return ""
    return str(value)


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
