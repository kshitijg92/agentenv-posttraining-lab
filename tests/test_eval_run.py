import json
from pathlib import Path

import pytest

from agentenv.agents.prompts import AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION
from agentenv.artifacts import ArtifactDirectoryError
from agentenv.artifacts.manifests import load_eval_run_manifest
from agentenv.artifacts.manifests import load_eval_suite_manifest
from agentenv.artifacts.payloads import DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION
from agentenv.artifacts.payloads import load_decoding_config_provenance
from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.orchestrators.eval_run import (
    EvalAttemptRecord,
    run_eval_config,
    run_eval_config_all_policies,
    _validate_unique_eval_attempt_ids,
)
from agentenv.tracing.schema import EvalTraceProvenance
from agentenv.tracing.validate import load_trace_events, validate_trace_file


CONTROL_EVAL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")
AGENT_CONTROL_EVAL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
DEV_BASELINE_EVAL_CONFIG = Path("configs/eval/dev_baseline.yaml")
AGENT_MODEL_DEV_QWEN_EVAL_CONFIG = Path(
    "configs/eval/agent_model_dev_ollama_qwen3_14b.yaml"
)
AGENT_MODEL_DEV_DEEPSEEK_R1_DISTILL_QWEN_EVAL_CONFIG = Path(
    "configs/eval/agent_model_dev_ollama_deepseek_r1_distill_qwen_14b.yaml"
)


def _write_agent_model_eval_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: agent_model_smoke",
                "task_pack: data/task_packs/repo_patch_python_v0",
                "tasks:",
                "  - toy_python_fix_001",
                "split: practice",
                "policies:",
                "  real-agent-smoke:",
                "    type: agent_model",
                "    model_config: configs/models/openai_compatible_chat_placeholder.yaml",
                "    decoding_config: configs/decoding/greedy_1024.yaml",
                "    attempts: 2",
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


def test_control_eval_config_loads() -> None:
    config = load_eval_config(CONTROL_EVAL_CONFIG)

    assert config.name == "scorer_control_policies"
    assert config.task_pack == "data/task_packs/repo_patch_python_v0"
    assert config.tasks == ["toy_python_fix_001"]
    assert sorted(config.policies) == ["bad-noop", "bad-public-only", "oracle"]
    assert config.policies["oracle"].attempts == 1
    assert config.policies["oracle"].replay.repeats == 1
    assert config.policies["bad-noop"].attempts == 1
    assert config.policies["bad-noop"].replay.repeats == 1


def test_control_eval_config_paths_are_valid() -> None:
    config = load_eval_config(CONTROL_EVAL_CONFIG)

    validate_eval_config_paths(config, CONTROL_EVAL_CONFIG)


def test_dev_baseline_eval_config_paths_are_valid() -> None:
    config = load_eval_config(DEV_BASELINE_EVAL_CONFIG)

    assert sorted(config.policies) == [
        "agent-happy",
        "agent-malformed",
        "agent-recoverable",
        "noop",
        "oracle",
        "public-tests-only",
    ]
    validate_eval_config_paths(config, DEV_BASELINE_EVAL_CONFIG)


def test_agent_model_dev_qwen_eval_config_paths_are_valid() -> None:
    config = load_eval_config(AGENT_MODEL_DEV_QWEN_EVAL_CONFIG)

    assert config.name == "agent_model_dev_ollama_qwen3_14b"
    assert sorted(config.policies) == [
        "agent-happy",
        "agent-malformed",
        "agent-recoverable",
        "local-qwen-dev",
        "noop",
        "oracle",
        "public-tests-only",
    ]
    assert config.policies["local-qwen-dev"].type == "agent_model"
    validate_eval_config_paths(config, AGENT_MODEL_DEV_QWEN_EVAL_CONFIG)


def test_agent_model_dev_deepseek_eval_config_paths_are_valid() -> None:
    config = load_eval_config(AGENT_MODEL_DEV_DEEPSEEK_R1_DISTILL_QWEN_EVAL_CONFIG)

    assert config.name == "agent_model_dev_ollama_deepseek_r1_distill_qwen_14b"
    assert sorted(config.policies) == [
        "agent-happy",
        "agent-malformed",
        "agent-recoverable",
        "local-deepseek-r1-distill-qwen-dev",
        "noop",
        "oracle",
        "public-tests-only",
    ]
    assert config.policies["local-deepseek-r1-distill-qwen-dev"].type == "agent_model"
    validate_eval_config_paths(
        config,
        AGENT_MODEL_DEV_DEEPSEEK_R1_DISTILL_QWEN_EVAL_CONFIG,
    )


