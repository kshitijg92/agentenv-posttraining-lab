import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from agentenv.artifacts import (
    MANIFEST_FILENAME,
    ArtifactType,
    prepare_artifact_output_dir,
)
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION
from agentenv.artifacts.manifests import AGENT_ATTEMPT_ARTIFACT_REFS
from agentenv.artifacts.manifests import REPLAY_RUN_ARTIFACT_SCHEMA_VERSION
from agentenv.artifacts.manifests import SCORER_ATTEMPT_ARTIFACT_REFS
from agentenv.artifacts.manifests import SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION
from agentenv.artifacts.manifests import AgentTaskRunManifest
from agentenv.artifacts.manifests import REPLAY_RUN_ARTIFACT_REFS
from agentenv.artifacts.manifests import ReplayRunManifest
from agentenv.artifacts.manifests import ScorerAttemptManifest
from agentenv.artifacts.manifests import load_attempt_manifest
from agentenv.artifacts.manifests import load_replay_source_manifest
from agentenv.artifacts.payloads import ReplayComparisonRecord
from agentenv.artifacts.payloads import ReplayResult
from agentenv.artifacts.payloads import REPLAY_RESULT_SCHEMA_VERSION
from agentenv.artifacts.payloads import load_agent_task_run_result
from agentenv.artifacts.payloads import load_decoding_config_provenance
from agentenv.artifacts.payloads import load_attempt_result
from agentenv.artifacts.payloads import load_prompt_loop_result
from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.ids import new_replay_run_id
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.agent_task_run import (
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.tracing.schema import TRACE_SCHEMA_VERSION, TraceEventType


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
    MANIFEST_FILENAME,
    *SCORER_ATTEMPT_ARTIFACT_REFS.values(),
)
VOLATILE_JSON_KEYS = {
    "agent_attempt_id",
    "message_id",
    "scorer_attempt_id",
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
    source_artifact_dir: Path
    replay_artifact_dir: Path
    field_matches: dict[str, bool]
    artifact_matches: dict[str, bool]
    source_eval_attempt_id: str | None = None
    source_scorer_attempt_id: str | None = None
    replayed_scorer_attempt_id: str | None = None
    source_agent_attempt_id: str | None = None
    replayed_agent_attempt_id: str | None = None

    @property
    def matched(self) -> bool:
        return all(self.field_matches.values()) and all(self.artifact_matches.values())


@dataclass(frozen=True)
class ReplayRun:
    replay_run_id: str
    status: ReplayStatus
    source_run_dir: Path
    out_dir: Path
    comparisons: list[ReplayComparison]


def run_replay(
    source_run_dir: Path,
    out_dir: Path,
    *,
    overwrite: bool = False,
) -> ReplayRun:
    source_run_dir = source_run_dir.resolve()
    replay_run_id = new_replay_run_id()
    created_at = _utc_now()
    out_dir = prepare_artifact_output_dir(out_dir, overwrite=overwrite)

    trace_events: list[dict[str, object]] = []
    base_provenance: dict[str, object] = {"replay_run_id": replay_run_id}
    _append_trace(
        trace_events,
        base_provenance,
        "replay_started",
        input_payload={
            "source_run_dir": str(source_run_dir),
            "out_dir": str(out_dir),
        },
    )
    source_manifest: dict[str, object] = {}

    try:
        source_manifest_path = source_run_dir / MANIFEST_FILENAME
        loaded_source_manifest = load_replay_source_manifest(source_manifest_path)
        source_manifest = loaded_source_manifest.model_dump(
            mode="json",
            by_alias=True,
        )
        base_provenance = _source_manifest_provenance(replay_run_id, source_manifest)
        _append_trace(
            trace_events,
            base_provenance,
            "source_manifest_loaded",
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
        if not comparisons:
            raise ValueError("Replay source produced no comparisons")
        status: ReplayStatus = (
            "PASS"
            if all(comparison.matched for comparison in comparisons)
            else "MISMATCH"
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

    replay_run = ReplayRun(
        replay_run_id=replay_run_id,
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
    artifact_type = source_manifest.get("artifact_type")
    if artifact_type == ArtifactType.EVAL_RUN.value:
        return _replay_eval_run_attempts(
            base_provenance,
            source_run_dir,
            out_dir,
            source_manifest,
            trace_events,
        )
    if artifact_type == ArtifactType.AGENT_ATTEMPT.value:
        return [
            _replay_agent_task_run_artifact(
                base_provenance,
                source_run_dir,
                out_dir,
                source_manifest,
                trace_events,
            )
        ]
    raise ValueError(f"Unsupported replay source artifact_type: {artifact_type!r}")


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
    replay_attempts_dir = out_dir / REPLAY_RUN_ARTIFACT_REFS["attempts"]
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
    source_eval_attempt_id = _required_str(
        source_attempt_record,
        "eval_attempt_id",
    )
    parent_artifact_type = _validated_attempt_source_artifact_type(
        source_attempt_record,
        source_run_dir / MANIFEST_FILENAME,
    )
    source_artifact_dir = resolve_relative_artifact_ref(source_run_dir, artifact_dir)
    source_artifact_manifest_model = load_attempt_manifest(
        source_artifact_dir / MANIFEST_FILENAME
    )
    source_artifact_manifest = source_artifact_manifest_model.model_dump(
        mode="json",
        by_alias=True,
    )
    artifact_type = source_artifact_manifest_model.artifact_type
    _validate_eval_child_manifest_matches_parent(
        source_attempt_record,
        source_artifact_manifest_model,
        artifact_dir=artifact_dir,
        parent_artifact_type=parent_artifact_type,
    )
    if artifact_type == ArtifactType.AGENT_ATTEMPT.value:
        if not isinstance(source_artifact_manifest_model, AgentTaskRunManifest):
            raise ValueError(f"Expected agent attempt manifest for {artifact_dir}")
        return _replay_agent_task_run_artifact(
            base_provenance,
            source_artifact_dir,
            replay_attempts_dir,
            source_artifact_manifest,
            trace_events,
            replay_agent_dir=replay_attempts_dir / Path(artifact_dir).name,
            source_eval_attempt_id=source_eval_attempt_id,
            parent_attempt_record=source_attempt_record,
        )
    if not isinstance(source_artifact_manifest_model, ScorerAttemptManifest):
        raise ValueError(f"Expected scorer attempt manifest for {artifact_dir}")
    return _replay_one_scorer_attempt(
        base_provenance,
        source_run_dir,
        replay_attempts_dir,
        source_attempt_record,
        trace_events,
        source_eval_attempt_id=source_eval_attempt_id,
        source_manifest=source_artifact_manifest_model,
    )


def _validated_attempt_source_artifact_type(
    source_manifest: dict[str, object],
    source_manifest_path: Path,
) -> str:
    artifact_type = source_manifest.get("artifact_type")
    artifact_schema_version = source_manifest.get("artifact_schema_version")
    expected_schema_versions = {
        ArtifactType.SCORER_ATTEMPT.value: SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        ArtifactType.AGENT_ATTEMPT.value: AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
    }
    if (
        not isinstance(artifact_type, str)
        or artifact_type not in expected_schema_versions
    ):
        raise ValueError(
            "Eval run child artifact_type must be one of "
            f"{ArtifactType.SCORER_ATTEMPT.value!r}, "
            f"{ArtifactType.AGENT_ATTEMPT.value!r}; got {artifact_type!r} "
            f"at {source_manifest_path}"
        )
    expected_schema_version = expected_schema_versions[artifact_type]
    if artifact_schema_version != expected_schema_version:
        raise ValueError(
            "Unsupported eval run child artifact_schema_version "
            f"{artifact_schema_version!r} for artifact_type {artifact_type!r}; "
            f"expected {expected_schema_version!r} at {source_manifest_path}"
        )
    return artifact_type


def _validate_eval_child_manifest_matches_parent(
    parent_attempt_record: dict[str, object],
    child_manifest: ScorerAttemptManifest | AgentTaskRunManifest,
    *,
    artifact_dir: str,
    parent_artifact_type: str,
) -> None:
    if child_manifest.artifact_type != parent_artifact_type:
        raise ValueError(
            "Eval run child artifact_type mismatch between parent attempt record "
            f"{parent_artifact_type!r} and child manifest {child_manifest.artifact_type!r} "
            f"for {artifact_dir}"
        )
    parent_schema_version = _required_str(
        parent_attempt_record,
        "artifact_schema_version",
    )
    if child_manifest.artifact_schema_version != parent_schema_version:
        raise ValueError(
            "Eval run child artifact_schema_version mismatch between parent attempt "
            f"record {parent_schema_version!r} and child manifest "
            f"{child_manifest.artifact_schema_version!r} for {artifact_dir}"
        )
    parent_task_id = _required_str(parent_attempt_record, "task_id")
    if child_manifest.task_id != parent_task_id:
        raise ValueError(
            "Eval run child task_id mismatch between parent attempt record "
            f"{parent_task_id!r} and child manifest {child_manifest.task_id!r} "
            f"for {artifact_dir}"
        )
    if isinstance(child_manifest, ScorerAttemptManifest):
        _validate_scorer_manifest_matches_eval_parent(
            child_manifest,
            parent_attempt_record,
            artifact_dir,
        )
        return
    _validate_agent_manifest_matches_eval_parent(
        child_manifest,
        parent_attempt_record,
        artifact_dir,
    )


def _validate_scorer_manifest_matches_eval_parent(
    child_manifest: ScorerAttemptManifest,
    parent_attempt_record: dict[str, object],
    artifact_dir: str,
) -> None:
    scorer_summary = parent_attempt_record.get("scorer")
    if not isinstance(scorer_summary, dict):
        raise ValueError(
            f"Scorer eval attempt record missing scorer summary: {artifact_dir}"
        )
    source_scorer_attempt_id = _required_str(scorer_summary, "scorer_attempt_id")
    if child_manifest.scorer_attempt_id != source_scorer_attempt_id:
        raise ValueError(
            "Eval run child scorer_attempt_id mismatch between parent attempt "
            f"record {source_scorer_attempt_id!r} and child manifest "
            f"{child_manifest.scorer_attempt_id!r} for {artifact_dir}"
        )
    _require_null_or_missing(parent_attempt_record, "agent", artifact_dir)


def _validate_agent_manifest_matches_eval_parent(
    child_manifest: AgentTaskRunManifest,
    parent_attempt_record: dict[str, object],
    artifact_dir: str,
) -> None:
    agent_summary = parent_attempt_record.get("agent")
    if not isinstance(agent_summary, dict):
        raise ValueError(
            f"Agent eval attempt record missing agent summary: {artifact_dir}"
        )
    source_agent_attempt_id = _required_str(agent_summary, "agent_attempt_id")
    if child_manifest.agent_attempt_id != source_agent_attempt_id:
        raise ValueError(
            "Eval run child agent_attempt_id mismatch between parent attempt "
            f"record {source_agent_attempt_id!r} and child manifest "
            f"{child_manifest.agent_attempt_id!r} for {artifact_dir}"
        )
    _require_null_or_missing(parent_attempt_record, "scorer", artifact_dir)


def _require_null_or_missing(
    payload: dict[str, object],
    field_name: str,
    artifact_dir: str,
) -> None:
    if payload.get(field_name) is not None:
        raise ValueError(f"{field_name} must be null for eval child {artifact_dir}")


def _replay_one_scorer_attempt(
    base_provenance: dict[str, object],
    source_run_dir: Path,
    replay_attempts_dir: Path,
    source_attempt_record: dict[str, object],
    trace_events: list[dict[str, object]],
    *,
    source_eval_attempt_id: str,
    source_manifest: ScorerAttemptManifest,
) -> ReplayComparison:
    artifact_dir = _required_str(source_attempt_record, "artifact_dir")
    task_id = _required_str(source_attempt_record, "task_id")
    source_attempt_dir = resolve_relative_artifact_ref(source_run_dir, artifact_dir)
    source_attempt_ref = source_manifest.artifacts["attempt"]
    source_attempt_path = resolve_relative_artifact_ref(
        source_attempt_dir,
        source_attempt_ref,
    )
    source_attempt = load_attempt_result(source_attempt_path)
    _validate_scorer_result_matches_manifest(
        source_attempt,
        source_manifest,
        source_attempt_path,
    )
    _validate_scorer_result_matches_eval_parent(
        source_attempt,
        source_attempt_record,
        source_attempt_path,
    )
    source_attempt_provenance = _event_provenance(
        base_provenance,
        task_id=task_id,
        source_eval_attempt_id=source_eval_attempt_id,
        source_scorer_attempt_id=source_attempt.scorer_attempt_id,
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
        source_eval_attempt_id=source_eval_attempt_id,
        source_scorer_attempt_id=source_attempt.scorer_attempt_id,
        replayed_scorer_attempt_id=replay_attempt.scorer_attempt_id,
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
            "attempt": str(
                replay_attempt_dir / SCORER_ATTEMPT_ARTIFACT_REFS["attempt"]
            ),
            "final_diff": str(
                replay_attempt_dir / SCORER_ATTEMPT_ARTIFACT_REFS["final_diff"]
            ),
        },
    )

    field_matches: dict[str, bool] = {
        field: getattr(source_attempt, field) == getattr(replay_attempt, field)
        for field in COMPARED_FIELDS
    }
    artifact_matches = _compare_artifacts(
        source_attempt_dir,
        replay_attempt_dir,
        artifact_refs=_scorer_artifact_refs(source_manifest),
        repo_roots=_repo_roots(source_attempt, replay_attempt),
    )
    comparison = ReplayComparison(
        comparison_type="scorer_attempt",
        task_id=task_id,
        source_artifact_dir=source_attempt_dir,
        replay_artifact_dir=replay_attempt_dir,
        field_matches=field_matches,
        artifact_matches=artifact_matches,
        source_eval_attempt_id=source_eval_attempt_id,
        source_scorer_attempt_id=source_attempt.scorer_attempt_id,
        replayed_scorer_attempt_id=replay_attempt.scorer_attempt_id,
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


def _validate_scorer_result_matches_manifest(
    result: AttemptResult,
    manifest: ScorerAttemptManifest,
    source_path: Path,
) -> None:
    if result.scorer_attempt_id != manifest.scorer_attempt_id:
        raise ValueError(
            f"scorer_attempt_id mismatch between result and manifest: {source_path}"
        )
    if result.task_id != manifest.task_id:
        raise ValueError(
            f"task_id mismatch between scorer result and manifest: {source_path}"
        )
    if result.task_manifest_path != manifest.task_manifest_path:
        raise ValueError(
            f"task_manifest_path mismatch between scorer result and manifest: {source_path}"
        )
    if result.submission_path != manifest.submission_path:
        raise ValueError(
            f"submission_path mismatch between scorer result and manifest: {source_path}"
        )
    if result.status != manifest.status:
        raise ValueError(
            f"status mismatch between scorer result and manifest: {source_path}"
        )


def _validate_scorer_result_matches_eval_parent(
    result: AttemptResult,
    parent_attempt_record: dict[str, object],
    source_path: Path,
) -> None:
    scorer_summary = parent_attempt_record.get("scorer")
    if not isinstance(scorer_summary, dict):
        raise ValueError(
            f"Scorer eval attempt record missing scorer summary: {source_path}"
        )
    _validate_scorer_result_matches_summary(
        result,
        scorer_summary,
        source_path,
        context="eval parent",
    )


def _validate_scorer_result_matches_summary(
    result: AttemptResult,
    scorer_summary: dict[str, object],
    source_path: Path,
    *,
    context: str,
) -> None:
    compared_fields = {
        "scorer_attempt_id": result.scorer_attempt_id,
        "status": result.status,
        "public_status": result.public_status,
        "hidden_status": result.hidden_status,
        "error_class": result.error_class,
        "final_diff_hash": result.final_diff_hash,
    }
    for field_name, result_value in compared_fields.items():
        if result_value != scorer_summary.get(field_name):
            raise ValueError(
                f"{field_name} mismatch between scorer result and {context}: "
                f"{source_path}"
            )


def _replay_agent_task_run_artifact(
    base_provenance: dict[str, object],
    source_run_dir: Path,
    out_dir: Path,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
    *,
    replay_agent_dir: Path | None = None,
    source_eval_attempt_id: str | None = None,
    parent_attempt_record: dict[str, object] | None = None,
) -> ReplayComparison:
    agent_task_run_ref = _required_manifest_artifact_ref(
        source_manifest,
        "agent_task_run",
    )
    source_agent_result = load_agent_task_run_result(
        resolve_relative_artifact_ref(source_run_dir, agent_task_run_ref)
    )
    _validate_agent_result_matches_manifest(
        source_agent_result,
        source_manifest,
        source_run_dir / agent_task_run_ref,
    )
    if parent_attempt_record is not None:
        _validate_agent_result_matches_eval_parent(
            source_agent_result,
            parent_attempt_record,
            source_run_dir / agent_task_run_ref,
        )
    source_provenance = _event_provenance(
        base_provenance,
        task_id=source_agent_result.task_id,
        source_eval_attempt_id=source_eval_attempt_id,
        source_agent_attempt_id=source_agent_result.agent_attempt_id,
    )
    _append_trace(
        trace_events,
        source_provenance,
        "source_attempt_loaded",
        input_payload={
            "source_artifact_dir": str(source_run_dir),
            "source_artifact_type": source_manifest.get("artifact_type"),
            "source_artifact_schema_version": source_manifest.get(
                "artifact_schema_version"
            ),
        },
        output_payload={
            "source_status": source_agent_result.status,
            "source_prompt_loop_status": source_agent_result.prompt_loop_status,
            "source_attempt_status": _attempt_status(
                source_agent_result.attempt_result
            ),
        },
    )

    agent_control_script_ref = _required_manifest_artifact_ref(
        source_manifest,
        "agent_control_script",
    )
    decoding_config_ref = _required_manifest_artifact_ref(
        source_manifest,
        "decoding_config",
    )
    control_case = load_agent_control_script_case(
        resolve_relative_artifact_ref(source_run_dir, agent_control_script_ref)
    )
    decoding_config = load_decoding_config_provenance(
        resolve_relative_artifact_ref(source_run_dir, decoding_config_ref)
    ).config
    model_client = ScriptedFakeModelClient(
        model_id=_source_agent_model_id(source_run_dir, source_manifest),
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
            "agent_control_script": agent_control_script_ref,
            "decoding_config": decoding_config_ref,
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
        source_eval_attempt_id=source_eval_attempt_id,
        source_agent_attempt_id=source_agent_result.agent_attempt_id,
        replayed_agent_attempt_id=replay_agent_result.agent_attempt_id,
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
        payload_refs={
            "agent_task_run": str(
                replay_agent_dir / AGENT_ATTEMPT_ARTIFACT_REFS["agent_task_run"]
            )
        },
    )

    field_matches = _agent_field_matches(source_agent_result, replay_agent_result)
    artifact_refs = _agent_artifact_refs(source_manifest)
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
        source_artifact_dir=source_run_dir,
        replay_artifact_dir=replay_agent_dir,
        field_matches=field_matches,
        artifact_matches=artifact_matches,
        source_eval_attempt_id=source_eval_attempt_id,
        source_agent_attempt_id=source_agent_result.agent_attempt_id,
        replayed_agent_attempt_id=replay_agent_result.agent_attempt_id,
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


def _validate_agent_result_matches_manifest(
    result: AgentTaskRunResult,
    manifest: dict[str, object],
    source_path: Path,
) -> None:
    if result.agent_attempt_id != _required_str(manifest, "agent_attempt_id"):
        raise ValueError(
            f"agent_attempt_id mismatch between result and manifest: {source_path}"
        )
    if result.task_id != _required_str(manifest, "task_id"):
        raise ValueError(
            f"task_id mismatch between agent result and manifest: {source_path}"
        )
    if result.task_manifest_path != _required_str(manifest, "task_manifest_path"):
        raise ValueError(
            f"task_manifest_path mismatch between agent result and manifest: {source_path}"
        )
    if result.status != _required_str(manifest, "status"):
        raise ValueError(
            f"status mismatch between agent result and manifest: {source_path}"
        )
    prompt_loop_status = manifest.get("prompt_loop_status")
    if result.prompt_loop_status != prompt_loop_status:
        raise ValueError(
            f"prompt_loop_status mismatch between agent result and manifest: {source_path}"
        )
    if _attempt_status(result.attempt_result) != manifest.get("attempt_status"):
        raise ValueError(
            f"attempt_status mismatch between agent result and manifest: {source_path}"
        )


def _validate_agent_result_matches_eval_parent(
    result: AgentTaskRunResult,
    parent_attempt_record: dict[str, object],
    source_path: Path,
) -> None:
    agent_summary = parent_attempt_record.get("agent")
    if not isinstance(agent_summary, dict):
        raise ValueError(
            f"Agent eval attempt record missing agent summary: {source_path}"
        )
    if result.agent_attempt_id != _required_str(agent_summary, "agent_attempt_id"):
        raise ValueError(
            f"agent_attempt_id mismatch between agent result and eval parent: {source_path}"
        )
    if result.task_id != _required_str(parent_attempt_record, "task_id"):
        raise ValueError(
            f"task_id mismatch between agent result and eval parent: {source_path}"
        )
    if result.status != _required_str(agent_summary, "status"):
        raise ValueError(
            f"status mismatch between agent result and eval parent: {source_path}"
        )
    if result.prompt_loop_status != agent_summary.get("prompt_loop_status"):
        raise ValueError(
            f"prompt_loop_status mismatch between agent result and eval parent: {source_path}"
        )
    if result.candidate_patch_hash != agent_summary.get("candidate_patch_hash"):
        raise ValueError(
            f"candidate_patch_hash mismatch between agent result and eval parent: {source_path}"
        )
    scorer_summary = agent_summary.get("scorer_attempt")
    if result.attempt_result is None:
        if scorer_summary is not None:
            raise ValueError(
                f"agent result missing scorer attempt referenced by eval parent: {source_path}"
            )
        return
    if not isinstance(scorer_summary, dict):
        raise ValueError(f"Eval parent missing nested scorer summary: {source_path}")
    if result.attempt_result.scorer_attempt_id != _required_str(
        scorer_summary,
        "scorer_attempt_id",
    ):
        raise ValueError(
            f"scorer_attempt_id mismatch between agent result and eval parent: {source_path}"
        )
    _validate_scorer_result_matches_summary(
        result.attempt_result,
        scorer_summary,
        source_path,
        context="eval parent",
    )


def _write_replay_artifacts(
    replay_run: ReplayRun,
    created_at: str,
    source_manifest: dict[str, object],
    trace_events: list[dict[str, object]],
) -> None:
    _append_trace(
        trace_events,
        _source_manifest_provenance(replay_run.replay_run_id, source_manifest),
        "replay_finished",
        output_payload={
            "status": replay_run.status,
            "attempt_count": len(replay_run.comparisons),
            "matched_attempts": sum(
                1 for comparison in replay_run.comparisons if comparison.matched
            ),
        },
    )

    replay_manifest = ReplayRunManifest.model_validate(
        _replay_manifest(replay_run, created_at, source_manifest)
    )
    replay_result = ReplayResult.model_validate(_replay_result(replay_run))
    replay_comparisons = [
        ReplayComparisonRecord.model_validate(
            _comparison_record(
                comparison,
                replay_run.source_run_dir,
                replay_run.out_dir,
            )
        )
        for comparison in replay_run.comparisons
    ]

    (replay_run.out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(
            replay_manifest.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (replay_run.out_dir / REPLAY_RUN_ARTIFACT_REFS["replay_result"]).write_text(
        json.dumps(
            replay_result.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (replay_run.out_dir / REPLAY_RUN_ARTIFACT_REFS["replay_results"]).write_text(
        "".join(
            json.dumps(
                comparison.model_dump(mode="json", exclude_none=True),
                sort_keys=True,
            )
            + "\n"
            for comparison in replay_comparisons
        )
    )
    (replay_run.out_dir / REPLAY_RUN_ARTIFACT_REFS["trace"]).write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in trace_events)
    )


def _replay_manifest(
    replay_run: ReplayRun,
    created_at: str,
    source_manifest: dict[str, object],
) -> dict[str, object]:
    artifacts = {
        "replay_result": REPLAY_RUN_ARTIFACT_REFS["replay_result"],
        "replay_results": REPLAY_RUN_ARTIFACT_REFS["replay_results"],
        "trace": REPLAY_RUN_ARTIFACT_REFS["trace"],
    }
    source_artifact_type = source_manifest.get("artifact_type")
    comparison_types = {
        comparison.comparison_type for comparison in replay_run.comparisons
    }
    if source_artifact_type == ArtifactType.EVAL_RUN.value:
        artifacts["attempts"] = REPLAY_RUN_ARTIFACT_REFS["attempts"]
    elif "agent_task_run" in comparison_types:
        artifacts["agent_task_run"] = REPLAY_RUN_ARTIFACT_REFS["agent_task_run"]
    return {
        "artifact_type": ArtifactType.REPLAY_RUN,
        "artifact_schema_version": REPLAY_RUN_ARTIFACT_SCHEMA_VERSION,
        "replay_run_id": replay_run.replay_run_id,
        "created_at": created_at,
        "source_run_dir": str(replay_run.source_run_dir),
        "source_eval_run_id": source_manifest.get("eval_run_id"),
        "source_agent_attempt_id": source_manifest.get("agent_attempt_id"),
        "source_artifact_type": source_manifest.get("artifact_type"),
        "source_artifact_schema_version": source_manifest.get(
            "artifact_schema_version"
        ),
        "artifacts": artifacts,
    }


def _replay_result(replay_run: ReplayRun) -> dict[str, object]:
    matched_attempts = sum(
        1 for comparison in replay_run.comparisons if comparison.matched
    )
    attempt_count = len(replay_run.comparisons)
    return {
        "schema_version": REPLAY_RESULT_SCHEMA_VERSION,
        "replay_run_id": replay_run.replay_run_id,
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
    source_artifact_ref = str(
        comparison.source_artifact_dir.relative_to(source_run_dir)
    )
    replay_artifact_ref = str(
        comparison.replay_artifact_dir.relative_to(replay_out_dir)
    )
    return {
        "comparison_type": comparison.comparison_type,
        "task_id": comparison.task_id,
        **_comparison_id_fields(comparison),
        "source_artifact_ref": source_artifact_ref,
        "source_artifact_path": str(comparison.source_artifact_dir),
        "replay_artifact_ref": replay_artifact_ref,
        "replay_artifact_path": str(comparison.replay_artifact_dir),
        "matched": comparison.matched,
        "field_matches": comparison.field_matches,
        "artifact_matches": comparison.artifact_matches,
    }


def _comparison_id_fields(comparison: ReplayComparison) -> dict[str, str]:
    fields = {
        "source_eval_attempt_id": comparison.source_eval_attempt_id,
        "source_scorer_attempt_id": comparison.source_scorer_attempt_id,
        "replayed_scorer_attempt_id": comparison.replayed_scorer_attempt_id,
        "source_agent_attempt_id": comparison.source_agent_attempt_id,
        "replayed_agent_attempt_id": comparison.replayed_agent_attempt_id,
    }
    return {key: value for key, value in fields.items() if value is not None}


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
        return [_normalize_json_value(item, repo_roots=repo_roots) for item in value]
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
        "error_class": source_agent_result.error_class
        == replay_agent_result.error_class,
        "error_message": (
            source_agent_result.error_message == replay_agent_result.error_message
        ),
    }


def _attempt_status(attempt_result: AttemptResult | None) -> str | None:
    return attempt_result.status if attempt_result is not None else None


def _scorer_artifact_refs(source_manifest: ScorerAttemptManifest) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys((MANIFEST_FILENAME, *source_manifest.artifacts.values()))
    )


def _agent_artifact_refs(source_manifest: dict[str, object]) -> tuple[str, ...]:
    artifacts = source_manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("Agent replay source manifest is missing artifacts object")
    artifact_refs = [MANIFEST_FILENAME]
    for artifact_name, raw_ref in artifacts.items():
        if not isinstance(artifact_name, str):
            raise ValueError(
                "Agent replay source manifest has non-string artifact name"
            )
        if not isinstance(raw_ref, str) or not raw_ref:
            raise ValueError(
                f"Agent replay source manifest has invalid {artifact_name!r} ref"
            )
        artifact_ref = raw_ref.rstrip("/")
        if artifact_name == "attempt":
            artifact_refs.extend(
                f"{artifact_ref}/{nested_ref}"
                for nested_ref in SCORER_ATTEMPT_ARTIFACTS
            )
            continue
        artifact_refs.append(artifact_ref)
    return tuple(dict.fromkeys(artifact_refs))


def _source_agent_model_id(
    source_agent_dir: Path,
    source_manifest: dict[str, object],
) -> str:
    artifacts = source_manifest.get("artifacts")
    prompt_loop_ref = (
        artifacts.get("prompt_loop_result") if isinstance(artifacts, dict) else None
    )
    if not isinstance(prompt_loop_ref, str):
        return "agent-control-scripted-v0"
    prompt_loop_result = load_prompt_loop_result(
        resolve_relative_artifact_ref(source_agent_dir, prompt_loop_ref)
    )
    for response in prompt_loop_result.model_responses:
        if response.model_id:
            return response.model_id
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


def _source_manifest_provenance(
    replay_run_id: str,
    source_manifest: dict[str, object],
) -> dict[str, object]:
    provenance: dict[str, object] = {"replay_run_id": replay_run_id}
    eval_run_id = source_manifest.get("eval_run_id")
    if isinstance(eval_run_id, str):
        provenance["source_eval_run_id"] = eval_run_id
    source_agent_attempt_id = source_manifest.get("agent_attempt_id")
    if isinstance(source_agent_attempt_id, str):
        provenance["source_agent_attempt_id"] = source_agent_attempt_id
    return provenance


def _required_manifest_artifact_ref(
    manifest: dict[str, object],
    artifact_name: str,
) -> str:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("Replay source manifest is missing artifacts object")
    artifact_ref = artifacts.get(artifact_name)
    if not isinstance(artifact_ref, str) or not artifact_ref:
        raise ValueError(
            f"Agent attempt replay sources require {artifact_name!r} artifact evidence"
        )
    return artifact_ref


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
    return {
        **base_provenance,
        **{key: value for key, value in extra.items() if value is not None},
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
