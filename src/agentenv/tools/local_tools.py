from dataclasses import dataclass
from pathlib import Path
from subprocess import TimeoutExpired
from time import perf_counter

from pydantic import ValidationError

from agentenv.agents.schema import AgentTaskView, ToolCallAction
from agentenv.hashing import hash_directory
from agentenv.runners.public_check_runner import run_public_check
from agentenv.security.secrets import redact_secrets
from agentenv.tools.hashing import hash_tool_arguments, hash_tool_input
from agentenv.tools.schema import (
    TOOL_REGISTRY,
    ListFilesInput,
    ListFilesOutput,
    ReadFileInput,
    ReadFileOutput,
    RunTestsInput,
    RunTestsOutput,
    ToolInput,
    ToolOutput,
    ToolResult,
    ToolResultStatus,
    WriteFileInput,
    WriteFileOutput,
    validate_tool_input,
)


class WorkspaceStateHashError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ToolExecutionOutcome:
    tool_name: str
    arguments_hash: str
    status: ToolResultStatus
    output: ToolOutput | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    error_class: str | None = None
    error_message: str | None = None


def execute_tool(
    tool_call_action: ToolCallAction,
    agent_task_view: AgentTaskView,
) -> ToolResult:
    started = perf_counter()
    workspace_hash_before = _hash_workspace_state(
        agent_task_view.workspace_path,
        phase="before",
    )
    outcome = _execute_tool_call(tool_call_action, agent_task_view, started=started)
    workspace_hash_after = _hash_workspace_state(
        agent_task_view.workspace_path,
        phase="after",
    )
    return ToolResult(
        tool_name=outcome.tool_name,
        arguments_hash=outcome.arguments_hash,
        canonical_workspace_hash_before=workspace_hash_before,
        canonical_workspace_hash_after=workspace_hash_after,
        status=outcome.status,
        output=outcome.output,
        stdout=outcome.stdout,
        stderr=outcome.stderr,
        exit_code=outcome.exit_code,
        duration_ms=outcome.duration_ms,
        error_class=outcome.error_class,
        error_message=outcome.error_message,
    )


def _execute_tool_call(
    tool_call_action: ToolCallAction,
    agent_task_view: AgentTaskView,
    *,
    started: float,
) -> _ToolExecutionOutcome:
    tool_name = tool_call_action.tool_name
    arguments_hash = hash_tool_arguments(tool_call_action.arguments)

    if tool_name not in agent_task_view.allowed_tools:
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="ToolNotAllowed",
            error_message=f"Tool is not allowed for this task: {tool_name}",
        )

    if tool_name not in TOOL_REGISTRY:
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="UnknownTool",
            error_message=f"Unknown tool: {tool_name}",
        )

    try:
        tool_input = validate_tool_input(tool_name, tool_call_action.arguments)
    except ValidationError as exc:
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="InvalidToolInput",
            error_message=str(exc),
        )

    arguments_hash = hash_tool_input(tool_input)
    if tool_name == "list_files":
        return _execute_list_files(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_task_view=agent_task_view,
            arguments_hash=arguments_hash,
            started=started,
        )
    if tool_name == "read_file":
        return _execute_read_file(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_task_view=agent_task_view,
            arguments_hash=arguments_hash,
            started=started,
        )
    if tool_name == "write_file":
        return _execute_write_file(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_task_view=agent_task_view,
            arguments_hash=arguments_hash,
            started=started,
        )
    return _execute_run_tests(
        tool_name=tool_name,
        tool_input=tool_input,
        agent_task_view=agent_task_view,
        arguments_hash=arguments_hash,
        started=started,
    )


_NOISY_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def _execute_list_files(
    *,
    tool_name: str,
    tool_input: ToolInput,
    agent_task_view: AgentTaskView,
    arguments_hash: str,
    started: float,
) -> _ToolExecutionOutcome:
    if not isinstance(tool_input, ListFilesInput):
        return _unexpected_input_result(tool_name, arguments_hash, started)

    resolved_path = _resolve_workspace_path(
        agent_task_view.workspace_path,
        tool_input.path,
    )
    if resolved_path is None:
        return _unsafe_path_result(
            tool_name,
            arguments_hash,
            started,
            tool_input.path,
        )
    if not resolved_path.is_dir():
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=f"Path is not a directory: {tool_input.path}",
        )

    try:
        files, truncated = _list_workspace_files(
            root=agent_task_view.workspace_path.resolve(),
            start=resolved_path,
            max_depth=tool_input.max_depth,
            max_files=tool_input.max_files,
        )
    except Exception as exc:
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=str(exc),
        )

    return _ToolExecutionOutcome(
        tool_name=tool_name,
        arguments_hash=arguments_hash,
        status="ok",
        output=ListFilesOutput(files=files, truncated=truncated),
        duration_ms=_duration_ms(started),
    )