def test_agent_control_eval_config_loads() -> None:
    config = load_eval_config(AGENT_CONTROL_EVAL_CONFIG)

    assert config.name == "agent_control_policies"
    assert config.task_pack == "data/task_packs/repo_patch_python_v0"
    assert config.tasks == ["toy_python_fix_001"]
    assert sorted(config.policies) == [
        "agent-happy",
        "agent-malformed",
        "agent-recoverable",
    ]
    happy_policy = config.policies["agent-happy"]
    malformed_policy = config.policies["agent-malformed"]
    recoverable_policy = config.policies["agent-recoverable"]
    assert happy_policy.type == "agent_control_script"
    assert malformed_policy.type == "agent_control_script"
    assert recoverable_policy.type == "agent_control_script"
    assert happy_policy.control == "happy"
    assert happy_policy.attempts == 1
    assert happy_policy.replay.repeats == 1
    assert malformed_policy.control == "malformed"
    assert recoverable_policy.control == "recoverable"


def test_agent_control_eval_config_paths_are_valid() -> None:
    config = load_eval_config(AGENT_CONTROL_EVAL_CONFIG)

    validate_eval_config_paths(config, AGENT_CONTROL_EVAL_CONFIG)


def test_agent_model_eval_config_loads_and_validates_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "agent_model_eval.yaml"
    _write_agent_model_eval_config(config_path)

    config = load_eval_config(config_path)

    policy = config.policies["real-agent-smoke"]
    assert policy.type == "agent_model"
    assert (
        policy.model_config_path
        == "configs/models/openai_compatible_chat_placeholder.yaml"
    )
    assert policy.decoding_config_path == "configs/decoding/greedy_1024.yaml"
    assert policy.attempts == 2
    assert policy.replay.repeats == 0
    validate_eval_config_paths(config, config_path)


