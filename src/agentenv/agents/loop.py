from collections.abc import Iterable
from time import perf_counter

from pydantic import ValidationError

from agentenv.agents.prompts import build_initial_messages
from agentenv.agents.schema import (
    AgentTaskView,
    FinalAnswerAction,
    PromptLoopResult,
    PromptLoopStatus,
    TokenUsage,
    ToolCallAction,
    parse_agent_action,
)
from agentenv.agents.tool_messages import render_tool_result_message
from agentenv.models.client import ModelClient
from agentenv.models.schema import DecodingConfig, Message, ModelResponse
from agentenv.tools.local_tools import execute_tool
from agentenv.tools.schema import ToolResult


RECOVERABLE_TOOL_ERROR_CLASSES = {
    "InvalidToolInput",
    "ToolExecutionError",
    "ToolTimeout",
}


def run_prompt_loop(
    agent_task_view: AgentTaskView,
    model_client: ModelClient,
    decoding_config: DecodingConfig,
) -> PromptLoopResult:
    started = perf_counter()
    messages = build_initial_messages(agent_task_view)
    model_responses: list[ModelResponse] = []
    tool_results: list[ToolResult] = []
    turns_executed = 0

    for turn_index in range(agent_task_view.max_turns):
        turns_executed = turn_index + 1
        try:
            model_response = model_client.generate(messages, decoding_config)
        except Exception as exc:
            return _build_result(
                agent_task_view=agent_task_view,
                status="model_error",
                turns_executed=turns_executed,
                started=started,
                messages=messages,
                model_responses=model_responses,
                tool_results=tool_results,
                error_class=exc.__class__.__name__,
                error_message=_model_exception_message(model_client, exc),
            )

        model_responses.append(model_response)
        messages.append(_assistant_message(model_response))

        if model_response.finish_reason != "stop_criteria_met":
            return _build_result(
                agent_task_view=agent_task_view,
                status="model_error",
                turns_executed=turns_executed,
                started=started,
                messages=messages,
                model_responses=model_responses,
                tool_results=tool_results,
                error_class=_prompt_loop_model_error_class(model_response),
                error_message=_model_error_message(model_response),
            )

        try:
            agent_action = parse_agent_action(model_response.output_text)
        except ValidationError as exc:
            return _build_result(
                agent_task_view=agent_task_view,
                status="invalid_model_output",
                turns_executed=turns_executed,
                started=started,
                messages=messages,
                model_responses=model_responses,
                tool_results=tool_results,
                error_class="InvalidModelOutput",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _build_result(
                agent_task_view=agent_task_view,
                status="invalid_model_output",
                turns_executed=turns_executed,
                started=started,
                messages=messages,
                model_responses=model_responses,
                tool_results=tool_results,
                error_class="MalformedModelOutput",
                error_message=str(exc),
            )

        if isinstance(agent_action, FinalAnswerAction):
            return _build_result(
                agent_task_view=agent_task_view,
                status="completed",
                turns_executed=turns_executed,
                started=started,
                messages=messages,
                model_responses=model_responses,
                tool_results=tool_results,
            )

        if isinstance(agent_action, ToolCallAction):
            tool_call_id = _tool_call_id(len(tool_results) + 1)
            messages[-1] = messages[-1].model_copy(
                update={"tool_call_id": tool_call_id}
            )
            tool_result = execute_tool(agent_action, agent_task_view)
            tool_results.append(tool_result)
            messages.append(render_tool_result_message(tool_result, tool_call_id))

            if _is_terminal_tool_error(tool_result):
                return _build_result(
                    agent_task_view=agent_task_view,
                    status="terminal_tool_error",
                    turns_executed=turns_executed,
                    started=started,
                    messages=messages,
                    model_responses=model_responses,
                    tool_results=tool_results,
                    error_class=tool_result.error_class,
                    error_message=tool_result.error_message,
                )

    return _build_result(
        agent_task_view=agent_task_view,
        status="max_turns_exceeded",
        turns_executed=turns_executed,
        started=started,
        messages=messages,
        model_responses=model_responses,
        tool_results=tool_results,
        error_class="MaxTurnsExceeded",
        error_message="Prompt loop reached max_turns.",
    )


def _assistant_message(model_response: ModelResponse) -> Message:
    return Message(
        role="assistant",
        content=model_response.output_text,
        name=model_response.model_id,
    )


def _tool_call_id(tool_call_number: int) -> str:
    return f"tool_call_{tool_call_number:04d}"


def _is_terminal_tool_error(tool_result: ToolResult) -> bool:
    if tool_result.status == "ok":
        return False
    return tool_result.error_class not in RECOVERABLE_TOOL_ERROR_CLASSES


def _prompt_loop_model_error_class(model_response: ModelResponse) -> str:
    # The ModelResponse schema requires timeout/error responses to carry
    # error_class. Budget stops such as max_new_tokens_reached do not.
    if model_response.error_class is not None:
        return model_response.error_class
    if model_response.finish_reason == "max_new_tokens_reached":
        return "MaxNewTokensReached"
    return "ModelGenerationStopped"


def _model_error_message(model_response: ModelResponse) -> str:
    message = f"Model generation stopped with finish_reason={model_response.finish_reason}."
    if model_response.error_message is None:
        return message
    return f"{message} {model_response.error_message}"


def _model_exception_message(model_client: ModelClient, exc: Exception) -> str:
    message = str(exc)
    if message:
        return f"Model {model_client.model_id} generate failed: {message}"
    return f"Model {model_client.model_id} generate failed."


def _build_result(
    *,
    agent_task_view: AgentTaskView,
    status: PromptLoopStatus,
    turns_executed: int,
    started: float,
    messages: list[Message],
    model_responses: list[ModelResponse],
    tool_results: list[ToolResult],
    error_class: str | None = None,
    error_message: str | None = None,
) -> PromptLoopResult:
    return PromptLoopResult(
        task_id=agent_task_view.task_id,
        status=status,
        turns_executed=turns_executed,
        duration_ms=_duration_ms(started),
        token_usage=_token_usage(model_responses),
        messages=messages,
        model_responses=model_responses,
        tool_results=tool_results,
        error_class=error_class,
        error_message=error_message,
    )


def _token_usage(model_responses: list[ModelResponse]) -> TokenUsage:
    if not model_responses:
        return TokenUsage()

    return TokenUsage(
        prompt_tokens=_sum_known_counts(
            model_response.prompt_tokens for model_response in model_responses
        ),
        completion_tokens=_sum_known_counts(
            model_response.completion_tokens for model_response in model_responses
        ),
        total_tokens=_sum_known_counts(
            model_response.total_tokens for model_response in model_responses
        ),
    )


def _sum_known_counts(counts: Iterable[int | None]) -> int | None:
    total = 0
    for count in counts:
        if count is None:
            return None
        total += count
    return total


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
