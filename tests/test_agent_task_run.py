import json
from pathlib import Path

import pytest

from agentenv.agents.schema import AgentTaskView, PromptLoopResult, TokenUsage
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.models.schema import DecodingConfig, Message, ModelResponse
from agentenv.orchestrators.agent_task_run import (
    AGENT_TASK_RUN_ORCHESTRATOR_VERSION,
    AgentTaskRun,
    AgentTaskRunErrorDetails,
    AgentTaskRunResult,
    run_and_persist_agent_task_attempt_to_dir,
    run_agent_task_attempt,
    write_agent_task_run_artifacts,
)
from agentenv.runners.diff_runner import hash_diff
from agentenv.security.secrets import REDACTED_SECRET
from agentenv.tools.schema import ToolResult


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
PUBLIC_CHECK_COMMAND = "uv run pytest tests/test_public.py"
CANARY = "agentenv-canary-secret-000000000000"
FIXED_MATHLIB = (
    "def normalize_ratio(numerator: int | float, denominator: int | float) -> float:\n"
    "    \"\"\"Return numerator divided by denominator as a normalized ratio.\"\"\"\n"
    "    if denominator == 0:\n"
    "        raise ValueError(\"denominator must not be zero\")\n"
    "    return float(numerator / denominator)\n"
)


def _decoding_config() -> DecodingConfig:
    return DecodingConfig(
        strategy="greedy",
        temperature=0.0,
        top_p=1.0,
        max_new_tokens=512,
        timeout_seconds=30,
    )


def _action(payload: object) -> str:
    return json.dumps(payload)


def test_run_agent_task_attempt_scores_fake_agent_patch_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    model_client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {"path": "src/mathlib.py"},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "src/mathlib.py",
                        "content": FIXED_MATHLIB,
                    },
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "run_tests",
                    "arguments": {"command": PUBLIC_CHECK_COMMAND},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ],
    )

    agent_task_run = run_agent_task_attempt(
        TOY_TASK_MANIFEST,
        model_client,
        _decoding_config(),
        workspace_parent=tmp_path / "work",
    )

    assert agent_task_run.result.status == "scored"
    assert agent_task_run.result.task_id == "toy_python_fix_001"
    assert agent_task_run.result.prompt_loop_status == "completed"
    assert agent_task_run.result.attempt_result is not None
    assert agent_task_run.result.attempt_result.status == "PASS"
    assert agent_task_run.result.attempt_result.public_status == "PASS"
    assert agent_task_run.result.attempt_result.hidden_status == "PASS"
    assert agent_task_run.agent_task_view is not None
    assert agent_task_run.agent_task_view.allowed_tools == [
        "list_files",
        "read_file",
        "write_file",
        "run_tests",
    ]
    assert agent_task_run.prompt_loop_result is not None
    assert agent_task_run.prompt_loop_result.status == "completed"
    assert agent_task_run.attempt_run is not None
    assert agent_task_run.attempt_run.result.status == "PASS"
    assert agent_task_run.attempt_run.result.public_status == "PASS"
    assert agent_task_run.attempt_run.result.hidden_status == "PASS"
    assert agent_task_run.candidate_patch
    assert "src/mathlib.py" in agent_task_run.candidate_patch
    assert "raise ValueError" in agent_task_run.candidate_patch
    assert agent_task_run.result.candidate_patch_hash == hash_diff(
        agent_task_run.candidate_patch
    )
    assert agent_task_run.attempt_run.final_diff == agent_task_run.candidate_patch

    artifact_paths = write_agent_task_run_artifacts(
        agent_task_run,
        tmp_path / "out",
    )

    assert artifact_paths.manifest_json == tmp_path / "out/manifest.json"
    assert artifact_paths.agent_task_run_json == tmp_path / "out/agent_task_run.json"
    assert artifact_paths.decoding_config_json is None
    assert artifact_paths.agent_control_script_json is None
    assert artifact_paths.agent_task_view_json == tmp_path / "out/agent_task_view.json"
    assert (
        artifact_paths.prompt_loop_result_json
        == tmp_path / "out/prompt_loop_result.json"
    )
    assert artifact_paths.candidate_patch == tmp_path / "out/candidate.patch"
    assert artifact_paths.error_txt == tmp_path / "out/error.txt"
    assert artifact_paths.attempt_dir == tmp_path / "out/attempt"
    assert artifact_paths.attempt_artifacts is not None
    assert artifact_paths.agent_task_view_json is not None
    assert artifact_paths.prompt_loop_result_json is not None
    assert artifact_paths.candidate_patch is not None
    assert artifact_paths.attempt_artifacts.attempt_json == (
        tmp_path / "out/attempt/attempt.json"
    )
    assert artifact_paths.attempt_artifacts.final_diff == (
        tmp_path / "out/attempt/final.diff"
    )

    run_manifest = json.loads(artifact_paths.manifest_json.read_text())
    agent_task_result = json.loads(artifact_paths.agent_task_run_json.read_text())
    agent_task_view = json.loads(artifact_paths.agent_task_view_json.read_text())
    prompt_loop_result = json.loads(
        artifact_paths.prompt_loop_result_json.read_text()
    )
    attempt_result = json.loads(artifact_paths.attempt_artifacts.attempt_json.read_text())

    assert run_manifest["artifact_type"] == "agent_attempt"
    assert run_manifest["artifact_schema_version"] == "agent_attempt_artifact_v0"
    assert (
        run_manifest["orchestrator_version"]
        == AGENT_TASK_RUN_ORCHESTRATOR_VERSION
    )
    assert run_manifest["status"] == "scored"
    assert run_manifest["prompt_loop_status"] == "completed"
    assert run_manifest["attempt_status"] == "PASS"
    assert run_manifest["agent_attempt_id"].startswith("agent_attempt_")
    assert "run_id" not in run_manifest
    assert run_manifest["artifacts"]["attempt"] == "attempt/"
    assert (
        agent_task_result["orchestrator_version"]
        == AGENT_TASK_RUN_ORCHESTRATOR_VERSION
    )
    assert (
        agent_task_result["agent_attempt_id"] == run_manifest["agent_attempt_id"]
    )
    assert "run_id" not in agent_task_result
    assert agent_task_result["attempt_result"]["status"] == "PASS"
    assert agent_task_result["attempt_result"]["public_status"] == "PASS"
    assert agent_task_result["attempt_result"]["hidden_status"] == "PASS"
    assert agent_task_result["candidate_patch_hash"] == hash_diff(
        artifact_paths.candidate_patch.read_text()
    )
    assert agent_task_view["allowed_tools"] == [
        "list_files",
        "read_file",
        "write_file",
        "run_tests",
    ]
    assert prompt_loop_result["status"] == "completed"
    assert attempt_result["status"] == "PASS"
    assert artifact_paths.candidate_patch.read_text() == agent_task_run.candidate_patch
    assert artifact_paths.attempt_artifacts.final_diff.read_text() == (
        agent_task_run.candidate_patch
    )
    assert artifact_paths.error_txt.read_text() == ""


