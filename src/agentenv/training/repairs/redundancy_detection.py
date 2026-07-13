import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from agentenv.agents.schema import PromptLoopResult, ToolCallAction, parse_agent_action
from agentenv.agents.tool_messages import render_tool_result_message
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.payloads import load_prompt_loop_result
from agentenv.controls.public_check_idempotency_schema import (
    PublicCheckIdempotencyCalibration,
)
from agentenv.hashing import hash_file, hash_json
from agentenv.models.schema import Message
from agentenv.security.secrets import redact_secrets
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest
from agentenv.tools.hashing import hash_tool_input
from agentenv.tools.schema import (
    TOOL_REGISTRY,
    RunTestsInput,
    ToolInput,
    ToolName,
    ToolResult,
    validate_tool_input,
)
from agentenv.training.candidates.schema import (
    MechanicalRedundancyAssessment,
    MechanicallyRedundantToolCallBlock,
)
from agentenv.trajectories.schema import TrajectoryRecord


MECHANICAL_REDUNDANCY_DETECTOR_VERSION = "mechanical_redundancy_detector_v0"


class MechanicalRedundancyEvidenceError(ValueError):
    pass


class MechanicalRedundancyArtifactIntegrityError(ValueError):
    pass


class MissingTrustedPublicCheckCalibration(MechanicalRedundancyEvidenceError):
    pass


class CalibratedPublicCheckRuntimeDrift(MechanicalRedundancyEvidenceError):
    pass


@dataclass(frozen=True)
class _ExecutedToolCall:
    tool_call_id: str
    tool_name: ToolName
    arguments_hash: str
    tool_input: ToolInput | None
    tool_result: ToolResult
    normalized_observation_hash: str


def compute_mechanical_redundancy_detector_code_hash() -> str:
    return hash_file(Path(__file__))


def assess_trajectory_mechanical_redundancy(
    trajectory: TrajectoryRecord,
    *,
    public_check_calibrations: Sequence[PublicCheckIdempotencyCalibration] = (),
) -> MechanicalRedundancyAssessment:
    try:
        prompt_loop_result = _load_trajectory_prompt_loop_result(trajectory)
        if prompt_loop_result is None:
            return _complete_assessment([])
        task_manifest_path = _external_path(
            trajectory.source_provenance.task_manifest_path
        )
        try:
            observed_task_manifest_hash = hash_file(task_manifest_path)
        except OSError as exc:
            raise MechanicalRedundancyArtifactIntegrityError(
                "Artifact hash validation failed for task-manifest evidence"
            ) from exc
        if (
            observed_task_manifest_hash
            != trajectory.source_provenance.task_manifest_hash
        ):
            raise MechanicalRedundancyArtifactIntegrityError(
                "Artifact hash mismatch for task-manifest evidence"
            )
        task_manifest = load_task_manifest(task_manifest_path)
        return assess_prompt_loop_mechanical_redundancy(
            prompt_loop_result,
            task_manifest=task_manifest,
            task_manifest_hash=observed_task_manifest_hash,
            public_check_calibrations=public_check_calibrations,
        )
    except MechanicalRedundancyArtifactIntegrityError:
        raise
    except Exception as exc:
        return _incomplete_assessment(exc)


def assess_prompt_loop_mechanical_redundancy(
    prompt_loop_result: PromptLoopResult,
    *,
    task_manifest: TaskManifest,
    task_manifest_hash: str,
    public_check_calibrations: Sequence[PublicCheckIdempotencyCalibration] = (),
) -> MechanicalRedundancyAssessment:
    try:
        if prompt_loop_result.task_id != task_manifest.id:
            raise MechanicalRedundancyEvidenceError(
                "prompt-loop task id does not match task manifest"
            )
        calls = _load_executed_tool_calls(prompt_loop_result)
        calibrations_by_identity = _index_public_check_calibrations(
            public_check_calibrations
        )
        blocks = _detect_redundant_blocks(
            calls,
            task_manifest=task_manifest,
            task_manifest_hash=task_manifest_hash,
            calibrations_by_identity=calibrations_by_identity,
        )
        return _complete_assessment(blocks)
    except Exception as exc:
        return _incomplete_assessment(exc)


