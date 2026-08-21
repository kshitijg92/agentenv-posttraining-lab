import json
from pathlib import Path

import pytest

import agentenv.orchestrators.agent_task_run as agent_task_run_module
import agentenv.orchestrators.eval_run as eval_run_module
from agentenv.artifacts.manifests import load_attempt_manifest
from agentenv.evals.suite_declaration import (
    EVAL_SUITE_DECLARATION_FILENAME,
    load_eval_suite_declaration,
)
from agentenv.models.config_schema import ModelConfig
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.models.input_protocol import LoadedModelInputProtocol
from agentenv.orchestrators.eval_run import run_eval_config_all_policies
from agentenv.runners.resume import classify_eval_suite_resume


CONTROL_EVAL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")


def _write_control_eval_config(path: Path, *, attempts: int) -> None:
    path.write_text(
        CONTROL_EVAL_CONFIG.read_text()
        .replace("attempts: 1", f"attempts: {attempts}")
        .replace("repeats: 1", "repeats: 0")
    )


def _write_agent_model_eval_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: resume_agent_model_smoke",
                "task_pack: data/task_packs/repo_patch_python_v0",
                "tasks:",
                "  - toy_python_fix_001",
                "split: practice",
                "policies:",
                "  real-agent-smoke:",
                "    type: agent_model",
                "    model_config: configs/models/openai_compatible_chat_placeholder.yaml",
                "    decoding_config: configs/decoding/greedy_1024.yaml",
                "    attempts: 1",
                "    replay:",
                "      repeats: 0",
                "trace:",
                "  version: trace_v0",
                "  capture_stdout: true",
                "  capture_stderr: true",
                "  capture_diff: true",
                "",
            ]
        )
    )


def _install_final_answer_fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = ScriptedFakeModelClient(
        model_id="resume-generation-test",
        script=[
            FakeModelScriptStep(
                output_text=json.dumps(
                    {"action": "final_answer", "text": "generation complete"}
                )
            )
        ],
    )

    def fake_build_model_client(
        config: ModelConfig,
        *,
        model_input_protocol: LoadedModelInputProtocol | None = None,
        model_config_path: Path | None = None,
    ) -> ScriptedFakeModelClient:
        del config, model_input_protocol, model_config_path
        return fake_client

    monkeypatch.setattr(
        eval_run_module,
        "build_model_client",
        fake_build_model_client,
    )


