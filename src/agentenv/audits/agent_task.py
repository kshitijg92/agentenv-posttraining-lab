"""Agent-task harness audit execution and historical output rendering."""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentenv.agents.schema import PromptLoopStatus
from agentenv.audits.types import AgentAuditField
from agentenv.controls.agent_control_scripts import (
    AgentControlScriptCase,
    ExpectedAgentControlToolResult,
    load_agent_control_script_case,
)
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.models.schema import ModelFinishReason
from agentenv.orchestrators.agent_task_schema import AgentTaskRunStatus
from agentenv.orchestrators.agent_task_run import (
    AgentTaskRun,
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.attempt import AttemptStatus, CheckStatus


AgentAuditValue = str | None | list[str] | list[dict[str, object]]

_EXPECTATION_FIELDS = {
    "expected_agent_run_status",
    "expected_agent_error_class",
    "expected_prompt_loop_status",
    "expected_prompt_loop_error_class",
    "expected_model_finish_reasons",
    "expected_tool_results",
    "expected_attempt_status",
    "expected_public_status",
    "expected_hidden_status",
}


class AgentTaskAuditCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    task_manifest: str = Field(min_length=1)
    agent_control_script: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    expected_agent_run_status: AgentTaskRunStatus | None = None
    expected_agent_error_class: str | None = Field(default=None, min_length=1)
    expected_prompt_loop_status: PromptLoopStatus | None = None
    expected_prompt_loop_error_class: str | None = Field(default=None, min_length=1)
    expected_model_finish_reasons: list[ModelFinishReason] | None = None
    expected_tool_results: list[ExpectedAgentControlToolResult] | None = None
    expected_attempt_status: AttemptStatus | None = None
    expected_public_status: CheckStatus | None = None
    expected_hidden_status: CheckStatus | None = None

    @model_validator(mode="after")
    def validate_expectations(self) -> "AgentTaskAuditCase":
        if not (_EXPECTATION_FIELDS & self.model_fields_set):
            raise ValueError("agent task audit cases require at least one expectation")
        return self


@dataclass(frozen=True)
class AgentAuditComparison:
    field: AgentAuditField
    expected: AgentAuditValue
    actual: AgentAuditValue

    @property
    def match(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True)
class AgentTaskAuditResult:
    case: AgentTaskAuditCase
    case_dir: Path
    agent_task_artifact_dir: Path
    agent_task_run: AgentTaskRun
    comparisons: tuple[AgentAuditComparison, ...]

    @property
    def overall_match(self) -> bool:
        return all(comparison.match for comparison in self.comparisons)


def run_agent_task_audit(
    case_root: Path,
    out_dir: Path,
) -> list[AgentTaskAuditResult]:
    case_root = case_root.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = out_dir / "agent_task_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    results: list[AgentTaskAuditResult] = []
    for case_dir in _case_dirs(case_root):
        case = load_agent_task_audit_case(case_dir / "case.yaml")
        task_manifest_path = _resolve_repo_relative_path(case.task_manifest)
        control_case = load_agent_control_script_case(
            _resolve_case_relative_path(case_dir, case.agent_control_script)
        )
        artifact_dir = runs_dir / case.id
        model_client = _model_client(control_case)
        decoding_config = model_client.default_decoding_config()
        agent_task_run = run_and_persist_agent_task_attempt_to_dir(
            task_manifest_path,
            model_client,
            decoding_config,
            artifact_dir,
            agent_control_script=control_case,
        )
        results.append(
            AgentTaskAuditResult(
                case=case,
                case_dir=case_dir,
                agent_task_artifact_dir=artifact_dir,
                agent_task_run=agent_task_run,
                comparisons=_comparisons(case, agent_task_run),
            )
        )

    _write_jsonl(results, out_dir / "agent_task_audit_results.jsonl", out_dir)
    _write_markdown(results, out_dir / "agent_task_audit.md", out_dir)
    return results


def load_agent_task_audit_case(path: Path) -> AgentTaskAuditCase:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected agent task audit case object at {path}")
    return AgentTaskAuditCase.model_validate(raw)


def _model_client(control_case: AgentControlScriptCase) -> ScriptedFakeModelClient:
    return ScriptedFakeModelClient(
        model_id="agent-audit-scripted-v0",
        script=control_case.script.steps,
    )


def _case_dirs(case_root: Path) -> list[Path]:
    return sorted(
        path
        for path in case_root.iterdir()
        if path.is_dir() and (path / "case.yaml").is_file()
    )


def _resolve_repo_relative_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return path.resolve()


def _resolve_case_relative_path(case_dir: Path, path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (case_dir / path).resolve()


def _comparisons(
    case: AgentTaskAuditCase,
    agent_task_run: AgentTaskRun,
) -> tuple[AgentAuditComparison, ...]:
    comparisons: list[AgentAuditComparison] = []
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_agent_run_status",
        comparison_field="agent_run_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_agent_error_class",
        comparison_field="agent_error_class",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_prompt_loop_status",
        comparison_field="prompt_loop_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_prompt_loop_error_class",
        comparison_field="prompt_loop_error_class",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_model_finish_reasons",
        comparison_field="model_finish_reasons",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_tool_results",
        comparison_field="tool_results",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_attempt_status",
        comparison_field="attempt_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_public_status",
        comparison_field="public_status",
    )
    _append_comparison(
        comparisons,
        case,
        agent_task_run,
        expected_field="expected_hidden_status",
        comparison_field="hidden_status",
    )
    return tuple(comparisons)


def _append_comparison(
    comparisons: list[AgentAuditComparison],
    case: AgentTaskAuditCase,
    agent_task_run: AgentTaskRun,
    *,
    expected_field: str,
    comparison_field: AgentAuditField,
) -> None:
    if expected_field not in case.model_fields_set:
        return
    comparisons.append(
        AgentAuditComparison(
            field=comparison_field,
            expected=_expected_value(case, expected_field),
            actual=_actual_value(agent_task_run, comparison_field),
        )
    )


def _expected_value(
    case: AgentTaskAuditCase,
    expected_field: str,
) -> AgentAuditValue:
    if expected_field == "expected_model_finish_reasons":
        if case.expected_model_finish_reasons is None:
            return None
        return list(case.expected_model_finish_reasons)
    if expected_field == "expected_tool_results":
        tool_results = case.expected_tool_results
        if tool_results is None:
            return None
        return [
            {
                "tool_name": tool_result.tool_name,
                "status": tool_result.status,
                "error_class": tool_result.error_class,
            }
            for tool_result in tool_results
        ]
    value = getattr(case, expected_field)
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"Unsupported expectation value for {expected_field}")


