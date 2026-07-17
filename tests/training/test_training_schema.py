from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.agents.prompts import AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION
from agentenv.training.candidates.schema import (
    TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION,
    MechanicalRedundancyAssessment,
    MechanicallyRedundantToolCallBlock,
    TrainingCandidateRecord,
    TrainingCandidateContentEligibility,
)
from agentenv.training.positive_sft.identity import build_positive_sft_example_id
from agentenv.training.positive_sft.schema import (
    POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION,
    PositiveSFTExampleRecord,
    PositiveSFTMessage,
    PositiveSFTTaskInput,
)


def _eligibility_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "analysis_eligible": True,
        "analysis_reason": "trajectory is available for analysis",
        "positive_sft_review_eligible": True,
        "positive_sft_review_reason": "accepted successful agent trajectory",
        "negative_example_eligible": False,
        "negative_example_reason": "trajectory succeeded",
        "preference_pairing_eligible": True,
        "preference_pairing_reason": "accepted gradable trajectory",
    }
    payload.update(updates)
    return payload


def _candidate_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "training_candidate_record_v0",
        "trajectory_id": "trajectory_001",
        "eval_attempt_id": "eval_attempt_001",
        "task_id": "repair_jsonl_deduper",
        "policy_id": "agent-happy",
        "review_status": "reviewed",
        "review_id": "review_001",
        "reviewer_id": "kshitij",
        "review_decision": "accepted",
        "mechanical_redundancy_assessment": _mechanical_assessment_payload(),
        "content_eligibility": _eligibility_payload(),
    }
    payload.update(updates)
    return payload


def _mechanical_assessment_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "detector_version": "mechanical_redundancy_detector_v0",
        "detector_code_hash": "xxh64:aaaaaaaaaaaaaaaa",
        "evaluation_status": "complete",
        "blocks": [],
        "error_class": None,
        "error_message": None,
    }
    payload.update(updates)
    return payload


def _redundant_block_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "tool_name": "read_file",
        "arguments_hash": "xxh64:bbbbbbbbbbbbbbbb",
        "baseline_tool_call_id": "tool_call_0001",
        "redundant_tool_call_ids": ["tool_call_0002", "tool_call_0003"],
        "redundant_call_count": 2,
        "stable_workspace_hash": "xxh64:cccccccccccccccc",
        "normalized_observation_hash": "xxh64:dddddddddddddddd",
        "public_check_index": None,
    }
    payload.update(updates)
    return payload


def _positive_sft_task_input_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "task_id": "repair_jsonl_deduper",
        "instruction": "Fix the JSONL deduper.",
        "allowed_tools": ["list_files", "read_file", "write_file", "run_tests"],
        "public_checks": ["uv run pytest tests/test_public.py"],
        "max_turns": 8,
        "timeout_seconds": 30,
        "network": "off",
    }
    payload.update(updates)
    return payload


def _positive_sft_messages_payload() -> list[dict[str, object]]:
    return [
        {
            "message_id": "message_00000000000000000000000000000001",
            "role": "system",
            "content": "Historical persisted system prompt.",
            "name": "agentenv",
        },
        {
            "message_id": "message_00000000000000000000000000000002",
            "role": "user",
            "content": "Historical persisted task prompt.",
            "name": "task_view",
        },
        {
            "message_id": "message_00000000000000000000000000000003",
            "role": "assistant",
            "content": (
                '{"action":"tool_call","tool_name":"run_tests","arguments":'
                '{"command":"uv run pytest tests/test_public.py"}}'
            ),
        },
        {
            "message_id": "message_00000000000000000000000000000004",
            "role": "tool",
            "content": '{"status":"ok","output":"1 passed"}',
            "name": "run_tests",
            "tool_call_id": "tool_call_0001",
        },
        {
            "message_id": "message_00000000000000000000000000000005",
            "role": "assistant",
            "content": '{"action":"final_answer","text":"done"}',
        },
    ]