def test_run_agent_task_attempt_does_not_score_failed_prompt_loop(
    tmp_path: Path,
) -> None:
    model_client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(output_text="{not valid json"),
        ],
    )

    agent_task_run = run_agent_task_attempt(
        TOY_TASK_MANIFEST,
        model_client,
        _decoding_config(),
        workspace_parent=tmp_path / "work",
    )

    assert agent_task_run.result.status == "agent_loop_failed"
    assert agent_task_run.result.prompt_loop_status == "invalid_model_output"
    assert agent_task_run.result.candidate_patch_path is None
    assert agent_task_run.result.candidate_patch_hash is None
    assert agent_task_run.result.attempt_result is None
    assert agent_task_run.agent_task_view is not None
    assert agent_task_run.prompt_loop_result is not None
    assert agent_task_run.prompt_loop_result.status == "invalid_model_output"
    assert agent_task_run.candidate_patch == ""
    assert agent_task_run.attempt_run is None

    artifact_paths = write_agent_task_run_artifacts(
        agent_task_run,
        tmp_path / "out",
    )

    run_manifest = json.loads(artifact_paths.manifest_json.read_text())
    agent_task_result = json.loads(artifact_paths.agent_task_run_json.read_text())
    assert artifact_paths.prompt_loop_result_json is not None
    prompt_loop_result = json.loads(
        artifact_paths.prompt_loop_result_json.read_text()
    )

    assert artifact_paths.candidate_patch is None
    assert artifact_paths.attempt_dir is None
    assert artifact_paths.attempt_artifacts is None
    assert run_manifest["status"] == "agent_loop_failed"
    assert run_manifest["prompt_loop_status"] == "invalid_model_output"
    assert run_manifest["agent_attempt_id"].startswith("agent_attempt_")
    assert "run_id" not in run_manifest
    assert "candidate_patch" not in run_manifest["artifacts"]
    assert "attempt" not in run_manifest["artifacts"]
    assert (
        agent_task_result["agent_attempt_id"] == run_manifest["agent_attempt_id"]
    )
    assert "run_id" not in agent_task_result
    assert agent_task_result["attempt_result"] is None
    assert prompt_loop_result["status"] == "invalid_model_output"