def _load_trajectory_prompt_loop_result(
    trajectory: TrajectoryRecord,
) -> PromptLoopResult | None:
    artifact = trajectory.artifacts.prompt_loop_result_json
    if artifact is None:
        if trajectory.statuses.agent_task_run_status is not None:
            raise MechanicalRedundancyEvidenceError(
                "agent trajectory is missing prompt-loop result evidence"
            )
        return None
    if artifact.content_hash is None:
        raise MechanicalRedundancyArtifactIntegrityError(
            "prompt-loop result evidence is not hash-pinned"
        )
    eval_run_dir = _external_path(trajectory.artifacts.eval_run_path)
    artifact_path = resolve_relative_artifact_ref(eval_run_dir, artifact.path)
    try:
        observed_hash = hash_file(artifact_path)
    except OSError as exc:
        raise MechanicalRedundancyArtifactIntegrityError(
            "Artifact hash validation failed for prompt-loop evidence"
        ) from exc
    if observed_hash != artifact.content_hash:
        raise MechanicalRedundancyArtifactIntegrityError(
            "Artifact hash mismatch for prompt-loop evidence"
        )
    return load_prompt_loop_result(artifact_path)


def _load_executed_tool_calls(
    prompt_loop_result: PromptLoopResult,
) -> tuple[_ExecutedToolCall, ...]:
    assistant_messages_by_tool_call_id: dict[str, Message] = {}
    for message in prompt_loop_result.messages:
        if message.role != "assistant" or message.tool_call_id is None:
            continue
        if message.tool_call_id in assistant_messages_by_tool_call_id:
            raise MechanicalRedundancyEvidenceError(
                "prompt-loop transcript contains duplicate assistant tool-call ids"
            )
        assistant_messages_by_tool_call_id[message.tool_call_id] = message

    tool_messages = [
        message for message in prompt_loop_result.messages if message.role == "tool"
    ]
    if len(tool_messages) != len(prompt_loop_result.tool_results):
        raise MechanicalRedundancyEvidenceError(
            "prompt-loop tool messages do not align with tool results"
        )

    calls: list[_ExecutedToolCall] = []
    observed_tool_call_ids: set[str] = set()
    for tool_message, tool_result in zip(
        tool_messages,
        prompt_loop_result.tool_results,
        strict=True,
    ):
        tool_call_id = tool_message.tool_call_id
        if tool_call_id is None:
            raise MechanicalRedundancyEvidenceError(
                "executed tool message is missing tool-call id"
            )
        if tool_call_id in observed_tool_call_ids:
            raise MechanicalRedundancyEvidenceError(
                "prompt-loop transcript contains duplicate executed tool-call ids"
            )
        observed_tool_call_ids.add(tool_call_id)

        assistant_message = assistant_messages_by_tool_call_id.get(tool_call_id)
        if assistant_message is None:
            raise MechanicalRedundancyEvidenceError(
                "executed tool result has no matching assistant tool call"
            )
        try:
            action = parse_agent_action(assistant_message.content)
        except (ValidationError, ValueError) as exc:
            raise MechanicalRedundancyEvidenceError(
                "executed assistant tool call is malformed"
            ) from exc
        if not isinstance(action, ToolCallAction):
            raise MechanicalRedundancyEvidenceError(
                "executed tool result maps to a non-tool assistant action"
            )
        if action.tool_name != tool_result.tool_name:
            raise MechanicalRedundancyEvidenceError(
                "assistant tool name does not match tool result"
            )
        if tool_result.status == "ok" and tool_result.tool_name not in TOOL_REGISTRY:
            raise MechanicalRedundancyEvidenceError(
                "successful tool evidence uses an unknown tool name"
            )

        expected_tool_message = render_tool_result_message(tool_result, tool_call_id)
        if (
            tool_message.name != expected_tool_message.name
            or tool_message.content != expected_tool_message.content
            or tool_message.metadata != expected_tool_message.metadata
        ):
            raise MechanicalRedundancyEvidenceError(
                "model-visible tool message does not match tool result"
            )
        if tool_message.metadata.get("arguments_hash") != tool_result.arguments_hash:
            raise MechanicalRedundancyEvidenceError(
                "tool-message argument hash does not match tool result"
            )

        tool_input: ToolInput | None = None
        if tool_result.status == "ok":
            try:
                tool_input = validate_tool_input(action.tool_name, action.arguments)
            except (ValidationError, ValueError) as exc:
                raise MechanicalRedundancyEvidenceError(
                    "successful tool result has invalid assistant arguments"
                ) from exc
            if hash_tool_input(tool_input) != tool_result.arguments_hash:
                raise MechanicalRedundancyEvidenceError(
                    "assistant tool arguments do not match tool-result hash"
                )

        calls.append(
            _ExecutedToolCall(
                tool_call_id=tool_call_id,
                tool_name=cast(ToolName, tool_result.tool_name),
                arguments_hash=tool_result.arguments_hash,
                tool_input=tool_input,
                tool_result=tool_result,
                normalized_observation_hash=_hash_model_visible_observation(
                    tool_message.content
                ),
            )
        )
    return tuple(calls)


