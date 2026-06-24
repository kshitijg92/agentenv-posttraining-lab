import json
from pathlib import Path
from statistics import median


def write_markdown_report(artifact_dir: Path, out_path: Path) -> Path:
    artifact_dir = artifact_dir.resolve()
    manifest = _load_artifact_manifest(artifact_dir)
    artifact_version = manifest.get("artifact_version")

    if artifact_version == "eval_run_v0":
        markdown = render_eval_report(artifact_dir, manifest)
    elif artifact_version == "eval_matrix_v0":
        markdown = render_eval_matrix_report(artifact_dir, manifest)
    elif artifact_version == "replay_v0":
        markdown = render_replay_report(artifact_dir, manifest)
    else:
        raise ValueError(f"Unsupported artifact_version: {artifact_version!r}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown)
    return out_path


def render_eval_report(
    artifact_dir: Path,
    manifest: dict[str, object],
) -> str:
    lines = [
        "# Eval Report",
        "",
        "## Run Details",
        "",
        f"- Artifact directory: {_relative_or_absolute(artifact_dir)}",
        "- Eval manifest: run_manifest.json",
        f"- Eval run id: {_display(manifest.get('eval_run_id'))}",
        f"- Config name: {_display(manifest.get('config_name'))}",
        f"- Config path: {_path_display(manifest.get('config_path'))}",
        f"- Config hash: {_display(manifest.get('config_hash'))}",
        f"- Policy: {_display(manifest.get('policy'))}",
        f"- Split: {_display(manifest.get('split'))}",
        f"- Task pack: {_display(manifest.get('task_pack'))}",
        f"- Attempt count: {_display(manifest.get('attempt_count'))}",
        "",
        "## Status Counts",
        "",
        "| status | count |",
        "| --- | ---: |",
    ]

    status_counts = manifest.get("status_counts")
    if isinstance(status_counts, dict):
        for status, count in sorted(status_counts.items()):
            lines.append(f"| {_display(status)} | {_display(count)} |")
    lines.extend(
        [
            "",
            "## Attempts",
            "",
            (
                "| task_id | attempt_index | status | public_status | "
                "hidden_status | error_class | final_diff_hash | artifact_dir |"
            ),
            "| --- | ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )

    attempts = manifest.get("attempts")
    if isinstance(attempts, list):
        for raw_attempt in attempts:
            if not isinstance(raw_attempt, dict):
                continue
            lines.append(_attempt_row(artifact_dir, raw_attempt))

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

    lines = [
        "# Eval Matrix Report",
        "",
        "## Run Details",
        "",
        f"- Artifact directory: {_relative_or_absolute(artifact_dir)}",
        "- Eval matrix manifest: eval_matrix_manifest.json",
        f"- Eval matrix id: {_display(manifest.get('eval_matrix_id'))}",
        f"- Config name: {_display(manifest.get('config_name'))}",
        f"- Config path: {_path_display(manifest.get('config_path'))}",
        f"- Config hash: {_display(manifest.get('config_hash'))}",
        f"- Split: {_display(manifest.get('split'))}",
        f"- Task pack: {_display(manifest.get('task_pack'))}",
        f"- Task count: {len(task_ids)}",
        f"- Policy count: {_display(manifest.get('policy_count'))}",
        f"- Attempt count: {_display(manifest.get('attempt_count'))}",
        (
            "- Hidden-validator version/hash: not captured in eval_matrix_v0; "
            f"current substitute is config hash {_display(manifest.get('config_hash'))}"
        ),
        "- Replay match rate: not captured in eval_matrix_v0",
        "",
        "## Tasks",
        "",
    ]
    lines.extend(f"- {task_id}" for task_id in task_ids)
    lines.extend(
        [
            "",
            "## Policy Summary",
            "",
            (
                "| policy | attempts | final_pass_rate | public_pass_rate | "
                "hidden_pass_rate | public_pass_hidden_fail | env_or_harness_failures | "
                "scorer_or_orchestrator_failures | median_duration_ms | trace |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for summary in policy_summaries:
        lines.append(_matrix_policy_summary_row(summary))

    lines.extend(
        [
            "",
            "## Calibration Checks",
            "",
            "### Control Expectations",
            "",
            (
                "| policy | expected final | observed final | expected public | "
                "observed public | expected hidden | observed hidden | result |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(_matrix_expectation_rows(policy_summaries))
    lines.extend(
        [
            "",
            "### Aggregate Rates",
            "",
            f"- Oracle pass rate: {_rate_display(_oracle_pass_rate(policy_summaries))}",
            f"- Known-bad final PASS rate: {_rate_display(_known_bad_pass_rate(policy_summaries))}",
            (
                "- Known-bad public-pass/hidden-fail rate: "
                f"{_rate_display(_known_bad_public_hidden_fail_rate(policy_summaries))}"
            ),
            f"- Environment/harness failure rate: {_rate_display(_env_failure_rate(policy_summaries))}",
            (
                "- Scorer/orchestrator failure rate: "
                f"{_rate_display(_scorer_or_orchestrator_failure_rate(policy_summaries))}"
            ),
            "- Task exclusions: none recorded in eval_matrix_v0",
            "",
            "## Per-Task Outcomes",
            "",
            (
                "| task_id | policy | status | public_status | hidden_status | "
                "error_class | duration_ms | final_diff_hash | artifact_dir |"
            ),
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for policy, run_artifact_dir, run_manifest in policy_runs:
        lines.extend(
            _matrix_attempt_rows(artifact_dir, policy, run_artifact_dir, run_manifest)
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
        "- Replay manifest: replay_manifest.json",
        f"- Replay id: {_display(manifest.get('replay_id'))}",
        f"- Source run directory: {_path_display(manifest.get('source_run_dir'))}",
        f"- Source eval run id: {_display(manifest.get('source_eval_run_id'))}",
        f"- Source artifact version: {_display(manifest.get('source_artifact_version'))}",
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
            "| task_id | matched | status | public_status | hidden_status | "
            "error_class | final_diff_hash | source_attempt | replay_attempt |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for comparison in _load_jsonl_objects(artifact_dir / "replay_results.jsonl"):
        lines.append(_comparison_row(comparison))

    return "\n".join(lines) + "\n"


def _attempt_row(artifact_dir: Path, attempt_record: dict[str, object]) -> str:
    attempt_artifact_ref = _required_str(attempt_record, "artifact_dir")
    attempt_json = _load_json_object(artifact_dir / attempt_artifact_ref / "attempt.json")
    return (
        f"| {_display(attempt_record.get('task_id'))} "
        f"| {_display(attempt_record.get('attempt_index'))} "
        f"| {_display(attempt_json.get('status'))} "
        f"| {_display(attempt_json.get('public_status'))} "
        f"| {_display(attempt_json.get('hidden_status'))} "
        f"| {_display(attempt_json.get('error_class'))} "
        f"| {_display(attempt_json.get('final_diff_hash'))} "
        f"| {attempt_artifact_ref} |"
    )


def _load_matrix_policy_runs(
    artifact_dir: Path,
    manifest: dict[str, object],
) -> list[tuple[str, str, dict[str, object]]]:
    raw_policy_runs = manifest.get("policy_runs")
    if not isinstance(raw_policy_runs, list):
        raise ValueError("Expected eval matrix policy_runs list")

    policy_runs: list[tuple[str, str, dict[str, object]]] = []
    for raw_policy_run in raw_policy_runs:
        if not isinstance(raw_policy_run, dict):
            raise ValueError("Expected eval matrix policy_runs entries to be objects")
        policy = _required_str(raw_policy_run, "policy")
        run_artifact_dir = _required_str(raw_policy_run, "artifact_dir")
        run_manifest_ref = _required_str(raw_policy_run, "run_manifest")
        run_manifest = _load_json_object(artifact_dir / run_manifest_ref)
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
    final_passes = sum(attempt.get("status") == "PASS" for attempt in attempts)
    public_passes = sum(attempt.get("public_status") == "PASS" for attempt in attempts)
    hidden_passes = sum(attempt.get("hidden_status") == "PASS" for attempt in attempts)
    public_pass_hidden_fail = sum(
        attempt.get("public_status") == "PASS"
        and attempt.get("hidden_status") == "FAIL"
        for attempt in attempts
    )
    status_counts = _field_counts(attempts, "status")
    public_status_counts = _field_counts(attempts, "public_status")
    hidden_status_counts = _field_counts(attempts, "hidden_status")
    env_or_harness_failures = sum(
        attempt.get("status") in {"PATCH_APPLY_ERROR", "TIMEOUT", "ORCHESTRATOR_ERROR"}
        for attempt in attempts
    )
    scorer_or_orchestrator_failures = sum(
        attempt.get("status") == "ORCHESTRATOR_ERROR" for attempt in attempts
    )
    duration_values = [
        duration_ms
        for attempt in attempts
        if isinstance((duration_ms := attempt.get("duration_ms")), int)
    ]
    return {
        "policy": policy,
        "attempt_count": attempt_count,
        "final_passes": final_passes,
        "public_passes": public_passes,
        "hidden_passes": hidden_passes,
        "public_pass_hidden_fail": public_pass_hidden_fail,
        "status_counts": status_counts,
        "public_status_counts": public_status_counts,
        "hidden_status_counts": hidden_status_counts,
        "env_or_harness_failures": env_or_harness_failures,
        "scorer_or_orchestrator_failures": scorer_or_orchestrator_failures,
        "median_duration_ms": int(median(duration_values)) if duration_values else None,
        "trace": f"{run_artifact_dir}/trace.jsonl",
    }


def _matrix_policy_summary_row(summary: dict[str, object]) -> str:
    attempt_count = _required_int(summary, "attempt_count")
    trace_ref = _display(summary.get("trace"))
    return (
        f"| {_display(summary.get('policy'))} "
        f"| {attempt_count} "
        f"| {_count_rate(summary.get('final_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('public_passes'), attempt_count)} "
        f"| {_count_rate(summary.get('hidden_passes'), attempt_count)} "
        f"| {_display(summary.get('public_pass_hidden_fail'))} "
        f"| {_display(summary.get('env_or_harness_failures'))} "
        f"| {_display(summary.get('scorer_or_orchestrator_failures'))} "
        f"| {_display(summary.get('median_duration_ms'))} "
        f"| {trace_ref} |"
    )


def _matrix_expectation_rows(summaries: list[dict[str, object]]) -> list[str]:
    return [_matrix_expectation_row(summary) for summary in summaries]


def _matrix_expectation_row(summary: dict[str, object]) -> str:
    policy = _display(summary.get("policy"))
    attempt_count = _required_int(summary, "attempt_count")
    expected = _control_expectation(policy)
    if expected is None:
        return f"| {policy} |  |  |  |  |  |  | {_colored_label('NOT_CHECKED', 'gray')} |"

    final_count = _status_count(summary, "status_counts", expected["final"])
    public_count = _status_count(summary, "public_status_counts", expected["public"])
    hidden_count = _status_count(summary, "hidden_status_counts", expected["hidden"])
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
        f"| {expected['final']} "
        f"| {_count_rate(final_count, attempt_count)} "
        f"| {expected['public']} "
        f"| {_count_rate(public_count, attempt_count)} "
        f"| {expected['hidden']} "
        f"| {_count_rate(hidden_count, attempt_count)} "
        f"| {result} |"
    )


def _control_expectation(policy: str) -> dict[str, str] | None:
    if policy == "oracle":
        return {"final": "PASS", "public": "PASS", "hidden": "PASS"}
    if policy in {"noop", "bad-noop", "public-tests-only", "bad-public-only"}:
        return {"final": "HIDDEN_TEST_FAIL", "public": "PASS", "hidden": "FAIL"}
    return None


def _field_counts(
    attempts: list[dict[str, object]],
    field_name: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for attempt in attempts:
        value = attempt.get(field_name)
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
            f"| {_display(attempt.get('status'))} "
            f"| {_display(attempt.get('public_status'))} "
            f"| {_display(attempt.get('hidden_status'))} "
            f"| {_display(attempt.get('error_class'))} "
            f"| {_display(attempt.get('duration_ms'))} "
            f"| {_display(attempt.get('final_diff_hash'))} "
            f"| {_display(attempt.get('artifact_dir'))} |"
        )
        for attempt in _matrix_attempts_with_artifacts(
            artifact_dir,
            run_artifact_dir,
            run_manifest,
        )
    ]


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
        attempt_json = _load_json_object(run_dir / attempt_artifact_ref / "attempt.json")
        attempt_record["artifact_dir"] = str(
            (run_dir / attempt_artifact_ref).relative_to(artifact_dir)
        )
        attempt_record["error_class"] = attempt_json.get("error_class")
        attempt_record["duration_ms"] = attempt_json.get("duration_ms")
        attempt_record["status"] = attempt_json.get("status")
        attempt_record["public_status"] = attempt_json.get("public_status")
        attempt_record["hidden_status"] = attempt_json.get("hidden_status")
        attempt_record["final_diff_hash"] = attempt_json.get("final_diff_hash")
        records.append(attempt_record)
    return records


def _comparison_row(comparison: dict[str, object]) -> str:
    field_matches = comparison.get("field_matches")
    if not isinstance(field_matches, dict):
        raise ValueError("Expected replay comparison field_matches object")

    return (
        f"| {_display(comparison.get('task_id'))} "
        f"| {_match_display(comparison.get('matched'))} "
        f"| {_match_display(field_matches.get('status'))} "
        f"| {_match_display(field_matches.get('public_status'))} "
        f"| {_match_display(field_matches.get('hidden_status'))} "
        f"| {_match_display(field_matches.get('error_class'))} "
        f"| {_match_display(field_matches.get('final_diff_hash'))} "
        f"| {_display(comparison.get('source_attempt_artifact_ref'))} "
        f"| {_display(comparison.get('replay_attempt_artifact_ref'))} |"
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
    eval_matrix_manifest = artifact_dir / "eval_matrix_manifest.json"
    if eval_matrix_manifest.is_file():
        return _load_json_object(eval_matrix_manifest)

    eval_manifest = artifact_dir / "run_manifest.json"
    if eval_manifest.is_file():
        return _load_json_object(eval_manifest)

    replay_manifest = artifact_dir / "replay_manifest.json"
    if replay_manifest.is_file():
        return _load_json_object(replay_manifest)

    raise ValueError(f"No supported artifact manifest found in {artifact_dir}")


def _required_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected string field {key!r}")
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
    return _summary_rate(summaries, {"oracle"}, "final_passes")


def _known_bad_pass_rate(summaries: list[dict[str, object]]) -> tuple[int, int] | None:
    return _summary_rate(_known_bad_summaries(summaries), None, "final_passes")


def _known_bad_public_hidden_fail_rate(
    summaries: list[dict[str, object]],
) -> tuple[int, int] | None:
    return _summary_rate(_known_bad_summaries(summaries), None, "public_pass_hidden_fail")


def _env_failure_rate(summaries: list[dict[str, object]]) -> tuple[int, int] | None:
    return _summary_rate(summaries, None, "env_or_harness_failures")


def _scorer_or_orchestrator_failure_rate(
    summaries: list[dict[str, object]],
) -> tuple[int, int] | None:
    return _summary_rate(summaries, None, "scorer_or_orchestrator_failures")


def _known_bad_summaries(
    summaries: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        summary
        for summary in summaries
        if summary.get("policy") in {"noop", "public-tests-only", "bad-noop", "bad-public-only"}
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
