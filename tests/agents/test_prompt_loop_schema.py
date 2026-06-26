import pytest
from pydantic import ValidationError

from agentenv.agents.schema import PromptLoopResult, TokenUsage
from agentenv.models.schema import Message, ModelResponse
from agentenv.tools.schema import ReadFileOutput, ToolResult


def _messages() -> list[Message]:
    return [
        Message(role="system", content="Return one JSON action."),
        Message(role="user", content="Fix the task."),
        Message(
            role="assistant",
            content='{"action": "final_answer", "text": "done"}',
            name="fake-scripted-v0",
        ),
    ]


def _model_responses() -> list[ModelResponse]:
    return [
        ModelResponse(
            model_id="fake-scripted-v0",
            output_text='{"action": "final_answer", "text": "done"}',
            finish_reason="stop_criteria_met",
            latency_ms=2,
            raw_response_ref="fake_model/raw_response.json",
        )
    ]


def _tool_results() -> list[ToolResult]:
    return [
        ToolResult(
            tool_name="read_file",
            input_hash="xxh64:abc123",
            status="ok",
            output=ReadFileOutput(
                content="file contents",
                bytes_read=13,
                truncated=False,
            ),
            duration_ms=1,
        )
    ]


def test_token_usage_accepts_unknown_counts() -> None:
    usage = TokenUsage(
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
    )

    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.total_tokens is None


def test_token_usage_accepts_known_counts() -> None:
    usage = TokenUsage(
        prompt_tokens=100,
        completion_tokens=25,
        total_tokens=125,
    )

    assert usage.total_tokens == 125


def test_token_usage_rejects_inconsistent_total() -> None:
    with pytest.raises(
        ValidationError,
        match="total_tokens must equal prompt_tokens \\+ completion_tokens",
    ):
        TokenUsage(
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=124,
        )


def test_prompt_loop_result_accepts_completed_result() -> None:
    result = PromptLoopResult(
        task_id="repair_jsonl_deduper",
        status="completed",
        turns_executed=1,
        duration_ms=5,
        token_usage=TokenUsage(),
        messages=_messages(),
        model_responses=_model_responses(),
        tool_results=[],
        error_class=None,
        error_message=None,
    )

    assert result.status == "completed"
    assert result.error_class is None


def test_prompt_loop_result_accepts_non_completed_result() -> None:
    result = PromptLoopResult(
        task_id="repair_jsonl_deduper",
        status="max_turns_exceeded",
        turns_executed=8,
        duration_ms=1000,
        token_usage=TokenUsage(),
        messages=_messages(),
        model_responses=_model_responses(),
        tool_results=_tool_results(),
        error_class="MaxTurnsExceeded",
        error_message="Prompt loop reached max_turns.",
    )

    assert result.status == "max_turns_exceeded"
    assert result.error_class == "MaxTurnsExceeded"


def test_prompt_loop_result_rejects_completed_with_error_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="completed prompt loops cannot include error fields",
    ):
        PromptLoopResult(
            task_id="repair_jsonl_deduper",
            status="completed",
            turns_executed=1,
            duration_ms=5,
            token_usage=TokenUsage(),
            messages=_messages(),
            model_responses=_model_responses(),
            tool_results=[],
            error_class="UnexpectedError",
            error_message=None,
        )


def test_prompt_loop_result_rejects_non_completed_without_error_class() -> None:
    with pytest.raises(
        ValidationError,
        match="non-completed prompt loops require error_class",
    ):
        PromptLoopResult(
            task_id="repair_jsonl_deduper",
            status="invalid_model_output",
            turns_executed=1,
            duration_ms=5,
            token_usage=TokenUsage(),
            messages=_messages(),
            model_responses=_model_responses(),
            tool_results=[],
            error_class=None,
            error_message="Model output was not valid JSON.",
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("task_id", ""),
        ("turns_executed", -1),
        ("duration_ms", -1),
        ("error_class", ""),
        ("error_message", ""),
    ],
)
def test_prompt_loop_result_rejects_invalid_common_fields(
    field_name: str,
    value: object,
) -> None:
    payload: dict[str, object] = {
        "task_id": "repair_jsonl_deduper",
        "status": "model_error",
        "turns_executed": 1,
        "duration_ms": 5,
        "token_usage": TokenUsage(),
        "messages": _messages(),
        "model_responses": _model_responses(),
        "tool_results": [],
        "error_class": "ModelTimeout",
        "error_message": None,
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        PromptLoopResult.model_validate(payload)
