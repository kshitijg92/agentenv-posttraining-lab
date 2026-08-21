import json
import shutil
from pathlib import Path
from subprocess import TimeoutExpired

import pytest

import agentenv.orchestrators.agent_task_run as agent_task_run_module
import agentenv.orchestrators.attempt as attempt_module
import agentenv.orchestrators.eval_run as eval_run_module
import agentenv.runners.resume as resume_module
from agentenv.artifacts.manifests import (
    AgentTaskRunManifest,
    ScorerAttemptManifest,
    load_attempt_manifest,
)
from agentenv.evals.suite_declaration import (
    EVAL_SUITE_DECLARATION_FILENAME,
    load_eval_suite_declaration,
)
from agentenv.models.config_schema import ModelConfig
from agentenv.models.fake import FakeModelScriptStep, ScriptedFakeModelClient
from agentenv.models.input_protocol import LoadedModelInputProtocol
from agentenv.orchestrators.eval_run import run_eval_config_all_policies
from agentenv.runners.resume import classify_eval_suite_resume, resume_eval_suite


CONTROL_EVAL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")


def _write_control_eval_config(
    path: Path,
    *,
    attempts: int,
    replay_repeats: int = 0,
) -> None:
    path.write_text(
        CONTROL_EVAL_CONFIG.read_text()
        .replace("attempts: 1", f"attempts: {attempts}")
        .replace("repeats: 1", f"repeats: {replay_repeats}")
    )


