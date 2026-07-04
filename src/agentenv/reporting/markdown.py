import json
from collections.abc import Iterable
from pathlib import Path
from statistics import median

from agentenv.artifacts import MANIFEST_FILENAME, ArtifactType
from agentenv.orchestrators.agent_task_run import AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION
from agentenv.orchestrators.eval_run import (
    EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
    EVAL_SUITE_ARTIFACT_SCHEMA_VERSION,
)
from agentenv.orchestrators.attempt_io import SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION
from agentenv.replay.runner import REPLAY_RUN_ARTIFACT_SCHEMA_VERSION


def write_markdown_report(artifact_dir: Path, out_path: Path) -> Path:
    artifact_dir = artifact_dir.resolve()
    manifest = _load_artifact_manifest(artifact_dir)
    artifact_type = manifest.get("artifact_type")

    if artifact_type == ArtifactType.EVAL_RUN.value:
        _require_artifact_schema_version(
            manifest,
            artifact_dir,
            EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
        )
        markdown = render_eval_report(artifact_dir, manifest)
    elif artifact_type == ArtifactType.EVAL_SUITE.value:
        _require_artifact_schema_version(
            manifest,
            artifact_dir,
            EVAL_SUITE_ARTIFACT_SCHEMA_VERSION,
        )
        markdown = render_eval_matrix_report(artifact_dir, manifest)
    elif artifact_type == ArtifactType.REPLAY_RUN.value:
        _require_artifact_schema_version(
            manifest,
            artifact_dir,
            REPLAY_RUN_ARTIFACT_SCHEMA_VERSION,
        )
        markdown = render_replay_report(artifact_dir, manifest)
    else:
        raise ValueError(f"Unsupported artifact_type: {artifact_type!r}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown)
    return out_path


def render_eval_report(
    artifact_dir: Path,
    manifest: dict[str, object],
) -> str:
    run_detail_lines = [
        "# Eval Report",
        "",
        "## Run Details",
        "",
        f"- Artifact directory: {_relative_or_absolute(artifact_dir)}",
        f"- Eval manifest: {MANIFEST_FILENAME}",
        f"- Eval run id: {_display(manifest.get('eval_run_id'))}",
        f"- Config name: {_display(manifest.get('config_name'))}",
        f"- Config path: {_path_display(manifest.get('config_path'))}",
        f"- Config hash: {_display(manifest.get('config_hash'))}",
    ]
    if "model_config" in manifest:
        run_detail_lines.append(
            f"- Model config: {_path_display(manifest.get('model_config'))}"
        )
    if "decoding_config" in manifest:
        run_detail_lines.append(
            f"- Decoding config: {_path_display(manifest.get('decoding_config'))}"
        )

    lines = [
        *run_detail_lines,
        f"- Policy: {_display(manifest.get('policy'))}",
        f"- Policy type: {_display(manifest.get('policy_type'))}",
        f"- Policy family: {_display(manifest.get('policy_family'))}",
        f"- Control layer: {_display(manifest.get('control_layer'))}",
        f"- Control name: {_display(manifest.get('control_name'))}",
        f"- Split: {_display(manifest.get('split'))}",
        f"- Task pack: {_display(manifest.get('task_pack'))}",
        f"- Attempts per task: {_display(manifest.get('attempts_per_task'))}",
        f"- Attempt count: {_display(manifest.get('attempt_count'))}",
        f"- Replay repeats: {_display(manifest.get('replay_repeats'))}",
        "",
        "## Layer Counts",
        "",
        "| layer | status | count |",
        "| --- | --- | ---: |",
    ]

    lines.extend(_layer_count_rows(manifest))
    lines.extend(
        [
            "",
            "## Attempts",
            "",
            (
                "| task_id | attempt_index | artifact_type | "
                "artifact_schema_version | scorer_status | scorer_public_status | "
                "scorer_hidden_status | agent_status | prompt_loop_status | "
                "agent_scorer_status | agent_scorer_public_status | "
                "agent_scorer_hidden_status | error_class | final_diff_hash | "
                "artifact_dir |"
            ),
            (
                "| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- "
                "| --- | --- | --- | --- |"
            ),
        ]
    )

    attempts = manifest.get("attempts")
    if isinstance(attempts, list):
        for raw_attempt in attempts:
            if not isinstance(raw_attempt, dict):
                continue
            attempt_record = dict(raw_attempt)
            _require_supported_attempt_artifact_identity(attempt_record)
            lines.append(_attempt_row(artifact_dir, attempt_record))

    return "\n".join(lines) + "\n"


def render_eval_matrix_report(
    artifact_dir: Path,
    manifest: dict[str, object],
) -> str:
    policy_runs = _load_matrix_policy_runs(artifact_dir, manifest)
    task_ids = _matrix_task_ids(manifest, policy_runs)
    policy_summaries = [
        _matrix_policy_summary(artifact_dir, policy, run_artifact_dir, run_manifest)
        for policy, run_artifact_dir, run_manifest in policy_runs
    ]
    scorer_control_policy_summaries = _summaries_for_control_layer(
        policy_summaries,
        "scorer",
    )
    agent_control_policy_summaries = _summaries_for_control_layer(
        policy_summaries,
        "agent",
    )
    agent_model_policy_summaries = _summaries_for_policy_type(
        policy_summaries,
        "agent_model",
    )
    control_policy_runs = _policy_runs_for_control_policies(policy_runs)
    agent_model_policy_runs = _policy_runs_for_policy_type(policy_runs, "agent_model")
    replay_match_rate = _matrix_replay_match_rate(manifest)

    lines = [
        "# Eval Suite Report",
        "",
        "## Run Details",
        "",
        f"- Artifact directory: {_relative_or_absolute(artifact_dir)}",
        f"- Eval suite manifest: {MANIFEST_FILENAME}",
        f"- Eval suite id: {_display(manifest.get('eval_suite_id'))}",
        f"- Config name: {_display(manifest.get('config_name'))}",
        f"- Config path: {_path_display(manifest.get('config_path'))}",
        f"- Config hash: {_display(manifest.get('config_hash'))}",
        f"- Split: {_display(manifest.get('split'))}",
        f"- Task pack: {_display(manifest.get('task_pack'))}",
        f"- Task count: {len(task_ids)}",
        f"- Policy count: {_display(manifest.get('policy_count'))}",
        f"- Attempt count: {_display(manifest.get('attempt_count'))}",
        (
            "- Hidden-validator version/hash: not captured in eval suite artifacts; "
            f"current substitute is config hash {_display(manifest.get('config_hash'))}"
        ),
        f"- Replay policy count: {_display(manifest.get('replay_policy_count'))}",
        f"- Replay run count: {_display(manifest.get('replay_run_count'))}",
        (
            "- Replay run success summary: "
            f"{_display(manifest.get('replay_run_success_summary'))}"
        ),
        (
            f"- Replay match rate: {_rate_display(replay_match_rate)}"
            if replay_match_rate is not None
            else "- Replay match rate: not run"
        ),
        "",
        "## Tasks",
        "",
    ]
    lines.extend(f"- {task_id}" for task_id in task_ids)
    lines.extend(
        [
            "",
            "## Control Calibration",
            "",
            "### Scorer Control Summary",
            "",
        ]
    )
    lines.extend(_scorer_policy_summary_table(scorer_control_policy_summaries))
    lines.extend(
        [
            "",
            "### Scorer Control Expectations",
            "",
        ]
    )
    lines.extend(_scorer_expectation_table(scorer_control_policy_summaries))
    lines.extend(
        [
            "",
            "### Scorer Aggregate Rates",
            "",
        ]
    )
    lines.extend(_scorer_aggregate_rate_lines(scorer_control_policy_summaries))
    lines.extend(
        [
            "",
            "### Agent Control Summary",
            "",
        ]
    )
    lines.extend(_agent_policy_summary_table(agent_control_policy_summaries))
    lines.extend(
        [
            "",
            "### Agent Control Budget Summary",
            "",
        ]
    )
    lines.extend(_agent_model_budget_table(agent_control_policy_summaries))
    lines.extend(
        [
            "",
            "### Agent Control Expectations",
            "",
        ]
    )
    lines.extend(_agent_expectation_table(agent_control_policy_summaries))
    lines.extend(
        [
            "",
            "### Agent Control Aggregate Rates",
            "",
        ]
    )
    lines.extend(_agent_aggregate_rate_lines(agent_control_policy_summaries))
    lines.extend(
        [
            "",
            "### Control Per-Task Outcomes",
            "",
        ]
    )
    lines.extend(
        _matrix_attempt_table(
            artifact_dir,
            control_policy_runs,
            empty_message="No control policy attempts in this eval suite.",
        )
    )
    lines.extend(
        [
            "",
            "### Replay Checks",
            "",
            (
                f"- Replay match rate: {_rate_display(replay_match_rate)}"
                if replay_match_rate is not None
                else "- Replay match rate: not run"
            ),
            "- Task exclusions: none recorded in eval suite artifacts",
            "",
        ]
    )
    lines.extend(_matrix_replay_rows(manifest))
    lines.extend(
        [
            "",
            "## Agent Model Results",
            "",
            "### Agent Model Outcome Summary",
            "",
        ]
    )
    lines.extend(_agent_model_outcome_table(agent_model_policy_summaries))
    lines.extend(
        [
            "",
            "### Agent Model Debug Signals",
            "",
        ]
    )
    lines.extend(_agent_model_debug_table(agent_model_policy_summaries))
    lines.extend(
        [
            "",
            "### Agent Model Budget Summary",
            "",
        ]
    )
    lines.extend(_agent_model_budget_table(agent_model_policy_summaries))
    lines.extend(
        [
            "",
            "### Agent Model Per-Task Outcomes",
            "",
        ]
    )
    lines.extend(
        _matrix_attempt_table(
            artifact_dir,
            agent_model_policy_runs,
            empty_message="No agent model policy attempts in this eval suite.",
        )
    )

    lines.extend(
        [
            "",
            "## Known Shortcuts",
            "",
            (
                "- `noop` and `public-tests-only` are calibration controls. "
                "They should pass public checks but fail hidden validators."
            ),
            (
                "- Public-test-only success is not task success; final PASS requires "
                "`status: PASS`, `public_status: PASS`, and `hidden_status: PASS`."
            ),
            "",
            "## Measures",
            "",
            (
                "This report measures whether the local repo-patch task suite, public "
                "checks, hidden validators, and scripted controls behave consistently "
                "on the configured dev task set."
            ),
            "",
            "## Does Not Measure",
            "",
            (
                "This is not a model baseline, not a post-training result, not a "
                "secure-sandbox claim, and not evidence of broad coding-agent capability."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def render_replay_report(
    artifact_dir: Path,
    manifest: dict[str, object],
) -> str:
    replay_result = _load_json_object(artifact_dir / "replay_result.json")
    lines = [
        "# Replay Report",
        "",
        "## Replay Details",
        "",
        f"- Artifact directory: {_relative_or_absolute(artifact_dir)}",
        f"- Replay manifest: {MANIFEST_FILENAME}",
        f"- Replay id: {_display(manifest.get('replay_id'))}",
        f"- Source run directory: {_path_display(manifest.get('source_run_dir'))}",
        f"- Source eval run id: {_display(manifest.get('source_eval_run_id'))}",
        f"- Source artifact type: {_display(manifest.get('source_artifact_type'))}",
        (
            "- Source artifact schema version: "
            f"{_display(manifest.get('source_artifact_schema_version'))}"
        ),
        "",
        "## Replay Result",
        "",
        f"- Status: {_display(replay_result.get('status'))}",
        f"- Attempt count: {_display(replay_result.get('attempt_count'))}",
        f"- Matched attempts: {_display(replay_result.get('matched_attempts'))}",
        f"- Mismatched attempts: {_display(replay_result.get('mismatched_attempts'))}",
        f"- Error count: {_display(replay_result.get('error_count'))}",
        "",
        "## Attempt Comparisons",
        "",
        (
            "| task_id | type | matched | artifacts | fields | source_artifact | "
            "replay_artifact |"
        ),
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]

    for comparison in _load_jsonl_objects(artifact_dir / "replay_results.jsonl"):
        lines.append(_comparison_row(comparison))

    return "\n".join(lines) + "\n"


def _attempt_row(artifact_dir: Path, attempt_record: dict[str, object]) -> str:
    del artifact_dir
    attempt_artifact_ref = _required_str(attempt_record, "artifact_dir")
    scorer = _optional_object(attempt_record.get("scorer"))
    agent = _optional_object(attempt_record.get("agent"))
    return (
        f"| {_display(attempt_record.get('task_id'))} "
        f"| {_display(attempt_record.get('attempt_index'))} "
        f"| {_display(attempt_record.get('artifact_type'))} "
        f"| {_display(attempt_record.get('artifact_schema_version'))} "
        f"| {_display(_field(scorer, 'status'))} "
        f"| {_display(_field(scorer, 'public_status'))} "
        f"| {_display(_field(scorer, 'hidden_status'))} "
        f"| {_display(_field(agent, 'status'))} "
        f"| {_display(_field(agent, 'prompt_loop_status'))} "
        f"| {_display(_attempt_agent_scorer_field(agent, 'status'))} "
        f"| {_display(_attempt_agent_scorer_field(agent, 'public_status'))} "
        f"| {_display(_attempt_agent_scorer_field(agent, 'hidden_status'))} "
        f"| {_display(_attempt_error_class(scorer, agent))} "
        f"| {_display(_attempt_final_diff_hash(scorer, agent))} "
        f"| {attempt_artifact_ref} |"
    )


def _load_matrix_policy_runs(
    artifact_dir: Path,
    manifest: dict[str, object],
) -> list[tuple[str, str, dict[str, object]]]:
    raw_policy_runs = manifest.get("policy_runs")
    if not isinstance(raw_policy_runs, list):
        raise ValueError("Expected eval suite policy_runs list")

    policy_runs: list[tuple[str, str, dict[str, object]]] = []
    for raw_policy_run in raw_policy_runs:
        if not isinstance(raw_policy_run, dict):
            raise ValueError("Expected eval suite policy_runs entries to be objects")
        policy = _required_str(raw_policy_run, "policy")
        run_artifact_dir = _required_str(raw_policy_run, "artifact_dir")
        run_manifest_ref = _required_str(raw_policy_run, "manifest")
        run_manifest = _load_json_object(artifact_dir / run_manifest_ref)
        _require_artifact_identity(
            run_manifest,
            artifact_dir / run_manifest_ref,
            ArtifactType.EVAL_RUN.value,
            EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
        )
        policy_runs.append((policy, run_artifact_dir, run_manifest))
    return policy_runs


def _matrix_task_ids(
    manifest: dict[str, object],
    policy_runs: list[tuple[str, str, dict[str, object]]],
) -> list[str]:
    raw_task_ids = manifest.get("tasks")
    if isinstance(raw_task_ids, list) and all(
        isinstance(task_id, str) for task_id in raw_task_ids
    ):
        return raw_task_ids

    task_ids: list[str] = []
    for _, _, run_manifest in policy_runs:
        attempts = run_manifest.get("attempts")
        if not isinstance(attempts, list):
            continue
        for raw_attempt in attempts:
            if not isinstance(raw_attempt, dict):
                continue
            task_id = raw_attempt.get("task_id")
            if isinstance(task_id, str) and task_id not in task_ids:
                task_ids.append(task_id)
    return task_ids


def _matrix_policy_summary(
    artifact_dir: Path,
    policy: str,
    run_artifact_dir: str,
    run_manifest: dict[str, object],
) -> dict[str, object]:
    attempts = _matrix_attempts_with_artifacts(
        artifact_dir,
        run_artifact_dir,
        run_manifest,
    )
    attempt_count = len(attempts)
    scorer_status_counts = _nested_field_counts(attempts, "scorer", "status")
    scorer_public_status_counts = _nested_field_counts(
        attempts,
        "scorer",
        "public_status",
    )
    scorer_hidden_status_counts = _nested_field_counts(
        attempts,
        "scorer",
        "hidden_status",
    )
    agent_status_counts = _nested_field_counts(attempts, "agent", "status")
    prompt_loop_status_counts = _nested_field_counts(
        attempts,
        "agent",
        "prompt_loop_status",
    )
    agent_scorer_status_counts = _agent_scorer_field_counts(attempts, "status")
    agent_scorer_public_status_counts = _agent_scorer_field_counts(
        attempts,
        "public_status",
    )
    agent_scorer_hidden_status_counts = _agent_scorer_field_counts(
        attempts,
        "hidden_status",
    )
    agent_error_class_counts = _nested_field_counts(attempts, "agent", "error_class")
    agent_scorer_error_class_counts = _agent_scorer_field_counts(attempts, "error_class")
    scorer_public_pass_hidden_fail = sum(
        _scorer_field(attempt, "public_status") == "PASS"
        and _scorer_field(attempt, "hidden_status") == "FAIL"
        for attempt in attempts
    )
    scorer_env_or_harness_failures = sum(
        _scorer_field(attempt, "status")
        in {"PATCH_APPLY_ERROR", "TIMEOUT", "ORCHESTRATOR_ERROR"}
        for attempt in attempts
    )
    scorer_or_orchestrator_failures = sum(
        _scorer_field(attempt, "status") == "ORCHESTRATOR_ERROR"
        for attempt in attempts
    )
    agent_scorer_public_pass_hidden_fail = sum(
        _agent_scorer_field(attempt, "public_status") == "PASS"
        and _agent_scorer_field(attempt, "hidden_status") == "FAIL"
        for attempt in attempts
    )
    agent_empty_patch_count = sum(
        _agent_artifact_field(attempt, "candidate_patch_bytes") == 0
        for attempt in attempts
    )
    agent_missing_patch_count = sum(
        _agent_field(attempt, "candidate_patch_hash") is None
        for attempt in attempts
    )
    duration_values = [
        duration_ms
        for attempt in attempts
        if isinstance((duration_ms := _attempt_duration_ms(attempt)), int)
    ]
    return {
        "policy": policy,
        "policy_type": _required_str(run_manifest, "policy_type"),
        "policy_family": _required_str(run_manifest, "policy_family"),
        "control_layer": _optional_str(run_manifest, "control_layer"),
        "control_name": _optional_str(run_manifest, "control_name"),
        "attempt_count": attempt_count,
        "scorer_final_passes": scorer_status_counts.get("PASS", 0),
        "scorer_public_passes": scorer_public_status_counts.get("PASS", 0),
        "scorer_hidden_passes": scorer_hidden_status_counts.get("PASS", 0),
        "scorer_public_pass_hidden_fail": scorer_public_pass_hidden_fail,
        "scorer_status_counts": scorer_status_counts,
        "scorer_public_status_counts": scorer_public_status_counts,
        "scorer_hidden_status_counts": scorer_hidden_status_counts,
        "scorer_env_or_harness_failures": scorer_env_or_harness_failures,
        "scorer_or_orchestrator_failures": scorer_or_orchestrator_failures,
        "agent_scored_count": agent_status_counts.get("scored", 0),
        "agent_loop_failed_count": agent_status_counts.get("agent_loop_failed", 0),
        "prompt_loop_completed_count": prompt_loop_status_counts.get("completed", 0),
        "agent_scorer_run_count": sum(agent_scorer_status_counts.values()),
        "agent_scorer_final_passes": agent_scorer_status_counts.get("PASS", 0),
        "agent_scorer_public_passes": agent_scorer_public_status_counts.get("PASS", 0),
        "agent_scorer_hidden_passes": agent_scorer_hidden_status_counts.get("PASS", 0),
        "agent_status_counts": agent_status_counts,
        "prompt_loop_status_counts": prompt_loop_status_counts,
        "agent_scorer_status_counts": agent_scorer_status_counts,
        "agent_scorer_public_status_counts": agent_scorer_public_status_counts,
        "agent_scorer_hidden_status_counts": agent_scorer_hidden_status_counts,
        "agent_error_class_counts": agent_error_class_counts,
        "agent_scorer_error_class_counts": agent_scorer_error_class_counts,
        "agent_scorer_public_pass_hidden_fail": (
            agent_scorer_public_pass_hidden_fail
        ),
        "agent_empty_patch_count": agent_empty_patch_count,
        "agent_missing_patch_count": agent_missing_patch_count,
        "agent_model_ids": _agent_artifact_unique_values(attempts, "model_ids"),
        "agent_decoding_strategies": _agent_artifact_unique_values(
            attempts,
            "decoding_strategy",
        ),
        "agent_temperatures": _agent_artifact_unique_values(
            attempts,
            "temperature",
        ),
        "agent_max_new_tokens": _agent_artifact_unique_values(
            attempts,
            "max_new_tokens",
        ),
        "agent_model_timeout_seconds": _agent_artifact_unique_values(
            attempts,
            "model_timeout_seconds",
        ),
        "agent_max_turns": _agent_artifact_unique_values(attempts, "max_turns"),
        "agent_prompt_tokens": _agent_token_sum(attempts, "prompt_tokens"),
        "agent_completion_tokens": _agent_token_sum(attempts, "completion_tokens"),
        "agent_total_tokens": _agent_token_sum(attempts, "total_tokens"),
        "agent_invalid_tool_calls": _agent_artifact_int_sum(
            attempts,
            "invalid_tool_calls",
        ),
        "agent_tool_errors": _agent_artifact_int_sum(attempts, "tool_errors"),
        "agent_cost": "not_recorded",
        "median_duration_ms": int(median(duration_values)) if duration_values else None,
        "trace": f"{run_artifact_dir}/trace.jsonl",
    }


def _summaries_for_control_layer(
    summaries: list[dict[str, object]],
    control_layer: str,
) -> list[dict[str, object]]:
    return [
        summary
        for summary in summaries
        if summary.get("control_layer") == control_layer
    ]


def _summaries_for_policy_type(
    summaries: list[dict[str, object]],
    policy_type: str,
) -> list[dict[str, object]]:
    return [
        summary
        for summary in summaries
        if summary.get("policy_type") == policy_type
    ]


def _policy_runs_for_control_policies(
    policy_runs: list[tuple[str, str, dict[str, object]]],
) -> list[tuple[str, str, dict[str, object]]]:
    return [
        policy_run
        for policy_run in policy_runs
        if _optional_str(policy_run[2], "control_layer") is not None
    ]


def _policy_runs_for_policy_type(
    policy_runs: list[tuple[str, str, dict[str, object]]],
    policy_type: str,
) -> list[tuple[str, str, dict[str, object]]]:
    return [
        policy_run
        for policy_run in policy_runs
        if _required_str(policy_run[2], "policy_type") == policy_type
    ]


def _scorer_policy_summary_table(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No scorer control policies in this eval suite."]

    return [
        (
            "| policy | control | attempts | final_pass_rate | public_pass_rate | "
            "hidden_pass_rate | public_pass_hidden_fail | env_or_harness_failures | "
            "scorer_or_orchestrator_failures | median_duration_ms | trace |"
        ),
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        *[_scorer_policy_summary_row(summary) for summary in summaries],
    ]


def _scorer_policy_summary_row(summary: dict[str, object]) -> str:
    attempt_count = _required_int(summary, "attempt_count")
    trace_ref = _display(summary.get("trace"))
    return (
        f"| {_display(summary.get('policy'))} "
        f"| {_display(summary.get('control_name'))} "
        f"| {attempt_count} "
        f"| {_count_rate(summary.get('scorer_final_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('scorer_public_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('scorer_hidden_passes'), attempt_count)} "
        f"| {_display(summary.get('scorer_public_pass_hidden_fail'))} "
        f"| {_display(summary.get('scorer_env_or_harness_failures'))} "
        f"| {_display(summary.get('scorer_or_orchestrator_failures'))} "
        f"| {_display(summary.get('median_duration_ms'))} "
        f"| {trace_ref} |"
    )


def _agent_policy_summary_table(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No agent control policies in this eval suite."]

    return [
        (
            "| policy | control | attempts | agent_scored_rate | "
            "prompt_loop_completed_rate | agent_loop_failed | "
            "nested_scorer_run_rate | nested_scorer_pass_rate | "
            "nested_public_pass_rate | nested_hidden_pass_rate | "
            "median_duration_ms | trace |"
        ),
        (
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
            "| ---: | --- |"
        ),
        *[_agent_policy_summary_row(summary) for summary in summaries],
    ]


def _agent_policy_summary_row(summary: dict[str, object]) -> str:
    attempt_count = _required_int(summary, "attempt_count")
    trace_ref = _display(summary.get("trace"))
    return (
        f"| {_display(summary.get('policy'))} "
        f"| {_display(summary.get('control_name'))} "
        f"| {attempt_count} "
        f"| {_count_rate(summary.get('agent_scored_count'), attempt_count)} "
        f"| {_count_rate(summary.get('prompt_loop_completed_count'), attempt_count)} "
        f"| {_display(summary.get('agent_loop_failed_count'))} "
        f"| {_count_rate(summary.get('agent_scorer_run_count'), attempt_count)} "
        f"| {_count_rate(summary.get('agent_scorer_final_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('agent_scorer_public_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('agent_scorer_hidden_passes'), attempt_count)} "
        f"| {_display(summary.get('median_duration_ms'))} "
        f"| {trace_ref} |"
    )


def _agent_model_outcome_table(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No agent model policies in this eval suite."]

    return [
        (
            "| policy | attempts | agent_scored_rate | prompt_loop_completed_rate | "
            "agent_loop_failed | scorer_run_rate | final_pass_rate | "
            "public_pass_rate | hidden_pass_rate | median_duration_ms | trace |"
        ),
        (
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
            "| ---: | --- |"
        ),
        *[_agent_model_outcome_row(summary) for summary in summaries],
    ]


def _agent_model_outcome_row(summary: dict[str, object]) -> str:
    attempt_count = _required_int(summary, "attempt_count")
    trace_ref = _display(summary.get("trace"))
    return (
        f"| {_display(summary.get('policy'))} "
        f"| {attempt_count} "
        f"| {_count_rate(summary.get('agent_scored_count'), attempt_count)} "
        f"| {_count_rate(summary.get('prompt_loop_completed_count'), attempt_count)} "
        f"| {_display(summary.get('agent_loop_failed_count'))} "
        f"| {_count_rate(summary.get('agent_scorer_run_count'), attempt_count)} "
        f"| {_count_rate(summary.get('agent_scorer_final_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('agent_scorer_public_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('agent_scorer_hidden_passes'), attempt_count)} "
        f"| {_display(summary.get('median_duration_ms'))} "
        f"| {trace_ref} |"
    )


def _agent_model_debug_table(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No agent model debug signals in this eval suite."]

    return [
        (
            "| policy | prompt_loop_statuses | agent_error_classes | "
            "nested_scorer_statuses | nested_scorer_error_classes | "
            "public_pass_hidden_fail | empty_patch | missing_patch | "
            "invalid_tool_calls | tool_errors |"
        ),
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        *[_agent_model_debug_row(summary) for summary in summaries],
    ]


def _agent_model_debug_row(summary: dict[str, object]) -> str:
    return (
        f"| {_display(summary.get('policy'))} "
        f"| {_counts_display(summary.get('prompt_loop_status_counts'))} "
        f"| {_counts_display(summary.get('agent_error_class_counts'))} "
        f"| {_counts_display(summary.get('agent_scorer_status_counts'))} "
        f"| {_counts_display(summary.get('agent_scorer_error_class_counts'))} "
        f"| {_display(summary.get('agent_scorer_public_pass_hidden_fail'))} "
        f"| {_display(summary.get('agent_empty_patch_count'))} "
        f"| {_display(summary.get('agent_missing_patch_count'))} "
        f"| {_display(summary.get('agent_invalid_tool_calls'))} "
        f"| {_display(summary.get('agent_tool_errors'))} |"
    )


def _agent_model_budget_table(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No agent budget metadata in this eval suite."]

    return [
        (
            "| policy | model_ids | strategy | temperature | max_new_tokens | "
            "model_timeout_seconds | max_turns | prompt_tokens | "
            "completion_tokens | total_tokens | cost | invalid_tool_calls | "
            "tool_errors |"
        ),
        (
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
            "| --- | ---: | ---: |"
        ),
        *[_agent_model_budget_row(summary) for summary in summaries],
    ]


def _agent_model_budget_row(summary: dict[str, object]) -> str:
    return (
        f"| {_display(summary.get('policy'))} "
        f"| {_value_set_display(summary.get('agent_model_ids'))} "
        f"| {_value_set_display(summary.get('agent_decoding_strategies'))} "
        f"| {_value_set_display(summary.get('agent_temperatures'))} "
        f"| {_value_set_display(summary.get('agent_max_new_tokens'))} "
        f"| {_value_set_display(summary.get('agent_model_timeout_seconds'))} "
        f"| {_value_set_display(summary.get('agent_max_turns'))} "
        f"| {_known_int_display(summary.get('agent_prompt_tokens'))} "
        f"| {_known_int_display(summary.get('agent_completion_tokens'))} "
        f"| {_known_int_display(summary.get('agent_total_tokens'))} "
        f"| {_display(summary.get('agent_cost'))} "
        f"| {_display(summary.get('agent_invalid_tool_calls'))} "
        f"| {_display(summary.get('agent_tool_errors'))} |"
    )


def _scorer_expectation_table(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No scorer control policies in this eval suite."]

    return [
        (
            "| policy | control | expected final | observed final | expected public | "
            "observed public | expected hidden | observed hidden | result |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *[_scorer_expectation_row(summary) for summary in summaries],
    ]


def _scorer_expectation_row(summary: dict[str, object]) -> str:
    policy = _display(summary.get("policy"))
    control_name = _display(summary.get("control_name"))
    attempt_count = _required_int(summary, "attempt_count")
    expected = _scorer_control_expectation(control_name)
    if expected is None:
        return (
            f"| {policy} | {control_name} |  |  |  |  |  |  | "
            f"{_colored_label('NOT_CHECKED', 'gray')} |"
        )

    final_count = _status_count(summary, "scorer_status_counts", expected["final"])
    public_count = _status_count(
        summary,
        "scorer_public_status_counts",
        expected["public"],
    )
    hidden_count = _status_count(
        summary,
        "scorer_hidden_status_counts",
        expected["hidden"],
    )
    on_track = (
        final_count == attempt_count
        and public_count == attempt_count
        and hidden_count == attempt_count
    )
    result = _colored_label(
        "ON_TRACK" if on_track else "OFF_TRACK",
        "green" if on_track else "red",
    )
    return (
        f"| {policy} "
        f"| {control_name} "
        f"| {expected['final']} "
        f"| {_count_rate(final_count, attempt_count)} "
        f"| {expected['public']} "
        f"| {_count_rate(public_count, attempt_count)} "
        f"| {expected['hidden']} "
        f"| {_count_rate(hidden_count, attempt_count)} "
        f"| {result} |"
    )


def _scorer_control_expectation(control_name: str) -> dict[str, str] | None:
    if control_name == "oracle":
        return {"final": "PASS", "public": "PASS", "hidden": "PASS"}
    if control_name in {"bad.noop", "bad.public_only"}:
        return {"final": "HIDDEN_TEST_FAIL", "public": "PASS", "hidden": "FAIL"}
    return None


def _agent_expectation_table(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No agent control policies in this eval suite."]

    return [
        (
            "| policy | control | expected agent_status | observed agent_status | "
            "expected prompt_loop | observed prompt_loop | "
            "expected nested_scorer | observed nested_scorer | result |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *[_agent_expectation_row(summary) for summary in summaries],
    ]


def _agent_expectation_row(summary: dict[str, object]) -> str:
    policy = _display(summary.get("policy"))
    control_name = _display(summary.get("control_name"))
    attempt_count = _required_int(summary, "attempt_count")
    expected = _agent_control_expectation(control_name)
    if expected is None:
        return (
            f"| {policy} | {control_name} |  |  |  |  |  |  | "
            f"{_colored_label('NOT_CHECKED', 'gray')} |"
        )

    expected_agent_status = _required_expected_status(expected, "agent_status")
    expected_prompt_loop_status = _required_expected_status(
        expected,
        "prompt_loop_status",
    )
    expected_nested_scorer_status = expected["nested_scorer_status"]
    agent_count = _status_count(
        summary,
        "agent_status_counts",
        expected_agent_status,
    )
    prompt_loop_count = _status_count(
        summary,
        "prompt_loop_status_counts",
        expected_prompt_loop_status,
    )
    nested_scorer_count = _expected_nested_scorer_count(
        summary,
        expected_nested_scorer_status,
        attempt_count,
    )
    on_track = _agent_expectation_on_track(summary, expected)
    result = _colored_label(
        "ON_TRACK" if on_track else "OFF_TRACK",
        "green" if on_track else "red",
    )
    return (
        f"| {policy} "
        f"| {control_name} "
        f"| {expected_agent_status} "
        f"| {_count_rate(agent_count, attempt_count)} "
        f"| {expected_prompt_loop_status} "
        f"| {_count_rate(prompt_loop_count, attempt_count)} "
        f"| {_expected_nested_scorer_display(expected_nested_scorer_status)} "
        f"| {_count_rate(nested_scorer_count, attempt_count)} "
        f"| {result} |"
    )


def _agent_control_expectation(control_name: str) -> dict[str, str | None] | None:
    if control_name in {"happy", "recoverable"}:
        return {
            "agent_status": "scored",
            "prompt_loop_status": "completed",
            "nested_scorer_status": "PASS",
        }
    if control_name == "malformed":
        return {
            "agent_status": "agent_loop_failed",
            "prompt_loop_status": "invalid_model_output",
            "nested_scorer_status": None,
        }
    return None


def _agent_expectation_on_track(
    summary: dict[str, object],
    expected: dict[str, str | None],
) -> bool:
    attempt_count = _required_int(summary, "attempt_count")
    expected_agent_status = _required_expected_status(expected, "agent_status")
    expected_prompt_loop_status = _required_expected_status(
        expected,
        "prompt_loop_status",
    )
    agent_count = _status_count(
        summary,
        "agent_status_counts",
        expected_agent_status,
    )
    prompt_loop_count = _status_count(
        summary,
        "prompt_loop_status_counts",
        expected_prompt_loop_status,
    )
    nested_scorer_count = _expected_nested_scorer_count(
        summary,
        expected["nested_scorer_status"],
        attempt_count,
    )
    return (
        agent_count == attempt_count
        and prompt_loop_count == attempt_count
        and nested_scorer_count == attempt_count
    )


def _expected_nested_scorer_count(
    summary: dict[str, object],
    expected_status: str | None,
    attempt_count: int,
) -> int:
    if expected_status is None:
        return _missing_status_count(summary, "agent_scorer_status_counts", attempt_count)
    return _status_count(summary, "agent_scorer_status_counts", expected_status)


def _expected_nested_scorer_display(expected_status: str | None) -> str:
    return "not_run" if expected_status is None else expected_status


def _required_expected_status(
    expected: dict[str, str | None],
    key: str,
) -> str:
    status = expected.get(key)
    if not isinstance(status, str):
        raise ValueError(f"Expected string status for {key!r}")
    return status


def _scorer_aggregate_rate_lines(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No scorer aggregate rates for this eval suite."]

    return [
        f"- Oracle pass rate: {_rate_display(_oracle_pass_rate(summaries))}",
        f"- Known-bad final PASS rate: {_rate_display(_known_bad_pass_rate(summaries))}",
        (
            "- Known-bad public-pass/hidden-fail rate: "
            f"{_rate_display(_known_bad_public_hidden_fail_rate(summaries))}"
        ),
        f"- Environment/harness failure rate: {_rate_display(_env_failure_rate(summaries))}",
        (
            "- Scorer/orchestrator failure rate: "
            f"{_rate_display(_scorer_or_orchestrator_failure_rate(summaries))}"
        ),
    ]


def _agent_aggregate_rate_lines(summaries: list[dict[str, object]]) -> list[str]:
    if not summaries:
        return ["No agent aggregate rates for this eval suite."]

    return [
        (
            "- Agent control expectation pass rate: "
            f"{_rate_display(_agent_expectation_pass_rate(summaries))}"
        )
    ]


def _matrix_replay_rows(manifest: dict[str, object]) -> list[str]:
    replay_runs = _matrix_replay_runs(manifest)
    if not replay_runs:
        return ["Replay was not run for this eval suite."]

    rows = [
        "| policy | status | match_rate | error_count | replay_result |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for replay_run in replay_runs:
        matched_attempts = _required_int(replay_run, "matched_attempts")
        attempt_count = _required_int(replay_run, "attempt_count")
        rows.append(
            f"| {_display(replay_run.get('policy'))} "
            f"| {_display(replay_run.get('status'))} "
            f"| {_count_rate(matched_attempts, attempt_count)} "
            f"| {_display(replay_run.get('error_count'))} "
            f"| {_display(replay_run.get('replay_result'))} |"
        )
    return rows


def _matrix_replay_match_rate(
    manifest: dict[str, object],
) -> tuple[int, int] | None:
    replay_runs = _matrix_replay_runs(manifest)
    if not replay_runs:
        return None

    matched_attempts = 0
    attempt_count = 0
    for replay_run in replay_runs:
        matched_attempts += _required_int(replay_run, "matched_attempts")
        attempt_count += _required_int(replay_run, "attempt_count")
    return matched_attempts, attempt_count


def _matrix_replay_runs(manifest: dict[str, object]) -> list[dict[str, object]]:
    raw_replay_runs = manifest.get("replay_runs")
    if raw_replay_runs is None:
        return []
    if not isinstance(raw_replay_runs, list):
        raise ValueError("Expected eval suite replay_runs list")
    replay_runs: list[dict[str, object]] = []
    for raw_replay_run in raw_replay_runs:
        if not isinstance(raw_replay_run, dict):
            raise ValueError("Expected eval suite replay_runs entries to be objects")
        replay_runs.append(raw_replay_run)
    return replay_runs


def _layer_count_rows(manifest: dict[str, object]) -> list[str]:
    layer_counts = manifest.get("layer_counts")
    if not isinstance(layer_counts, dict):
        return []
    rows: list[str] = []
    for layer_name, raw_status_counts in sorted(layer_counts.items()):
        if not isinstance(raw_status_counts, dict):
            continue
        for status, count in sorted(raw_status_counts.items()):
            rows.append(
                f"| {_display(layer_name)} | {_display(status)} | {_display(count)} |"
            )
    return rows


def _nested_field_counts(
    attempts: list[dict[str, object]],
    object_name: str,
    field_name: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in attempts:
        nested = _optional_object(attempt.get(object_name))
        value = _field(nested, field_name)
        if not isinstance(value, str):
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _agent_scorer_field_counts(
    attempts: list[dict[str, object]],
    field_name: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in attempts:
        value = _agent_scorer_field(attempt, field_name)
        if not isinstance(value, str):
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _status_count(
    summary: dict[str, object],
    counts_key: str,
    status: str,
) -> int:
    raw_counts = summary.get(counts_key)
    if not isinstance(raw_counts, dict):
        return 0
    value = raw_counts.get(status)
    return value if isinstance(value, int) else 0


def _missing_status_count(
    summary: dict[str, object],
    counts_key: str,
    attempt_count: int,
) -> int:
    raw_counts = summary.get(counts_key)
    if not isinstance(raw_counts, dict):
        return attempt_count
    observed_count = sum(
        count for count in raw_counts.values() if isinstance(count, int)
    )
    return max(attempt_count - observed_count, 0)


def _optional_object(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _field(data: dict[str, object] | None, key: str) -> object:
    if data is None:
        return None
    return data.get(key)


def _scorer_field(attempt: dict[str, object], key: str) -> object:
    return _field(_optional_object(attempt.get("scorer")), key)


def _agent_field(attempt: dict[str, object], key: str) -> object:
    return _field(_optional_object(attempt.get("agent")), key)


def _agent_scorer_field(attempt: dict[str, object], key: str) -> object:
    agent = _optional_object(attempt.get("agent"))
    scorer_attempt = _optional_object(_field(agent, "scorer_attempt"))
    return _field(scorer_attempt, key)


def _agent_artifact_field(attempt: dict[str, object], key: str) -> object:
    return _field(_optional_object(attempt.get("agent_artifact")), key)


def _attempt_agent_scorer_field(
    agent: dict[str, object] | None,
    key: str,
) -> object:
    scorer_attempt = _optional_object(_field(agent, "scorer_attempt"))
    return _field(scorer_attempt, key)


def _attempt_error_class(
    scorer: dict[str, object] | None,
    agent: dict[str, object] | None,
) -> object:
    if scorer is not None:
        return scorer.get("error_class")
    if agent is not None:
        return agent.get("error_class")
    return None


def _attempt_final_diff_hash(
    scorer: dict[str, object] | None,
    agent: dict[str, object] | None,
) -> object:
    if scorer is not None:
        return scorer.get("final_diff_hash")
    if agent is not None:
        scorer_attempt = _optional_object(agent.get("scorer_attempt"))
        return _field(scorer_attempt, "final_diff_hash")
    return None


def _attempt_error_class_from_record(attempt: dict[str, object]) -> object:
    scorer = _optional_object(attempt.get("scorer"))
    agent = _optional_object(attempt.get("agent"))
    return _attempt_error_class(scorer, agent)


def _attempt_final_diff_hash_from_record(attempt: dict[str, object]) -> object:
    scorer = _optional_object(attempt.get("scorer"))
    agent = _optional_object(attempt.get("agent"))
    return _attempt_final_diff_hash(scorer, agent)


def _attempt_candidate_patch_bytes_from_record(attempt: dict[str, object]) -> object:
    return _agent_artifact_field(attempt, "candidate_patch_bytes")


def _attempt_duration_ms(attempt: dict[str, object]) -> object:
    duration_ms = _scorer_field(attempt, "duration_ms")
    if duration_ms is not None:
        return duration_ms
    return _agent_field(attempt, "duration_ms")


def _matrix_attempt_rows(
    artifact_dir: Path,
    policy: str,
    run_artifact_dir: str,
    run_manifest: dict[str, object],
) -> list[str]:
    return [
        (
            f"| {_display(attempt.get('task_id'))} "
            f"| {policy} "
            f"| {_display(attempt.get('artifact_type'))} "
            f"| {_display(attempt.get('artifact_schema_version'))} "
            f"| {_display(_scorer_field(attempt, 'status'))} "
            f"| {_display(_scorer_field(attempt, 'public_status'))} "
            f"| {_display(_scorer_field(attempt, 'hidden_status'))} "
            f"| {_display(_agent_field(attempt, 'status'))} "
            f"| {_display(_agent_field(attempt, 'prompt_loop_status'))} "
            f"| {_display(_agent_scorer_field(attempt, 'status'))} "
            f"| {_display(_agent_scorer_field(attempt, 'public_status'))} "
            f"| {_display(_agent_scorer_field(attempt, 'hidden_status'))} "
            f"| {_display(_attempt_error_class_from_record(attempt))} "
            f"| {_display(_attempt_duration_ms(attempt))} "
            f"| {_display(_attempt_candidate_patch_bytes_from_record(attempt))} "
            f"| {_display(_attempt_final_diff_hash_from_record(attempt))} "
            f"| {_display(attempt.get('artifact_dir'))} |"
        )
        for attempt in _matrix_attempts_with_artifacts(
            artifact_dir,
            run_artifact_dir,
            run_manifest,
        )
    ]


def _matrix_attempt_table(
    artifact_dir: Path,
    policy_runs: list[tuple[str, str, dict[str, object]]],
    *,
    empty_message: str,
) -> list[str]:
    if not policy_runs:
        return [empty_message]

    rows = [
        (
            "| task_id | policy | artifact_type | artifact_schema_version | "
            "scorer_status | scorer_public_status | scorer_hidden_status | "
            "agent_status | prompt_loop_status | agent_scorer_status | "
            "agent_scorer_public_status | agent_scorer_hidden_status | "
            "error_class | duration_ms | candidate_patch_bytes | "
            "final_diff_hash | artifact_dir |"
        ),
        (
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
            "| --- | --- | ---: | ---: | --- | --- |"
        ),
    ]
    for policy, run_artifact_dir, run_manifest in policy_runs:
        rows.extend(
            _matrix_attempt_rows(artifact_dir, policy, run_artifact_dir, run_manifest)
        )
    return rows


def _matrix_attempts_with_artifacts(
    artifact_dir: Path,
    run_artifact_dir: str,
    run_manifest: dict[str, object],
) -> list[dict[str, object]]:
    attempts = run_manifest.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError("Expected eval run attempts list")

    run_dir = artifact_dir / run_artifact_dir
    records: list[dict[str, object]] = []
    for raw_attempt in attempts:
        if not isinstance(raw_attempt, dict):
            raise ValueError("Expected eval run attempt entries to be objects")
        attempt_record = dict(raw_attempt)
        attempt_artifact_ref = _required_str(attempt_record, "artifact_dir")
        attempt_record["artifact_dir"] = str(
            (run_dir / attempt_artifact_ref).relative_to(artifact_dir)
        )
        _require_supported_attempt_artifact_identity(attempt_record)
        if attempt_record.get("artifact_type") == ArtifactType.AGENT_ATTEMPT.value:
            attempt_record["agent_artifact"] = _agent_artifact_summary(
                run_dir / attempt_artifact_ref
            )
        records.append(attempt_record)
    return records


def _agent_artifact_summary(artifact_dir: Path) -> dict[str, object]:
    prompt_loop = _load_optional_json_object(artifact_dir / "prompt_loop_result.json")
    decoding_config = _config_payload(
        _load_optional_json_object(artifact_dir / "decoding_config.json")
    )
    agent_task_view = _load_optional_json_object(artifact_dir / "agent_task_view.json")
    candidate_patch_path = artifact_dir / "candidate.patch"
    model_responses = _object_list(_field(prompt_loop, "model_responses"))
    tool_results = _object_list(_field(prompt_loop, "tool_results"))

    return {
        "model_ids": _unique_values(
            response.get("model_id")
            for response in model_responses
            if isinstance(response.get("model_id"), str)
        ),
        "decoding_strategy": _field(decoding_config, "strategy"),
        "temperature": _field(decoding_config, "temperature"),
        "max_new_tokens": _field(decoding_config, "max_new_tokens"),
        "model_timeout_seconds": _field(decoding_config, "timeout_seconds"),
        "max_turns": _field(agent_task_view, "max_turns"),
        "turns_executed": _field(prompt_loop, "turns_executed"),
        "candidate_patch_bytes": (
            candidate_patch_path.stat().st_size
            if candidate_patch_path.is_file()
            else None
        ),
        "token_usage": _optional_object(_field(prompt_loop, "token_usage")),
        "invalid_tool_calls": sum(
            result.get("status") == "error"
            and result.get("error_class") == "InvalidToolInput"
            for result in tool_results
        ),
        "tool_errors": sum(result.get("status") == "error" for result in tool_results),
    }


def _load_optional_json_object(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    return _load_json_object(path)


def _config_payload(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    config = value.get("config")
    if isinstance(config, dict):
        return config
    return value


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _agent_artifact_unique_values(
    attempts: list[dict[str, object]],
    key: str,
) -> list[object]:
    values: list[object] = []
    for attempt in attempts:
        value = _agent_artifact_field(attempt, key)
        if isinstance(value, list):
            raw_values = value
        else:
            raw_values = [value]
        for raw_value in raw_values:
            if (
                isinstance(raw_value, (str, int, float))
                and not isinstance(raw_value, bool)
                and raw_value not in values
            ):
                values.append(raw_value)
    return values


def _agent_artifact_int_sum(
    attempts: list[dict[str, object]],
    key: str,
) -> int:
    return sum(
        value
        for attempt in attempts
        if isinstance((value := _agent_artifact_field(attempt, key)), int)
        and not isinstance(value, bool)
    )


def _agent_token_sum(
    attempts: list[dict[str, object]],
    key: str,
) -> int | None:
    total = 0
    observed = False
    for attempt in attempts:
        token_usage = _optional_object(_agent_artifact_field(attempt, "token_usage"))
        value = _field(token_usage, key)
        if isinstance(value, int):
            total += value
            observed = True
    return total if observed else None


def _unique_values(values: Iterable[object]) -> list[object]:
    unique: list[object] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _comparison_row(comparison: dict[str, object]) -> str:
    field_matches = comparison.get("field_matches")
    if not isinstance(field_matches, dict):
        raise ValueError("Expected replay comparison field_matches object")
    artifact_matches = comparison.get("artifact_matches")

    return (
        f"| {_display(comparison.get('task_id'))} "
        f"| {_display(comparison.get('comparison_type'))} "
        f"| {_match_display(comparison.get('matched'))} "
        f"| {_artifact_match_display(artifact_matches)} "
        f"| {_field_match_display(field_matches)} "
        f"| {_display(comparison.get('source_artifact_ref'))} "
        f"| {_display(comparison.get('replay_artifact_ref'))} |"
    )


def _load_json_object(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _load_jsonl_objects(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text().splitlines():
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object line at {path}")
        records.append(raw)
    return records


def _load_artifact_manifest(artifact_dir: Path) -> dict[str, object]:
    manifest = artifact_dir / MANIFEST_FILENAME
    if manifest.is_file():
        return _load_json_object(manifest)

    raise ValueError(f"No supported artifact manifest found in {artifact_dir}")


def _require_artifact_schema_version(
    manifest: dict[str, object],
    artifact_dir: Path,
    expected: str,
) -> None:
    artifact_schema_version = manifest.get("artifact_schema_version")
    if artifact_schema_version != expected:
        raise ValueError(
            "Unsupported artifact_schema_version "
            f"{artifact_schema_version!r} at {artifact_dir / MANIFEST_FILENAME}; "
            f"expected {expected!r}"
        )


def _require_artifact_identity(
    manifest: dict[str, object],
    manifest_path: Path,
    expected_artifact_type: str,
    expected_artifact_schema_version: str,
) -> None:
    artifact_type = manifest.get("artifact_type")
    if artifact_type != expected_artifact_type:
        raise ValueError(
            f"Unsupported artifact_type {artifact_type!r} at {manifest_path}; "
            f"expected {expected_artifact_type!r}"
        )
    artifact_schema_version = manifest.get("artifact_schema_version")
    if artifact_schema_version != expected_artifact_schema_version:
        raise ValueError(
            "Unsupported artifact_schema_version "
            f"{artifact_schema_version!r} at {manifest_path}; "
            f"expected {expected_artifact_schema_version!r}"
        )


def _require_supported_attempt_artifact_identity(
    attempt_record: dict[str, object],
) -> None:
    artifact_type = attempt_record.get("artifact_type")
    artifact_schema_version = attempt_record.get("artifact_schema_version")
    expected_schema_versions = {
        ArtifactType.SCORER_ATTEMPT.value: SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        ArtifactType.AGENT_ATTEMPT.value: AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    }
    if not isinstance(artifact_type, str) or artifact_type not in expected_schema_versions:
        raise ValueError(
            "Eval report attempt artifact_type must be one of "
            f"{ArtifactType.SCORER_ATTEMPT.value!r}, "
            f"{ArtifactType.AGENT_ATTEMPT.value!r}; got {artifact_type!r}"
        )
    expected_schema_version = expected_schema_versions[artifact_type]
    if artifact_schema_version != expected_schema_version:
        raise ValueError(
            "Unsupported eval report attempt artifact_schema_version "
            f"{artifact_schema_version!r} for artifact_type {artifact_type!r}; "
            f"expected {expected_schema_version!r}"
        )


def _required_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected string field {key!r}")
    return value


def _optional_str(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected string or null field {key!r}")
    return value


def _required_int(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"Expected integer field {key!r}")
    return value


def _display(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _known_int_display(value: object) -> str:
    if value is None:
        return "not_recorded"
    return _display(value)


def _value_set_display(value: object) -> str:
    if not isinstance(value, list):
        return _display(value)
    return ", ".join(_display(item) for item in value)


def _counts_display(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    parts: list[str] = []
    for key, count in sorted(value.items(), key=lambda item: str(item[0])):
        if isinstance(count, int) and not isinstance(count, bool):
            parts.append(f"{_display(key)}={count}")
    return ", ".join(parts) if parts else "none"


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _path_display(value: object) -> str:
    if not isinstance(value, str):
        return _display(value)
    return _relative_or_absolute(Path(value))


def _match_display(value: object) -> str:
    if value is True:
        return "match"
    if value is False:
        return "mismatch"
    return _display(value)


def _artifact_match_display(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    total = len(value)
    matches = sum(artifact_match is True for artifact_match in value.values())
    return _count_rate(matches, total)


def _field_match_display(value: dict[object, object]) -> str:
    total = len(value)
    matches = sum(field_match is True for field_match in value.values())
    return _count_rate(matches, total)


def _count_rate(count_value: object, total: int) -> str:
    if not isinstance(count_value, int) or total == 0:
        return ""
    return f"{count_value}/{total} ({count_value / total:.0%})"


def _colored_label(label: str, color: str) -> str:
    return f'<span style="color: {color}">{label}</span>'


def _rate_display(rate: tuple[int, int] | None) -> str:
    if rate is None:
        return ""
    count, total = rate
    return _count_rate(count, total)


def _oracle_pass_rate(summaries: list[dict[str, object]]) -> tuple[int, int] | None:
    return _summary_rate(summaries, {"oracle"}, "scorer_final_passes")


def _known_bad_pass_rate(summaries: list[dict[str, object]]) -> tuple[int, int] | None:
    return _summary_rate(_known_bad_summaries(summaries), None, "scorer_final_passes")


def _known_bad_public_hidden_fail_rate(
    summaries: list[dict[str, object]],
) -> tuple[int, int] | None:
    return _summary_rate(
        _known_bad_summaries(summaries),
        None,
        "scorer_public_pass_hidden_fail",
    )


def _env_failure_rate(summaries: list[dict[str, object]]) -> tuple[int, int] | None:
    return _summary_rate(summaries, None, "scorer_env_or_harness_failures")


def _scorer_or_orchestrator_failure_rate(
    summaries: list[dict[str, object]],
) -> tuple[int, int] | None:
    return _summary_rate(summaries, None, "scorer_or_orchestrator_failures")


def _agent_expectation_pass_rate(
    summaries: list[dict[str, object]],
) -> tuple[int, int] | None:
    total = 0
    passed = 0
    for summary in summaries:
        control_name = _display(summary.get("control_name"))
        expected = _agent_control_expectation(control_name)
        if expected is None:
            continue
        total += 1
        if _agent_expectation_on_track(summary, expected):
            passed += 1
    if total == 0:
        return None
    return passed, total


def _known_bad_summaries(
    summaries: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        summary
        for summary in summaries
        if summary.get("control_name") in {"bad.noop", "bad.public_only"}
    ]


def _summary_rate(
    summaries: list[dict[str, object]],
    policy_names: set[str] | None,
    count_key: str,
) -> tuple[int, int] | None:
    selected = [
        summary
        for summary in summaries
        if policy_names is None or summary.get("policy") in policy_names
    ]
    if not selected:
        return None
    count = 0
    total = 0
    for summary in selected:
        count_value = summary.get(count_key)
        attempt_count = summary.get("attempt_count")
        if not isinstance(count_value, int) or not isinstance(attempt_count, int):
            continue
        count += count_value
        total += attempt_count
    return count, total