def _detect_redundant_blocks(
    calls: Sequence[_ExecutedToolCall],
    *,
    task_manifest: TaskManifest,
    task_manifest_hash: str,
    calibrations_by_identity: dict[tuple[str, int], PublicCheckIdempotencyCalibration],
) -> list[MechanicallyRedundantToolCallBlock]:
    blocks: list[MechanicallyRedundantToolCallBlock] = []
    baseline_index = 0
    while baseline_index + 1 < len(calls):
        baseline = calls[baseline_index]
        repeated = calls[baseline_index + 1]
        if not _same_successful_call(baseline, repeated):
            baseline_index += 1
            continue

        public_check_index = _public_check_index_for_redundancy(
            baseline,
            task_manifest=task_manifest,
            task_manifest_hash=task_manifest_hash,
            calibrations_by_identity=calibrations_by_identity,
        )
        if baseline.tool_name == "run_tests" and public_check_index is None:
            baseline_index += 1
            continue

        if not _repeated_observation_is_stable(baseline, repeated):
            if baseline.tool_name == "run_tests":
                raise CalibratedPublicCheckRuntimeDrift(
                    "repeated calibrated public check changed workspace or observation"
                )
            baseline_index += 1
            continue

        redundant_calls = [repeated]
        next_index = baseline_index + 2
        while next_index < len(calls):
            candidate = calls[next_index]
            if not _same_successful_call(baseline, candidate):
                break
            if not _repeated_observation_is_stable(baseline, candidate):
                if baseline.tool_name == "run_tests":
                    raise CalibratedPublicCheckRuntimeDrift(
                        "repeated calibrated public check changed workspace or observation"
                    )
                break
            redundant_calls.append(candidate)
            next_index += 1

        blocks.append(
            MechanicallyRedundantToolCallBlock(
                tool_name=baseline.tool_name,
                arguments_hash=baseline.arguments_hash,
                baseline_tool_call_id=baseline.tool_call_id,
                redundant_tool_call_ids=[call.tool_call_id for call in redundant_calls],
                redundant_call_count=len(redundant_calls),
                stable_workspace_hash=(
                    baseline.tool_result.canonical_workspace_hash_after
                ),
                normalized_observation_hash=(baseline.normalized_observation_hash),
                public_check_index=public_check_index,
            )
        )
        baseline_index = next_index
    return blocks


def _same_successful_call(
    baseline: _ExecutedToolCall,
    candidate: _ExecutedToolCall,
) -> bool:
    if baseline.tool_result.status != "ok" or candidate.tool_result.status != "ok":
        return False
    if baseline.tool_input is None or candidate.tool_input is None:
        return False
    return (
        baseline.tool_name == candidate.tool_name
        and baseline.arguments_hash == candidate.arguments_hash
        and baseline.tool_input.model_dump(mode="json")
        == candidate.tool_input.model_dump(mode="json")
    )


