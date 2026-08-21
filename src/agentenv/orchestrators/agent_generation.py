from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from agentenv.agents.schema import AgentTaskView, PromptLoopResult
from agentenv.artifacts import ArtifactType
from agentenv.artifacts.base import load_json_object, resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    AGENT_GENERATION_ARTIFACT_REFS,
    AGENT_GENERATION_ARTIFACT_SCHEMA_VERSION,
    AGENT_GENERATION_MANIFEST_FILENAME,
    AgentGenerationManifest,
    EvalAttemptReference,
    load_agent_generation_manifest,
)
from agentenv.artifacts.payloads import (
    DecodingConfigProvenance,
    ModelConfigProvenance,
    load_decoding_config_provenance,
    load_model_config_provenance,
    load_prompt_loop_result,
)
from agentenv.hashing import hash_file
from agentenv.runners.diff_runner import hash_diff
from agentenv.security.secrets import redact_jsonable


@dataclass(frozen=True)
class ValidatedAgentGeneration:
    manifest_path: Path
    manifest: AgentGenerationManifest
    agent_task_view: AgentTaskView
    prompt_loop_result: PromptLoopResult
    model_config_provenance: ModelConfigProvenance
    decoding_config_provenance: DecodingConfigProvenance
    candidate_patch: str | None


def write_agent_generation_artifact(
    out_dir: Path,
    *,
    agent_attempt_id: str,
    task_manifest_path: Path,
    agent_task_view: AgentTaskView,
    prompt_loop_result: PromptLoopResult,
    candidate_patch: str | None,
    started_at: str,
    ended_at: str,
    duration_ms: int,
    eval_attempt: EvalAttemptReference,
    model_config_provenance: ModelConfigProvenance,
    decoding_config_provenance: DecodingConfigProvenance,
) -> Path:
    """Publish terminal model-generation evidence before downstream scoring."""

    out_dir = out_dir.resolve()
    if not out_dir.is_dir():
        raise ValueError(f"Agent attempt output directory does not exist: {out_dir}")
    if agent_task_view.task_id != prompt_loop_result.task_id:
        raise ValueError("Agent task view and prompt-loop result task ids differ")
    if prompt_loop_result.status == "completed":
        if candidate_patch is None:
            raise ValueError("Completed agent generation requires a candidate patch")
    elif candidate_patch is not None:
        raise ValueError("Failed agent generation cannot include a candidate patch")

    artifact_payloads = {
        "agent_task_view": agent_task_view,
        "prompt_loop_result": prompt_loop_result,
        "decoding_config": decoding_config_provenance,
        "model_config": model_config_provenance,
    }
    artifacts = {
        name: AGENT_GENERATION_ARTIFACT_REFS[name]
        for name in artifact_payloads
    }
    for name, payload in artifact_payloads.items():
        artifact_path = out_dir / artifacts[name]
        _require_absent(artifact_path)
        artifact_path.write_text(_model_json(payload))

    if candidate_patch is not None:
        candidate_ref = AGENT_GENERATION_ARTIFACT_REFS["candidate_patch"]
        candidate_path = out_dir / candidate_ref
        _require_absent(candidate_path)
        candidate_path.write_text(candidate_patch)
        artifacts["candidate_patch"] = candidate_ref

    artifact_hashes = {
        name: hash_file(out_dir / artifact_ref)
        for name, artifact_ref in artifacts.items()
    }
    manifest = AgentGenerationManifest(
        artifact_type=ArtifactType.AGENT_GENERATION,
        artifact_schema_version=AGENT_GENERATION_ARTIFACT_SCHEMA_VERSION,
        agent_attempt_id=agent_attempt_id,
        task_id=agent_task_view.task_id,
        task_manifest_path=str(task_manifest_path.resolve()),
        eval_attempt=eval_attempt,
        prompt_loop_status=prompt_loop_result.status,
        candidate_patch_hash=(
            hash_diff(candidate_patch) if candidate_patch is not None else None
        ),
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        artifacts=artifacts,
        artifact_hashes=artifact_hashes,
    )
    manifest_path = out_dir / AGENT_GENERATION_MANIFEST_FILENAME
    temporary_path = out_dir / f".{AGENT_GENERATION_MANIFEST_FILENAME}.tmp"
    _require_absent(manifest_path)
    temporary_path.write_text(_model_json(manifest))
    temporary_path.replace(manifest_path)

    validated = load_validated_agent_generation(manifest_path)
    if validated.manifest != manifest:
        raise ValueError("Persisted agent generation failed exact readback")
    return manifest_path


