import json
from pathlib import Path

import pytest

from agentenv.agents.schema import PromptLoopResult
from agentenv.controls.agent_control_scripts import (
    AGENT_CONTROL_SCRIPT_SCHEMA_VERSION,
    ExpectedAgentControlResult,
    load_agent_control_script_case,
)
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_task_run import run_agent_task_attempt


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TOY_HAPPY_PATH_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix"
    "/controls/agent_control_scripts/happy_path.json"
)
TOY_MALFORMED_JSON_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix"
    "/controls/agent_control_scripts/malformed_json.json"
)
TOY_BAD_TOOL_INPUT_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix"
    "/controls/agent_control_scripts/bad_tool_input_then_recovery.json"
)
TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
ALL_AGENT_CONTROL_CASES = sorted(
    TASK_PACK.glob("tasks/*/controls/agent_control_scripts/*.json")
)


def test_happy_path_agent_control_script_loads() -> None:
    control_case = load_agent_control_script_case(TOY_HAPPY_PATH_AGENT_CONTROL)

    assert control_case.schema_version == AGENT_CONTROL_SCRIPT_SCHEMA_VERSION
    assert len(control_case.script.steps) == 4
    assert control_case.expected_result.prompt_loop_status == "completed"


def test_agent_control_script_rejects_unknown_schema_version(tmp_path: Path) -> None:
    raw_case = json.loads(TOY_HAPPY_PATH_AGENT_CONTROL.read_text())
    raw_case["schema_version"] = "agent_control_script_v1"
    control_path = tmp_path / "control.json"
    control_path.write_text(json.dumps(raw_case))

    with pytest.raises(ValueError, match="unsupported agent control script"):
        load_agent_control_script_case(control_path)


def test_expected_tool_results_require_error_class_for_errors() -> None:
    with pytest.raises(ValueError, match="require error_class"):
        ExpectedAgentControlResult.model_validate({
            "prompt_loop_status": "completed",
            "tool_results": [
                {
                    "tool_name": "read_file",
                    "status": "error",
                }
            ],
        })


def test_expected_tool_results_reject_error_class_for_ok_results() -> None:
    with pytest.raises(ValueError, match="cannot include error_class"):
        ExpectedAgentControlResult.model_validate({
            "prompt_loop_status": "completed",
            "tool_results": [
                {
                    "tool_name": "read_file",
                    "status": "ok",
                    "error_class": "InvalidToolInput",
                }
            ],
        })


@pytest.mark.parametrize(
    "control_path",
    ALL_AGENT_CONTROL_CASES,
    ids=lambda path: f"{path.parents[2].name}/{path.stem}",
)
def test_agent_control_matches_prompt_loop_expectation(
    control_path: Path,
    tmp_path: Path,
) -> None:
    control_case = load_agent_control_script_case(control_path)
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )
    task_manifest_path = control_path.parents[2] / "task.yaml"

    agent_task_run = run_agent_task_attempt(
        task_manifest_path,
        model_client,
        model_client.default_decoding_config(),
        workspace_parent=tmp_path / "work",
    )

    assert agent_task_run.prompt_loop_result is not None
    _assert_expected_result_matches(
        control_case.expected_result,
        agent_task_run.prompt_loop_result,
    )
    assert agent_task_run.result.prompt_loop_status == (
        control_case.expected_result.prompt_loop_status
    )


def _assert_expected_result_matches(
    expected_result: ExpectedAgentControlResult,
    prompt_loop_result: PromptLoopResult,
) -> None:
    assert prompt_loop_result.status == expected_result.prompt_loop_status

    expected_tool_results = expected_result.tool_results
    if expected_tool_results is None:
        return

    assert len(prompt_loop_result.tool_results) == len(expected_tool_results)
    for actual, expected in zip(
        prompt_loop_result.tool_results,
        expected_tool_results,
        strict=True,
    ):
        assert actual.tool_name == expected.tool_name
        assert actual.status == expected.status
        assert actual.error_class == expected.error_class