def _repeated_observation_is_stable(
    baseline: _ExecutedToolCall,
    candidate: _ExecutedToolCall,
) -> bool:
    stable_workspace_hash = baseline.tool_result.canonical_workspace_hash_after
    return (
        candidate.tool_result.canonical_workspace_hash_before == stable_workspace_hash
        and candidate.tool_result.canonical_workspace_hash_after
        == stable_workspace_hash
        and candidate.normalized_observation_hash
        == baseline.normalized_observation_hash
    )


def _public_check_index_for_redundancy(
    call: _ExecutedToolCall,
    *,
    task_manifest: TaskManifest,
    task_manifest_hash: str,
    calibrations_by_identity: dict[tuple[str, int], PublicCheckIdempotencyCalibration],
) -> int | None:
    if call.tool_name != "run_tests":
        return None
    if not isinstance(call.tool_input, RunTestsInput):
        raise MechanicalRedundancyEvidenceError(
            "successful run_tests call lacks validated run-tests input"
        )
    matching_indexes = [
        index
        for index, public_check in enumerate(task_manifest.public_checks)
        if public_check.command == call.tool_input.command
    ]
    if len(matching_indexes) != 1:
        raise MechanicalRedundancyEvidenceError(
            "run_tests command must identify exactly one task public check"
        )
    public_check_index = matching_indexes[0]
    public_check = task_manifest.public_checks[public_check_index]
    if not public_check.are_tests_idempotent:
        return None

    calibration = calibrations_by_identity.get((task_manifest.id, public_check_index))
    if calibration is None:
        raise MissingTrustedPublicCheckCalibration(
            "repeated run_tests call lacks trusted idempotency calibration"
        )
    if (
        calibration.status != "IDEMPOTENT"
        or calibration.task_manifest_hash != task_manifest_hash
        or calibration.command != public_check.command
    ):
        raise MissingTrustedPublicCheckCalibration(
            "run_tests idempotency calibration does not match task evidence"
        )
    if (
        call.tool_result.canonical_workspace_hash_before
        != call.tool_result.canonical_workspace_hash_after
    ):
        raise CalibratedPublicCheckRuntimeDrift(
            "calibrated public check mutated the model workspace"
        )
    return public_check_index


def _index_public_check_calibrations(
    calibrations: Sequence[PublicCheckIdempotencyCalibration],
) -> dict[tuple[str, int], PublicCheckIdempotencyCalibration]:
    indexed: dict[tuple[str, int], PublicCheckIdempotencyCalibration] = {}
    for calibration in calibrations:
        identity = (calibration.task_id, calibration.public_check_index)
        if identity in indexed:
            raise MechanicalRedundancyEvidenceError(
                "public-check calibrations contain duplicate identities"
            )
        indexed[identity] = calibration
    return indexed


def _hash_model_visible_observation(content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MechanicalRedundancyEvidenceError(
            "model-visible tool observation is not valid JSON"
        ) from exc
    return hash_json(payload)


def _complete_assessment(
    blocks: list[MechanicallyRedundantToolCallBlock],
) -> MechanicalRedundancyAssessment:
    return MechanicalRedundancyAssessment(
        detector_version=MECHANICAL_REDUNDANCY_DETECTOR_VERSION,
        detector_code_hash=compute_mechanical_redundancy_detector_code_hash(),
        evaluation_status="complete",
        blocks=blocks,
    )


def _incomplete_assessment(exc: Exception) -> MechanicalRedundancyAssessment:
    if isinstance(exc, MechanicalRedundancyEvidenceError):
        message = redact_secrets(str(exc)) or type(exc).__name__
    else:
        message = f"{type(exc).__name__} while evaluating redundancy evidence"
    return MechanicalRedundancyAssessment(
        detector_version=MECHANICAL_REDUNDANCY_DETECTOR_VERSION,
        detector_code_hash=compute_mechanical_redundancy_detector_code_hash(),
        evaluation_status="incomplete",
        blocks=[],
        error_class=type(exc).__name__,
        error_message=message[:1000],
    )


def _external_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()
