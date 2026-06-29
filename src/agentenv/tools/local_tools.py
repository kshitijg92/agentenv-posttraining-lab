import json
from collections.abc import Mapping
from pathlib import Path
from subprocess import TimeoutExpired
from time import perf_counter

import xxhash
from pydantic import ValidationError

from agentenv.agents.schema import AgentTaskView, ToolCallAction
from agentenv.runners.command_runner import run_shell
from agentenv.security.secrets import redact_secrets
from agentenv.tools.schema import (
    TOOL_REGISTRY,
    ReadFileInput,
    ReadFileOutput,
    RunTestsInput,
    RunTestsOutput,
    ToolInput,
    ToolResult,
    WriteFileInput,
    WriteFileOutput,
    validate_tool_input,
)


def execute_tool(
    tool_call_action: ToolCallAction,
    agent_task_view: AgentTaskView,
) -> ToolResult:
    started = perf_counter()
    tool_name = tool_call_action.tool_name
    input_hash = _input_hash(tool_call_action.arguments)

    if tool_name not in agent_task_view.allowed_tools:
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="ToolNotAllowed",
            error_message=f"Tool is not allowed for this task: {tool_name}",
        )

    if tool_name not in TOOL_REGISTRY:
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="UnknownTool",
            error_message=f"Unknown tool: {tool_name}",
        )

    try:
        tool_input = validate_tool_input(tool_name, tool_call_action.arguments)
    except ValidationError as exc:
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="InvalidToolInput",
            error_message=str(exc),
        )

    input_hash = _validated_input_hash(tool_input)
    if tool_name == "read_file":
        return _execute_read_file(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_task_view=agent_task_view,
            input_hash=input_hash,
            started=started,
        )
    if tool_name == "write_file":
        return _execute_write_file(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_task_view=agent_task_view,
            input_hash=input_hash,
            started=started,
        )
    return _execute_run_tests(
        tool_name=tool_name,
        tool_input=tool_input,
        agent_task_view=agent_task_view,
        input_hash=input_hash,
        started=started,
    )


def _execute_read_file(
    *,
    tool_name: str,
    tool_input: ToolInput,
    agent_task_view: AgentTaskView,
    input_hash: str,
    started: float,
) -> ToolResult:
    if not isinstance(tool_input, ReadFileInput):
        return _unexpected_input_result(tool_name, input_hash, started)

    resolved_path = _resolve_workspace_path(
        agent_task_view.workspace_path,
        tool_input.path,
    )
    if resolved_path is None:
        return _unsafe_path_result(tool_name, input_hash, started, tool_input.path)

    try:
        content = resolved_path.read_text()
    except Exception as exc:
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=str(exc),
        )

    return ToolResult(
        tool_name=tool_name,
        input_hash=input_hash,
        status="ok",
        output=ReadFileOutput(
            content=redact_secrets(content),
            bytes_read=len(content.encode()),
            truncated=False,
        ),
        duration_ms=_duration_ms(started),
    )


def _execute_write_file(
    *,
    tool_name: str,
    tool_input: ToolInput,
    agent_task_view: AgentTaskView,
    input_hash: str,
    started: float,
) -> ToolResult:
    if not isinstance(tool_input, WriteFileInput):
        return _unexpected_input_result(tool_name, input_hash, started)

    resolved_path = _resolve_workspace_path(
        agent_task_view.workspace_path,
        tool_input.path,
    )
    if resolved_path is None:
        return _unsafe_path_result(tool_name, input_hash, started, tool_input.path)
    if not resolved_path.parent.is_dir():
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=f"Parent directory does not exist: {tool_input.path}",
        )

    try:
        resolved_path.write_text(tool_input.content)
    except Exception as exc:
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=str(exc),
        )

    return ToolResult(
        tool_name=tool_name,
        input_hash=input_hash,
        status="ok",
        output=WriteFileOutput(bytes_written=len(tool_input.content.encode())),
        duration_ms=_duration_ms(started),
    )


def _execute_run_tests(
    *,
    tool_name: str,
    tool_input: ToolInput,
    agent_task_view: AgentTaskView,
    input_hash: str,
    started: float,
) -> ToolResult:
    if not isinstance(tool_input, RunTestsInput):
        return _unexpected_input_result(tool_name, input_hash, started)
    if tool_input.command not in agent_task_view.public_checks:
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="CommandNotAllowed",
            error_message=f"Command is not an allowed public check: {tool_input.command}",
        )

    try:
        completed = run_shell(
            tool_input.command,
            cwd=agent_task_view.workspace_path,
            timeout_seconds=agent_task_view.timeout_seconds,
        )
    except TimeoutExpired as exc:
        return ToolResult(
            tool_name=tool_name,
            input_hash=input_hash,
            status="error",
            output=None,
            stdout=redact_secrets(_stream_text(exc.stdout)),
            stderr=redact_secrets(_stream_text(exc.stderr)),
            exit_code=None,
            duration_ms=_duration_ms(started),
            error_class="ToolTimeout",
            error_message=redact_secrets(
                f"Tool command timed out: {tool_input.command}"
            ),
        )
    except Exception as exc:
        return _error_result(
            tool_name=tool_name,
            input_hash=input_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=redact_secrets(str(exc)),
        )

    return ToolResult(
        tool_name=tool_name,
        input_hash=input_hash,
        status="ok",
        output=RunTestsOutput(passed=completed.returncode == 0),
        stdout=redact_secrets(completed.stdout),
        stderr=redact_secrets(completed.stderr),
        exit_code=completed.returncode,
        duration_ms=_duration_ms(started),
    )


def _error_result(
    *,
    tool_name: str,
    input_hash: str,
    started: float,
    error_class: str,
    error_message: str,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        input_hash=input_hash,
        status="error",
        output=None,
        duration_ms=_duration_ms(started),
        error_class=error_class,
        error_message=redact_secrets(error_message),
    )


def _unexpected_input_result(
    tool_name: str,
    input_hash: str,
    started: float,
) -> ToolResult:
    return _error_result(
        tool_name=tool_name,
        input_hash=input_hash,
        started=started,
        error_class="InvalidToolInput",
        error_message=f"Validated input did not match tool: {tool_name}",
    )


def _unsafe_path_result(
    tool_name: str,
    input_hash: str,
    started: float,
    path: str,
) -> ToolResult:
    return _error_result(
        tool_name=tool_name,
        input_hash=input_hash,
        started=started,
        error_class="UnsafePath",
        error_message=f"Path is outside the workspace: {path}",
    )


def _resolve_workspace_path(workspace_path: Path, requested_path: str) -> Path | None:
    requested = Path(requested_path)
    if requested.is_absolute():
        return None

    workspace_root = workspace_path.resolve()
    resolved_path = (workspace_root / requested).resolve()
    if workspace_root == resolved_path or workspace_root in resolved_path.parents:
        return resolved_path
    return None


def _input_hash(arguments: Mapping[str, object]) -> str:
    payload = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return f"xxh64:{xxhash.xxh64_hexdigest(payload.encode())}"


def _validated_input_hash(tool_input: ToolInput) -> str:
    return _input_hash(tool_input.model_dump(mode="json"))


def _stream_text(stream: object) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return str(stream)


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
