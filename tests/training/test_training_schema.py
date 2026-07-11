from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.agents.prompts import AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION
from agentenv.training.schema import (
    POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION,
    TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION,
    PositiveSFTExampleRecord,
    PositiveSFTMessage,
    PositiveSFTTaskInput,
    TrainingCandidateRecord,
    TrainingEligibility,
    build_positive_sft_example_id,
)


def _eligibility_payload(**updates: Any) -> dict[str, Any]:
    payload = {
        "analysis_allowed": True,
        "analysis_reason": "trajectory is available for analysis",
        "positive_sft_allowed": True,
        "positive_sft_reason": "accepted successful agent trajectory",
        "negative_example_allowed": False,
        "negative_example_reason": "trajectory succeeded",
        "preference_data_allowed": True,
        "preference_data_reason": "accepted gradable trajectory",
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
        "training_eligibility": _eligibility_payload(),
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
            "role": "system",
            "content": "Historical persisted system prompt.",
            "name": "agentenv",
        },
        {
            "role": "user",
            "content": "Historical persisted task prompt.",
            "name": "task_view",
        },
        {
            "role": "assistant",
            "content": (
                '{"action":"tool_call","tool_name":"run_tests","arguments":'
                '{"command":"uv run pytest tests/test_public.py"}}'
            ),
        },
        {
            "role": "tool",
            "content": '{"status":"ok","output":"1 passed"}',
            "name": "run_tests",
            "tool_call_id": "tool_call_0001",
        },
        {
            "role": "assistant",
            "content": '{"action":"final_answer","text":"done"}',
        },
    ]


def _positive_sft_payload(**updates: Any) -> dict[str, Any]:
    task_input = PositiveSFTTaskInput.model_validate(_positive_sft_task_input_payload())
    payload = {
        "schema_version": "positive_sft_example_record_v0",
        "example_id": build_positive_sft_example_id("trajectory_001"),
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
    assert record.training_eligibility.is_trainable
    assert not record.training_eligibility.is_analysis_only
    assert not record.training_eligibility.is_not_trainable


def test_training_eligibility_exposes_analysis_only_utility() -> None:
    eligibility = TrainingEligibility.model_validate(
        _eligibility_payload(
            positive_sft_allowed=False,
            positive_sft_reason="not a positive SFT target",
            preference_data_allowed=False,
            preference_data_reason="not a preference candidate",
        )
    )

    assert not eligibility.is_trainable
    assert eligibility.is_analysis_only
    assert not eligibility.is_not_trainable


def test_training_eligibility_exposes_not_trainable_utility() -> None:
    eligibility = TrainingEligibility.model_validate(
        _eligibility_payload(
            analysis_allowed=False,
            analysis_reason="source artifact failed validation",
            positive_sft_allowed=False,
            positive_sft_reason="source artifact failed validation",
            preference_data_allowed=False,
            preference_data_reason="source artifact failed validation",
        )
    )

    assert not eligibility.is_trainable
    assert not eligibility.is_analysis_only
    assert eligibility.is_not_trainable


def test_training_candidate_rejects_training_paths_without_accepted_review() -> None:
    payload = _candidate_payload(
        review_status="reviewed",
        review_decision="rejected",
    )

    with pytest.raises(
        ValidationError,
        match="training-eligible candidates require accepted human review",
    ):
        TrainingCandidateRecord.model_validate(payload)


def test_training_candidate_accepts_rejected_analysis_only_candidate() -> None:
    payload = _candidate_payload(
        review_decision="rejected",
        training_eligibility=_eligibility_payload(
            positive_sft_allowed=False,
            positive_sft_reason="human review rejected trajectory",
            negative_example_allowed=False,
            negative_example_reason="human review rejected trajectory",
            preference_data_allowed=False,
            preference_data_reason="human review rejected trajectory",
        ),
    )

    record = TrainingCandidateRecord.model_validate(payload)

    assert record.review_decision == "rejected"
    assert record.training_eligibility.is_analysis_only


def test_not_reviewed_candidate_cannot_include_review_details() -> None:
    payload = _candidate_payload(
        review_status="not_reviewed",
        review_id="review_001",
        reviewer_id=None,
        review_decision=None,
        training_eligibility=_eligibility_payload(
            positive_sft_allowed=False,
            positive_sft_reason="trajectory has not been reviewed",
            negative_example_allowed=False,
            negative_example_reason="trajectory has not been reviewed",
            preference_data_allowed=False,
            preference_data_reason="trajectory has not been reviewed",
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


def test_training_eligibility_requires_path_reasons() -> None:
    payload = _eligibility_payload(positive_sft_reason="")

    with pytest.raises(
        ValidationError, match="String should have at least 1 character"
    ):
        TrainingEligibility.model_validate(payload)


def test_positive_sft_example_record_accepts_model_visible_row() -> None:
    record = PositiveSFTExampleRecord.model_validate(_positive_sft_payload())

    assert record.schema_version == POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
    assert record.example_id == "positive_sft_example_001"
    assert record.provenance_ids.trajectory_id == "trajectory_001"
    assert record.provenance_ids.task_id == record.task_input.task_id
    assert (
        record.prompt_provenance.prompt_builder_version
        == AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION
    )
    assert record.prompt_provenance.prompt_builder_code_hash == "xxh64:promptbuilder"
    assert [message.role for message in record.messages[:2]] == ["system", "user"]
    assert any(message.role == "assistant" for message in record.messages)


def test_positive_sft_task_input_rejects_workspace_path() -> None:
    payload = _positive_sft_task_input_payload(workspace_path="/tmp/workspace")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PositiveSFTTaskInput.model_validate(payload)


def test_positive_sft_message_rejects_metadata() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PositiveSFTMessage.model_validate(
            {
                "role": "assistant",
                "content": '{"action":"final_answer","text":"done"}',
                "metadata": {"source": "private"},
            }
        )


def test_positive_sft_tool_message_requires_name_and_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="tool messages require name"):
        PositiveSFTMessage.model_validate(
            {
                "role": "tool",
                "content": '{"status":"ok"}',
                "tool_call_id": "tool_call_0001",
            }
        )

    with pytest.raises(ValidationError, match="tool messages require tool_call_id"):
        PositiveSFTMessage.model_validate(
            {
                "role": "tool",
                "content": '{"status":"ok"}',
                "name": "run_tests",
            }
        )


def test_positive_sft_system_and_user_messages_reject_tool_call_id() -> None:
    with pytest.raises(ValidationError, match="system messages cannot include"):
        PositiveSFTMessage.model_validate(
            {
                "role": "system",
                "content": "Use JSON actions.",
                "tool_call_id": "tool_call_0001",
            }
        )

    with pytest.raises(ValidationError, match="user messages cannot include"):
        PositiveSFTMessage.model_validate(
            {
                "role": "user",
                "content": "Fix the task.",
                "tool_call_id": "tool_call_0001",
            }
        )


def test_positive_sft_assistant_message_can_include_tool_call_id() -> None:
    message = PositiveSFTMessage.model_validate(
        {
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
        match="positive SFT example_id must be derived from trajectory_id",
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
                "role": "system",
                "content": "Historical persisted system prompt.",
                "name": "agentenv",
            },
            {
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