def _original_positive_sft_source_payload() -> dict[str, object]:
    return {
        "source_type": "original",
        "source_training_candidate_record_hash": "xxh64:1111111111111111",
        "source_artifact_ref": {
            "path": "agent/attempt_001/prompt_loop_result.json",
            "content_hash": "xxh64:2222222222222222",
        },
        "task_outcome_provenance": "executed_source_trajectory",
    }


def _repaired_positive_sft_source_payload() -> dict[str, object]:
    return {
        "source_type": "repaired",
        "source_training_candidate_record_hash": "xxh64:1111111111111111",
        "source_artifact_ref": {
            "path": "transcripts/repair_001.json",
            "content_hash": "xxh64:3333333333333333",
        },
        "repair_id": "repair_001",
        "source_training_candidate_repair_record_hash": ("xxh64:4444444444444444"),
        "source_training_candidate_repair_review_record_hash": (
            "xxh64:5555555555555555"
        ),
        "repair_review_id": "repair_review_001",
        "task_outcome_provenance": "inherited_from_source_trajectory",
        "task_outcome_inheritance_basis": (
            "mechanical_redundancy_state_and_observation_preserving_deletion"
        ),
    }


def _positive_sft_example_id(source: dict[str, object]) -> str:
    artifact_ref = source["source_artifact_ref"]
    assert isinstance(artifact_ref, dict)
    content_hash = artifact_ref["content_hash"]
    assert isinstance(content_hash, str)
    source_type = source["source_type"]
    candidate_hash = source["source_training_candidate_record_hash"]
    assert isinstance(source_type, str)
    assert isinstance(candidate_hash, str)
    repair_record_hash = source.get("source_training_candidate_repair_record_hash")
    assert repair_record_hash is None or isinstance(repair_record_hash, str)
    return build_positive_sft_example_id(
        source_type=source_type,
        source_training_candidate_record_hash=candidate_hash,
        source_artifact_content_hash=content_hash,
        source_positive_sft_review_record_hash="xxh64:6666666666666666",
        source_training_candidate_repair_record_hash=repair_record_hash,
    )


def _positive_sft_payload(**updates: Any) -> dict[str, Any]:
    task_input = PositiveSFTTaskInput.model_validate(_positive_sft_task_input_payload())
    source_provenance = _original_positive_sft_source_payload()
    payload = {
        "schema_version": "positive_sft_example_record_v0",
        "example_id": _positive_sft_example_id(source_provenance),
        "provenance_ids": {
            "trajectory_id": "trajectory_001",
            "eval_suite_id": "eval_suite_001",
            "eval_run_id": "eval_run_001",
            "eval_attempt_id": "eval_attempt_001",
            "agent_attempt_id": "agent_attempt_001",
            "task_id": "repair_jsonl_deduper",
            "policy_id": "local-qwen-dev",
        },
        "prompt_provenance": {
            "prompt_builder_version": AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION,
            "prompt_builder_code_hash": "xxh64:promptbuilder",
        },
        "review_provenance": {
            "source_positive_sft_review_record_hash": "xxh64:6666666666666666",
            "positive_sft_review_id": "positive_sft_review_001",
            "last_approved_assistant_message_id": (
                "message_00000000000000000000000000000005"
            ),
        },
        "source_provenance": source_provenance,
        "task_input": task_input.model_dump(mode="json"),
        "messages": _positive_sft_messages_payload(),
    }
    payload.update(updates)
    return payload


def test_training_candidate_record_accepts_reviewed_candidate() -> None:
    record = TrainingCandidateRecord.model_validate(_candidate_payload())

    assert record.schema_version == TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
    assert record.trajectory_id == "trajectory_001"
    assert record.review_id == "review_001"
    assert record.review_decision == "accepted"
    assert record.mechanical_redundancy_assessment.evaluation_status == "complete"
    assert record.mechanical_redundancy_assessment.blocks == []
    assert record.content_eligibility.has_objective_use_path
    assert not record.content_eligibility.is_analysis_only
    assert not record.content_eligibility.is_fully_ineligible


def test_mechanically_redundant_tool_call_block_accepts_ordered_source_ids() -> None:
    block = MechanicallyRedundantToolCallBlock.model_validate(
        _redundant_block_payload()
    )

    assert block.baseline_tool_call_id == "tool_call_0001"
    assert block.redundant_tool_call_ids == ["tool_call_0002", "tool_call_0003"]
    assert block.redundant_call_count == 2