def test_agent_model_eval_records_missing_model_env_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "agent_model_eval.yaml"
    _write_agent_model_eval_config(config_path)
    monkeypatch.setenv("AGENTENV_MODEL_BASE_URL", "https://provider.test/v1")
    monkeypatch.delenv("AGENTENV_MODEL_API_KEY", raising=False)

    eval_run = run_eval_config(config_path, "real-agent-smoke", tmp_path / "eval")

    run_manifest = json.loads((tmp_path / "eval/manifest.json").read_text())
    loaded_manifest = load_eval_run_manifest(tmp_path / "eval/manifest.json")

    assert len(eval_run.attempts) == 2
    assert loaded_manifest.eval_run_id == eval_run.eval_run_id
    assert run_manifest["policy_type"] == "agent_model"
    assert run_manifest["policy_family"] == "agent"
    assert run_manifest["model_config"] == (
        "configs/models/openai_compatible_chat_placeholder.yaml"
    )
    assert run_manifest["decoding_config"] == "configs/decoding/greedy_1024.yaml"
    assert run_manifest["layer_counts"] == {
        "agent_status": {"agent_loop_failed": 2},
        "prompt_loop_status": {"model_error": 2},
    }
    first_attempt = run_manifest["attempts"][0]
    eval_attempt_ids = [
        attempt["eval_attempt_id"] for attempt in run_manifest["attempts"]
    ]
    assert all(
        eval_attempt_id.startswith("eval_attempt_")
        for eval_attempt_id in eval_attempt_ids
    )
    assert len(set(eval_attempt_ids)) == 2
    assert first_attempt["artifact_type"] == "agent_attempt"
    assert first_attempt["artifact_schema_version"] == "agent_attempt_artifact_v0"
    assert first_attempt["scorer"] is None
    assert first_attempt["agent"]["status"] == "agent_loop_failed"
    assert first_attempt["agent"]["prompt_loop_status"] == "model_error"
    assert first_attempt["agent"]["error_class"] == "MissingModelApiKeyEnvVar"
    assert first_attempt["agent"]["scorer_attempt"] is None
    attempt_dir = tmp_path / "eval" / first_attempt["artifact_dir"]
    attempt_manifest = json.loads((attempt_dir / "manifest.json").read_text())
    assert attempt_manifest["artifacts"]["model_config"] == "model_config.json"
    assert attempt_manifest["artifacts"]["decoding_config"] == "decoding_config.json"
    assert (attempt_dir / "agent_task_run.json").is_file()
    assert (attempt_dir / "agent_task_view.json").is_file()
    assert (attempt_dir / "model_config.json").is_file()
    assert (attempt_dir / "decoding_config.json").is_file()
    assert (attempt_dir / "prompt_loop_result.json").is_file()
    assert not (attempt_dir / "agent_control_script.json").exists()
    assert not (attempt_dir / "candidate.patch").exists()
    assert not (attempt_dir / "attempt").exists()
    decoding_config_provenance = json.loads(
        (attempt_dir / "decoding_config.json").read_text()
    )
    assert decoding_config_provenance["source_path"].endswith(
        "configs/decoding/greedy_1024.yaml"
    )
    assert decoding_config_provenance["source_hash"].startswith("xxh64:")
    assert decoding_config_provenance["config"]["max_new_tokens"] == 1024
    assert decoding_config_provenance["config"]["timeout_seconds"] == 60
    prompt_loop_result = json.loads(
        (attempt_dir / "prompt_loop_result.json").read_text()
    )
    assert (
        prompt_loop_result["prompt_builder_version"]
        == AGENT_TASK_INITIAL_PROMPT_BUILDER_VERSION
    )
    assert prompt_loop_result["prompt_builder_code_hash"].startswith("xxh64:")
    assert prompt_loop_result["model_responses"][0]["finish_reason"] == "error"
    assert (
        prompt_loop_result["model_responses"][0]["error_class"]
        == "MissingModelApiKeyEnvVar"
    )
    model_config_provenance = json.loads(
        (attempt_dir / "model_config.json").read_text()
    )
    assert model_config_provenance["source_path"].endswith(
        "configs/models/openai_compatible_chat_placeholder.yaml"
    )
    assert model_config_provenance["source_hash"].startswith("xxh64:")
    assert model_config_provenance["config"] == {
        "api_key_env": "AGENTENV_MODEL_API_KEY",
        "base_url_env": "AGENTENV_MODEL_BASE_URL",
        "capabilities": {
            "supports_seed": False,
            "supports_stop": True,
            "supports_top_k": False,
            "token_usage": "native",
        },
        "model_id": "placeholder-model",
        "prompt_adapter": None,
        "agent_action_format": "prompt_only",
        "provider": "openai_compatible_chat",
        "version": "model_config_v0",
    }
    assert "secret-token" not in (attempt_dir / "model_config.json").read_text()
    validate_trace_file(tmp_path / "eval/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "eval/trace.jsonl")
    attempt_trace_events = [
        event
        for event in trace_events
        if event.event_type in {"eval_attempt_started", "eval_attempt_finished"}
    ]
    assert len(attempt_trace_events) == 4
    for attempt_index, eval_attempt_id in enumerate(eval_attempt_ids):
        started_provenance = attempt_trace_events[attempt_index * 2].provenance_config
        finished_provenance = attempt_trace_events[
            attempt_index * 2 + 1
        ].provenance_config
        assert isinstance(started_provenance, EvalTraceProvenance)
        assert isinstance(finished_provenance, EvalTraceProvenance)
        assert started_provenance.attempt_index == attempt_index
        assert started_provenance.eval_attempt_id == eval_attempt_id
        assert finished_provenance.attempt_index == attempt_index
        assert finished_provenance.eval_attempt_id == eval_attempt_id
    assert trace_events[3].payload_refs == {
        "agent_task_run": "attempts/toy_python_fix_001__attempt_001/agent_task_run.json",
        "agent_task_view": "attempts/toy_python_fix_001__attempt_001/agent_task_view.json",
        "decoding_config": "attempts/toy_python_fix_001__attempt_001/decoding_config.json",
        "model_config": "attempts/toy_python_fix_001__attempt_001/model_config.json",
        "prompt_loop_result": (
            "attempts/toy_python_fix_001__attempt_001/prompt_loop_result.json"
        ),
    }


def test_run_eval_config_writes_agent_control_happy_manifest(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_EVAL_CONFIG,
        "agent-happy",
        tmp_path / "eval",
    )

    run_manifest_path = tmp_path / "eval/manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text())
    loaded_manifest = load_eval_run_manifest(run_manifest_path)

    assert eval_run.config.name == "agent_control_policies"
    assert loaded_manifest.eval_run_id == eval_run.eval_run_id
    assert eval_run.policy == "agent-happy"
    assert eval_run.eval_run_id.startswith("eval_run_")
    assert len(eval_run.attempts) == 1
    assert eval_run.attempts[0].scorer is None
    assert eval_run.attempts[0].agent is not None
    assert eval_run.attempts[0].agent.status == "scored"
    assert run_manifest["policy_type"] == "agent_control_script"
    assert run_manifest["eval_run_id"].startswith("eval_run_")
    assert run_manifest["policy_family"] == "control"
    assert run_manifest["control_layer"] == "agent"
    assert run_manifest["control_name"] == "happy"
    assert run_manifest["attempts_per_task"] == 1
    assert run_manifest["replay_repeats"] == 1
    assert run_manifest["layer_counts"] == {
        "agent_scorer_hidden_status": {"PASS": 1},
        "agent_scorer_public_status": {"PASS": 1},
        "agent_scorer_status": {"PASS": 1},
        "agent_status": {"scored": 1},
        "prompt_loop_status": {"completed": 1},
    }
    attempt_record = run_manifest["attempts"][0]
    assert attempt_record["task_id"] == "toy_python_fix_001"
    assert attempt_record["eval_attempt_id"].startswith("eval_attempt_")
    assert "attempt_id" not in attempt_record
    assert attempt_record["artifact_type"] == "agent_attempt"
    assert attempt_record["artifact_schema_version"] == "agent_attempt_artifact_v0"
    assert attempt_record["scorer"] is None
    assert attempt_record["agent"]["agent_attempt_id"].startswith("agent_attempt_")
    assert "run_id" not in attempt_record["agent"]
    assert attempt_record["agent"]["status"] == "scored"
    assert attempt_record["agent"]["prompt_loop_status"] == "completed"
    assert attempt_record["agent"]["error_class"] is None
    assert attempt_record["agent"]["candidate_patch_hash"] == "xxh64:e3fc746d6fe0786c"
    assert attempt_record["agent"]["scorer_attempt"]["status"] == "PASS"
    assert attempt_record["agent"]["scorer_attempt"]["public_status"] == "PASS"
    assert attempt_record["agent"]["scorer_attempt"]["hidden_status"] == "PASS"
    attempt_dir = tmp_path / "eval" / attempt_record["artifact_dir"]
    assert (attempt_dir / "agent_task_run.json").is_file()
    assert (attempt_dir / "prompt_loop_result.json").is_file()
    assert (attempt_dir / "candidate.patch").is_file()
    assert (attempt_dir / "attempt/attempt.json").is_file()
    assert (attempt_dir / "decoding_config.json").is_file()
    assert (attempt_dir / "agent_control_script.json").is_file()
    decoding_config = json.loads((attempt_dir / "decoding_config.json").read_text())
    decoding_provenance = load_decoding_config_provenance(
        attempt_dir / "decoding_config.json"
    )
    assert (
        decoding_config["schema_version"] == DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION
    )
    assert decoding_config["source_path"] is None
    assert decoding_config["source_hash"] is None
    assert decoding_provenance.source_path is None
    assert decoding_config["config"]["max_new_tokens"] == 512
    assert decoding_config["config"]["timeout_seconds"] == 30
    validate_trace_file(tmp_path / "eval/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "eval/trace.jsonl")
    attempt_started_provenance = trace_events[2].provenance_config
    assert isinstance(attempt_started_provenance, EvalTraceProvenance)
    assert (
        attempt_started_provenance.eval_attempt_id == attempt_record["eval_attempt_id"]
    )
    assert trace_events[3].output_payload is not None
    assert trace_events[3].output_payload["agent"]["status"] == "scored"
    attempt_finished_provenance = trace_events[3].provenance_config
    assert isinstance(attempt_finished_provenance, EvalTraceProvenance)
    assert (
        attempt_finished_provenance.eval_attempt_id == attempt_record["eval_attempt_id"]
    )
    assert (
        attempt_finished_provenance.agent_attempt_id
        == attempt_record["agent"]["agent_attempt_id"]
    )
    assert (
        attempt_finished_provenance.scorer_attempt_id
        == attempt_record["agent"]["scorer_attempt"]["scorer_attempt_id"]
    )
    assert trace_events[3].payload_refs == {
        "agent_control_script": (
            "attempts/toy_python_fix_001__attempt_001/agent_control_script.json"
        ),
        "agent_task_run": "attempts/toy_python_fix_001__attempt_001/agent_task_run.json",
        "agent_task_view": "attempts/toy_python_fix_001__attempt_001/agent_task_view.json",
        "candidate_patch": "attempts/toy_python_fix_001__attempt_001/candidate.patch",
        "decoding_config": "attempts/toy_python_fix_001__attempt_001/decoding_config.json",
        "nested_attempt": "attempts/toy_python_fix_001__attempt_001/attempt/attempt.json",
        "prompt_loop_result": (
            "attempts/toy_python_fix_001__attempt_001/prompt_loop_result.json"
        ),
    }


def test_run_eval_config_records_agent_control_malformed_failure(
    tmp_path: Path,
) -> None:
    run_eval_config(
        AGENT_CONTROL_EVAL_CONFIG,
        "agent-malformed",
        tmp_path / "eval",
    )

    run_manifest = json.loads((tmp_path / "eval/manifest.json").read_text())

    assert run_manifest["layer_counts"] == {
        "agent_status": {"agent_loop_failed": 1},
        "prompt_loop_status": {"invalid_model_output": 1},
    }
    attempt_record = run_manifest["attempts"][0]
    assert attempt_record["eval_attempt_id"].startswith("eval_attempt_")
    assert "attempt_id" not in attempt_record
    assert attempt_record["artifact_type"] == "agent_attempt"
    assert attempt_record["artifact_schema_version"] == "agent_attempt_artifact_v0"
    assert attempt_record["scorer"] is None
    assert attempt_record["agent"]["agent_attempt_id"].startswith("agent_attempt_")
    assert "run_id" not in attempt_record["agent"]
    assert attempt_record["agent"]["status"] == "agent_loop_failed"
    assert attempt_record["agent"]["prompt_loop_status"] == "invalid_model_output"
    assert attempt_record["agent"]["error_class"] == "MalformedModelOutput"
    assert attempt_record["agent"]["candidate_patch_hash"] is None
    assert attempt_record["agent"]["scorer_attempt"] is None
    attempt_dir = tmp_path / "eval" / attempt_record["artifact_dir"]
    assert (attempt_dir / "agent_task_run.json").is_file()
    assert (attempt_dir / "prompt_loop_result.json").is_file()
    assert (attempt_dir / "decoding_config.json").is_file()
    assert (attempt_dir / "agent_control_script.json").is_file()
    assert not (attempt_dir / "candidate.patch").exists()
    assert not (attempt_dir / "attempt").exists()


def test_run_eval_config_writes_run_manifest(tmp_path: Path) -> None:
    eval_run = run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "eval")

    run_manifest_path = tmp_path / "eval/manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text())

    assert eval_run.config.name == "scorer_control_policies"
    assert eval_run.policy == "oracle"
    assert eval_run.eval_run_id.startswith("eval_run_")
    assert len(eval_run.attempts) == 1
    assert eval_run.attempts[0].scorer is not None
    assert eval_run.attempts[0].scorer.status == "PASS"
    assert run_manifest["artifact_type"] == "eval_run"
    assert run_manifest["artifact_schema_version"] == "eval_run_artifact_v0"
    assert run_manifest["eval_run_id"].startswith("eval_run_")
    assert run_manifest["config_name"] == "scorer_control_policies"
    task_hashes = run_manifest["task_hashes"]
    assert task_hashes["schema_version"] == "eval_task_hashes_v0"
    assert task_hashes["task_pack_id"] == "repo_patch_python_v0"
    assert task_hashes["selected_task_hash_set"].startswith("xxh64:")
    assert len(task_hashes["selected_tasks"]) == 1
    selected_task_hash = task_hashes["selected_tasks"][0]
    assert selected_task_hash["task_id"] == "toy_python_fix_001"
    assert selected_task_hash["task_record_hash"].startswith("xxh64:")
    assert selected_task_hash["required_task_files_hash"].startswith("xxh64:")
    assert selected_task_hash["full_task_dir_hash"].startswith("xxh64:")
    assert {record["path"] for record in selected_task_hash["required_task_files"]} >= {
        "task.yaml",
        "seed_workspace",
        "hidden_tests",
    }
    assert run_manifest["policy"] == "oracle"
    assert run_manifest["policy_type"] == "scorer_control_patch"
    assert run_manifest["policy_family"] == "control"
    assert run_manifest["control_layer"] == "scorer"
    assert run_manifest["control_name"] == "oracle"
    assert run_manifest["attempts_per_task"] == 1
    assert run_manifest["replay_repeats"] == 1
    assert run_manifest["attempt_count"] == 1
    assert "status_counts" not in run_manifest
    assert run_manifest["layer_counts"] == {
        "scorer_hidden_status": {"PASS": 1},
        "scorer_public_status": {"PASS": 1},
        "scorer_status": {"PASS": 1},
    }
    assert run_manifest["artifacts"] == {
        "attempts": "attempts",
        "trace": "trace.jsonl",
    }
    attempt_record = run_manifest["attempts"][0]
    assert attempt_record["task_id"] == "toy_python_fix_001"
    assert attempt_record["eval_attempt_id"].startswith("eval_attempt_")
    assert "attempt_id" not in attempt_record
    assert attempt_record["attempt_index"] == 0
    assert attempt_record["artifact_dir"] == "attempts/toy_python_fix_001__attempt_001"
    assert attempt_record["artifact_type"] == "scorer_attempt"
    assert attempt_record["artifact_schema_version"] == "scorer_attempt_artifact_v0"
    assert attempt_record["agent"] is None
    assert attempt_record["scorer"]["status"] == "PASS"
    assert attempt_record["scorer"]["public_status"] == "PASS"
    assert attempt_record["scorer"]["hidden_status"] == "PASS"
    assert attempt_record["scorer"]["error_class"] is None
    assert attempt_record["scorer"]["final_diff_hash"] == "xxh64:e3fc746d6fe0786c"
    validate_trace_file(tmp_path / "eval/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "eval/trace.jsonl")
    assert [event.event_type for event in trace_events] == [
        "eval_started",
        "eval_task_started",
        "eval_attempt_started",
        "eval_attempt_finished",
        "eval_task_finished",
        "eval_finished",
    ]
    first_provenance = trace_events[0].provenance_config
    assert isinstance(first_provenance, EvalTraceProvenance)
    assert first_provenance.eval_run_id == eval_run.eval_run_id
    assert first_provenance.config_name == "scorer_control_policies"
    assert first_provenance.policy == "oracle"
    attempt_finished_provenance = trace_events[3].provenance_config
    assert isinstance(attempt_finished_provenance, EvalTraceProvenance)
    assert attempt_finished_provenance.task_id == "toy_python_fix_001"
    assert attempt_finished_provenance.task_index == 0
    assert attempt_finished_provenance.attempt_index == 0
    assert (
        attempt_finished_provenance.eval_attempt_id == attempt_record["eval_attempt_id"]
    )
    assert (
        attempt_finished_provenance.scorer_attempt_id
        == attempt_record["scorer"]["scorer_attempt_id"]
    )
    assert trace_events[3].output_payload is not None
    assert trace_events[3].output_payload["scorer"]["status"] == "PASS"
    assert trace_events[4].output_payload is not None
    assert trace_events[4].output_payload["layer_counts"] == {
        "scorer_hidden_status": {"PASS": 1},
        "scorer_public_status": {"PASS": 1},
        "scorer_status": {"PASS": 1},
    }
    assert trace_events[3].payload_refs == {
        "attempt": "attempts/toy_python_fix_001__attempt_001/attempt.json",
        "attempt_trace": "attempts/toy_python_fix_001__attempt_001/trace.jsonl",
    }
    assert trace_events[5].payload_refs == {"manifest": "manifest.json"}
    assert (tmp_path / "eval/attempts/toy_python_fix_001__attempt_001").is_dir()
    assert (
        tmp_path / "eval/attempts/toy_python_fix_001__attempt_001/attempt.json"
    ).is_file()
    assert (tmp_path / "eval/trace.jsonl").is_file()


def test_validate_unique_eval_attempt_ids_rejects_duplicates(tmp_path: Path) -> None:
    attempts = [
        EvalAttemptRecord(
            eval_attempt_id="eval_attempt_duplicate",
            task_id="task_001",
            attempt_index=0,
            attempt_dir=tmp_path / "attempt_1",
            artifact_type="scorer_attempt",
            artifact_schema_version="scorer_attempt_artifact_v0",
            scorer=None,
            agent=None,
        ),
        EvalAttemptRecord(
            eval_attempt_id="eval_attempt_duplicate",
            task_id="task_002",
            attempt_index=0,
            attempt_dir=tmp_path / "attempt_2",
            artifact_type="scorer_attempt",
            artifact_schema_version="scorer_attempt_artifact_v0",
            scorer=None,
            agent=None,
        ),
    ]

    with pytest.raises(ValueError, match="Duplicate eval_attempt_id"):
        _validate_unique_eval_attempt_ids(attempts)


def test_run_eval_config_distinguishes_bad_noop(tmp_path: Path) -> None:
    eval_run = run_eval_config(CONTROL_EVAL_CONFIG, "bad-noop", tmp_path / "eval")

    assert len(eval_run.attempts) == 1
    scorer = eval_run.attempts[0].scorer
    assert scorer is not None
    assert scorer.status == "HIDDEN_TEST_FAIL"
    assert scorer.public_status == "PASS"
    assert scorer.hidden_status == "FAIL"


def test_run_eval_config_rejects_non_empty_output_dir(tmp_path: Path) -> None:
    out_dir = tmp_path / "eval"
    out_dir.mkdir()
    stale_file = out_dir / "candidate.patch"
    stale_file.write_text("stale\n")

    with pytest.raises(ArtifactDirectoryError, match="Output directory is not empty"):
        run_eval_config(CONTROL_EVAL_CONFIG, "oracle", out_dir)

    assert stale_file.read_text() == "stale\n"
    assert not (out_dir / "manifest.json").exists()


def test_run_eval_config_overwrite_clears_non_empty_output_dir(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "eval"
    out_dir.mkdir()
    stale_file = out_dir / "candidate.patch"
    stale_file.write_text("stale\n")

    eval_run = run_eval_config(
        CONTROL_EVAL_CONFIG,
        "oracle",
        out_dir,
        overwrite=True,
    )

    assert eval_run.out_dir == out_dir.resolve()
    assert not stale_file.exists()
    assert (out_dir / "manifest.json").is_file()


def test_run_eval_config_all_policies_writes_matrix_manifest(
    tmp_path: Path,
) -> None:
    eval_matrix = run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )

    matrix_manifest_path = tmp_path / "eval_matrix/manifest.json"
    matrix_manifest = json.loads(matrix_manifest_path.read_text())

    assert eval_matrix.config.name == "scorer_control_policies"
    assert [run.policy for run in eval_matrix.policy_runs] == [
        "oracle",
        "bad-noop",
        "bad-public-only",
    ]
    assert matrix_manifest["artifact_type"] == "eval_suite"
    assert matrix_manifest["artifact_schema_version"] == "eval_suite_artifact_v0"
    assert matrix_manifest["eval_suite_id"].startswith("eval_suite_")
    assert "eval_matrix_id" not in matrix_manifest
    assert matrix_manifest["config_name"] == "scorer_control_policies"
    task_hashes = matrix_manifest["task_hashes"]
    assert task_hashes["schema_version"] == "eval_task_hashes_v0"
    assert task_hashes["task_pack_id"] == "repo_patch_python_v0"
    assert task_hashes["selected_task_hash_set"].startswith("xxh64:")
    assert len(task_hashes["selected_tasks"]) == 1
    selected_task_hash = task_hashes["selected_tasks"][0]
    assert selected_task_hash["task_id"] == "toy_python_fix_001"
    assert selected_task_hash["required_task_files_hash"].startswith("xxh64:")
    assert selected_task_hash["full_task_dir_hash"].startswith("xxh64:")
    assert {record["path"] for record in selected_task_hash["required_task_files"]} >= {
        "task.yaml",
        "seed_workspace",
        "hidden_tests",
    }
    assert matrix_manifest["task_count"] == 1
    assert matrix_manifest["policy_count"] == 3
    assert matrix_manifest["attempt_count"] == 3
    assert "status_counts" not in matrix_manifest
    assert matrix_manifest["layer_counts"] == {
        "scorer_hidden_status": {"FAIL": 2, "PASS": 1},
        "scorer_public_status": {"PASS": 3},
        "scorer_status": {"HIDDEN_TEST_FAIL": 2, "PASS": 1},
    }
    assert matrix_manifest["artifacts"] == {
        "policies": "policies",
        "replays": "replays",
    }
    assert matrix_manifest["policy_runs"] == [
        {
            "policy": "oracle",
            "policy_type": "scorer_control_patch",
            "policy_family": "control",
            "control_layer": "scorer",
            "control_name": "oracle",
            "attempts_per_task": 1,
            "replay_repeats": 1,
            "eval_run_id": eval_matrix.policy_runs[0].eval_run_id,
            "artifact_dir": "policies/oracle",
            "manifest": "policies/oracle/manifest.json",
            "attempt_count": 1,
            "layer_counts": {
                "scorer_hidden_status": {"PASS": 1},
                "scorer_public_status": {"PASS": 1},
                "scorer_status": {"PASS": 1},
            },
        },
        {
            "policy": "bad-noop",
            "policy_type": "scorer_control_patch",
            "policy_family": "control",
            "control_layer": "scorer",
            "control_name": "bad.noop",
            "attempts_per_task": 1,
            "replay_repeats": 1,
            "eval_run_id": eval_matrix.policy_runs[1].eval_run_id,
            "artifact_dir": "policies/bad-noop",
            "manifest": "policies/bad-noop/manifest.json",
            "attempt_count": 1,
            "layer_counts": {
                "scorer_hidden_status": {"FAIL": 1},
                "scorer_public_status": {"PASS": 1},
                "scorer_status": {"HIDDEN_TEST_FAIL": 1},
            },
        },
        {
            "policy": "bad-public-only",
            "policy_type": "scorer_control_patch",
            "policy_family": "control",
            "control_layer": "scorer",
            "control_name": "bad.public_only",
            "attempts_per_task": 1,
            "replay_repeats": 1,
            "eval_run_id": eval_matrix.policy_runs[2].eval_run_id,
            "artifact_dir": "policies/bad-public-only",
            "manifest": "policies/bad-public-only/manifest.json",
            "attempt_count": 1,
            "layer_counts": {
                "scorer_hidden_status": {"FAIL": 1},
                "scorer_public_status": {"PASS": 1},
                "scorer_status": {"HIDDEN_TEST_FAIL": 1},
            },
        },
    ]
    assert (tmp_path / "eval_matrix/policies/oracle/manifest.json").is_file()
    assert (tmp_path / "eval_matrix/policies/bad-noop/manifest.json").is_file()
    assert (tmp_path / "eval_matrix/policies/bad-public-only/manifest.json").is_file()
    assert matrix_manifest["replay_policy_count"] == 3
    assert matrix_manifest["replay_run_count"] == 3
    assert matrix_manifest["replay_run_success_summary"] == "3/3"
    assert len(matrix_manifest["replay_runs"]) == 3


def test_run_eval_config_all_policies_replays_configured_control_policies(
    tmp_path: Path,
) -> None:
    eval_matrix = run_eval_config_all_policies(
        CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )

    matrix_manifest_path = tmp_path / "eval_matrix/manifest.json"
    matrix_manifest = json.loads(matrix_manifest_path.read_text())

    assert len(eval_matrix.replay_runs) == 3
    assert matrix_manifest["artifacts"] == {
        "policies": "policies",
        "replays": "replays",
    }
    assert matrix_manifest["replay_policy_count"] == 3
    assert matrix_manifest["replay_run_count"] == 3
    assert matrix_manifest["replay_run_success_summary"] == "3/3"
    assert matrix_manifest["replay_runs"] == [
        {
            "policy": "oracle",
            "replay_index": 0,
            "replay_run_id": eval_matrix.replay_runs[0].replay_run.replay_run_id,
            "status": "PASS",
            "artifact_dir": "replays/oracle__replay_001",
            "manifest": "replays/oracle__replay_001/manifest.json",
            "replay_result": "replays/oracle__replay_001/replay_result.json",
            "attempt_count": 1,
            "matched_attempts": 1,
            "mismatched_attempts": 0,
            "error_count": 0,
        },
        {
            "policy": "bad-noop",
            "replay_index": 0,
            "replay_run_id": eval_matrix.replay_runs[1].replay_run.replay_run_id,
            "status": "PASS",
            "artifact_dir": "replays/bad-noop__replay_001",
            "manifest": "replays/bad-noop__replay_001/manifest.json",
            "replay_result": "replays/bad-noop__replay_001/replay_result.json",
            "attempt_count": 1,
            "matched_attempts": 1,
            "mismatched_attempts": 0,
            "error_count": 0,
        },
        {
            "policy": "bad-public-only",
            "replay_index": 0,
            "replay_run_id": eval_matrix.replay_runs[2].replay_run.replay_run_id,
            "status": "PASS",
            "artifact_dir": "replays/bad-public-only__replay_001",
            "manifest": ("replays/bad-public-only__replay_001/manifest.json"),
            "replay_result": ("replays/bad-public-only__replay_001/replay_result.json"),
            "attempt_count": 1,
            "matched_attempts": 1,
            "mismatched_attempts": 0,
            "error_count": 0,
        },
    ]
    assert (
        tmp_path / "eval_matrix/replays/oracle__replay_001/replay_result.json"
    ).is_file()
    assert (
        tmp_path / "eval_matrix/replays/bad-noop__replay_001/replay_result.json"
    ).is_file()
    assert (
        tmp_path / "eval_matrix/replays/bad-public-only__replay_001/replay_result.json"
    ).is_file()


def test_run_eval_config_all_policies_replays_agent_control_policies(
    tmp_path: Path,
) -> None:
    eval_matrix = run_eval_config_all_policies(
        AGENT_CONTROL_EVAL_CONFIG,
        tmp_path / "eval_matrix",
    )

    matrix_manifest = json.loads((tmp_path / "eval_matrix/manifest.json").read_text())
    loaded_matrix_manifest = load_eval_suite_manifest(
        tmp_path / "eval_matrix/manifest.json"
    )

    assert [run.policy for run in eval_matrix.policy_runs] == [
        "agent-happy",
        "agent-malformed",
        "agent-recoverable",
    ]
    assert len(eval_matrix.replay_runs) == 3
    assert loaded_matrix_manifest.eval_suite_id == eval_matrix.eval_suite_id
    assert matrix_manifest["task_count"] == 1
    assert matrix_manifest["layer_counts"] == {
        "agent_scorer_hidden_status": {"PASS": 2},
        "agent_scorer_public_status": {"PASS": 2},
        "agent_scorer_status": {"PASS": 2},
        "agent_status": {"agent_loop_failed": 1, "scored": 2},
        "prompt_loop_status": {"completed": 2, "invalid_model_output": 1},
    }
    assert [
        replay_record["policy"] for replay_record in matrix_manifest["replay_runs"]
    ] == [
        "agent-happy",
        "agent-malformed",
        "agent-recoverable",
    ]
    assert {
        replay_record["status"] for replay_record in matrix_manifest["replay_runs"]
    } == {"PASS"}
    assert matrix_manifest["replay_run_success_summary"] == "3/3"
    happy_manifest = json.loads(
        (tmp_path / "eval_matrix/policies/agent-happy/manifest.json").read_text()
    )
    malformed_manifest = json.loads(
        (tmp_path / "eval_matrix/policies/agent-malformed/manifest.json").read_text()
    )
    assert happy_manifest["attempts"][0]["agent"]["scorer_attempt"]["status"] == "PASS"
    assert malformed_manifest["attempts"][0]["agent"]["scorer_attempt"] is None
    assert (
        tmp_path / "eval_matrix/replays/agent-happy__replay_001/replay_result.json"
    ).is_file()
    assert (
        tmp_path / "eval_matrix/replays/agent-malformed__replay_001/replay_result.json"
    ).is_file()
