from pathlib import Path

from agentenv.agents.schema import (
    AgentActionValue,
    PromptLoopResult,
    TokenUsage,
    ToolCallAction,
)
from agentenv.agents.tool_messages import render_tool_result_message
from agentenv.controls.public_check_idempotency_schema import (
    PUBLIC_CHECK_IDEMPOTENCY_CALIBRATION_SCHEMA_VERSION,
    PublicCheckIdempotencyCalibration,
)
from agentenv.hashing import hash_file
from agentenv.models.schema import Message
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest
from agentenv.tools.hashing import hash_tool_input
from agentenv.tools.schema import (
    ReadFileOutput,
    RunTestsOutput,
    ToolOutput,
    ToolResult,
    WriteFileOutput,
    validate_tool_input,
)
from agentenv.training.mechanical_redundancy import (
    assess_prompt_loop_mechanical_redundancy,
)


TASK_MANIFEST_PATH = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TASK_MANIFEST = load_task_manifest(TASK_MANIFEST_PATH)
TASK_MANIFEST_HASH = hash_file(TASK_MANIFEST_PATH)
PUBLIC_CHECK_COMMAND = TASK_MANIFEST.public_checks[0].command


def test_consecutive_identical_reads_form_one_maximal_block() -> None:
    calls = [
        _successful_call(
            "read_file",
            {"path": "src/mathlib.py"},
            ReadFileOutput(content="same", bytes_read=4),
            before="xxh64:state",
            after="xxh64:state",
        )
        for _ in range(3)
    ]

    assessment = _assess(calls)

    assert assessment.evaluation_status == "complete"
    assert assessment.detector_version == "mechanical_redundancy_detector_v0"
    assert assessment.detector_code_hash.startswith("xxh64:")
    assert len(assessment.blocks) == 1
    block = assessment.blocks[0]
    assert block.tool_name == "read_file"
    assert block.baseline_tool_call_id == "tool_call_0001"
    assert block.redundant_tool_call_ids == [
        "tool_call_0002",
        "tool_call_0003",
    ]
    assert block.redundant_call_count == 2
    assert block.stable_workspace_hash == "xxh64:state"
    assert block.public_check_index is None


def test_repeated_write_is_redundant_after_first_write_establishes_state() -> None:
    calls = [
        _successful_call(
            "write_file",
            {"path": "src/mathlib.py", "content": "replacement\n"},
            WriteFileOutput(bytes_written=12),
            before="xxh64:before",
            after="xxh64:written",
        ),
        _successful_call(
            "write_file",
            {"path": "src/mathlib.py", "content": "replacement\n"},
            WriteFileOutput(bytes_written=12),
            before="xxh64:written",
            after="xxh64:written",
        ),
    ]

    assessment = _assess(calls)

    assert assessment.evaluation_status == "complete"
    assert len(assessment.blocks) == 1
    assert assessment.blocks[0].stable_workspace_hash == "xxh64:written"


def test_nonconsecutive_identical_calls_do_not_form_a_block() -> None:
    calls = [
        _read_call("src/a.py"),
        _read_call("src/b.py"),
        _read_call("src/a.py"),
    ]

    assessment = _assess(calls)

    assert assessment.evaluation_status == "complete"
    assert assessment.blocks == []


def test_changed_observation_does_not_form_a_non_test_block() -> None:
    calls = [
        _successful_call(
            "read_file",
            {"path": "src/mathlib.py"},
            ReadFileOutput(content="first", bytes_read=5),
            before="xxh64:state",
            after="xxh64:state",
        ),
        _successful_call(
            "read_file",
            {"path": "src/mathlib.py"},
            ReadFileOutput(content="second", bytes_read=6),
            before="xxh64:state",
            after="xxh64:state",
        ),
    ]

    assessment = _assess(calls)

    assert assessment.evaluation_status == "complete"
    assert assessment.blocks == []


def test_repeated_tool_errors_do_not_form_a_block() -> None:
    calls = [
        _error_call("read_file", {"path": "missing.py"}),
        _error_call("read_file", {"path": "missing.py"}),
    ]

    assessment = _assess(calls)

    assert assessment.evaluation_status == "complete"
    assert assessment.blocks == []


def test_repeated_successful_failing_public_check_is_redundant_when_calibrated() -> (
    None
):
    calls = [
        _successful_call(
            "run_tests",
            {"command": PUBLIC_CHECK_COMMAND},
            RunTestsOutput(passed=False),
            before="xxh64:state",
            after="xxh64:state",
            stdout="first timing",
            exit_code=1,
        ),
        _successful_call(
            "run_tests",
            {"command": PUBLIC_CHECK_COMMAND},
            RunTestsOutput(passed=False),
            before="xxh64:state",
            after="xxh64:state",
            stdout="different hidden timing",
            exit_code=1,
        ),
    ]

    assessment = _assess(calls, calibrations=(_idempotent_calibration(),))

    assert assessment.evaluation_status == "complete"
    assert len(assessment.blocks) == 1
    block = assessment.blocks[0]
    assert block.tool_name == "run_tests"
    assert block.public_check_index == 0
    assert block.redundant_call_count == 1


def test_repeated_public_check_without_calibration_is_incomplete() -> None:
    calls = [_failing_test_call(), _failing_test_call()]

    assessment = _assess(calls)

    assert assessment.evaluation_status == "incomplete"
    assert assessment.blocks == []
    assert assessment.error_class == "MissingTrustedPublicCheckCalibration"