def load_validated_agent_generation(
    manifest_path: Path,
) -> ValidatedAgentGeneration:
    manifest_path = manifest_path.resolve()
    manifest = load_agent_generation_manifest(manifest_path)
    root = manifest_path.parent
    for artifact_name, artifact_ref in manifest.artifacts.items():
        artifact_path = resolve_relative_artifact_ref(root, artifact_ref)
        if not artifact_path.is_file():
            raise ValueError(
                "Agent generation artifact is missing for "
                f"{artifact_name!r}: {artifact_path}"
            )
        observed_hash = hash_file(artifact_path)
        expected_hash = manifest.artifact_hashes[artifact_name]
        if observed_hash != expected_hash:
            raise ValueError(
                "Agent generation artifact hash mismatch for "
                f"{artifact_name!r}: {observed_hash!r} != {expected_hash!r}"
            )

    agent_task_view = AgentTaskView.model_validate(
        load_json_object(
            resolve_relative_artifact_ref(
                root,
                manifest.artifacts["agent_task_view"],
            )
        )
    )
    prompt_loop_result = load_prompt_loop_result(
        resolve_relative_artifact_ref(
            root,
            manifest.artifacts["prompt_loop_result"],
        )
    )
    model_config_provenance = load_model_config_provenance(
        resolve_relative_artifact_ref(
            root,
            manifest.artifacts["model_config"],
        )
    )
    decoding_config_provenance = load_decoding_config_provenance(
        resolve_relative_artifact_ref(
            root,
            manifest.artifacts["decoding_config"],
        )
    )
    candidate_patch = _load_candidate_patch(root, manifest)

    if agent_task_view.task_id != manifest.task_id:
        raise ValueError("Agent generation task view does not match manifest task id")
    if prompt_loop_result.task_id != manifest.task_id:
        raise ValueError("Agent generation prompt result does not match manifest task id")
    if prompt_loop_result.status != manifest.prompt_loop_status:
        raise ValueError("Agent generation prompt status does not match manifest")

    return ValidatedAgentGeneration(
        manifest_path=manifest_path,
        manifest=manifest,
        agent_task_view=agent_task_view,
        prompt_loop_result=prompt_loop_result,
        model_config_provenance=model_config_provenance,
        decoding_config_provenance=decoding_config_provenance,
        candidate_patch=candidate_patch,
    )


def validate_agent_generation_for_eval_attempt(
    manifest_path: Path,
    *,
    expected_eval_attempt: EvalAttemptReference,
    expected_agent_attempt_id: str,
    expected_task_id: str,
    expected_task_manifest_path: Path,
    expected_prompt_loop_status: str,
    expected_candidate_patch_hash: str | None,
    expected_model_config_provenance: ModelConfigProvenance,
    expected_decoding_config_provenance: DecodingConfigProvenance,
) -> ValidatedAgentGeneration:
    generation = load_validated_agent_generation(manifest_path)
    compared_fields = (
        ("declared eval attempt", generation.manifest.eval_attempt, expected_eval_attempt),
        (
            "agent attempt id",
            generation.manifest.agent_attempt_id,
            expected_agent_attempt_id,
        ),
        ("task id", generation.manifest.task_id, expected_task_id),
        (
            "task manifest path",
            Path(generation.manifest.task_manifest_path).resolve(),
            expected_task_manifest_path.resolve(),
        ),
        (
            "prompt-loop status",
            generation.manifest.prompt_loop_status,
            expected_prompt_loop_status,
        ),
        (
            "candidate patch hash",
            generation.manifest.candidate_patch_hash,
            expected_candidate_patch_hash,
        ),
        (
            "model config provenance",
            generation.model_config_provenance,
            expected_model_config_provenance,
        ),
        (
            "decoding config provenance",
            generation.decoding_config_provenance,
            expected_decoding_config_provenance,
        ),
    )
    for field_name, observed, expected in compared_fields:
        if observed != expected:
            raise ValueError(
                f"Agent generation {field_name} does not match its eval attempt"
            )
    return generation


def _load_candidate_patch(
    root: Path,
    manifest: AgentGenerationManifest,
) -> str | None:
    candidate_ref = manifest.artifacts.get("candidate_patch")
    if candidate_ref is None:
        return None
    candidate_patch = resolve_relative_artifact_ref(root, candidate_ref).read_text()
    if hash_diff(candidate_patch) != manifest.candidate_patch_hash:
        raise ValueError("Agent generation candidate patch hash mismatch")
    return candidate_patch


def _model_json(value: BaseModel) -> str:
    payload = value.model_dump(mode="json")
    return json.dumps(redact_jsonable(payload), indent=2, sort_keys=True) + "\n"


def _require_absent(path: Path) -> None:
    if path.exists():
        raise ValueError(f"Refusing to overwrite agent generation artifact: {path}")