def test_mechanically_redundant_tool_call_block_requires_exact_repeat_count() -> None:
    with pytest.raises(
        ValidationError,
        match="redundant_call_count must equal redundant_tool_call_ids length",
    ):
        MechanicallyRedundantToolCallBlock.model_validate(
            _redundant_block_payload(redundant_call_count=1)
        )


@pytest.mark.parametrize(
    ("tool_name", "public_check_index", "match"),
    [
        ("run_tests", None, "run_tests redundancy requires public_check_index"),
        ("read_file", 0, "public_check_index is only valid for run_tests"),
    ],
)
def test_mechanically_redundant_tool_call_block_scopes_public_check_index(
    tool_name: str,
    public_check_index: int | None,
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        MechanicallyRedundantToolCallBlock.model_validate(
            _redundant_block_payload(
                tool_name=tool_name,
                public_check_index=public_check_index,
            )
        )


def test_incomplete_mechanical_redundancy_assessment_requires_error() -> None:
    with pytest.raises(
        ValidationError,
        match="incomplete mechanical-redundancy assessments require errors",
    ):
        MechanicalRedundancyAssessment.model_validate(
            _mechanical_assessment_payload(evaluation_status="incomplete")
        )


def test_mechanical_redundancy_assessment_rejects_overlapping_blocks() -> None:
    with pytest.raises(
        ValidationError,
        match="mechanical-redundancy blocks cannot share tool-call ids",
    ):
        MechanicalRedundancyAssessment.model_validate(
            _mechanical_assessment_payload(
                blocks=[
                    _redundant_block_payload(),
                    _redundant_block_payload(
                        baseline_tool_call_id="tool_call_0003",
                        redundant_tool_call_ids=["tool_call_0004"],
                        redundant_call_count=1,
                    ),
                ]
            )
        )


def test_content_eligibility_exposes_analysis_only_utility() -> None:
    eligibility = TrainingCandidateContentEligibility.model_validate(
        _eligibility_payload(
            positive_sft_review_eligible=False,
            positive_sft_review_reason="not a positive SFT target",
            preference_pairing_eligible=False,
            preference_pairing_reason="not a preference candidate",
        )
    )

    assert not eligibility.has_objective_use_path
    assert eligibility.is_analysis_only
    assert not eligibility.is_fully_ineligible


def test_content_eligibility_exposes_fully_ineligible_utility() -> None:
    eligibility = TrainingCandidateContentEligibility.model_validate(
        _eligibility_payload(
            analysis_eligible=False,
            analysis_reason="source artifact failed validation",
            positive_sft_review_eligible=False,
            positive_sft_review_reason="source artifact failed validation",
            preference_pairing_eligible=False,
            preference_pairing_reason="source artifact failed validation",
        )
    )

    assert not eligibility.has_objective_use_path
    assert not eligibility.is_analysis_only
    assert eligibility.is_fully_ineligible


def test_training_candidate_rejects_objective_paths_without_accepted_review() -> None:
    payload = _candidate_payload(
        review_status="reviewed",
        review_decision="rejected",
    )

    with pytest.raises(
        ValidationError,
        match="candidates with an objective-use path require accepted human review",
    ):
        TrainingCandidateRecord.model_validate(payload)


def test_training_candidate_accepts_rejected_analysis_only_candidate() -> None:
    payload = _candidate_payload(
        review_decision="rejected",
        content_eligibility=_eligibility_payload(
            positive_sft_review_eligible=False,
            positive_sft_review_reason="human review rejected trajectory",
            negative_example_eligible=False,
            negative_example_reason="human review rejected trajectory",
            preference_pairing_eligible=False,
            preference_pairing_reason="human review rejected trajectory",
        ),
    )

    record = TrainingCandidateRecord.model_validate(payload)

    assert record.review_decision == "rejected"
    assert record.content_eligibility.is_analysis_only


def test_not_reviewed_candidate_cannot_include_review_details() -> None:
    payload = _candidate_payload(
        review_status="not_reviewed",
        review_id="review_001",
        reviewer_id=None,
        review_decision=None,
        content_eligibility=_eligibility_payload(
            positive_sft_review_eligible=False,
            positive_sft_review_reason="trajectory has not been reviewed",
            negative_example_eligible=False,
            negative_example_reason="trajectory has not been reviewed",
            preference_pairing_eligible=False,
            preference_pairing_reason="trajectory has not been reviewed",
        ),
    )

    with pytest.raises(
        ValidationError,
        match="not_reviewed training candidates cannot include review details",
    ):
        TrainingCandidateRecord.model_validate(payload)


def test_reviewed_candidate_requires_review_decision() -> None:
    payload = _candidate_payload(review_decision=None)

    with pytest.raises(
        ValidationError,
        match="reviewed training candidates require review_decision",
    ):
        TrainingCandidateRecord.model_validate(payload)


def test_training_candidate_rejects_extra_fields() -> None:
    payload = _candidate_payload(embedded_trajectory={"unexpected": True})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TrainingCandidateRecord.model_validate(payload)


def test_content_eligibility_requires_path_reasons() -> None:
    payload = _eligibility_payload(positive_sft_review_reason="")

    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        TrainingCandidateContentEligibility.model_validate(payload)


def test_positive_sft_example_record_accepts_model_visible_row() -> None:
    record = PositiveSFTExampleRecord.model_validate(_positive_sft_payload())

    assert record.schema_version == POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
    assert record.example_id.startswith("positive_sft_example_")
    assert record.provenance_ids.trajectory_id == "trajectory_001"
    assert record.provenance_ids.task_id == record.task_input.task_id
    assert (
        record.prompt_provenance.prompt_builder_version
        == AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION
    )
    assert record.prompt_provenance.prompt_builder_code_hash == "xxh64:promptbuilder"
    assert [message.role for message in record.messages[:2]] == ["system", "user"]
    assert any(message.role == "assistant" for message in record.messages)


def test_positive_sft_example_accepts_exact_repaired_source() -> None:
    source_provenance = _repaired_positive_sft_source_payload()
    record = PositiveSFTExampleRecord.model_validate(
        _positive_sft_payload(
            source_provenance=source_provenance,
            example_id=_positive_sft_example_id(source_provenance),
        )
    )

    assert record.source_provenance.source_type == "repaired"
    assert record.source_provenance.repair_id == "repair_001"
    assert (
        record.source_provenance.task_outcome_inheritance_basis
        == "mechanical_redundancy_state_and_observation_preserving_deletion"
    )


def test_positive_sft_example_id_distinguishes_selected_source() -> None:
    original = _original_positive_sft_source_payload()
    repaired = _repaired_positive_sft_source_payload()

    assert _positive_sft_example_id(original) != _positive_sft_example_id(repaired)


def test_positive_sft_source_artifact_must_be_hash_pinned() -> None:
    source_provenance = _original_positive_sft_source_payload()
    artifact_ref = source_provenance["source_artifact_ref"]
    assert isinstance(artifact_ref, dict)
    artifact_ref["content_hash"] = None

    with pytest.raises(
        ValidationError,
        match="positive SFT source artifact must be content-hash pinned",
    ):
        PositiveSFTExampleRecord.model_validate(
            _positive_sft_payload(source_provenance=source_provenance)
        )


def test_positive_sft_task_input_rejects_workspace_path() -> None:
    payload = _positive_sft_task_input_payload(workspace_path="/tmp/workspace")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PositiveSFTTaskInput.model_validate(payload)


def test_positive_sft_message_rejects_metadata() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PositiveSFTMessage.model_validate(
            {
                "message_id": "message_00000000000000000000000000000006",
                "role": "assistant",
                "content": '{"action":"final_answer","text":"done"}',
                "metadata": {"source": "private"},
            }
        )


def test_positive_sft_tool_message_requires_name_and_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="tool messages require name"):
        PositiveSFTMessage.model_validate(
            {
                "message_id": "message_00000000000000000000000000000007",
                "role": "tool",
                "content": '{"status":"ok"}',
                "tool_call_id": "tool_call_0001",
            }
        )

    with pytest.raises(ValidationError, match="tool messages require tool_call_id"):
        PositiveSFTMessage.model_validate(
            {
                "message_id": "message_00000000000000000000000000000008",
                "role": "tool",
                "content": '{"status":"ok"}',
                "name": "run_tests",
            }
        )


