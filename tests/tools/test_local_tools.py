import sys
from pathlib import Path

import pytest

from agentenv.agents.schema import AgentTaskView, ToolCallAction
from agentenv.security.secrets import REDACTED_SECRET
from agentenv.tools.local_tools import execute_tool
from agentenv.tools.schema import ReadFileOutput, RunTestsOutput, WriteFileOutput


CANARY = "agentenv-canary-secret-000000000000"


def _agent_task_view(
    workspace_path: Path,
    *,
    allowed_tools: list[str] | None = None,
    public_checks: list[str] | None = None,
    timeout_seconds: int = 5,
) -> AgentTaskView:
    return AgentTaskView(
        task_id="task_001",
        instruction="Fix the task.",
        workspace_path=workspace_path,
        allowed_tools=allowed_tools or ["read_file", "write_file", "run_tests"],
        public_checks=public_checks if public_checks is not None else ["true"],
        max_turns=8,
        timeout_seconds=timeout_seconds,
        network="off",
    )


def test_execute_tool_reads_file_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src.py").write_text("print('hello')\n")

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="read_file",
            arguments={"path": "src.py"},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "ok"
    assert isinstance(result.output, ReadFileOutput)
    assert result.output.content == "print('hello')\n"
    assert result.output.bytes_read == len("print('hello')\n".encode())
    assert result.error_class is None


def test_execute_tool_writes_file_inside_existing_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="write_file",
            arguments={
                "path": "src.py",
                "content": "print('fixed')\n",
            },
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "ok"
    assert isinstance(result.output, WriteFileOutput)
    assert result.output.bytes_written == len("print('fixed')\n".encode())
    assert (workspace / "src.py").read_text() == "print('fixed')\n"


def test_execute_tool_rejects_write_to_missing_parent_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="write_file",
            arguments={
                "path": "missing/src.py",
                "content": "print('fixed')\n",
            },
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "error"
    assert result.error_class == "ToolExecutionError"
    assert result.output is None


def test_execute_tool_runs_allowed_public_check(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = f'{sys.executable} -c "print(\\"ok\\")"'

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="run_tests",
            arguments={"command": command},
        ),
        _agent_task_view(workspace, public_checks=[command]),
    )

    assert result.status == "ok"
    assert isinstance(result.output, RunTestsOutput)
    assert result.output.passed is True
    assert result.exit_code == 0
    assert result.stdout == "ok\n"


def test_execute_tool_run_tests_scrubs_and_redacts_secret_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", CANARY)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = (
        f"{sys.executable} -c 'import os; "
        f"print(os.getenv(\"AGENTENV_MODEL_API_KEY\", \"missing\")); "
        f"print(\"{CANARY}\")'"
    )

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="run_tests",
            arguments={"command": command},
        ),
        _agent_task_view(workspace, public_checks=[command]),
    )

    assert result.status == "ok"
    assert result.stdout == f"missing\n{REDACTED_SECRET}\n"
    assert CANARY not in result.stdout


def test_execute_tool_reports_failing_public_check_as_ok_tool_execution(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command = f'{sys.executable} -c "import sys; sys.exit(1)"'

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="run_tests",
            arguments={"command": command},
        ),
        _agent_task_view(workspace, public_checks=[command]),
    )

    assert result.status == "ok"
    assert isinstance(result.output, RunTestsOutput)
    assert result.output.passed is False
    assert result.exit_code == 1


def test_execute_tool_checks_allowed_tools_before_registry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="delete_file",
            arguments={"path": "src.py"},
        ),
        _agent_task_view(workspace, allowed_tools=["read_file"]),
    )

    assert result.status == "error"
    assert result.tool_name == "delete_file"
    assert result.error_class == "ToolNotAllowed"


def test_execute_tool_reports_unknown_allowed_tool(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="delete_file",
            arguments={"path": "src.py"},
        ),
        _agent_task_view(workspace, allowed_tools=["delete_file"]),
    )

    assert result.status == "error"
    assert result.tool_name == "delete_file"
    assert result.error_class == "UnknownTool"


def test_execute_tool_reports_invalid_tool_input(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="read_file",
            arguments={},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "error"
    assert result.error_class == "InvalidToolInput"


def test_execute_tool_rejects_absolute_and_traversal_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    absolute_result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="read_file",
            arguments={"path": str(tmp_path / "outside.py")},
        ),
        _agent_task_view(workspace),
    )
    traversal_result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="read_file",
            arguments={"path": "../outside.py"},
        ),
        _agent_task_view(workspace),
    )

    assert absolute_result.status == "error"
    assert absolute_result.error_class == "UnsafePath"
    assert traversal_result.status == "error"
    assert traversal_result.error_class == "UnsafePath"


def test_execute_tool_rejects_unlisted_test_command(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="run_tests",
            arguments={"command": "pytest"},
        ),
        _agent_task_view(workspace, public_checks=["python -c pass"]),
    )

    assert result.status == "error"
    assert result.error_class == "CommandNotAllowed"
