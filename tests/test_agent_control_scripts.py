import json
from pathlib import Path

import pytest

from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig
from agentenv.orchestrators.agent_control_scripts import (
    AGENT_CONTROL_SCRIPT_SCHEMA_VERSION,
    load_agent_control_script_case,
)
from agentenv.orchestrators.agent_task_run import run_agent_task_attempt


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TOY_HAPPY_PATH_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix"
    "/controls/agent_control_scripts/happy_path.json"
)


def _decoding_config() -> DecodingConfig:
    return DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=512,
        timeout_seconds=30,
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


def test_happy_path_agent_control_matches_prompt_loop_expectation(
    tmp_path: Path,
) -> None:
    control_case = load_agent_control_script_case(TOY_HAPPY_PATH_AGENT_CONTROL)
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )

    agent_task_run = run_agent_task_attempt(
        TOY_TASK_MANIFEST,
        model_client,
        _decoding_config(),
        workspace_parent=tmp_path / "work",
    )

    assert agent_task_run.prompt_loop_result is not None
    assert agent_task_run.prompt_loop_result.status == (
        control_case.expected_result.prompt_loop_status
    )
    assert agent_task_run.result.prompt_loop_status == (
        control_case.expected_result.prompt_loop_status
    )