def test_write_agent_task_run_artifacts_redacts_secret_canary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTENV_MODEL_API_KEY", CANARY)
    agent_task_run = AgentTaskRun(
        result=AgentTaskRunResult(
            agent_attempt_id="agent_attempt_001",
            task_id="task_001",
            task_manifest_path=f"tasks/{CANARY}/task.yaml",
            status="agent_loop_failed",
            prompt_loop_status="model_error",
            candidate_patch_path=None,
            candidate_patch_hash=None,
            attempt_result=None,
            error_class="ProviderHTTPError",
            error_message=f"agent result {CANARY}",
            started_at="2026-06-19T00:00:00Z",
            ended_at="2026-06-19T00:00:01Z",
            duration_ms=1,
            orchestrator_version=AGENT_TASK_RUN_ORCHESTRATOR_VERSION,
        ),
        agent_task_view=AgentTaskView(
            task_id="task_001",
            instruction=f"instruction {CANARY}",
            workspace_path=tmp_path / "workspace",
            allowed_tools=["run_tests"],
            public_checks=[f"python -c 'print(\"{CANARY}\")'"],
            max_turns=1,
            timeout_seconds=5,
            network="off",
        ),
        prompt_loop_result=PromptLoopResult(
            task_id="task_001",
            status="model_error",
            turns_executed=1,
            duration_ms=1,
            token_usage=TokenUsage(),
            messages=[
                Message(
                    role="assistant",
                    content=f"assistant {CANARY}",
                    name="fake-model",
                )
            ],
            model_responses=[
                ModelResponse(
                    model_id="fake-model",
                    output_text=f"model output {CANARY}",
                    finish_reason="error",
                    latency_ms=1,
                    error_class="ProviderHTTPError",
                    error_message=f"model error {CANARY}",
                    raw_response_ref="provider_response/not_persisted",
                )
            ],
            tool_results=[
                ToolResult(
                    tool_name="run_tests",
                    input_hash="xxh64:abc123",
                    status="error",
                    stdout=f"stdout {CANARY}",
                    stderr=f"stderr {CANARY}",
                    exit_code=1,
                    duration_ms=1,
                    error_class="ToolExecutionError",
                    error_message=f"tool error {CANARY}",
                )
            ],
            error_class="ProviderHTTPError",
            error_message=f"prompt loop {CANARY}",
        ),
        candidate_patch="",
        attempt_run=None,
        error_details=AgentTaskRunErrorDetails(
            error_class="ProviderHTTPError",
            message=f"agent details {CANARY}",
            traceback=f"traceback {CANARY}",
        ),
    )

    artifact_paths = write_agent_task_run_artifacts(agent_task_run, tmp_path / "out")
    written_text = "\n".join(
        path.read_text()
        for path in [
            artifact_paths.manifest_json,
            artifact_paths.agent_task_run_json,
            artifact_paths.agent_task_view_json,
            artifact_paths.prompt_loop_result_json,
            artifact_paths.error_txt,
        ]
        if path is not None
    )

    assert CANARY not in written_text
    assert REDACTED_SECRET in artifact_paths.agent_task_run_json.read_text()
    assert artifact_paths.agent_task_view_json is not None
    assert REDACTED_SECRET in artifact_paths.agent_task_view_json.read_text()
    assert artifact_paths.prompt_loop_result_json is not None
    assert REDACTED_SECRET in artifact_paths.prompt_loop_result_json.read_text()
    assert REDACTED_SECRET in artifact_paths.error_txt.read_text()


def test_run_and_persist_agent_task_attempt_keeps_scratch_out_of_artifacts(
    tmp_path: Path,
) -> None:
    model_client = ScriptedFakeModelClient(
        model_id="fake-scripted-v0",
        script=[
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "read_file",
                    "arguments": {"path": "src/mathlib.py"},
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "tool_call",
                    "tool_name": "write_file",
                    "arguments": {
                        "path": "src/mathlib.py",
                        "content": FIXED_MATHLIB,
                    },
                }),
            ),
            FakeModelScriptStep(
                output_text=_action({
                    "action": "final_answer",
                    "text": "done",
                }),
            ),
        ],
    )
    out_dir = tmp_path / "out"
    agent_control_script = {"schema_version": "test_agent_control_script_v0"}

    agent_task_run = run_and_persist_agent_task_attempt_to_dir(
        TOY_TASK_MANIFEST,
        model_client,
        _decoding_config(),
        out_dir,
        agent_control_script=agent_control_script,
    )

    run_manifest = json.loads((out_dir / "manifest.json").read_text())
    assert agent_task_run.result.prompt_loop_status == "completed"
    assert (out_dir / "agent_task_run.json").is_file()
    assert (out_dir / "decoding_config.json").is_file()
    assert (out_dir / "agent_control_script.json").is_file()
    assert (out_dir / "prompt_loop_result.json").is_file()
    assert run_manifest["artifacts"]["decoding_config"] == "decoding_config.json"
    assert (
        run_manifest["artifacts"]["agent_control_script"]
        == "agent_control_script.json"
    )
    decoding_artifact = json.loads((out_dir / "decoding_config.json").read_text())
    assert decoding_artifact["source_path"] is None
    assert decoding_artifact["source_hash"] is None
    assert decoding_artifact["config"]["max_new_tokens"] == 512
    assert decoding_artifact["config"]["timeout_seconds"] == 30
    assert json.loads((out_dir / "agent_control_script.json").read_text()) == (
        agent_control_script
    )
    assert not (out_dir / "work").exists()
    assert not (out_dir / "agent_interaction_workspace").exists()
    assert not (out_dir / "scoring_workspace").exists()