def _write_oracle_eval_config(
    path: Path,
    *,
    attempts: int = 1,
    task_ids: tuple[str, ...] = ("toy_python_fix_001",),
    task_pack: str = "data/task_packs/repo_patch_python_v0",
) -> None:
    path.write_text(
        "\n".join(
            [
                "name: resume_failure_injection",
                f"task_pack: {json.dumps(task_pack)}",
                "tasks:",
                *(f"  - {json.dumps(task_id)}" for task_id in task_ids),
                "split: practice",
                "policies:",
                "  oracle:",
                "    type: scorer_control_patch",
                "    control: oracle",
                f"    attempts: {attempts}",
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
    assert all(decision.eval_attempt_id for decision in inventory.decisions)


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


def test_resume_executor_preserves_completed_attempts_and_fills_declared_gaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "control_eval.yaml"
    _write_control_eval_config(config_path, attempts=2, replay_repeats=1)
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

    inventory_before = classify_eval_suite_resume(out_dir)
    first_attempt_dir = inventory_before.decisions[0].attempt_dir
    first_manifest_before = load_attempt_manifest(first_attempt_dir / "manifest.json")
    partial_path = inventory_before.decisions[1].attempt_dir / "partial.txt"
    assert partial_path.is_file()

    resumed = resume_eval_suite(out_dir)

    assert resumed.status == "completed"
    assert resumed.eval_matrix is not None
    assert len(resumed.eval_matrix.policy_runs) == 3
    assert len(resumed.eval_matrix.policy_runs[0].attempts) == 2
    assert len(resumed.replay_runs) == 3
    assert all(record.replay_run.status == "PASS" for record in resumed.replay_runs)
    assert (out_dir / "manifest.json").is_file()
    assert not partial_path.exists()
    assert {decision.action for decision in resumed.inventory_after.decisions} == {
        "reuse_completed_attempt"
    }
    first_manifest_after = load_attempt_manifest(first_attempt_dir / "manifest.json")
    assert first_manifest_after == first_manifest_before


def test_resume_executor_finishes_generation_without_another_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "agent_model_eval.yaml"
    _write_agent_model_eval_config(config_path)
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.delenv("AGENTENV_MODEL_API_KEY", raising=False)
    _install_final_answer_fake_model(monkeypatch)
    real_run_patch_attempt = agent_task_run_module.run_patch_attempt

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

    inventory_before = classify_eval_suite_resume(out_dir)
    attempt_dir = inventory_before.decisions[0].attempt_dir
    generation_payload = json.loads(
        (attempt_dir / "agent_generation_manifest.json").read_text()
    )
    monkeypatch.setattr(
        agent_task_run_module,
        "run_patch_attempt",
        real_run_patch_attempt,
    )

    def fail_if_model_is_built(*args, **kwargs):
        del args, kwargs
        raise AssertionError("resume must not prepare or call the model")

    monkeypatch.setattr(
        eval_run_module,
        "build_model_client",
        fail_if_model_is_built,
    )
    resumed = resume_eval_suite(out_dir)

    final_manifest = load_attempt_manifest(attempt_dir / "manifest.json")
    assert resumed.status == "completed"
    assert resumed.inventory_before.decisions[0].action == (
        "reuse_completed_generation"
    )
    assert resumed.inventory_after.decisions[0].action == ("reuse_completed_attempt")
    assert isinstance(final_manifest, AgentTaskRunManifest)
    assert final_manifest.agent_attempt_id == generation_payload["agent_attempt_id"]
    assert final_manifest.eval_attempt is not None
    assert (
        final_manifest.eval_attempt.model_dump(mode="json")
        == (generation_payload["eval_attempt"])
    )


def test_resume_executor_keeps_typed_model_timeout_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "agent_model_eval.yaml"
    _write_agent_model_eval_config(config_path)
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.delenv("AGENTENV_MODEL_API_KEY", raising=False)
    failed_client = ScriptedFakeModelClient(
        model_id="resume-terminal-timeout-test",
        script=[
            FakeModelScriptStep(
                output_text="",
                finish_reason="timeout",
                error_class="InjectedModelTimeout",
            )
        ],
    )
    monkeypatch.setattr(
        eval_run_module,
        "build_model_client",
        lambda *args, **kwargs: failed_client,
    )
    real_finish = agent_task_run_module._finish_agent_task_attempt

    def interrupt_after_generation(*args, **kwargs):
        del args, kwargs
        raise KeyboardInterrupt("injected after failed generation")

    monkeypatch.setattr(
        agent_task_run_module,
        "_finish_agent_task_attempt",
        interrupt_after_generation,
    )
    out_dir = tmp_path / "eval_suite"
    with pytest.raises(KeyboardInterrupt, match="injected after failed generation"):
        run_eval_config_all_policies(config_path, out_dir)

    inventory_before = classify_eval_suite_resume(out_dir)
    attempt_dir = inventory_before.decisions[0].attempt_dir
    generation_payload = json.loads(
        (attempt_dir / "agent_generation_manifest.json").read_text()
    )
    assert generation_payload["prompt_loop_status"] == "model_error"
    prompt_loop_payload = json.loads(
        (attempt_dir / "prompt_loop_result.json").read_text()
    )
    assert prompt_loop_payload["error_class"] == "InjectedModelTimeout"
    assert prompt_loop_payload["model_responses"][0]["finish_reason"] == "timeout"
    monkeypatch.setattr(
        agent_task_run_module,
        "_finish_agent_task_attempt",
        real_finish,
    )

    def fail_if_model_is_built(*args, **kwargs):
        del args, kwargs
        raise AssertionError("terminal model timeout must not be resampled")

    monkeypatch.setattr(
        eval_run_module,
        "build_model_client",
        fail_if_model_is_built,
    )
    resumed = resume_eval_suite(out_dir)

    final_manifest = load_attempt_manifest(attempt_dir / "manifest.json")
    assert resumed.status == "completed"
    assert isinstance(final_manifest, AgentTaskRunManifest)
    assert final_manifest.agent_attempt_id == generation_payload["agent_attempt_id"]
    assert final_manifest.status == "agent_loop_failed"
    assert final_manifest.prompt_loop_status == "model_error"
    assert "attempt" not in final_manifest.artifacts


def test_resume_executor_rejects_corruption_but_continues_siblings(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "control_eval.yaml"
    _write_control_eval_config(config_path, attempts=2)
    out_dir = tmp_path / "eval_suite"
    run_eval_config_all_policies(config_path, out_dir)
    clean_inventory = classify_eval_suite_resume(out_dir)
    first_attempt = clean_inventory.decisions[0]
    second_attempt = clean_inventory.decisions[1]

    (out_dir / "manifest.json").unlink()
    corrupt_result_path = first_attempt.attempt_dir / "attempt.json"
    corrupt_result_path.write_text("{}\n")
    corrupt_bytes = corrupt_result_path.read_bytes()
    shutil.rmtree(second_attempt.attempt_dir)

    resumed = resume_eval_suite(out_dir)

    assert resumed.status == "rejected"
    assert resumed.eval_matrix is None
    assert not (out_dir / "manifest.json").exists()
    assert corrupt_result_path.read_bytes() == corrupt_bytes
    assert (second_attempt.attempt_dir / "manifest.json").is_file()
    assert [decision.action for decision in resumed.inventory_after.decisions] == [
        "reject_attempt",
        "reuse_completed_attempt",
        "reuse_completed_attempt",
        "reuse_completed_attempt",
        "reuse_completed_attempt",
        "reuse_completed_attempt",
    ]
    rejected_policy_dir = first_attempt.attempt_dir.parent.parent
    assert not (rejected_policy_dir / "manifest.json").exists()
    assert not (rejected_policy_dir / "trace.jsonl").exists()
    assert len(resumed.policy_runs) == 2


def test_eval_config_rejects_duplicate_task_ids_before_declaring_suite(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "duplicate_tasks.yaml"
    _write_oracle_eval_config(
        config_path,
        task_ids=("toy_python_fix_001", "toy_python_fix_001"),
    )
    out_dir = tmp_path / "eval_suite"

    with pytest.raises(ValueError, match="Duplicate eval task id"):
        run_eval_config_all_policies(config_path, out_dir)

    assert not out_dir.exists()


def test_resume_rejects_duplicate_predeclared_attempt_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "duplicate_attempt.yaml"
    _write_oracle_eval_config(config_path, attempts=2)
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
    declaration_payload = json.loads(declaration_path.read_text())
    planned_attempts = declaration_payload["policy_runs"][0]["planned_attempts"]
    planned_attempts[1]["eval_attempt_id"] = planned_attempts[0]["eval_attempt_id"]
    declaration_path.write_text(
        json.dumps(declaration_payload, indent=2, sort_keys=True) + "\n"
    )

    with pytest.raises(ValueError, match="Duplicate eval_attempt_id"):
        classify_eval_suite_resume(out_dir)

    assert not (out_dir / "manifest.json").exists()


def test_resume_rejects_attempt_with_missing_terminal_payload(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "missing_payload.yaml"
    _write_oracle_eval_config(config_path)
    out_dir = tmp_path / "eval_suite"
    run_eval_config_all_policies(config_path, out_dir)
    clean_inventory = classify_eval_suite_resume(out_dir)
    attempt_dir = clean_inventory.decisions[0].attempt_dir

    (out_dir / "manifest.json").unlink()
    missing_result_path = attempt_dir / "attempt.json"
    missing_result_path.unlink()

    inventory = classify_eval_suite_resume(out_dir)
    assert inventory.decisions[0].action == "reject_attempt"
    assert inventory.decisions[0].reason == "invalid_completed_attempt"
    assert "artifact is missing" in (inventory.decisions[0].detail or "")

    resumed = resume_eval_suite(out_dir)

    assert resumed.status == "rejected"
    assert resumed.inventory_after.decisions[0].action == "reject_attempt"
    assert not missing_result_path.exists()
    assert not (out_dir / "manifest.json").exists()
    assert not (attempt_dir.parent.parent / "manifest.json").exists()


def test_resume_reuses_terminal_scorer_timeout_without_retrying_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "scorer_timeout.yaml"
    _write_oracle_eval_config(config_path, attempts=2)
    out_dir = tmp_path / "eval_suite"
    real_public_checks = attempt_module.run_public_checks
    real_eval_attempt = eval_run_module._run_scorer_eval_attempt
    call_count = 0

    def raise_timeout(*args, **kwargs):
        del args, kwargs
        raise TimeoutExpired(cmd="pytest public", timeout=1)

    def timeout_then_interrupt(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("injected after timeout attempt")
        return real_eval_attempt(**kwargs)

    monkeypatch.setattr(attempt_module, "run_public_checks", raise_timeout)
    monkeypatch.setattr(
        eval_run_module,
        "_run_scorer_eval_attempt",
        timeout_then_interrupt,
    )
    with pytest.raises(RuntimeError, match="injected after timeout attempt"):
        run_eval_config_all_policies(config_path, out_dir)

    inventory_before = classify_eval_suite_resume(out_dir)
    timeout_attempt = inventory_before.decisions[0]
    pending_attempt = inventory_before.decisions[1]
    timeout_manifest_before = load_attempt_manifest(
        timeout_attempt.attempt_dir / "manifest.json"
    )
    assert isinstance(timeout_manifest_before, ScorerAttemptManifest)
    assert timeout_manifest_before.status == "TIMEOUT"
    timeout_result_bytes = (timeout_attempt.attempt_dir / "attempt.json").read_bytes()

    monkeypatch.setattr(attempt_module, "run_public_checks", real_public_checks)
    real_resume_attempt = resume_module.run_and_persist_patch_attempt_to_dir
    resumed_attempt_dirs: list[Path] = []

    def track_resumed_attempt(
        task_manifest_path,
        submission_path,
        attempt_dir,
        *,
        eval_attempt=None,
    ):
        assert attempt_dir.resolve() != timeout_attempt.attempt_dir
        resumed_attempt_dirs.append(attempt_dir.resolve())
        return real_resume_attempt(
            task_manifest_path,
            submission_path,
            attempt_dir,
            eval_attempt=eval_attempt,
        )

    monkeypatch.setattr(
        resume_module,
        "run_and_persist_patch_attempt_to_dir",
        track_resumed_attempt,
    )
    resumed = resume_eval_suite(out_dir)

    assert resumed.status == "completed"
    assert resumed_attempt_dirs == [pending_attempt.attempt_dir]
    assert (timeout_attempt.attempt_dir / "attempt.json").read_bytes() == (
        timeout_result_bytes
    )
    assert (
        load_attempt_manifest(timeout_attempt.attempt_dir / "manifest.json")
        == timeout_manifest_before
    )
    scorer_summaries = [attempt.scorer for attempt in resumed.policy_runs[0].attempts]
    assert [summary.status for summary in scorer_summaries if summary is not None] == [
        "TIMEOUT",
        "PASS",
    ]
    suite_manifest = json.loads((out_dir / "manifest.json").read_text())
    assert suite_manifest["layer_counts"]["scorer_status"] == {
        "PASS": 1,
        "TIMEOUT": 1,
    }


def test_resume_rejects_missing_hidden_validator_before_attempt_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_pack = tmp_path / "task_pack"
    shutil.copytree(Path("data/task_packs/repo_patch_python_v0"), task_pack)
    config_path = tmp_path / "missing_hidden_validator.yaml"
    _write_oracle_eval_config(config_path, task_pack=str(task_pack))
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

    shutil.rmtree(task_pack / "tasks/toy_python_fix/hidden_tests")

    with pytest.raises(
        ValueError,
        match="Missing hidden validator behavior_pytest",
    ):
        resume_eval_suite(out_dir)

    assert (out_dir / EVAL_SUITE_DECLARATION_FILENAME).is_file()
    assert not (out_dir / "manifest.json").exists()
    assert not list((out_dir / "policies").glob("**/manifest.json"))


def test_bad_eval_config_path_fails_before_suite_creation(tmp_path: Path) -> None:
    missing_config = tmp_path / "missing_eval.yaml"
    out_dir = tmp_path / "eval_suite"

    with pytest.raises(FileNotFoundError, match="missing_eval.yaml"):
        run_eval_config_all_policies(missing_config, out_dir)

    assert not out_dir.exists()