def test_positive_sft_system_and_user_messages_reject_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="system messages cannot include"):
        PositiveSFTMessage.model_validate(
            {
                "message_id": "message_00000000000000000000000000000009",
                "role": "system",
                "content": "Use JSON actions.",
                "tool_call_id": "tool_call_0001",
            }
        )

    with pytest.raises(ValidationError, match="user messages cannot include"):
        PositiveSFTMessage.model_validate(
            {
                "message_id": "message_0000000000000000000000000000000a",
                "role": "user",
                "content": "Fix the task.",
                "tool_call_id": "tool_call_0001",
            }
        )


def test_positive_sft_assistant_message_can_include_tool_call_id() -> None:
    message = PositiveSFTMessage.model_validate(
        {
            "message_id": "message_0000000000000000000000000000000b",
            "role": "assistant",
            "content": '{"action":"tool_call","tool_name":"run_tests"}',
            "tool_call_id": "tool_call_0001",
        }
    )

    assert message.tool_call_id == "tool_call_0001"


def test_positive_sft_example_rejects_wrong_example_id() -> None:
    payload = _positive_sft_payload(example_id="positive_sft_example_wrong")

    with pytest.raises(
        ValidationError,
        match="positive SFT example_id must be derived from its selected source",
    ):
        PositiveSFTExampleRecord.model_validate(payload)


