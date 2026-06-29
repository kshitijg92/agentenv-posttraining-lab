import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig
from agentenv.orchestrators.agent_task_run import (
    AgentTaskRunResult,
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.tracing.schema import TRACE_SCHEMA_VERSION, TraceEventType


REPLAY_ARTIFACT_VERSION = "replay_v0"
SOURCE_EVAL_ARTIFACT_VERSION = "eval_run_v0"
SOURCE_AGENT_TASK_ARTIFACT_VERSION = "agent_task_run_artifacts_v0"
AGENT_CONTROL_SCRIPT_ARTIFACT = "agent_control_script.json"
DECODING_CONFIG_ARTIFACT = "decoding_config.json"

ReplayStatus = Literal["PASS", "MISMATCH", "REPLAY_ERROR"]
ReplayComparisonType = Literal["scorer_attempt", "agent_task_run"]
ComparedField = Literal[
    "status",
    "public_status",
    "hidden_status",
    "error_class",
    "final_diff_hash",
]

COMPARED_FIELDS: tuple[ComparedField, ...] = (
    "status",
    "public_status",
    "hidden_status",
    "error_class",
    "final_diff_hash",
)

SCORER_ATTEMPT_ARTIFACTS = (
    "run_manifest.json",
    "attempt.json",
    "stdout.txt",
    "stderr.txt",
    "error.txt",
    "trace.jsonl",
    "final.diff",
)
AGENT_BASE_ARTIFACTS = (
    "run_manifest.json",
    "agent_task_run.json",
    "error.txt",
    "agent_task_view.json",
    "prompt_loop_result.json",
    DECODING_CONFIG_ARTIFACT,
    AGENT_CONTROL_SCRIPT_ARTIFACT,
)

VOLATILE_JSON_KEYS = {
    "run_id",
    "attempt_id",
    "started_at",
    "ended_at",
    "timestamp_utc",
    "duration_ms",
    "latency_ms",
    "stdout_bytes",
    "stderr_bytes",
}


@dataclass(frozen=True)
class ReplayComparison:
    comparison_type: ReplayComparisonType
    task_id: str
    source_id: str
    source_artifact_dir: Path
    replay_id: str
    replay_artifact_dir: Path
    field_matches: dict[str, bool]
    artifact_matches: dict[str, bool]

    @property
    def matched(self) -> bool:
        return all(self.field_matches.values()) and all(self.artifact_matches.values())


@dataclass(frozen=True)
class ReplayRun:
    replay_id: str
    status: ReplayStatus
    source_run_dir: Path
    out_dir: Path
    comparisons: list[ReplayComparison]


def run_replay(source_run_dir: Path, out_dir: Path) -> ReplayRun:
    source_run_dir = source_run_dir.resolve()
    out_dir = out_dir.resolve()
    replay_id = f"replay_{uuid4().hex}"
    created_at = _utc_now()
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_events: list[dict[str, object]] = []
    base_provenance: dict[str, object] = {"replay_id": replay_id}
    _append_trace(
        trace_events,
        base_provenance,
        "replay_started",
        input_payload={
            "source_run_dir": str(source_run_dir),
            "out_dir": str(out_dir),
        },
    )

    try:
        source_manifest_path = source_run_dir / "run_manifest.json"
        source_manifest = _load_json_object(source_manifest_path)
        _require_supported_source_manifest(source_manifest, source_manifest_path)
        base_provenance = _source_manifest_provenance(replay_id, source_manifest)
        _append_trace(
            trace_events,
            base_provenance,
            "source_run_manifest_loaded",
            input_payload={
                "source_manifest_path": str(source_manifest_path),
            },
            output_payload={
                "source_eval_run_id": source_manifest.get("eval_run_id"),
            },
        )

        comparisons = _replay_source_artifact(
            base_provenance,
            source_run_dir,
            out_dir,
            source_manifest,
            trace_events,
        )
        status: ReplayStatus = (
            "PASS" if all(comparison.matched for comparison in comparisons) else "MISMATCH"
        )
    except Exception as exc:
        comparisons = []
        status = "REPLAY_ERROR"
        _append_trace(
            trace_events,
            base_provenance,
            "replay_error",
            output_payload={"error_class": type(exc).__name__, "message": str(exc)},
        )
        source_manifest = {}

    replay_run = ReplayRun(
        replay_id=replay_id,
        status=status,
        source_run_dir=source_run_dir,
        out_dir=out_dir,
        comparisons=comparisons,
    )
    _write_replay_artifacts(
        replay_run,
        created_at,
        source_manifest,
        trace_events,
    )
    return replay_run


def _replay_source_artifact(
    base_provenance: dict[str, object],
    source_run_dir: Path,
    out_dir: Path,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
) -> list[ReplayComparison]:
    artifact_version = source_manifest.get("artifact_version")
    if artifact_version == SOURCE_EVAL_ARTIFACT_VERSION:
        return _replay_eval_run_attempts(
            base_provenance,
            source_run_dir,
            out_dir,
            source_manifest,
            trace_events,
        )
    if artifact_version == SOURCE_AGENT_TASK_ARTIFACT_VERSION:
        return [
            _replay_agent_task_run_artifact(
                base_provenance,
                source_run_dir,
                out_dir,
                source_manifest,
                trace_events,
            )
        ]
    raise ValueError(f"Unsupported replay source artifact_version: {artifact_version!r}")


def _replay_eval_run_attempts(
    base_provenance: dict[str, object],
    source_run_dir: Path,
    out_dir: Path,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
) -> list[ReplayComparison]:
    attempts = source_manifest.get("attempts")
    if not isinstance(attempts, list):
        raise ValueError("Source eval run manifest is missing attempts list")

    comparisons: list[ReplayComparison] = []
    replay_attempts_dir = out_dir / "attempts"
    replay_attempts_dir.mkdir(parents=True, exist_ok=True)

    for raw_attempt in attempts:
        if not isinstance(raw_attempt, dict):
            raise ValueError("Source eval run manifest contains non-object attempt")
        comparison = _replay_one_eval_attempt_artifact(
            base_provenance,
            source_run_dir,
            replay_attempts_dir,
            raw_attempt,
            trace_events,
        )
        comparisons.append(comparison)
    return comparisons


def _replay_one_eval_attempt_artifact(
    base_provenance: dict[str, object],
    source_run_dir: Path,
    replay_attempts_dir: Path,
    source_attempt_record: dict[str, object],
    trace_events: list[dict[str, object]],
) -> ReplayComparison:
    artifact_dir = _required_str(source_attempt_record, "artifact_dir")
    source_artifact_dir = source_run_dir / artifact_dir
    source_artifact_manifest = _load_json_object(source_artifact_dir / "run_manifest.json")
    artifact_version = source_artifact_manifest.get("artifact_version")
    if artifact_version == SOURCE_AGENT_TASK_ARTIFACT_VERSION:
        return _replay_agent_task_run_artifact(
            base_provenance,
            source_artifact_dir,
            replay_attempts_dir,
            source_artifact_manifest,
            trace_events,
            replay_agent_dir=replay_attempts_dir / Path(artifact_dir).name,
        )
    return _replay_one_scorer_attempt(
        base_provenance,
        source_run_dir,
        replay_attempts_dir,
        source_attempt_record,
        trace_events,
    )


def _replay_one_scorer_attempt(
    base_provenance: dict[str, object],
    source_run_dir: Path,
    replay_attempts_dir: Path,
    source_attempt_record: dict[str, object],
    trace_events: list[dict[str, object]],
) -> ReplayComparison:
    artifact_dir = _required_str(source_attempt_record, "artifact_dir")
    task_id = _required_str(source_attempt_record, "task_id")
    source_attempt_dir = source_run_dir / artifact_dir
    source_attempt = AttemptResult.model_validate(
        _load_json_object(source_attempt_dir / "attempt.json")
    )
    source_attempt_provenance = _event_provenance(
        base_provenance,
        task_id=task_id,
        source_attempt_id=source_attempt.attempt_id,
    )
    _append_trace(
        trace_events,
        source_attempt_provenance,
        "source_attempt_loaded",
        input_payload={
            "source_attempt_dir": str(source_attempt_dir),
        },
        output_payload={
            "source_status": source_attempt.status,
            "source_public_status": source_attempt.public_status,
            "source_hidden_status": source_attempt.hidden_status,
        },
    )

    replay_attempt_dir = replay_attempts_dir / Path(artifact_dir).name
    _append_trace(
        trace_events,
        source_attempt_provenance,
        "fresh_attempt_started",
        input_payload={
            "replay_attempt_dir": str(replay_attempt_dir),
            "task_manifest_path": source_attempt.task_manifest_path,
            "submission_path": source_attempt.submission_path,
        },
    )
    replay_attempt_run = run_and_persist_patch_attempt_to_dir(
        Path(source_attempt.task_manifest_path),
        Path(source_attempt.submission_path),
        replay_attempt_dir,
    )
    replay_attempt = replay_attempt_run.result
    replay_attempt_provenance = _event_provenance(
        base_provenance,
        task_id=task_id,
        source_attempt_id=source_attempt.attempt_id,
        replay_attempt_id=replay_attempt.attempt_id,
    )
    _append_trace(
        trace_events,
        replay_attempt_provenance,
        "fresh_attempt_finished",
        output_payload={
            "status": replay_attempt.status,
            "public_status": replay_attempt.public_status,
            "hidden_status": replay_attempt.hidden_status,
            "error_class": replay_attempt.error_class,
            "final_diff_hash": replay_attempt.final_diff_hash,
        },
        payload_refs={
            "attempt": str(replay_attempt_dir / "attempt.json"),
            "final_diff": str(replay_attempt_dir / "final.diff"),
        },
    )

    field_matches: dict[str, bool] = {
        field: getattr(source_attempt, field) == getattr(replay_attempt, field)
        for field in COMPARED_FIELDS
    }
    artifact_matches = _compare_artifacts(
        source_attempt_dir,
        replay_attempt_dir,
        artifact_refs=SCORER_ATTEMPT_ARTIFACTS,
        repo_roots=_repo_roots(source_attempt, replay_attempt),
    )
    comparison = ReplayComparison(
        comparison_type="scorer_attempt",
        task_id=task_id,
        source_id=source_attempt.attempt_id,
        source_artifact_dir=source_attempt_dir,
        replay_id=replay_attempt.attempt_id,
        replay_artifact_dir=replay_attempt_dir,
        field_matches=field_matches,
        artifact_matches=artifact_matches,
    )
    _append_trace(
        trace_events,
        replay_attempt_provenance,
        "comparison_recorded",
        output_payload={
            "matched": comparison.matched,
            "field_matches": comparison.field_matches,
            "artifact_matches": comparison.artifact_matches,
        },
        payload_refs={
            "source_artifact": str(comparison.source_artifact_dir),
            "replay_artifact": str(comparison.replay_artifact_dir),
        },
    )
    return comparison


def _replay_agent_task_run_artifact(
    base_provenance: dict[str, object],
    source_run_dir: Path,
    out_dir: Path,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
    *,
    replay_agent_dir: Path | None = None,
) -> ReplayComparison:
    source_agent_result = AgentTaskRunResult.model_validate(
        _load_json_object(source_run_dir / "agent_task_run.json")
    )
    source_provenance = _event_provenance(
        base_provenance,
        task_id=source_agent_result.task_id,
        source_artifact_id=source_agent_result.run_id,
    )
    _append_trace(
        trace_events,
        source_provenance,
        "source_attempt_loaded",
        input_payload={
            "source_artifact_dir": str(source_run_dir),
            "source_artifact_version": source_manifest.get("artifact_version"),
        },
        output_payload={
            "source_status": source_agent_result.status,
            "source_prompt_loop_status": source_agent_result.prompt_loop_status,
            "source_attempt_status": _attempt_status(
                source_agent_result.attempt_result
            ),
        },
    )

    control_case = load_agent_control_script_case(
        source_run_dir / AGENT_CONTROL_SCRIPT_ARTIFACT
    )
    decoding_config = DecodingConfig.model_validate(
        _config_payload(_load_json_object(source_run_dir / DECODING_CONFIG_ARTIFACT))
    )
    model_client = ScriptedFakeModelClient(
        model_id=_source_agent_model_id(source_run_dir),
        script=control_case.script.steps,
    )
    if replay_agent_dir is None:
        replay_agent_dir = out_dir / "agent_task_run"
    _append_trace(
        trace_events,
        source_provenance,
        "fresh_attempt_started",
        input_payload={
            "replay_artifact_dir": str(replay_agent_dir),
            "task_manifest_path": source_agent_result.task_manifest_path,
            "agent_control_script": AGENT_CONTROL_SCRIPT_ARTIFACT,
            "decoding_config": DECODING_CONFIG_ARTIFACT,
        },
    )
    replay_agent_run = run_and_persist_agent_task_attempt_to_dir(
        Path(source_agent_result.task_manifest_path),
        model_client,
        decoding_config,
        replay_agent_dir,
        agent_control_script=control_case,
    )
    replay_agent_result = replay_agent_run.result
    replay_provenance = _event_provenance(
        base_provenance,
        task_id=source_agent_result.task_id,
        source_artifact_id=source_agent_result.run_id,
        replay_artifact_id=replay_agent_result.run_id,
    )
    _append_trace(
        trace_events,
        replay_provenance,
        "fresh_attempt_finished",
        output_payload={
            "status": replay_agent_result.status,
            "prompt_loop_status": replay_agent_result.prompt_loop_status,
            "attempt_status": _attempt_status(replay_agent_result.attempt_result),
            "error_class": replay_agent_result.error_class,
            "candidate_patch_hash": replay_agent_result.candidate_patch_hash,
        },
        payload_refs={"agent_task_run": str(replay_agent_dir / "agent_task_run.json")},
    )

    field_matches = _agent_field_matches(source_agent_result, replay_agent_result)
    artifact_refs = _agent_artifact_refs(source_run_dir)
    artifact_matches = _compare_artifacts(
        source_run_dir,
        replay_agent_dir,
        artifact_refs=artifact_refs,
        repo_roots=_repo_roots_from_agent_results(
            source_agent_result,
            replay_agent_result,
        ),
    )
    comparison = ReplayComparison(
        comparison_type="agent_task_run",
        task_id=source_agent_result.task_id,
        source_id=source_agent_result.run_id,
        source_artifact_dir=source_run_dir,
        replay_id=replay_agent_result.run_id,
        replay_artifact_dir=replay_agent_dir,
        field_matches=field_matches,
        artifact_matches=artifact_matches,
    )
    _append_trace(
        trace_events,
        replay_provenance,
        "comparison_recorded",
        output_payload={
            "matched": comparison.matched,
            "field_matches": comparison.field_matches,
            "artifact_matches": comparison.artifact_matches,
        },
        payload_refs={
            "source_artifact": str(comparison.source_artifact_dir),
            "replay_artifact": str(comparison.replay_artifact_dir),
        },
    )
    return comparison


def _write_replay_artifacts(
    replay_run: ReplayRun,
    created_at: str,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
) -> None:
    _append_trace(
        trace_events,
        _source_manifest_provenance(replay_run.replay_id, source_manifest),
        "replay_finished",
        output_payload={
            "status": replay_run.status,
            "attempt_count": len(replay_run.comparisons),
            "matched_attempts": sum(
                1 for comparison in replay_run.comparisons if comparison.matched
            ),
        },
    )

    (replay_run.out_dir / "replay_manifest.json").write_text(
        json.dumps(
            _replay_manifest(replay_run, created_at, source_manifest),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (replay_run.out_dir / "replay_result.json").write_text(
        json.dumps(
            _replay_result(replay_run),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (replay_run.out_dir / "replay_results.jsonl").write_text(
        "".join(
            json.dumps(
                _comparison_record(
                    comparison,
                    replay_run.source_run_dir,
                    replay_run.out_dir,
                ),
                sort_keys=True,
            )
            + "\n"
            for comparison in replay_run.comparisons
        )
    )
    (replay_run.out_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in trace_events)
    )


def _replay_manifest(
    replay_run: ReplayRun,
    created_at: str,
    source_manifest: dict[str, object],
) -> dict[str, object]:
    artifacts = {
        "replay_result": "replay_result.json",
        "replay_results": "replay_results.jsonl",
        "trace": "trace.jsonl",
    }
    source_artifact_version = source_manifest.get("artifact_version")
    comparison_types = {
        comparison.comparison_type for comparison in replay_run.comparisons
    }
    if source_artifact_version == SOURCE_EVAL_ARTIFACT_VERSION:
        artifacts["attempts"] = "attempts"
    elif "agent_task_run" in comparison_types:
        artifacts["agent_task_run"] = "agent_task_run"
    return {
        "artifact_version": REPLAY_ARTIFACT_VERSION,
        "replay_id": replay_run.replay_id,
        "created_at": created_at,
        "source_run_dir": str(replay_run.source_run_dir),
        "source_eval_run_id": source_manifest.get("eval_run_id"),
        "source_artifact_version": source_manifest.get("artifact_version"),
        "artifacts": artifacts,
    }


def _replay_result(replay_run: ReplayRun) -> dict[str, object]:
    matched_attempts = sum(
        1 for comparison in replay_run.comparisons if comparison.matched
    )
    attempt_count = len(replay_run.comparisons)
    return {
        "artifact_version": REPLAY_ARTIFACT_VERSION,
        "replay_id": replay_run.replay_id,
        "status": replay_run.status,
        "attempt_count": attempt_count,
        "matched_attempts": matched_attempts,
        "mismatched_attempts": attempt_count - matched_attempts,
        "error_count": 1 if replay_run.status == "REPLAY_ERROR" else 0,
    }


def _comparison_record(
    comparison: ReplayComparison,
    source_run_dir: Path,
    replay_out_dir: Path,
) -> dict[str, object]:
    source_artifact_ref = str(comparison.source_artifact_dir.relative_to(source_run_dir))
    replay_artifact_ref = str(comparison.replay_artifact_dir.relative_to(replay_out_dir))
    return {
        "comparison_type": comparison.comparison_type,
        "task_id": comparison.task_id,
        "source_id": comparison.source_id,
        "source_artifact_ref": source_artifact_ref,
        "source_artifact_path": str(comparison.source_artifact_dir),
        "replay_id": comparison.replay_id,
        "replay_artifact_ref": replay_artifact_ref,
        "replay_artifact_path": str(comparison.replay_artifact_dir),
        "matched": comparison.matched,
        "field_matches": comparison.field_matches,
        "artifact_matches": comparison.artifact_matches,
    }


def _compare_artifacts(
    source_artifact_dir: Path,
    replay_artifact_dir: Path,
    *,
    artifact_refs: tuple[str, ...],
    repo_roots: tuple[Path, ...],
) -> dict[str, bool]:
    artifact_matches: dict[str, bool] = {}
    for artifact in artifact_refs:
        source_path = source_artifact_dir / artifact
        replay_path = replay_artifact_dir / artifact
        if not source_path.is_file() or not replay_path.is_file():
            artifact_matches[artifact] = False
            continue
        artifact_matches[artifact] = _normalized_artifact(
            artifact,
            source_path,
            repo_roots=repo_roots,
        ) == _normalized_artifact(
            artifact,
            replay_path,
            repo_roots=repo_roots,
        )
    return artifact_matches


def _normalized_artifact(
    artifact: str,
    path: Path,
    *,
    repo_roots: tuple[Path, ...],
) -> object:
    if artifact.endswith(".json"):
        return _normalize_json_value(_load_json_object(path), repo_roots=repo_roots)
    if artifact.endswith(".jsonl"):
        return [
            _normalize_json_value(event, repo_roots=repo_roots)
            for event in _load_jsonl_objects(path)
        ]
    return _normalize_text(path.read_text(), repo_roots=repo_roots)


def _normalize_json_value(value: object, *, repo_roots: tuple[Path, ...]) -> object:
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for key, raw_value in value.items():
            if key in VOLATILE_JSON_KEYS:
                normalized[key] = f"<{key.upper()}>"
            else:
                normalized[key] = _normalize_json_value(
                    raw_value,
                    repo_roots=repo_roots,
                )
        return normalized
    if isinstance(value, list):
        return [
            _normalize_json_value(item, repo_roots=repo_roots)
            for item in value
        ]
    if isinstance(value, str):
        return _normalize_text(value, repo_roots=repo_roots)
    return value


def _normalize_text(text: str, *, repo_roots: tuple[Path, ...]) -> str:
    normalized = text
    for repo_root in repo_roots:
        normalized = normalized.replace(str(repo_root), "<REPO_ROOT>")
    normalized = re.sub(r"/tmp/agentenv-[^/\s:]+", "<AGENTENV_TMP>", normalized)
    normalized = re.sub(
        r"/tmp/pytest-of-[^/\s:]+/pytest-(?:\d+|current)",
        "<PYTEST_TMP>",
        normalized,
    )
    normalized = re.sub(
        r"\.\.\.[^'\"\s]*/?p?ytest-(?:\d+|current)",
        "...<PYTEST_TMP>",
        normalized,
    )
    normalized = re.sub(r"in \d+\.\d+s", "in <PYTEST_DURATION>s", normalized)
    normalized = re.sub(r"in \d+ms", "in <TOOL_DURATION>ms", normalized)
    return normalized


def _repo_roots(
    source_attempt: AttemptResult,
    replay_attempt: AttemptResult,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    for raw_path in (
        source_attempt.task_manifest_path,
        source_attempt.submission_path,
        replay_attempt.task_manifest_path,
        replay_attempt.submission_path,
    ):
        root = _repo_root_from_path(Path(raw_path))
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def _repo_roots_from_agent_results(
    source_agent_result: AgentTaskRunResult,
    replay_agent_result: AgentTaskRunResult,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    for raw_path in (
        source_agent_result.task_manifest_path,
        replay_agent_result.task_manifest_path,
    ):
        root = _repo_root_from_path(Path(raw_path))
        if root not in roots:
            roots.append(root)
    source_attempt = source_agent_result.attempt_result
    replay_attempt = replay_agent_result.attempt_result
    if source_attempt is not None and replay_attempt is not None:
        for root in _repo_roots(source_attempt, replay_attempt):
            if root not in roots:
                roots.append(root)
    return tuple(roots)


def _agent_field_matches(
    source_agent_result: AgentTaskRunResult,
    replay_agent_result: AgentTaskRunResult,
) -> dict[str, bool]:
    return {
        "status": source_agent_result.status == replay_agent_result.status,
        "prompt_loop_status": (
            source_agent_result.prompt_loop_status
            == replay_agent_result.prompt_loop_status
        ),
        "attempt_status": (
            _attempt_status(source_agent_result.attempt_result)
            == _attempt_status(replay_agent_result.attempt_result)
        ),
        "candidate_patch_hash": (
            source_agent_result.candidate_patch_hash
            == replay_agent_result.candidate_patch_hash
        ),
        "error_class": source_agent_result.error_class == replay_agent_result.error_class,
        "error_message": (
            source_agent_result.error_message == replay_agent_result.error_message
        ),
    }


def _attempt_status(attempt_result: AttemptResult | None) -> str | None:
    return attempt_result.status if attempt_result is not None else None


def _agent_artifact_refs(source_agent_dir: Path) -> tuple[str, ...]:
    artifact_refs: list[str] = []
    for artifact_ref in AGENT_BASE_ARTIFACTS:
        if (source_agent_dir / artifact_ref).is_file():
            artifact_refs.append(artifact_ref)
    if (source_agent_dir / "candidate.patch").is_file():
        artifact_refs.append("candidate.patch")
    if (source_agent_dir / "attempt").is_dir():
        artifact_refs.extend(
            f"attempt/{artifact_ref}" for artifact_ref in SCORER_ATTEMPT_ARTIFACTS
        )
    return tuple(artifact_refs)


def _source_agent_model_id(source_agent_dir: Path) -> str:
    prompt_loop_result = _load_json_object(source_agent_dir / "prompt_loop_result.json")
    model_responses = prompt_loop_result.get("model_responses")
    if isinstance(model_responses, list):
        for raw_response in model_responses:
            if isinstance(raw_response, dict):
                model_id = raw_response.get("model_id")
                if isinstance(model_id, str) and model_id:
                    return model_id
    return "agent-control-scripted-v0"


def _repo_root_from_path(path: Path) -> Path:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "src/agentenv").is_dir():
            return parent
    return Path.cwd().resolve()


def _load_jsonl_objects(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text().splitlines():
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected JSON object line at {path}")
        records.append(raw)
    return records


def _load_json_object(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return raw


def _config_payload(value: dict[str, object]) -> dict[str, object]:
    config = value.get("config")
    if isinstance(config, dict):
        return config
    return value


def _require_supported_source_manifest(
    source_manifest: dict[str, object],
    source_manifest_path: Path,
) -> None:
    artifact_version = source_manifest.get("artifact_version")
    if artifact_version not in {
        SOURCE_EVAL_ARTIFACT_VERSION,
        SOURCE_AGENT_TASK_ARTIFACT_VERSION,
    }:
        raise ValueError(
            "Replay input must be one of "
            f"{SOURCE_EVAL_ARTIFACT_VERSION!r}, "
            f"{SOURCE_AGENT_TASK_ARTIFACT_VERSION!r}; got {artifact_version!r} "
            f"at {source_manifest_path}"
        )


def _source_manifest_provenance(
    replay_id: str,
    source_manifest: dict[str, object],
) -> dict[str, object]:
    provenance: dict[str, object] = {"replay_id": replay_id}
    eval_run_id = source_manifest.get("eval_run_id")
    if isinstance(eval_run_id, str):
        provenance["source_eval_run_id"] = eval_run_id
    source_artifact_id = source_manifest.get("run_id")
    if isinstance(source_artifact_id, str):
        provenance["source_artifact_id"] = source_artifact_id
    return provenance


def _required_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected string field {key!r}")
    return value


def _append_trace(
    trace_events: list[dict[str, object]],
    provenance_config: dict[str, object],
    event_type: TraceEventType,
    *,
    input_payload: dict[str, object] | None = None,
    output_payload: dict[str, object] | None = None,
    payload_refs: dict[str, str] | None = None,
    payload_hashes: dict[str, str] | None = None,
) -> None:
    event: dict[str, object] = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "event_index": len(trace_events),
        "timestamp_utc": _utc_now(),
        "event_type": event_type,
        "provenance_config": provenance_config,
    }
    if input_payload is not None:
        event["input_payload"] = input_payload
    if output_payload is not None:
        event["output_payload"] = output_payload
    if payload_refs is not None:
        event["payload_refs"] = payload_refs
    if payload_hashes is not None:
        event["payload_hashes"] = payload_hashes
    trace_events.append(event)


def _event_provenance(
    base_provenance: dict[str, object],
    **extra: object,
) -> dict[str, object]:
    return {**base_provenance, **extra}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
