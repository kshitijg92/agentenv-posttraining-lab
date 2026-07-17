from pathlib import Path
from typing import Any

import pytest

from agentenv.agents.schema import PromptLoopResult, TokenUsage, ToolCallAction
from agentenv.agents.tool_messages import render_tool_result_message
from agentenv.hashing import hash_file
from agentenv.ids import new_message_id
from agentenv.models.schema import Message
from agentenv.tasks.validate import load_task_manifest
from agentenv.tools.hashing import hash_tool_input
from agentenv.tools.schema import ReadFileOutput, ToolResult, validate_tool_input
from agentenv.training.repairs.redundancy_detection import (
    assess_prompt_loop_mechanical_redundancy,
)
from agentenv.training.repairs.redundancy_repair import (
    MechanicalRedundancyRepairCannotComplete,
    build_training_candidate_repair_id,
    hash_training_candidate_record,
    repair_prompt_loop_mechanical_redundancy,
)
from agentenv.training.candidates.schema import TrainingCandidateRecord


TASK_MANIFEST_PATH = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TASK_MANIFEST = load_task_manifest(TASK_MANIFEST_PATH)
TASK_MANIFEST_HASH = hash_file(TASK_MANIFEST_PATH)


def test_deterministic_repair_removes_only_redundant_call_result_pairs() -> None:
    prompt_loop = _prompt_loop_result(read_count=3)
    original_assessment = _assess(prompt_loop)
    retained_message_ids = [
        message.message_id
        for message in prompt_loop.messages
        if message.tool_call_id not in {"tool_call_0002", "tool_call_0003"}
    ]

    result = repair_prompt_loop_mechanical_redundancy(
        prompt_loop,
        original_assessment=original_assessment,
        task_manifest=TASK_MANIFEST,
        task_manifest_hash=TASK_MANIFEST_HASH,
    )

    assert original_assessment.blocks[0].redundant_tool_call_ids == [
        "tool_call_0002",
        "tool_call_0003",
    ]
    assert result.after_repair_assessment.evaluation_status == "complete"
    assert result.after_repair_assessment.blocks == []
    assert [message.tool_call_id for message in result.transcript.root] == [
        None,
        None,
        "tool_call_0001",
        "tool_call_0001",
        None,
    ]
    assert [message.message_id for message in result.transcript.root] == (
        retained_message_ids
    )
    assert result.transcript.root[0] == prompt_loop.messages[0]
    assert result.transcript.root[1] == prompt_loop.messages[1]
    assert result.transcript.root[-1] == prompt_loop.messages[-1]


def test_deterministic_repair_retains_baseline_tool_evidence() -> None:
    prompt_loop = _prompt_loop_result(read_count=2)
    original_assessment = _assess(prompt_loop)

    result = repair_prompt_loop_mechanical_redundancy(
        prompt_loop,
        original_assessment=original_assessment,
        task_manifest=TASK_MANIFEST,
        task_manifest_hash=TASK_MANIFEST_HASH,
    )

    baseline_messages = [
        message
        for message in result.transcript.root
        if message.tool_call_id == "tool_call_0001"
    ]
    assert [message.role for message in baseline_messages] == ["assistant", "tool"]


def test_deterministic_repair_rejects_missing_redundant_tool_result() -> None:
    prompt_loop = _prompt_loop_result(read_count=2)
    original_assessment = _assess(prompt_loop)
    malformed = prompt_loop.model_copy(
        update={
            "messages": [
                message
                for message in prompt_loop.messages
                if not (
                    message.role == "tool" and message.tool_call_id == "tool_call_0002"
                )
            ]
        }
    )

    with pytest.raises(
        MechanicalRedundancyRepairCannotComplete,
        match="does not have exactly one call/result pair",
    ):
        repair_prompt_loop_mechanical_redundancy(
            malformed,
            original_assessment=original_assessment,
            task_manifest=TASK_MANIFEST,
            task_manifest_hash=TASK_MANIFEST_HASH,
        )


def test_deterministic_repair_rejects_non_adjacent_redundant_pair() -> None:
    prompt_loop = _prompt_loop_result(read_count=2)
    original_assessment = _assess(prompt_loop)
    messages = list(prompt_loop.messages)
    redundant_tool_result = messages.pop(5)
    messages.append(redundant_tool_result)
    malformed = prompt_loop.model_copy(update={"messages": messages})

    with pytest.raises(
        MechanicalRedundancyRepairCannotComplete,
        match="call/result messages are not adjacent",
    ):
        repair_prompt_loop_mechanical_redundancy(
            malformed,
            original_assessment=original_assessment,
            task_manifest=TASK_MANIFEST,
            task_manifest_hash=TASK_MANIFEST_HASH,
        )