def test_calibrated_public_check_runtime_drift_is_incomplete() -> None:
    calls = [
        _failing_test_call(),
        _successful_call(
            "run_tests",
            {"command": PUBLIC_CHECK_COMMAND},
            RunTestsOutput(passed=True),
            before="xxh64:state",
            after="xxh64:state",
            exit_code=0,
        ),
    ]

    assessment = _assess(calls, calibrations=(_idempotent_calibration(),))

    assert assessment.evaluation_status == "incomplete"
    assert assessment.blocks == []
    assert assessment.error_class == "CalibratedPublicCheckRuntimeDrift"


def test_repeated_public_check_declared_non_idempotent_is_not_labeled() -> None:
    payload = TASK_MANIFEST.model_dump(mode="json")
    payload["public_checks"][0]["are_tests_idempotent"] = False
    task_manifest = TaskManifest.model_validate(payload)
    calls = [_failing_test_call(), _failing_test_call()]

    assessment = _assess(calls, task_manifest=task_manifest)

    assert assessment.evaluation_status == "complete"
    assert assessment.blocks == []


def _assess(
    calls: list[tuple[ToolCallAction, ToolResult]],
    *,
    task_manifest: TaskManifest = TASK_MANIFEST,
    calibrations: tuple[PublicCheckIdempotencyCalibration, ...] = (),
):
    return assess_prompt_loop_mechanical_redundancy(
        _prompt_loop_result(calls, task_id=task_manifest.id),
        task_manifest=task_manifest,
        task_manifest_hash=TASK_MANIFEST_HASH,
        public_check_calibrations=calibrations,
    )


def _prompt_loop_result(
    calls: list[tuple[ToolCallAction, ToolResult]],
    *,
    task_id: str,
) -> PromptLoopResult:
    messages: list[Message] = []
    for index, (action, result) in enumerate(calls, start=1):
        tool_call_id = f"tool_call_{index:04d}"
        messages.append(
            Message(
                role="assistant",
                content=action.model_dump_json(),
                tool_call_id=tool_call_id,
            )
        )
        messages.append(render_tool_result_message(result, tool_call_id))
    return PromptLoopResult(
        task_id=task_id,
        prompt_builder_version="test_prompt_v0",
        prompt_builder_code_hash="xxh64:prompt",
        status="completed",
        turns_executed=len(calls),
        duration_ms=0,
        token_usage=TokenUsage(),
        messages=messages,
        model_responses=[],
        tool_results=[result for _action, result in calls],
    )


def _successful_call(
    tool_name: str,
    arguments: dict[str, AgentActionValue],
    output: ToolOutput,
    *,
    before: str,
    after: str,
    stdout: str = "",
    exit_code: int | None = None,
) -> tuple[ToolCallAction, ToolResult]:
    action = ToolCallAction(
        action="tool_call",
        tool_name=tool_name,
        arguments=arguments,
    )
    tool_input = validate_tool_input(tool_name, arguments)
    return action, ToolResult(
        tool_name=tool_name,
        arguments_hash=hash_tool_input(tool_input),
        canonical_workspace_hash_before=before,
        canonical_workspace_hash_after=after,
        status="ok",
        output=output,
        stdout=stdout,
        exit_code=exit_code,
        duration_ms=1,
    )


def _error_call(
    tool_name: str,
    arguments: dict[str, AgentActionValue],
) -> tuple[ToolCallAction, ToolResult]:
    action = ToolCallAction(
        action="tool_call",
        tool_name=tool_name,
        arguments=arguments,
    )
    tool_input = validate_tool_input(tool_name, arguments)
    return action, ToolResult(
        tool_name=tool_name,
        arguments_hash=hash_tool_input(tool_input),
        canonical_workspace_hash_before="xxh64:state",
        canonical_workspace_hash_after="xxh64:state",
        status="error",
        output=None,
        duration_ms=1,
        error_class="ToolExecutionError",
        error_message="tool failed",
    )


def _read_call(path: str) -> tuple[ToolCallAction, ToolResult]:
    return _successful_call(
        "read_file",
        {"path": path},
        ReadFileOutput(content=path, bytes_read=len(path.encode())),
        before="xxh64:state",
        after="xxh64:state",
    )


def _failing_test_call() -> tuple[ToolCallAction, ToolResult]:
    return _successful_call(
        "run_tests",
        {"command": PUBLIC_CHECK_COMMAND},
        RunTestsOutput(passed=False),
        before="xxh64:state",
        after="xxh64:state",
        exit_code=1,
    )


def _idempotent_calibration() -> PublicCheckIdempotencyCalibration:
    runs = [
        {
            "run_index": index,
            "canonical_workspace_hash_before": "xxh64:state",
            "canonical_workspace_hash_after": "xxh64:state",
            "status": "COMPLETED",
            "exit_code": 1,
            "stdout": {
                "path": f"runs/{index}/stdout.txt",
                "content_hash": f"xxh64:stdout{index}",
            },
            "stderr": {
                "path": f"runs/{index}/stderr.txt",
                "content_hash": f"xxh64:stderr{index}",
            },
            "normalized_result_hash": "xxh64:normalized",
        }
        for index in range(2)
    ]
    return PublicCheckIdempotencyCalibration.model_validate(
        {
            "schema_version": PUBLIC_CHECK_IDEMPOTENCY_CALIBRATION_SCHEMA_VERSION,
            "task_id": TASK_MANIFEST.id,
            "task_manifest_hash": TASK_MANIFEST_HASH,
            "public_check_index": 0,
            "command": PUBLIC_CHECK_COMMAND,
            "normalizer_version": "test_normalizer_v0",
            "normalizer_code_hash": "xxh64:normalizer",
            "normalization_context": {
                "workspace_root": "/workspace",
                "runner_temp_root": "/runner-temp",
            },
            "repeat_count": 2,
            "status": "IDEMPOTENT",
            "non_idempotency_reasons": [],
            "runs": runs,
        }
    )