def _actual_value(
    agent_task_run: AgentTaskRun,
    field: AgentAuditField,
) -> AgentAuditValue:
    result = agent_task_run.result
    attempt_result = result.attempt_result
    if field == "agent_run_status":
        return result.status
    if field == "agent_error_class":
        return result.error_class
    if field == "prompt_loop_status":
        return result.prompt_loop_status
    if field == "prompt_loop_error_class":
        prompt_loop_result = agent_task_run.prompt_loop_result
        return (
            prompt_loop_result.error_class if prompt_loop_result is not None else None
        )
    if field == "model_finish_reasons":
        prompt_loop_result = agent_task_run.prompt_loop_result
        if prompt_loop_result is None:
            return []
        return [
            str(model_response.finish_reason)
            for model_response in prompt_loop_result.model_responses
        ]
    if field == "tool_results":
        return _actual_tool_results(agent_task_run)
    if field == "attempt_status":
        return attempt_result.status if attempt_result is not None else None
    if field == "public_status":
        return attempt_result.public_status if attempt_result is not None else None
    if field == "hidden_status":
        return attempt_result.hidden_status if attempt_result is not None else None


def _actual_tool_results(agent_task_run: AgentTaskRun) -> list[dict[str, object]]:
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


def _write_jsonl(
    results: list[AgentTaskAuditResult],
    path: Path,
    out_dir: Path,
) -> None:
    lines = [
        json.dumps(_json_record(result, out_dir), sort_keys=True) for result in results
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def _json_record(
    result: AgentTaskAuditResult,
    out_dir: Path,
) -> dict[str, object]:
    run_result = result.agent_task_run.result
    return {
        "case_id": result.case.id,
        "purpose": result.case.purpose,
        "task_manifest": result.case.task_manifest,
        "agent_control_script": result.case.agent_control_script,
        "agent_task_artifact_dir": str(
            result.agent_task_artifact_dir.relative_to(out_dir)
        ),
        "agent_attempt_id": run_result.agent_attempt_id,
        "agent_run_status": run_result.status,
        "prompt_loop_status": run_result.prompt_loop_status,
        "error_class": run_result.error_class,
        "overall_match": result.overall_match,
        "comparisons": [
            {
                "field": comparison.field,
                "expected": comparison.expected,
                "actual": comparison.actual,
                "match": comparison.match,
            }
            for comparison in result.comparisons
        ],
    }


def _write_markdown(
    results: list[AgentTaskAuditResult],
    path: Path,
    out_dir: Path,
) -> None:
    lines = [
        "# Agent Task Audit",
        "",
        "## Summary",
        "",
        "| case | overall | agent_run_status | prompt_loop_status | agent_task_artifact_dir |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in results:
        run_result = result.agent_task_run.result
        lines.append(
            f"| {result.case.id} "
            f"| {_match_display(result.overall_match)} "
            f"| {_display(run_result.status)} "
            f"| {_display(run_result.prompt_loop_status)} "
            f"| {result.agent_task_artifact_dir.relative_to(out_dir)} |"
        )

    lines.extend(
        [
            "",
            "## Field Comparisons",
            "",
            "| case | field | expected | actual | match |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for result_index, result in enumerate(results):
        for comparison in result.comparisons:
            lines.append(
                f"| {result.case.id} "
                f"| {comparison.field} "
                f"| {_value_display(comparison.expected)} "
                f"| {_value_display(comparison.actual)} "
                f"| {_match_display(comparison.match)} |"
            )
        if result_index < len(results) - 1:
            lines.append("|  |  |  |  |  |")

    path.write_text("\n".join(lines) + "\n")


def _value_display(value: AgentAuditValue) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return json.dumps(value, sort_keys=True)
    return value


def _display(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _match_display(match: bool) -> str:
    return "PASS" if match else "FAIL"