def test_deterministic_repair_requires_detected_blocks() -> None:
    prompt_loop = _prompt_loop_result(read_count=1)
    assessment = _assess(prompt_loop)

    with pytest.raises(
        MechanicalRedundancyRepairCannotComplete,
        match="has no blocks",
    ):
        repair_prompt_loop_mechanical_redundancy(
            prompt_loop,
            original_assessment=assessment,
            task_manifest=TASK_MANIFEST,
            task_manifest_hash=TASK_MANIFEST_HASH,
        )


def test_candidate_record_hash_is_canonical_and_content_sensitive() -> None:
    candidate = TrainingCandidateRecord.model_validate(_candidate_payload())
    same_candidate = TrainingCandidateRecord.model_validate(
        dict(reversed(list(_candidate_payload().items())))
    )
    changed_candidate = candidate.model_copy(
        update={"reviewer_id": "different-reviewer"}
    )

    assert hash_training_candidate_record(candidate) == hash_training_candidate_record(
        same_candidate
    )
    assert hash_training_candidate_record(candidate) != hash_training_candidate_record(
        changed_candidate
    )


def test_repair_id_is_deterministic_and_source_specific() -> None:
    first = build_training_candidate_repair_id(
        source_training_candidate_record_hash="xxh64:1111111111111111",
        repairer_code_hash="xxh64:2222222222222222",
    )
    repeated = build_training_candidate_repair_id(
        source_training_candidate_record_hash="xxh64:1111111111111111",
        repairer_code_hash="xxh64:2222222222222222",
    )
    changed = build_training_candidate_repair_id(
        source_training_candidate_record_hash="xxh64:3333333333333333",
        repairer_code_hash="xxh64:2222222222222222",
    )

    assert first == repeated
    assert first != changed


def _prompt_loop_result(*, read_count: int) -> PromptLoopResult:
    messages = [
        Message(message_id=new_message_id(), role="system", content="system"),
        Message(message_id=new_message_id(), role="user", content="task"),
    ]
    tool_results: list[ToolResult] = []
    for index in range(1, read_count + 1):
        tool_call_id = f"tool_call_{index:04d}"
        action = ToolCallAction(
            action="tool_call",
            tool_name="read_file",
            arguments={"path": "src/mathlib.py"},
        )
        tool_input = validate_tool_input(action.tool_name, action.arguments)
        result = ToolResult(
            tool_name="read_file",
            arguments_hash=hash_tool_input(tool_input),
            canonical_workspace_hash_before="xxh64:workspace",
            canonical_workspace_hash_after="xxh64:workspace",
            status="ok",
            output=ReadFileOutput(content="same", bytes_read=4),
            duration_ms=1,
        )
        messages.append(
            Message(
                message_id=new_message_id(),
                role="assistant",
                content=action.model_dump_json(),
                tool_call_id=tool_call_id,
            )
        )
        messages.append(render_tool_result_message(result, tool_call_id))
        tool_results.append(result)
    messages.append(
        Message(
            message_id=new_message_id(),
            role="assistant",
            content='{"action":"final_answer","text":"done"}',
        )
    )
    return PromptLoopResult(
        task_id=TASK_MANIFEST.id,
        prompt_builder_version="test_prompt_v0",
        prompt_builder_code_hash="xxh64:prompt",
        status="completed",
        turns_executed=read_count + 1,
        duration_ms=0,
        token_usage=TokenUsage(),
        messages=messages,
        model_responses=[],
        tool_results=tool_results,
    )


def _assess(prompt_loop: PromptLoopResult):
    return assess_prompt_loop_mechanical_redundancy(
        prompt_loop,
        task_manifest=TASK_MANIFEST,
        task_manifest_hash=TASK_MANIFEST_HASH,
    )


def _candidate_payload() -> dict[str, Any]:
    prompt_loop = _prompt_loop_result(read_count=2)
    return {
        "trajectory_id": "trajectory_001",
        "eval_attempt_id": "eval_attempt_001",
        "task_id": TASK_MANIFEST.id,
        "policy_id": "local-model",
        "review_status": "reviewed",
        "review_id": "review_001",
        "reviewer_id": "reviewer",
        "review_decision": "accepted",
        "mechanical_redundancy_assessment": _assess(prompt_loop),
        "content_eligibility": {
            "analysis_eligible": True,
            "analysis_reason": "available",
            "positive_sft_review_eligible": True,
            "positive_sft_review_reason": "allowed",
            "negative_example_eligible": False,
            "negative_example_reason": "succeeded",
            "preference_pairing_eligible": True,
            "preference_pairing_reason": "gradable",
        },
    }
