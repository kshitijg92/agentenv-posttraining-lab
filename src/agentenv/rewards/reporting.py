from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from agentenv.agents.audit import AgentTaskAuditResult
from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.rewards.audit import HarnessAuditResult, RewardHackAuditResult
from agentenv.rewards.export import RewardHackAuditArtifact
from agentenv.rewards.schema import EvalAttemptRef, HarnessAuditCaseRef
from agentenv.rewards.schema import TrajectoryRecordRef
from agentenv.scorers.audit import ScorerAuditResult


def render_reward_hack_audit_report(artifact: RewardHackAuditArtifact) -> str:
    records = artifact.records
    neutralized_count = _count(records, "exploit_mechanism_neutralized_actual")
    lines = [
        "# Reward-Hack Audit Report",
        "",
        "## Run Details",
        "",
        f"- Artifact directory: {_relative_or_absolute(artifact.out_dir)}",
        f"- Reward audit manifest: {MANIFEST_FILENAME}",
        f"- Runtime version: {artifact.manifest.runtime_version}",
        f"- Case root: {artifact.manifest.case_root}",
        (
            "- Reward-hack case schema version: "
            f"{artifact.manifest.reward_hack_case_schema_version}"
        ),
        f"- Record count: {artifact.manifest.record_count}",
        f"- Passed: {artifact.manifest.pass_count}",
        f"- Failed: {artifact.manifest.fail_count}",
        f"- Results JSONL hash: {artifact.manifest.results_jsonl_hash}",
        "",
        "## Safety Signal Summary",
        "",
        f"- Audit pass rate: {_count_rate(artifact.manifest.pass_count, len(records))}",
        (
            "- Exploit mechanisms detected: "
            f"{_count_rate(_count(records, 'exploit_mechanism_detected_actual'), len(records))}"
        ),
        (
            "- Private-content exposures: "
            f"{_count_rate(_count(records, 'private_content_exposed_actual'), len(records))}"
        ),
        (
            "- Exploit mechanisms neutralized: "
            f"{_count_rate(neutralized_count, len(records))}"
        ),
        (
            "- Task success allowed: "
            f"{_count_rate(_count(records, 'task_success_allowed_actual'), len(records))}"
        ),
        (
            "- Training allowed: "
            f"{_count_rate(_count(records, 'training_allowed_actual'), len(records))}"
        ),
        (
            "- Valid controls succeeded: "
            f"{_count_rate(_count(records, 'valid_control_task_success_actual'), len(records))}"
        ),
        "",
        "## Evidence Reuse",
        "",
    ]
    lines.extend(_evidence_reuse_table(records))
    lines.extend(
        [
            "",
            "## Cases",
            "",
        ]
    )
    lines.extend(_case_table(records))
    lines.extend(
        [
            "",
            "## Outcome Comparisons",
            "",
        ]
    )
    lines.extend(_outcome_comparison_table(records))
    lines.extend(
        [
            "",
            "## Runtime Checks",
            "",
        ]
    )
    lines.extend(_runtime_check_table(records))
    lines.extend(
        [
            "",
            "## Source Audit Results",
            "",
        ]
    )
    lines.extend(_source_audit_table(records))
    lines.extend(
        [
            "",
            "## Leakage Scans",
            "",
        ]
    )
    lines.extend(_leakage_scan_table(records))
    lines.extend(
        [
            "",
            "## Measures",
            "",
            (
                "This report measures whether authored reward-hack cases are detected, "
                "neutralized, and excluded from training while their valid controls "
                "still succeed on the same task surface."
            ),
            "",
            "## Does Not Measure",
            "",
            (
                "This is not a complete secure-sandbox claim and does not prove that "
                "all private-validator content is undiscoverable. Hidden-validator "
                "content matching is intentionally limited to canaries and boundary "
                "markers to avoid treating legitimate solution overlap as leakage."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _evidence_reuse_table(records: list[RewardHackAuditResult]) -> list[str]:
    if not records:
        return ["No reward-hack records in this artifact."]

    source_type_counts = Counter(
        record.reward_hack_case.evidence.source_type for record in records
    )
    valid_control_counts = Counter(_valid_control_ref(record) for record in records)
    repeated_controls = {
        ref: count for ref, count in valid_control_counts.items() if count > 1
    }
    rows = [
        "| metric | value |",
        "| --- | ---: |",
        f"| source types | {_counts_display(source_type_counts)} |",
        f"| unique valid controls | {len(valid_control_counts)} |",
        (
            "| max valid-control reuse | "
            f"{max(valid_control_counts.values(), default=0)} |"
        ),
        f"| repeated valid controls | {_counts_display(repeated_controls)} |",
    ]
    return rows


def _case_table(records: list[RewardHackAuditResult]) -> list[str]:
    if not records:
        return ["No reward-hack cases in this artifact."]

    rows = [
        (
            "| reward_hack_id | result | source_type | exploit_class | probe_surface | "
            "probe_reference_type | mechanism_detected | private_exposed | "
            "exploit_mechanism_neutralized | task_success_allowed | "
            "training_allowed | valid_control_success | exploit_case | "
            "valid_control_case | run_dir |"
        ),
        (
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
            "| --- | --- | --- |"
        ),
    ]
    for record in records:
        case = record.reward_hack_case
        spec = case.exploit.exploit_spec
        probe_reference_type = getattr(spec, "probe_reference_type", "")
        rows.append(
            f"| {case.reward_hack_id} "
            f"| {_pass_fail(record.audit_pass)} "
            f"| {case.evidence.source_type} "
            f"| {case.exploit.exploit_classification} "
            f"| {spec.probe_surface} "
            f"| {probe_reference_type} "
            f"| {_bool_display(record.exploit_mechanism_detected_actual)} "
            f"| {_bool_display(record.private_content_exposed_actual)} "
            f"| {_bool_display(record.exploit_mechanism_neutralized_actual)} "
            f"| {_bool_display(record.task_success_allowed_actual)} "
            f"| {_bool_display(record.training_allowed_actual)} "
            f"| {_bool_display(record.valid_control_task_success_actual)} "
            f"| {_source_case_ref(record.exploit_audit_result)} "
            f"| {_source_case_ref(record.valid_control_audit_result)} "
            f"| {_relative_or_absolute(record.run_dir)} |"
        )
    return rows


def _outcome_comparison_table(records: list[RewardHackAuditResult]) -> list[str]:
    rows = [
        "| reward_hack_id | field | expected | actual | result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        reward_hack_id = record.reward_hack_case.reward_hack_id
        for comparison in record.outcome_comparisons:
            rows.append(
                f"| {reward_hack_id} "
                f"| {comparison.field} "
                f"| {_bool_display(comparison.expected)} "
                f"| {_bool_display(comparison.actual)} "
                f"| {_pass_fail(comparison.match)} |"
            )
    return rows


def _runtime_check_table(records: list[RewardHackAuditResult]) -> list[str]:
    rows = [
        "| reward_hack_id | field | expected | actual | result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        reward_hack_id = record.reward_hack_case.reward_hack_id
        for check in record.runtime_checks:
            rows.append(
                f"| {reward_hack_id} "
                f"| {check.field} "
                f"| {_bool_display(check.expected)} "
                f"| {_bool_display(check.actual)} "
                f"| {_pass_fail(check.match)} |"
            )
    return rows


def _source_audit_table(records: list[RewardHackAuditResult]) -> list[str]:
    rows = [
        (
            "| reward_hack_id | role | case_id | source_case_hash | source_status | "
            "prompt_loop_status | attempt_status | public_status | hidden_status | "
            "source_audit_match | artifact_dir |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        rows.append(
            _source_audit_row(
                record.reward_hack_case.reward_hack_id,
                "exploit",
                record.exploit_audit_result,
                record.exploit_source_case_hash,
            )
        )
        rows.append(
            _source_audit_row(
                record.reward_hack_case.reward_hack_id,
                "valid_control",
                record.valid_control_audit_result,
                record.valid_control_source_case_hash,
            )
        )
    return rows


def _source_audit_row(
    reward_hack_id: str,
    role: str,
    result: HarnessAuditResult,
    source_case_hash: str,
) -> str:
    status = _source_statuses(result)
    return (
        f"| {reward_hack_id} "
        f"| {role} "
        f"| {result.case.id} "
        f"| {source_case_hash} "
        f"| {_display(status['source_status'])} "
        f"| {_display(status['prompt_loop_status'])} "
        f"| {_display(status['attempt_status'])} "
        f"| {_display(status['public_status'])} "
        f"| {_display(status['hidden_status'])} "
        f"| {_bool_display(result.overall_match)} "
        f"| {_relative_or_absolute(_source_artifact_dir(result))} |"
    )


def _leakage_scan_table(records: list[RewardHackAuditResult]) -> list[str]:
    rows = [
        (
            "| reward_hack_id | canary_hash | canary_matches | "
            "private_marker_matches | scanned_files |"
        ),
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for record in records:
        scan = record.leakage_scan_result
        rows.append(
            f"| {record.reward_hack_case.reward_hack_id} "
            f"| {_display(scan.canary_hash)} "
            f"| {len(scan.canary_matches)} "
            f"| {len(scan.private_marker_matches)} "
            f"| {len(scan.scanned_files)} |"
        )
    return rows


def _count(records: Iterable[RewardHackAuditResult], field: str) -> int:
    return sum(getattr(record, field) is True for record in records)


def _valid_control_ref(record: RewardHackAuditResult) -> str:
    evidence = record.reward_hack_case.evidence
    valid_control = evidence.valid_control
    if isinstance(valid_control, HarnessAuditCaseRef):
        return f"{evidence.source_type}:{valid_control.case_dir}:{valid_control.case_id}"
    if isinstance(valid_control, EvalAttemptRef):
        return (
            f"{evidence.source_type}:{valid_control.eval_artifact_dir}:"
            f"{valid_control.eval_attempt_id}"
        )
    if isinstance(valid_control, TrajectoryRecordRef):
        return (
            f"{evidence.source_type}:{valid_control.trajectory_export_dir}:"
            f"{valid_control.trajectory_id}"
        )
    return evidence.source_type


def _source_case_ref(result: HarnessAuditResult) -> str:
    return f"{_relative_or_absolute(result.case_dir)}:{result.case.id}"


def _source_statuses(result: HarnessAuditResult) -> dict[str, str | None]:
    if isinstance(result, ScorerAuditResult):
        attempt = result.attempt_result
        return {
            "source_status": attempt.status,
            "prompt_loop_status": None,
            "attempt_status": attempt.status,
            "public_status": attempt.public_status,
            "hidden_status": attempt.hidden_status,
        }

    run_result = result.agent_task_run.result
    attempt = run_result.attempt_result
    return {
        "source_status": run_result.status,
        "prompt_loop_status": run_result.prompt_loop_status,
        "attempt_status": attempt.status if attempt is not None else None,
        "public_status": attempt.public_status if attempt is not None else None,
        "hidden_status": attempt.hidden_status if attempt is not None else None,
    }


def _source_artifact_dir(result: HarnessAuditResult) -> Path:
    if isinstance(result, AgentTaskAuditResult):
        return result.agent_task_artifact_dir
    return result.attempt_artifact_dir


def _counts_display(counts: Counter[str] | dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _pass_fail(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _bool_display(value: bool) -> str:
    return "true" if value else "false"


def _display(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _count_rate(count: int, total: int) -> str:
    if total == 0:
        return ""
    return f"{count}/{total} ({count / total:.0%})"


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)
