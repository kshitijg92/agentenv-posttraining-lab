from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agentenv.agents.schema import PromptLoopResult
from agentenv.controls.public_check_idempotency_schema import (
    PublicCheckIdempotencyCalibration,
)
from agentenv.hashing import hash_file, hash_json
from agentenv.models.schema import Message
from agentenv.tasks.schema import TaskManifest
from agentenv.tools.schema import ToolResult
from agentenv.training.mechanical_redundancy import (
    assess_prompt_loop_mechanical_redundancy,
)
from agentenv.training.repair_schema import (
    RepairedTranscriptArtifact,
    TrainingCandidateRepairRecord,
)
from agentenv.training.schema import (
    MechanicalRedundancyAssessment,
    TrainingCandidateRecord,
)


MECHANICAL_REDUNDANCY_REPAIRER_VERSION = "mechanical_redundancy_deletion_repairer_v0"
MECHANICAL_REDUNDANCY_REPAIR_METHOD = "mechanical_redundancy_deletion"


class MechanicalRedundancyRepairCannotComplete(ValueError):
    pass


@dataclass(frozen=True)
class CompletedMechanicalRedundancyRepair:
    transcript: RepairedTranscriptArtifact
    after_repair_assessment: MechanicalRedundancyAssessment


def compute_mechanical_redundancy_repairer_code_hash() -> str:
    return hash_file(Path(__file__))


def hash_training_candidate_record(record: TrainingCandidateRecord) -> str:
    return hash_json(record.model_dump(mode="json"))


def hash_training_candidate_repair_record(
    record: TrainingCandidateRepairRecord,
) -> str:
    return hash_json(record.model_dump(mode="json"))


def build_training_candidate_repair_id(
    *,
    source_training_candidate_record_hash: str,
    repair_method: str = MECHANICAL_REDUNDANCY_REPAIR_METHOD,
    repairer_version: str = MECHANICAL_REDUNDANCY_REPAIRER_VERSION,
    repairer_code_hash: str | None = None,
) -> str:
    code_hash = (
        repairer_code_hash
        if repairer_code_hash is not None
        else compute_mechanical_redundancy_repairer_code_hash()
    )
    identity_hash = hash_json(
        {
            "source_training_candidate_record_hash": (
                source_training_candidate_record_hash
            ),
            "repair_method": repair_method,
            "repairer_version": repairer_version,
            "repairer_code_hash": code_hash,
        }
    )
    return f"training_candidate_repair_{identity_hash.removeprefix('xxh64:')}"


def repair_prompt_loop_mechanical_redundancy(
    prompt_loop_result: PromptLoopResult,
    *,
    original_assessment: MechanicalRedundancyAssessment,
    task_manifest: TaskManifest,
    task_manifest_hash: str,
    public_check_calibrations: Sequence[PublicCheckIdempotencyCalibration] = (),
) -> CompletedMechanicalRedundancyRepair:
    _validate_original_assessment(original_assessment)
    redundant_ids = {
        tool_call_id
        for block in original_assessment.blocks
        for tool_call_id in block.redundant_tool_call_ids
    }
    baseline_ids = {block.baseline_tool_call_id for block in original_assessment.blocks}
    _validate_repair_message_pairs(
        prompt_loop_result.messages,
        redundant_ids=redundant_ids,
        baseline_ids=baseline_ids,
    )

    repaired_messages = [
        message
        for message in prompt_loop_result.messages
        if message.tool_call_id not in redundant_ids
    ]
    repaired_tool_results = _remove_redundant_tool_results(
        prompt_loop_result,
        redundant_ids=redundant_ids,
    )
    _validate_complete_tool_linkage(repaired_messages)

    repaired_prompt_loop_result = prompt_loop_result.model_copy(
        update={
            "messages": repaired_messages,
            "tool_results": repaired_tool_results,
        }
    )
    after_assessment = assess_prompt_loop_mechanical_redundancy(
        repaired_prompt_loop_result,
        task_manifest=task_manifest,
        task_manifest_hash=task_manifest_hash,
        public_check_calibrations=public_check_calibrations,
    )
    if after_assessment.evaluation_status != "complete":
        raise MechanicalRedundancyRepairCannotComplete(
            "after-repair mechanical-redundancy assessment is incomplete"
        )
    if after_assessment.blocks:
        raise MechanicalRedundancyRepairCannotComplete(
            "after-repair transcript still contains mechanical redundancy"
        )
    if (
        after_assessment.detector_version != original_assessment.detector_version
        or after_assessment.detector_code_hash != original_assessment.detector_code_hash
    ):
        raise MechanicalRedundancyRepairCannotComplete(
            "before- and after-repair assessments use different detectors"
        )

    return CompletedMechanicalRedundancyRepair(
        transcript=RepairedTranscriptArtifact.model_validate(repaired_messages),
        after_repair_assessment=after_assessment,
    )


def _validate_original_assessment(
    assessment: MechanicalRedundancyAssessment,
) -> None:
    if assessment.evaluation_status != "complete":
        raise MechanicalRedundancyRepairCannotComplete(
            "original mechanical-redundancy assessment is incomplete"
        )
    if not assessment.blocks:
        raise MechanicalRedundancyRepairCannotComplete(
            "original mechanical-redundancy assessment has no blocks"
        )


def _validate_repair_message_pairs(
    messages: Sequence[Message],
    *,
    redundant_ids: set[str],
    baseline_ids: set[str],
) -> None:
    indexes_by_id: dict[str, list[tuple[int, str]]] = {
        tool_call_id: [] for tool_call_id in redundant_ids | baseline_ids
    }
    for index, message in enumerate(messages):
        if message.tool_call_id in indexes_by_id:
            indexes_by_id[message.tool_call_id].append((index, message.role))

    for tool_call_id, indexed_roles in indexes_by_id.items():
        if len(indexed_roles) != 2:
            raise MechanicalRedundancyRepairCannotComplete(
                f"tool call {tool_call_id} does not have exactly one call/result pair"
            )
        (assistant_index, assistant_role), (tool_index, tool_role) = indexed_roles
        if assistant_role != "assistant" or tool_role != "tool":
            raise MechanicalRedundancyRepairCannotComplete(
                f"tool call {tool_call_id} has invalid call/result roles"
            )
        if tool_index != assistant_index + 1:
            raise MechanicalRedundancyRepairCannotComplete(
                f"tool call {tool_call_id} call/result messages are not adjacent"
            )


def _remove_redundant_tool_results(
    prompt_loop_result: PromptLoopResult,
    *,
    redundant_ids: set[str],
) -> list[ToolResult]:
    tool_messages = [
        message for message in prompt_loop_result.messages if message.role == "tool"
    ]
    if len(tool_messages) != len(prompt_loop_result.tool_results):
        raise MechanicalRedundancyRepairCannotComplete(
            "tool messages do not align with tool results"
        )
    return [
        tool_result
        for message, tool_result in zip(
            tool_messages,
            prompt_loop_result.tool_results,
            strict=True,
        )
        if message.tool_call_id not in redundant_ids
    ]


def _validate_complete_tool_linkage(messages: Sequence[Message]) -> None:
    assistant_ids = [
        message.tool_call_id
        for message in messages
        if message.role == "assistant" and message.tool_call_id is not None
    ]
    tool_ids = [message.tool_call_id for message in messages if message.role == "tool"]
    if Counter(assistant_ids) != Counter(tool_ids):
        raise MechanicalRedundancyRepairCannotComplete(
            "repaired transcript contains unmatched tool call/result messages"
        )
