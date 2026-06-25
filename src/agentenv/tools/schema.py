from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

ToolName = Literal["read_file", "write_file", "run_tests"]
ToolResultStatus = Literal["ok", "error"]


class ReadFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)


class WriteFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    content: str


class RunTestsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1)


class ReadFileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    bytes_read: int = Field(ge=0)
    truncated: bool = False


class WriteFileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bytes_written: int = Field(ge=0)


class RunTestsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool


ToolInput = ReadFileInput | WriteFileInput | RunTestsInput
ToolOutput = ReadFileOutput | WriteFileOutput | RunTestsOutput


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    input_hash: str = Field(min_length=1)
    status: ToolResultStatus
    output: ToolOutput | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = Field(ge=0)
    error_class: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_status_consistency(self) -> "ToolResult":
        if self.status == "ok":
            if self.output is None:
                raise ValueError("ok tool results require output")
            if self.error_class is not None or self.error_message is not None:
                raise ValueError("ok tool results cannot include error fields")
            _validate_output_matches_tool(self.tool_name, self.output)
            return self

        if self.output is not None:
            raise ValueError("error tool results cannot include output")
        if self.error_class is None:
            raise ValueError("error tool results require error_class")
        return self


@dataclass(frozen=True)
class ToolDefinition:
    name: ToolName
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]


READ_FILE_TOOL = ToolDefinition(
    name="read_file",
    description="Read a text file from the prepared task workspace.",
    input_model=ReadFileInput,
    output_model=ReadFileOutput,
)
WRITE_FILE_TOOL = ToolDefinition(
    name="write_file",
    description="Write text content to a file in the prepared task workspace.",
    input_model=WriteFileInput,
    output_model=WriteFileOutput,
)
RUN_TESTS_TOOL = ToolDefinition(
    name="run_tests",
    description="Run a test command in the prepared task workspace.",
    input_model=RunTestsInput,
    output_model=RunTestsOutput,
)
TOOL_REGISTRY: dict[ToolName, ToolDefinition] = {
    "read_file": READ_FILE_TOOL,
    "write_file": WRITE_FILE_TOOL,
    "run_tests": RUN_TESTS_TOOL,
}

_READ_FILE_ADAPTER = TypeAdapter(ReadFileInput)
_WRITE_FILE_ADAPTER = TypeAdapter(WriteFileInput)
_RUN_TESTS_ADAPTER = TypeAdapter(RunTestsInput)


def validate_tool_input(tool_name: str, arguments: Mapping[str, object]) -> ToolInput:
    if tool_name == "read_file":
        return _READ_FILE_ADAPTER.validate_python(arguments)
    if tool_name == "write_file":
        return _WRITE_FILE_ADAPTER.validate_python(arguments)
    if tool_name == "run_tests":
        return _RUN_TESTS_ADAPTER.validate_python(arguments)
    raise ValueError(f"Unknown tool name: {tool_name}")


def _validate_output_matches_tool(tool_name: str, output: ToolOutput) -> None:
    if tool_name == "read_file" and isinstance(output, ReadFileOutput):
        return
    if tool_name == "write_file" and isinstance(output, WriteFileOutput):
        return
    if tool_name == "run_tests" and isinstance(output, RunTestsOutput):
        return
    raise ValueError(f"output type does not match tool_name: {tool_name}")
