import json
from pathlib import Path


def write_markdown_report(artifact_dir: Path, out_path: Path) -> Path:
    artifact_dir = artifact_dir.resolve()
    manifest = _load_artifact_manifest(artifact_dir)
    artifact_version = manifest.get("artifact_version")

    if artifact_version == "eval_run_v0":
        markdown = render_eval_report(artifact_dir, manifest)
    elif artifact_version == "replay_v0":
        raise NotImplementedError("Replay reports are not implemented yet")
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


def _load_json_object(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _load_artifact_manifest(artifact_dir: Path) -> dict[str, object]:
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