def _execute_read_file(
    *,
    tool_name: str,
    tool_input: ToolInput,
    agent_task_view: AgentTaskView,
    arguments_hash: str,
    started: float,
) -> _ToolExecutionOutcome:
    if not isinstance(tool_input, ReadFileInput):
        return _unexpected_input_result(tool_name, arguments_hash, started)

    resolved_path = _resolve_workspace_path(
        agent_task_view.workspace_path,
        tool_input.path,
    )
    if resolved_path is None:
        return _unsafe_path_result(
            tool_name,
            arguments_hash,
            started,
            tool_input.path,
        )

    try:
        content = resolved_path.read_text()
    except Exception as exc:
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=str(exc),
        )

    return _ToolExecutionOutcome(
        tool_name=tool_name,
        arguments_hash=arguments_hash,
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
    arguments_hash: str,
    started: float,
) -> _ToolExecutionOutcome:
    if not isinstance(tool_input, WriteFileInput):
        return _unexpected_input_result(tool_name, arguments_hash, started)

    resolved_path = _resolve_workspace_path(
        agent_task_view.workspace_path,
        tool_input.path,
    )
    if resolved_path is None:
        return _unsafe_path_result(
            tool_name,
            arguments_hash,
            started,
            tool_input.path,
        )
    if not resolved_path.parent.is_dir():
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=f"Parent directory does not exist: {tool_input.path}",
        )

    try:
        resolved_path.write_text(tool_input.content)
    except Exception as exc:
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=str(exc),
        )

    return _ToolExecutionOutcome(
        tool_name=tool_name,
        arguments_hash=arguments_hash,
        status="ok",
        output=WriteFileOutput(bytes_written=len(tool_input.content.encode())),
        duration_ms=_duration_ms(started),
    )


def _execute_run_tests(
    *,
    tool_name: str,
    tool_input: ToolInput,
    agent_task_view: AgentTaskView,
    arguments_hash: str,
    started: float,
) -> _ToolExecutionOutcome:
    if not isinstance(tool_input, RunTestsInput):
        return _unexpected_input_result(tool_name, arguments_hash, started)
    if tool_input.command not in agent_task_view.public_checks:
        return _error_result(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            started=started,
            error_class="CommandNotAllowed",
            error_message=f"Command is not an allowed public check: {tool_input.command}",
        )

    try:
        completed = run_public_check(
            tool_input.command,
            workspace=agent_task_view.workspace_path,
            timeout_seconds=agent_task_view.timeout_seconds,
        )
    except TimeoutExpired as exc:
        return _ToolExecutionOutcome(
            tool_name=tool_name,
            arguments_hash=arguments_hash,
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
            arguments_hash=arguments_hash,
            started=started,
            error_class="ToolExecutionError",
            error_message=redact_secrets(str(exc)),
        )

    return _ToolExecutionOutcome(
        tool_name=tool_name,
        arguments_hash=arguments_hash,
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
    arguments_hash: str,
    started: float,
    error_class: str,
    error_message: str,
) -> _ToolExecutionOutcome:
    return _ToolExecutionOutcome(
        tool_name=tool_name,
        arguments_hash=arguments_hash,
        status="error",
        output=None,
        duration_ms=_duration_ms(started),
        error_class=error_class,
        error_message=redact_secrets(error_message),
    )


def _unexpected_input_result(
    tool_name: str,
    arguments_hash: str,
    started: float,
) -> _ToolExecutionOutcome:
    return _error_result(
        tool_name=tool_name,
        arguments_hash=arguments_hash,
        started=started,
        error_class="InvalidToolInput",
        error_message=f"Validated input did not match tool: {tool_name}",
    )


def _unsafe_path_result(
    tool_name: str,
    arguments_hash: str,
    started: float,
    path: str,
) -> _ToolExecutionOutcome:
    return _error_result(
        tool_name=tool_name,
        arguments_hash=arguments_hash,
        started=started,
        error_class="UnsafePath",
        error_message=f"Path is outside the workspace: {path}",
    )


def _list_workspace_files(
    *,
    root: Path,
    start: Path,
    max_depth: int,
    max_files: int,
) -> tuple[list[str], bool]:
    files: list[str] = []
    truncated = False

    def visit(directory: Path, depth: int) -> None:
        nonlocal truncated
        if len(files) >= max_files:
            truncated = True
            return

        entries = sorted(directory.iterdir(), key=lambda path: path.name)
        for entry in entries:
            if len(files) >= max_files:
                truncated = True
                return
            if entry.is_dir():
                if entry.name in _NOISY_DIRECTORY_NAMES:
                    continue
                if depth < max_depth:
                    visit(entry, depth + 1)
                continue
            if entry.is_file():
                files.append(entry.relative_to(root).as_posix())

    visit(start, 0)
    return files, truncated


def _resolve_workspace_path(workspace_path: Path, requested_path: str) -> Path | None:
    requested = Path(requested_path)
    if requested.is_absolute():
        return None

    workspace_root = workspace_path.resolve()
    resolved_path = (workspace_root / requested).resolve()
    if workspace_root == resolved_path or workspace_root in resolved_path.parents:
        return resolved_path
    return None


def _hash_workspace_state(workspace_path: Path, *, phase: str) -> str:
    try:
        return hash_directory(workspace_path)
    except Exception as exc:
        message = redact_secrets(
            f"Failed to hash canonical workspace {phase} tool execution: {exc}"
        )
        raise WorkspaceStateHashError(message) from exc


def _stream_text(stream: object) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return str(stream)


def _duration_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