def test_positive_sft_example_rejects_task_id_mismatch() -> None:
    payload = _positive_sft_payload(
        task_input=_positive_sft_task_input_payload(task_id="other_task")
    )

    with pytest.raises(
        ValidationError,
        match="positive SFT provenance task_id must match task_input",
    ):
        PositiveSFTExampleRecord.model_validate(payload)


def test_positive_sft_example_requires_assistant_message() -> None:
    payload = _positive_sft_payload(
        messages=[
            {
                "message_id": "message_0000000000000000000000000000000c",
                "role": "system",
                "content": "Historical persisted system prompt.",
                "name": "agentenv",
            },
            {
                "message_id": "message_0000000000000000000000000000000d",
                "role": "user",
                "content": "Historical persisted task prompt.",
                "name": "task_view",
            },
        ]
    )

    with pytest.raises(
        ValidationError,
        match="positive SFT examples require an assistant message",
    ):
        PositiveSFTExampleRecord.model_validate(payload)


def test_positive_sft_example_requires_system_then_user_start() -> None:
    payload = _positive_sft_payload()
    payload["messages"][0] = {
        "message_id": "message_0000000000000000000000000000000e",
        "role": "user",
        "content": "Historical persisted task prompt.",
        "name": "task_view",
    }

    with pytest.raises(
        ValidationError,
        match="positive SFT messages must start with system and user messages",
    ):
        PositiveSFTExampleRecord.model_validate(payload)


def test_positive_sft_example_requires_prompt_provenance() -> None:
    payload = _positive_sft_payload()
    del payload["prompt_provenance"]

    with pytest.raises(ValidationError, match="prompt_provenance"):
        PositiveSFTExampleRecord.model_validate(payload)


def test_positive_sft_example_allows_historical_prompt_text() -> None:
    payload = _positive_sft_payload()
    payload["messages"][0]["content"] = "Historical system prompt v1."
    payload["messages"][1]["content"] = "Historical task prompt v1."

    record = PositiveSFTExampleRecord.model_validate(payload)

    assert record.messages[0].content == "Historical system prompt v1."
    assert record.messages[1].content == "Historical task prompt v1."


def test_positive_sft_example_rejects_review_or_scorer_fields() -> None:
    payload = _positive_sft_payload(review_id="review_001")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PositiveSFTExampleRecord.model_validate(payload)