def test_resume_inventory_preserves_declared_coverage_across_attempt_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "control_eval.yaml"
    _write_control_eval_config(config_path, attempts=2)
    out_dir = tmp_path / "eval_suite"
    real_run_attempt = eval_run_module._run_scorer_eval_attempt
    call_count = 0

    def interrupt_second_attempt(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            attempt_dir = kwargs["attempt_dir"]
            attempt_dir.mkdir(parents=True)
            (attempt_dir / "partial.txt").write_text("not terminal\n")
            raise RuntimeError("injected interruption")
        return real_run_attempt(**kwargs)

    monkeypatch.setattr(
        eval_run_module,
        "_run_scorer_eval_attempt",
        interrupt_second_attempt,
    )

    with pytest.raises(RuntimeError, match="injected interruption"):
        run_eval_config_all_policies(config_path, out_dir)

    inventory = classify_eval_suite_resume(out_dir)
    declared_attempts = [
        attempt
        for policy in inventory.declaration.policy_runs
        for attempt in policy.planned_attempts
    ]

    assert len(inventory.decisions) == len(declared_attempts) == 6
    assert [decision.eval_attempt_id for decision in inventory.decisions] == [
        attempt.eval_attempt_id for attempt in declared_attempts
    ]
    assert [decision.action for decision in inventory.decisions] == [
        "reuse_completed_attempt",
        "run_attempt",
        "run_attempt",
        "run_attempt",
        "run_attempt",
        "run_attempt",
    ]
    assert [decision.reason for decision in inventory.decisions] == [
        "completed_attempt",
        "incomplete_without_terminal_result",
        "not_started",
        "not_started",
        "not_started",
        "not_started",
    ]

    first_manifest = load_attempt_manifest(
        inventory.decisions[0].attempt_dir / "manifest.json"
    )
    assert first_manifest.eval_attempt is not None
    assert (
        first_manifest.eval_attempt.eval_attempt_id
        == inventory.decisions[0].eval_attempt_id
    )


def test_resume_inventory_reuses_valid_generation_and_rejects_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "agent_model_eval.yaml"
    _write_agent_model_eval_config(config_path)
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.delenv("AGENTENV_MODEL_API_KEY", raising=False)
    _install_final_answer_fake_model(monkeypatch)

    def interrupt_scorer(*args, **kwargs):
        del args, kwargs
        raise KeyboardInterrupt("injected after generation")

    monkeypatch.setattr(
        agent_task_run_module,
        "run_patch_attempt",
        interrupt_scorer,
    )
    out_dir = tmp_path / "eval_suite"

    with pytest.raises(KeyboardInterrupt, match="injected after generation"):
        run_eval_config_all_policies(config_path, out_dir)

    inventory = classify_eval_suite_resume(out_dir)
    assert len(inventory.decisions) == 1
    assert inventory.decisions[0].action == "reuse_completed_generation"
    assert inventory.decisions[0].reason == "terminal_generation"

    candidate_path = inventory.decisions[0].attempt_dir / "candidate.patch"
    candidate_path.write_text("# changed after terminal generation\n")

    corrupt_inventory = classify_eval_suite_resume(out_dir)
    assert corrupt_inventory.decisions[0].action == "reject_attempt"
    assert corrupt_inventory.decisions[0].reason == "invalid_terminal_generation"
    assert "hash mismatch" in (corrupt_inventory.decisions[0].detail or "")


def test_resume_inventory_rejects_only_the_corrupt_completed_attempt(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "control_eval.yaml"
    _write_control_eval_config(config_path, attempts=1)
    out_dir = tmp_path / "eval_suite"
    run_eval_config_all_policies(config_path, out_dir)

    clean_inventory = classify_eval_suite_resume(out_dir)
    assert {decision.action for decision in clean_inventory.decisions} == {
        "reuse_completed_attempt"
    }
    corrupt_attempt_path = clean_inventory.decisions[0].attempt_dir / "attempt.json"
    corrupt_attempt_path.write_text("{}\n")

    inventory = classify_eval_suite_resume(out_dir)
    assert [decision.action for decision in inventory.decisions] == [
        "reject_attempt",
        "reuse_completed_attempt",
        "reuse_completed_attempt",
    ]
    assert inventory.decisions[0].reason == "invalid_completed_attempt"
    assert all(
        decision.eval_attempt_id
        for decision in inventory.decisions
    )


def test_resume_inventory_rejects_global_semantic_input_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "control_eval.yaml"
    _write_control_eval_config(config_path, attempts=1)
    out_dir = tmp_path / "eval_suite"

    def interrupt_before_first_attempt(**kwargs):
        del kwargs
        raise RuntimeError("injected before first attempt")

    monkeypatch.setattr(
        eval_run_module,
        "_run_scorer_eval_attempt",
        interrupt_before_first_attempt,
    )
    with pytest.raises(RuntimeError, match="injected before first attempt"):
        run_eval_config_all_policies(config_path, out_dir)

    declaration_path = out_dir / EVAL_SUITE_DECLARATION_FILENAME
    declaration = load_eval_suite_declaration(declaration_path)
    real_capture_runtime = eval_run_module.capture_harness_runtime_provenance
    changed_runtime = declaration.runtime_provenance.model_copy(
        update={
            "python_version": f"{declaration.runtime_provenance.python_version}-changed"
        }
    )
    monkeypatch.setattr(
        eval_run_module,
        "capture_harness_runtime_provenance",
        lambda _repo_root: changed_runtime,
    )
    with pytest.raises(ValueError, match="Harness runtime changed"):
        classify_eval_suite_resume(out_dir)

    monkeypatch.setattr(
        eval_run_module,
        "capture_harness_runtime_provenance",
        real_capture_runtime,
    )
    real_build_task_hashes = eval_run_module.build_eval_task_hashes
    changed_task_hashes = declaration.task_hashes.model_copy(
        update={"selected_task_hash_set": "xxh64:0000000000000000"}
    )
    monkeypatch.setattr(
        eval_run_module,
        "build_eval_task_hashes",
        lambda *_args, **_kwargs: changed_task_hashes,
    )
    with pytest.raises(ValueError, match="Task bytes changed"):
        classify_eval_suite_resume(out_dir)

    monkeypatch.setattr(
        eval_run_module,
        "build_eval_task_hashes",
        real_build_task_hashes,
    )
    config_path.write_text(config_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Eval config changed"):
        classify_eval_suite_resume(out_dir)
