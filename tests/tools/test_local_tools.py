import sys
from pathlib import Path

import pytest

from agentenv.agents.schema import AgentActionValue, AgentTaskView, ToolCallAction
from agentenv.security.secrets import REDACTED_SECRET
from agentenv.tools.local_tools import execute_tool
from agentenv.tools.schema import (
    ListFilesOutput,
    ReadFileOutput,
    RunTestsOutput,
    WriteFileOutput,
)


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
        allowed_tools=allowed_tools
        or ["list_files", "read_file", "write_file", "run_tests"],
        public_checks=public_checks if public_checks is not None else ["true"],
        max_turns=8,
        timeout_seconds=timeout_seconds,
        network="off",
    )


def test_execute_tool_lists_files_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "pyproject.toml").write_text("[project]\n")
    (workspace / "src" / "mathlib.py").write_text("def f(): ...\n")
    (workspace / "tests" / "test_public.py").write_text("def test_public(): ...\n")

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="list_files",
            arguments={"path": ".", "max_depth": 1, "max_files": 20},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "ok"
    assert isinstance(result.output, ListFilesOutput)
    assert result.output.files == [
        "pyproject.toml",
        "src/mathlib.py",
        "tests/test_public.py",
    ]
    assert result.output.truncated is False


def test_execute_tool_lists_files_relative_to_workspace_for_subdir(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src" / "pkg").mkdir(parents=True)
    (workspace / "src" / "pkg" / "module.py").write_text("x = 1\n")

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="list_files",
            arguments={"path": "src", "max_depth": 1, "max_files": 20},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "ok"
    assert isinstance(result.output, ListFilesOutput)
    assert result.output.files == ["src/pkg/module.py"]


def test_execute_tool_list_files_respects_max_depth(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src" / "pkg").mkdir(parents=True)
    (workspace / "src" / "top.py").write_text("x = 1\n")
    (workspace / "src" / "pkg" / "nested.py").write_text("x = 2\n")

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="list_files",
            arguments={"path": ".", "max_depth": 0, "max_files": 20},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "ok"
    assert isinstance(result.output, ListFilesOutput)
    assert result.output.files == []


def test_execute_tool_list_files_respects_max_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for index in range(3):
        (workspace / f"{index}.py").write_text("x = 1\n")

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="list_files",
            arguments={"path": ".", "max_depth": 0, "max_files": 2},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "ok"
    assert isinstance(result.output, ListFilesOutput)
    assert result.output.files == ["0.py", "1.py"]
    assert result.output.truncated is True


def test_execute_tool_list_files_skips_noisy_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / ".git").mkdir()
    (workspace / "__pycache__").mkdir()
    (workspace / "node_modules").mkdir()
    (workspace / "src" / "mathlib.py").write_text("x = 1\n")
    (workspace / ".git" / "config").write_text("private\n")
    (workspace / "__pycache__" / "module.pyc").write_text("cache\n")
    (workspace / "node_modules" / "package.json").write_text("{}\n")

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="list_files",
            arguments={"path": ".", "max_depth": 2, "max_files": 20},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "ok"
    assert isinstance(result.output, ListFilesOutput)
    assert result.output.files == ["src/mathlib.py"]


def test_execute_tool_list_files_rejects_file_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src.py").write_text("x = 1\n")

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name="list_files",
            arguments={"path": "src.py"},
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "error"
    assert result.error_class == "ToolExecutionError"
    assert result.output is None


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


@pytest.mark.parametrize("tool_name", ["list_files", "read_file", "write_file"])
@pytest.mark.parametrize("path_kind", ["absolute", "traversal"])
def test_execute_file_tools_reject_paths_outside_workspace(
    tmp_path: Path,
    tool_name: str,
    path_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("private\n")

    requested_path = str(outside) if path_kind == "absolute" else "../outside.py"
    arguments: dict[str, AgentActionValue] = {"path": requested_path}
    if tool_name == "write_file":
        arguments["content"] = "overwrite\n"

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name=tool_name,
            arguments=arguments,
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "error"
    assert result.error_class == "UnsafePath"
    assert outside.read_text() == "private\n"


@pytest.mark.parametrize("tool_name", ["list_files", "read_file", "write_file"])
def test_execute_file_tools_reject_symlink_escapes(
    tmp_path: Path,
    tool_name: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "secret.py"
    outside_file.write_text("private\n")

    if tool_name == "list_files":
        (workspace / "escape").symlink_to(outside, target_is_directory=True)
        requested_path = "escape"
        arguments: dict[str, AgentActionValue] = {"path": requested_path}
    else:
        (workspace / "escape.py").symlink_to(outside_file)
        requested_path = "escape.py"
        arguments = {"path": requested_path}
        if tool_name == "write_file":
            arguments["content"] = "overwrite\n"

    result = execute_tool(
        ToolCallAction(
            action="tool_call",
            tool_name=tool_name,
            arguments=arguments,
        ),
        _agent_task_view(workspace),
    )

    assert result.status == "error"
    assert result.error_class == "UnsafePath"
    assert outside_file.read_text() == "private\n"


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
