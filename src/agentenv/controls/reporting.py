from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Protocol


ControlLayer = Literal["scorer", "agent"]
FlakeDetectionStatus = Literal["stable", "drifted"]
MatchStatus = Literal["PASS", "FAIL"]
JsonObject = dict[str, Any]


class ControlRecordView(Protocol):
    @property
    def task_id(self) -> str: ...

    @property
    def control_layer(self) -> ControlLayer: ...

    @property
    def control_name(self) -> str: ...

    @property
    def repeat_index(self) -> int: ...

    @property
    def artifact_dir(self) -> Path: ...

    @property
    def expected(self) -> JsonObject: ...

    @property
    def actual(self) -> JsonObject: ...

    @property
    def match(self) -> bool: ...


class ControlRunView(Protocol):
    @property
    def control_run_id(self) -> str: ...

    @property
    def task_pack_path(self) -> Path: ...

    @property
    def out_dir(self) -> Path: ...

    @property
    def repeats(self) -> int: ...

    @property
    def records(self) -> Sequence[ControlRecordView]: ...

    @property
    def flake_detection(self) -> JsonObject | None: ...

    @property
    def overall_match(self) -> bool: ...


def render_control_report(control_run: ControlRunView) -> str:
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
        "## Flake Detection",
        "",
    ]
    lines.extend(_flake_detection_table(control_run.flake_detection))
    lines.extend(
        [
            "",
            "## Scorer Control Overview",
            "",
        ]
    )
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

    return "\n".join(lines) + "\n"


def _records_for_layer(
    control_run: ControlRunView,
    control_layer: ControlLayer,
) -> list[ControlRecordView]:
    return [
        record
        for record in control_run.records
        if record.control_layer == control_layer
    ]


def _flake_detection_table(flake_detection: JsonObject | None) -> list[str]:
    if flake_detection is None:
        return ["No flake detection recorded."]

    rows = [
        "| scope | stability | groups checked | drifted groups |",
        "| --- | --- | ---: | ---: |",
    ]
    rows.append(
        _flake_detection_row(
            "overall",
            flake_detection["status"],
            flake_detection["groups_checked"],
            flake_detection["drifted_groups"],
        )
    )
    for layer in ("scorer", "agent"):
        status, groups_checked, drifted_groups = _flake_detection_layer_counts(
            flake_detection,
            layer,
        )
        rows.append(
            _flake_detection_row(
                layer,
                status,
                groups_checked,
                drifted_groups,
            )
        )
    rows.extend(
        [
            "",
            (
                "Per-file normalized hashes and drift details are in "
                "`control_run_manifest.json`."
            ),
        ]
    )
    return rows


def _flake_detection_layer_counts(
    flake_detection: JsonObject,
    layer: ControlLayer,
) -> tuple[FlakeDetectionStatus, int, int]:
    layer_groups = flake_detection["groups"][layer]
    drifted_groups = sum(
        group["status"] == "drifted"
        for group in layer_groups
    )
    status: FlakeDetectionStatus = "drifted" if drifted_groups else "stable"
    return status, len(layer_groups), drifted_groups


def _flake_detection_row(
    scope: str,
    status: object,
    groups_checked: object,
    drifted_groups: object,
) -> str:
    return (
        f"| {scope} | {_display(status)} | {_display(groups_checked)} "
        f"| {_display(drifted_groups)} |"
    )


def _overview_table(records: list[ControlRecordView]) -> list[str]:
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


def _scorer_summary_table(records: list[ControlRecordView]) -> list[str]:
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


def _agent_summary_table(records: list[ControlRecordView]) -> list[str]:
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
    control_run: ControlRunView,
    records: list[ControlRecordView],
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
    control_run: ControlRunView,
    records: list[ControlRecordView],
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


def _summary_keys(records: Sequence[ControlRecordView]) -> list[tuple[str, str]]:
    return sorted(
        {
            (record.task_id, record.control_name)
            for record in records
        }
    )


def _record_group(
    records: Sequence[ControlRecordView],
    task_id: str,
    control_name: str,
) -> list[ControlRecordView]:
    return [
        record
        for record in records
        if record.task_id == task_id and record.control_name == control_name
    ]


def _overview_rows(
    records: Sequence[ControlRecordView],
) -> list[tuple[str, int, int, int]]:
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
    records: Sequence[ControlRecordView],
) -> tuple[str, int, int, int]:
    return (
        control_name,
        len({record.task_id for record in records}),
        len(records),
        sum(record.match for record in records),
    )


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
