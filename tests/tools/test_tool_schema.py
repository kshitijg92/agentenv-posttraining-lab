import pytest
from pydantic import ValidationError

from agentenv.tools.schema import ReadFileInput, ReadFileOutput
from agentenv.tools.schema import RunTestsInput, RunTestsOutput
from agentenv.tools.schema import TOOL_REGISTRY
from agentenv.tools.schema import ToolResult
from agentenv.tools.schema import WriteFileInput, WriteFileOutput
from agentenv.tools.schema import validate_tool_input


def test_validate_tool_input_accepts_read_file() -> None:
    tool_input = validate_tool_input("read_file", {"path": "src/foo.py"})

    assert tool_input == ReadFileInput(path="src/foo.py")


def test_validate_tool_input_accepts_write_file() -> None:
    tool_input = validate_tool_input(
        "write_file",
        {
            "path": "src/foo.py",
            "content": "print('fixed')\n",
        },
    )

    assert tool_input == WriteFileInput(
        path="src/foo.py",
        content="print('fixed')\n",
    )


def test_validate_tool_input_accepts_run_tests() -> None:
    tool_input = validate_tool_input(
        "run_tests",
        {"command": "uv run pytest tests/test_public.py"},
    )

    assert tool_input == RunTestsInput(command="uv run pytest tests/test_public.py")


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("read_file", {}),
        ("read_file", {"path": ""}),
        ("read_file", {"path": "src/foo.py", "content": "not allowed"}),
        ("write_file", {"path": "src/foo.py"}),
        ("write_file", {"path": "", "content": "x"}),
        ("write_file", {"path": "src/foo.py", "content": "x", "mode": "append"}),
        ("run_tests", {}),
        ("run_tests", {"command": ""}),
        ("run_tests", {"command": "pytest", "cwd": "src"}),
    ],
)
def test_validate_tool_input_rejects_invalid_arguments(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        validate_tool_input(tool_name, arguments)


def test_validate_tool_input_rejects_unknown_tool_name() -> None:
    with pytest.raises(ValueError, match="Unknown tool name: delete_file"):
        validate_tool_input("delete_file", {"path": "src/foo.py"})


def test_tool_registry_links_names_to_input_and_output_models() -> None:
    assert sorted(TOOL_REGISTRY) == ["read_file", "run_tests", "write_file"]

    assert TOOL_REGISTRY["read_file"].input_model is ReadFileInput
    assert TOOL_REGISTRY["read_file"].output_model is ReadFileOutput
    assert TOOL_REGISTRY["write_file"].input_model is WriteFileInput
    assert TOOL_REGISTRY["write_file"].output_model is WriteFileOutput
    assert TOOL_REGISTRY["run_tests"].input_model is RunTestsInput
    assert TOOL_REGISTRY["run_tests"].output_model is RunTestsOutput


def test_tool_registry_descriptions_are_non_empty() -> None:
    for definition in TOOL_REGISTRY.values():
        assert definition.description


def test_tool_output_schemas_accept_valid_outputs() -> None:
    read_output = ReadFileOutput(
        content="file contents",
        bytes_read=13,
        truncated=False,
    )
    write_output = WriteFileOutput(bytes_written=18)
    run_tests_output = RunTestsOutput(passed=True)

    assert read_output.content == "file contents"
    assert read_output.bytes_read == 13
    assert write_output.bytes_written == 18
    assert run_tests_output.passed is True


@pytest.mark.parametrize(
    ("output_model", "payload"),
    [
        (ReadFileOutput, {"content": "x", "bytes_read": -1}),
        (ReadFileOutput, {"content": "x", "bytes_read": 1, "path": "src/foo.py"}),
        (WriteFileOutput, {"bytes_written": -1}),
        (WriteFileOutput, {"bytes_written": 1, "content": "not included"}),
        (RunTestsOutput, {"passed": True, "exit_code": 0}),
    ],
)
def test_tool_output_schemas_reject_invalid_outputs(
    output_model: type[ReadFileOutput] | type[WriteFileOutput] | type[RunTestsOutput],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        output_model.model_validate(payload)


def test_tool_result_accepts_successful_read_file_result() -> None:
    result = ToolResult(
        tool_name="read_file",
        input_hash="xxh64:abc123",
        status="ok",
        output=ReadFileOutput(
            content="file contents",
            bytes_read=13,
            truncated=False,
        ),
        duration_ms=2,
    )

    assert result.status == "ok"
    assert result.output == ReadFileOutput(
        content="file contents",
        bytes_read=13,
        truncated=False,
    )
    assert result.exit_code is None
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.error_class is None


def test_tool_result_accepts_successful_run_tests_result() -> None:
    result = ToolResult(
        tool_name="run_tests",
        input_hash="xxh64:def456",
        status="ok",
        output=RunTestsOutput(passed=False),
        stdout="1 failed\n",
        stderr="",
        exit_code=1,
        duration_ms=530,
    )

    assert result.status == "ok"
    assert result.exit_code == 1
    assert result.stdout == "1 failed\n"


def test_tool_result_accepts_error_result_without_output() -> None:
    result = ToolResult(
        tool_name="read_file",
        input_hash="xxh64:abc123",
        status="error",
        output=None,
        stderr="Permission denied\n",
        duration_ms=2,
        error_class="PermissionDenied",
        error_message="read_file was denied",
    )

    assert result.status == "error"
    assert result.output is None
    assert result.error_class == "PermissionDenied"


def test_tool_result_allows_unknown_tool_name_for_error_results() -> None:
    result = ToolResult(
        tool_name="delete_file",
        input_hash="xxh64:abc123",
        status="error",
        output=None,
        duration_ms=2,
        error_class="ToolNotAllowed",
        error_message="Tool is not allowed for this task: delete_file",
    )

    assert result.tool_name == "delete_file"
    assert result.error_class == "ToolNotAllowed"


def test_tool_result_rejects_ok_without_output() -> None:
    with pytest.raises(ValidationError, match="ok tool results require output"):
        ToolResult(
            tool_name="read_file",
            input_hash="xxh64:abc123",
            status="ok",
            output=None,
            duration_ms=2,
        )


def test_tool_result_rejects_ok_with_error_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="ok tool results cannot include error fields",
    ):
        ToolResult(
            tool_name="read_file",
            input_hash="xxh64:abc123",
            status="ok",
            output=ReadFileOutput(
                content="file contents",
                bytes_read=13,
                truncated=False,
            ),
            duration_ms=2,
            error_class="Unexpected",
        )


def test_tool_result_rejects_error_with_output() -> None:
    with pytest.raises(ValidationError, match="error tool results cannot include output"):
        ToolResult(
            tool_name="read_file",
            input_hash="xxh64:abc123",
            status="error",
            output=ReadFileOutput(
                content="file contents",
                bytes_read=13,
                truncated=False,
            ),
            duration_ms=2,
            error_class="PermissionDenied",
        )


def test_tool_result_rejects_error_without_error_class() -> None:
    with pytest.raises(ValidationError, match="error tool results require error_class"):
        ToolResult(
            tool_name="read_file",
            input_hash="xxh64:abc123",
            status="error",
            output=None,
            duration_ms=2,
        )


def test_tool_result_rejects_mismatched_success_output_type() -> None:
    with pytest.raises(
        ValidationError,
        match="output type does not match tool_name: read_file",
    ):
        ToolResult(
            tool_name="read_file",
            input_hash="xxh64:abc123",
            status="ok",
            output=RunTestsOutput(passed=True),
            duration_ms=2,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("input_hash", ""),
        ("duration_ms", -1),
        ("error_class", ""),
        ("error_message", ""),
    ],
)
def test_tool_result_rejects_invalid_common_fields(
    field_name: str,
    value: object,
) -> None:
    payload: dict[str, object] = {
        "tool_name": "read_file",
        "input_hash": "xxh64:abc123",
        "status": "error",
        "output": None,
        "duration_ms": 2,
        "error_class": "PermissionDenied",
    }
    payload[field_name] = value

    with pytest.raises(ValidationError):
        ToolResult.model_validate(payload)
