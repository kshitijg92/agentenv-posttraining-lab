import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agentenv.orchestrators.attempt import AttemptResult, AttemptStatus, CheckStatus
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir


StatusField = Literal["attempt_status", "public_status", "hidden_status"]


class ScorerAuditCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    task_manifest: str = Field(min_length=1)
    submission: str = Field(min_length=1)
    expected_attempt_status: AttemptStatus
    expected_public_status: CheckStatus
    expected_hidden_status: CheckStatus
    purpose: str = Field(min_length=1)


@dataclass(frozen=True)
class StatusComparison:
    field: StatusField
    expected: str
    actual: str

    @property
    def match(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True)
class ScorerAuditResult:
    case: ScorerAuditCase
    case_dir: Path
    attempt_artifact_dir: Path
    attempt_result: AttemptResult
    comparisons: tuple[StatusComparison, ...]

    @property
    def overall_match(self) -> bool:
        return all(comparison.match for comparison in self.comparisons)


def run_scorer_audit(case_root: Path, out_dir: Path) -> list[ScorerAuditResult]:
    case_root = case_root.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir = out_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    results: list[ScorerAuditResult] = []
    for case_dir in _case_dirs(case_root):
        case = load_scorer_audit_case(case_dir / "case.yaml")
        attempt_artifact_dir = attempts_dir / case.id
        attempt_run = run_and_persist_patch_attempt_to_dir(
            _resolve_repo_relative_path(case.task_manifest),
            (case_dir / case.submission).resolve(),
            attempt_artifact_dir,
        )
        results.append(
            ScorerAuditResult(
                case=case,
                case_dir=case_dir,
                attempt_artifact_dir=attempt_artifact_dir,
                attempt_result=attempt_run.result,
                comparisons=_comparisons(case, attempt_run.result),
            )
        )

    _write_jsonl(results, out_dir / "scorer_audit_results.jsonl", out_dir)
    _write_markdown(results, out_dir / "scorer_audit.md", out_dir)
    return results


def load_scorer_audit_case(path: Path) -> ScorerAuditCase:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected scorer audit case object at {path}")
    return ScorerAuditCase.model_validate(raw)


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


def _comparisons(
    case: ScorerAuditCase,
    result: AttemptResult,
) -> tuple[StatusComparison, ...]:
    return (
        StatusComparison(
            field="attempt_status",
            expected=case.expected_attempt_status,
            actual=result.status,
        ),
        StatusComparison(
            field="public_status",
            expected=case.expected_public_status,
            actual=result.public_status,
        ),
        StatusComparison(
            field="hidden_status",
            expected=case.expected_hidden_status,
            actual=result.hidden_status,
        ),
    )


def _write_jsonl(
    results: list[ScorerAuditResult],
    path: Path,
    out_dir: Path,
) -> None:
    lines = [
        json.dumps(_json_record(result, out_dir), sort_keys=True) for result in results
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def _json_record(result: ScorerAuditResult, out_dir: Path) -> dict[str, object]:
    return {
        "case_id": result.case.id,
        "purpose": result.case.purpose,
        "task_manifest": result.case.task_manifest,
        "submission": result.case.submission,
        "attempt_artifact_dir": str(result.attempt_artifact_dir.relative_to(out_dir)),
        "attempt_id": result.attempt_result.attempt_id,
        "error_class": result.attempt_result.error_class,
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
    results: list[ScorerAuditResult],
    path: Path,
    out_dir: Path,
) -> None:
    lines = [
        "# Scorer Audit",
        "",
        "## Summary",
        "",
        "| case | overall | attempt_artifact_dir |",
        "| --- | --- | --- |",
    ]
    for result in results:
        lines.append(
            f"| {result.case.id} | {_match_display(result.overall_match)} | "
            f"{result.attempt_artifact_dir.relative_to(out_dir)} |"
        )

    lines.extend(
        [
            "",
            "## Status Comparisons",
            "",
            "| case | field | expected | actual | match |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for result_index, result in enumerate(results):
        for comparison in result.comparisons:
            lines.append(
                f"| {result.case.id} | {comparison.field} | "
                f"{comparison.expected} | {comparison.actual} | "
                f"{_match_display(comparison.match)} |"
            )
        if result_index < len(results) - 1:
            lines.append("|  |  |  |  |  |")

    path.write_text("\n".join(lines) + "\n")


def _match_display(match: bool) -> str:
    return "PASS" if match else "FAIL"
