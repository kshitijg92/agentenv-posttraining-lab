import json
from pathlib import Path

from agentenv.artifacts.manifests import load_replay_run_manifest
from agentenv.artifacts.payloads import load_replay_comparison_records
from agentenv.artifacts.payloads import load_replay_result
from agentenv.audits.schema import (
    HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
    derive_harness_runtime_hash,
)
from agentenv.controls.agent_control_scripts import load_agent_control_script_case
from agentenv.models.fake import ScriptedFakeModelClient
from agentenv.orchestrators.agent_task_run import (
    run_and_persist_agent_task_attempt_to_dir,
)
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.replay.runner import _normalize_text, run_replay
from agentenv.tracing.schema import ReplayTraceProvenance
from agentenv.tracing.validate import load_trace_events, validate_trace_file


CONTROL_EVAL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")
DEV_BASELINE_EVAL_CONFIG = Path("configs/eval/dev_baseline.yaml")
TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TOY_HAPPY_AGENT_CONTROL = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/"
    "controls/agent_control_scripts/happy_path.json"
)
SCORER_ATTEMPT_ARTIFACTS = {
    "attempt.json": True,
    "error.txt": True,
    "final.diff": True,
    "manifest.json": True,
    "stderr.txt": True,
    "stdout.txt": True,
    "trace.jsonl": True,
}
AGENT_FIELD_MATCHES = {
    "attempt_status": True,
    "candidate_patch_hash": True,
    "error_class": True,
    "error_message": True,
    "prompt_loop_status": True,
    "status": True,
}


def _runtime_provenance() -> dict[str, object]:
    harness_source_hash = "xxh64:aaaaaaaaaaaaaaaa"
    pyproject_hash = "xxh64:bbbbbbbbbbbbbbbb"
    uv_lock_hash = "xxh64:cccccccccccccccc"
    runtime_hash = derive_harness_runtime_hash(
        harness_source_hash=harness_source_hash,
        root_pyproject_hash=pyproject_hash,
        root_uv_lock_hash=uv_lock_hash,
        python_implementation="cpython",
        python_version="3.11.14",
        sys_platform="linux",
        platform_machine="x86_64",
    )
    return {
        "schema_version": HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
        "harness_source_root": "src/agentenv",
        "harness_source_hash": harness_source_hash,
        "root_pyproject_path": "pyproject.toml",
        "root_pyproject_hash": pyproject_hash,
        "root_uv_lock_path": "uv.lock",
        "root_uv_lock_hash": uv_lock_hash,
        "python_implementation": "cpython",
        "python_version": "3.11.14",
        "sys_platform": "linux",
        "platform_machine": "x86_64",
        "harness_runtime_hash": runtime_hash,
    }


def _write_agent_control_source_artifact(
    control_path: Path,
    out_dir: Path,
) -> None:
    control_case = load_agent_control_script_case(control_path)
    model_client = ScriptedFakeModelClient(
        model_id="agent-control-scripted-v0",
        script=control_case.script.steps,
    )
    run_and_persist_agent_task_attempt_to_dir(
        TOY_TASK_MANIFEST,
        model_client,
        model_client.default_decoding_config(),
        out_dir,
        agent_control_script=control_case,
    )


def _write_eval_with_child_attempt_manifest(
    tmp_path: Path,
    *,
    child_artifact_type: str,
    child_artifact_schema_version: str,
    parent_artifact_type: str = "scorer_attempt",
    parent_artifact_schema_version: str = "scorer_attempt_artifact_v0",
) -> Path:
    source_eval_dir = tmp_path / "source_eval"
    child_dir = source_eval_dir / "attempts/toy_python_fix_001__attempt_001"
    child_dir.mkdir(parents=True, exist_ok=True)
    (child_dir / "manifest.json").write_text(
        json.dumps(
            _child_attempt_manifest(
                artifact_type=child_artifact_type,
                artifact_schema_version=child_artifact_schema_version,
            ),
            indent=2,
        )
        + "\n"
    )
    (source_eval_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "eval_run",
                "artifact_schema_version": "eval_run_artifact_v0",
                "eval_run_id": "eval_run_child_validation_001",
                "created_at": "2026-01-01T00:00:00Z",
                "config_path": "configs/eval/scorer_control_policies.yaml",
                "config_hash": "xxh64:config",
                "config_name": "unit",
                "task_pack": "data/task_packs/repo_patch_python_v0",
                "split": "dev",
                "runtime_provenance": _runtime_provenance(),
                "task_hashes": {
                    "schema_version": "eval_task_hashes_v0",
                    "task_pack_id": "repo_patch_python_v0",
                    "selected_task_hash_set": "xxh64:selected",
                    "selected_tasks": [
                        {
                            "task_id": "toy_python_fix_001",
                            "split": "dev",
                            "task_record_hash": "xxh64:task",
                            "task_yaml_hash": "xxh64:yaml",
                            "required_task_files_hash": "xxh64:required",
                            "full_task_dir_hash": "xxh64:full",
                            "required_task_files": [
                                {
                                    "path": "task.yaml",
                                    "kind": "file",
                                    "hash": "xxh64:file",
                                }
                            ],
                        }
                    ],
                },
                "policy": "oracle",
                "policy_type": "scorer_control_patch",
                "policy_family": "control",
                "control_layer": "scorer",
                "control_name": "oracle",
                "attempts_per_task": 1,
                "replay_repeats": 0,
                "attempt_count": 1,
                "layer_counts": {
                    "scorer_hidden_status": {"PASS": 1},
                    "scorer_public_status": {"PASS": 1},
                    "scorer_status": {"PASS": 1},
                },
                "artifacts": {
                    "trace": "trace.jsonl",
                    "attempts": "attempts",
                },
                "attempts": [
                    {
                        "eval_attempt_id": "eval_attempt_child_validation_001",
                        "task_id": "toy_python_fix_001",
                        "attempt_index": 0,
                        "artifact_dir": "attempts/toy_python_fix_001__attempt_001",
                        "artifact_type": parent_artifact_type,
                        "artifact_schema_version": parent_artifact_schema_version,
                        "scorer": {
                            "scorer_attempt_id": "scorer_attempt_child_validation_001",
                            "status": "PASS",
                            "public_status": "PASS",
                            "hidden_status": "PASS",
                            "error_class": None,
                            "final_diff_hash": "xxh64:diff",
                            "duration_ms": 1,
                        },
                        "agent": None,
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return source_eval_dir


def _child_attempt_manifest(
    *,
    artifact_type: str,
    artifact_schema_version: str,
) -> dict[str, object]:
    if artifact_type == "scorer_attempt":
        return {
            "artifact_type": artifact_type,
            "artifact_schema_version": artifact_schema_version,
            "orchestrator_version": "scorer_attempt_orchestrator_v0",
            "scorer_attempt_id": "scorer_attempt_child_validation_001",
            "task_id": "toy_python_fix_001",
            "task_manifest_path": str(TOY_TASK_MANIFEST),
            "submission_path": "submission.patch",
            "status": "PASS",
            "artifacts": {
                "attempt": "attempt.json",
                "stdout": "stdout.txt",
                "stderr": "stderr.txt",
                "error": "error.txt",
                "trace": "trace.jsonl",
                "final_diff": "final.diff",
            },
        }
    if artifact_type == "agent_attempt":
        return {
            "artifact_type": artifact_type,
            "artifact_schema_version": artifact_schema_version,
            "orchestrator_version": "agent_task_run_orchestrator_v0",
            "agent_attempt_id": "agent_attempt_child_validation_001",
            "task_id": "toy_python_fix_001",
            "task_manifest_path": str(TOY_TASK_MANIFEST),
            "status": "scored",
            "prompt_loop_status": "completed",
            "attempt_status": "PASS",
            "artifacts": {
                "agent_task_run": "agent_task_run.json",
                "decoding_config": "decoding_config.json",
                "agent_task_view": "agent_task_view.json",
                "prompt_loop_result": "prompt_loop_result.json",
                "candidate_patch": "candidate.patch",
                "attempt": "attempt",
                "error": "error.txt",
            },
        }
    return {
        "artifact_type": artifact_type,
        "artifact_schema_version": artifact_schema_version,
    }


def test_run_replay_matches_oracle_eval_run(tmp_path: Path) -> None:
    source_run = run_eval_config(
        CONTROL_EVAL_CONFIG,
        "oracle",
        tmp_path / "source_run",
    )

    replay_run = run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    source_manifest = json.loads((tmp_path / "source_run/manifest.json").read_text())
    source_attempt_record = source_manifest["attempts"][0]
    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_manifest = json.loads((tmp_path / "replay_run/manifest.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_run.replay_run_id.startswith("replay_run_")
    assert replay_result["schema_version"] == "replay_result_v0"
    assert replay_result["replay_run_id"] == replay_run.replay_run_id
    assert "replay_id" not in replay_result
    assert replay_result["status"] == "PASS"
    assert replay_result["attempt_count"] == 1
    assert replay_result["matched_attempts"] == 1
    assert replay_manifest["artifact_type"] == "replay_run"
    assert replay_manifest["artifact_schema_version"] == "replay_run_artifact_v0"
    assert replay_manifest["replay_run_id"] == replay_run.replay_run_id
    assert "replay_id" not in replay_manifest
    assert replay_manifest["source_eval_run_id"] == source_run.eval_run_id
    assert replay_manifest["source_agent_attempt_id"] is None
    assert replay_manifest["artifacts"]["attempts"] == "attempts"
    assert "agent_task_run" not in replay_manifest["artifacts"]
    assert (
        load_replay_run_manifest(tmp_path / "replay_run/manifest.json").replay_run_id
        == replay_run.replay_run_id
    )
    assert load_replay_result(tmp_path / "replay_run/replay_result.json").status == (
        "PASS"
    )
    assert (
        len(
            load_replay_comparison_records(tmp_path / "replay_run/replay_results.jsonl")
        )
        == 1
    )
    assert len(replay_records) == 1
    assert replay_records[0]["matched"] is True
    assert replay_records[0]["comparison_type"] == "scorer_attempt"
    assert (
        replay_records[0]["source_eval_attempt_id"]
        == source_attempt_record["eval_attempt_id"]
    )
    assert replay_records[0]["source_scorer_attempt_id"].startswith("scorer_attempt_")
    assert replay_records[0]["replayed_scorer_attempt_id"].startswith("scorer_attempt_")
    assert "source_id" not in replay_records[0]
    assert "replay_id" not in replay_records[0]
    assert "source_attempt_id" not in replay_records[0]
    assert "replay_attempt_id" not in replay_records[0]
    assert (
        replay_records[0]["source_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert (
        replay_records[0]["replay_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert replay_records[0]["source_artifact_path"] == str(
        tmp_path / "source_run/attempts/toy_python_fix_001__attempt_001"
    )
    assert replay_records[0]["replay_artifact_path"] == str(
        tmp_path / "replay_run/attempts/toy_python_fix_001__attempt_001"
    )
    assert "source_attempt_artifact_ref" not in replay_records[0]
    assert "replay_attempt_artifact_ref" not in replay_records[0]
    assert "source_agent_artifact_ref" not in replay_records[0]
    assert "replay_agent_artifact_ref" not in replay_records[0]
    assert replay_records[0]["field_matches"] == {
        "error_class": True,
        "final_diff_hash": True,
        "hidden_status": True,
        "public_status": True,
        "status": True,
    }
    assert replay_records[0]["artifact_matches"] == SCORER_ATTEMPT_ARTIFACTS
    assert (
        tmp_path / "replay_run/attempts/toy_python_fix_001__attempt_001/attempt.json"
    ).is_file()
    validate_trace_file(tmp_path / "replay_run/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "replay_run/trace.jsonl")
    assert trace_events[0].schema_version == "trace_v0"
    assert trace_events[0].event_type == "replay_started"
    first_provenance = trace_events[0].provenance_config
    assert isinstance(first_provenance, ReplayTraceProvenance)
    assert first_provenance.replay_run_id == replay_run.replay_run_id
    second_provenance = trace_events[1].provenance_config
    assert isinstance(second_provenance, ReplayTraceProvenance)
    assert second_provenance.source_eval_run_id == source_run.eval_run_id
    source_attempt_provenance = trace_events[2].provenance_config
    assert isinstance(source_attempt_provenance, ReplayTraceProvenance)
    assert (
        source_attempt_provenance.source_eval_attempt_id
        == source_attempt_record["eval_attempt_id"]
    )


def test_run_replay_detects_durable_attempt_artifact_mismatch(
    tmp_path: Path,
) -> None:
    run_eval_config(
        CONTROL_EVAL_CONFIG,
        "oracle",
        tmp_path / "source_run",
    )
    source_manifest = json.loads((tmp_path / "source_run/manifest.json").read_text())
    source_attempt_ref = source_manifest["attempts"][0]["artifact_dir"]
    source_stdout = tmp_path / "source_run" / source_attempt_ref / "stdout.txt"
    source_stdout.write_text(source_stdout.read_text() + "deterministic tamper\n")

    replay_run = run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "MISMATCH"
    assert replay_result["status"] == "MISMATCH"
    assert replay_result["matched_attempts"] == 0
    assert replay_result["mismatched_attempts"] == 1
    assert replay_records[0]["matched"] is False
    assert replay_records[0]["field_matches"] == {
        "error_class": True,
        "final_diff_hash": True,
        "hidden_status": True,
        "public_status": True,
        "status": True,
    }
    assert replay_records[0]["artifact_matches"] == {
        **SCORER_ATTEMPT_ARTIFACTS,
        "stdout.txt": False,
    }


def test_run_replay_normalizes_pytest_tmp_paths_for_dev_controls(
    tmp_path: Path,
) -> None:
    run_eval_config(
        DEV_BASELINE_EVAL_CONFIG,
        "noop",
        tmp_path / "source_run",
    )

    replay_run = run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_run.replay_run_id.startswith("replay_run_")
    assert replay_result["schema_version"] == "replay_result_v0"
    assert replay_result["replay_run_id"] == replay_run.replay_run_id
    assert "replay_id" not in replay_result
    assert replay_result["status"] == "PASS"
    assert replay_result["matched_attempts"] == 3
    assert all(record["artifact_matches"]["stdout.txt"] for record in replay_records)


def test_replay_normalizes_elided_pytest_tmp_path_fragments() -> None:
    first = _normalize_text(
        "...pytest-1119/test_duplicate_id_exits_with_i0/records.jsonl",
        repo_roots=(),
    )
    second = _normalize_text(
        "...ytest-1123/test_duplicate_id_exits_with_i0/records.jsonl",
        repo_roots=(),
    )

    assert (
        first
        == second
        == ("...<PYTEST_TMP>/test_duplicate_id_exits_with_i0/records.jsonl")
    )


def test_run_replay_matches_agent_control_artifact(tmp_path: Path) -> None:
    _write_agent_control_source_artifact(
        TOY_HAPPY_AGENT_CONTROL,
        tmp_path / "source_agent",
    )

    replay_run = run_replay(tmp_path / "source_agent", tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_manifest = json.loads((tmp_path / "replay_run/manifest.json").read_text())
    source_manifest = json.loads((tmp_path / "source_agent/manifest.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_run.replay_run_id.startswith("replay_run_")
    assert replay_result["status"] == "PASS"
    assert replay_result["replay_run_id"] == replay_run.replay_run_id
    assert "replay_id" not in replay_result
    assert replay_manifest["replay_run_id"] == replay_run.replay_run_id
    assert "replay_id" not in replay_manifest
    assert replay_manifest["source_artifact_type"] == "agent_attempt"
    assert replay_manifest["source_eval_run_id"] is None
    assert (
        replay_manifest["source_agent_attempt_id"]
        == source_manifest["agent_attempt_id"]
    )
    assert (
        replay_manifest["source_artifact_schema_version"] == "agent_attempt_artifact_v0"
    )
    assert replay_manifest["artifacts"]["agent_task_run"] == "agent_task_run"
    assert len(replay_records) == 1
    assert replay_records[0]["comparison_type"] == "agent_task_run"
    assert replay_records[0]["source_artifact_ref"] == "."
    assert (
        load_replay_comparison_records(tmp_path / "replay_run/replay_results.jsonl")[
            0
        ].source_artifact_ref
        == "."
    )
    assert replay_records[0]["source_agent_attempt_id"].startswith("agent_attempt_")
    assert replay_records[0]["replayed_agent_attempt_id"].startswith("agent_attempt_")
    assert "source_eval_attempt_id" not in replay_records[0]
    assert "source_id" not in replay_records[0]
    assert "replay_id" not in replay_records[0]
    assert replay_records[0]["matched"] is True
    assert replay_records[0]["field_matches"] == AGENT_FIELD_MATCHES
    assert all(replay_records[0]["artifact_matches"].values())
    assert {
        "agent_control_script.json",
        "agent_task_run.json",
        "agent_task_view.json",
        "attempt/attempt.json",
        "attempt/final.diff",
        "attempt/trace.jsonl",
        "candidate.patch",
        "decoding_config.json",
        "error.txt",
        "prompt_loop_result.json",
        "manifest.json",
    }.issubset(set(replay_records[0]["artifact_matches"]))
    assert (tmp_path / "replay_run/agent_task_run/agent_task_run.json").is_file()
    validate_trace_file(tmp_path / "replay_run/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "replay_run/trace.jsonl")
    assert trace_events[1].event_type == "source_manifest_loaded"
    second_provenance = trace_events[1].provenance_config
    assert isinstance(second_provenance, ReplayTraceProvenance)
    assert (
        second_provenance.source_agent_attempt_id == source_manifest["agent_attempt_id"]
    )
    assert "source_artifact_id" not in second_provenance.model_dump()
    assert second_provenance.source_eval_run_id is None
    assert second_provenance.source_eval_attempt_id is None
    raw_trace_events = [
        json.loads(line)
        for line in (tmp_path / "replay_run/trace.jsonl").read_text().splitlines()
    ]
    assert "source_eval_attempt_id" not in raw_trace_events[1]["provenance_config"]


def test_run_replay_dispatches_eval_agent_attempt_artifact(tmp_path: Path) -> None:
    source_eval_dir = tmp_path / "source_eval"
    source_agent_attempt_dir = (
        source_eval_dir / "attempts/toy_python_fix_001__attempt_001"
    )
    _write_agent_control_source_artifact(
        TOY_HAPPY_AGENT_CONTROL,
        source_agent_attempt_dir,
    )
    agent_task_result = json.loads(
        (source_agent_attempt_dir / "agent_task_run.json").read_text()
    )
    attempt_result = agent_task_result["attempt_result"]
    source_eval_dir.mkdir(parents=True, exist_ok=True)
    (source_eval_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "eval_run",
                "artifact_schema_version": "eval_run_artifact_v0",
                "eval_run_id": "eval_run_agent_001",
                "created_at": "2026-01-01T00:00:00Z",
                "config_path": "configs/eval/agent_control_policies.yaml",
                "config_hash": "xxh64:config",
                "config_name": "unit",
                "task_pack": "data/task_packs/repo_patch_python_v0",
                "split": "dev",
                "runtime_provenance": _runtime_provenance(),
                "task_hashes": {
                    "schema_version": "eval_task_hashes_v0",
                    "task_pack_id": "repo_patch_python_v0",
                    "selected_task_hash_set": "xxh64:selected",
                    "selected_tasks": [
                        {
                            "task_id": "toy_python_fix_001",
                            "split": "dev",
                            "task_record_hash": "xxh64:task",
                            "task_yaml_hash": "xxh64:yaml",
                            "required_task_files_hash": "xxh64:required",
                            "full_task_dir_hash": "xxh64:full",
                            "required_task_files": [
                                {
                                    "path": "task.yaml",
                                    "kind": "file",
                                    "hash": "xxh64:file",
                                }
                            ],
                        }
                    ],
                },
                "policy": "agent-happy",
                "policy_type": "agent_control_script",
                "policy_family": "control",
                "control_layer": "agent",
                "control_name": "happy",
                "attempts_per_task": 1,
                "replay_repeats": 0,
                "attempt_count": 1,
                "layer_counts": {
                    "agent_scorer_hidden_status": {"PASS": 1},
                    "agent_scorer_public_status": {"PASS": 1},
                    "agent_scorer_status": {"PASS": 1},
                    "agent_status": {"scored": 1},
                    "prompt_loop_status": {"completed": 1},
                },
                "artifacts": {
                    "trace": "trace.jsonl",
                    "attempts": "attempts",
                },
                "attempts": [
                    {
                        "eval_attempt_id": "eval_attempt_agent_001",
                        "task_id": "toy_python_fix_001",
                        "attempt_index": 0,
                        "artifact_dir": "attempts/toy_python_fix_001__attempt_001",
                        "artifact_type": "agent_attempt",
                        "artifact_schema_version": "agent_attempt_artifact_v0",
                        "scorer": None,
                        "agent": {
                            "agent_attempt_id": agent_task_result["agent_attempt_id"],
                            "status": "scored",
                            "prompt_loop_status": "completed",
                            "error_class": None,
                            "candidate_patch_hash": agent_task_result[
                                "candidate_patch_hash"
                            ],
                            "duration_ms": 1,
                            "scorer_attempt": {
                                "scorer_attempt_id": attempt_result[
                                    "scorer_attempt_id"
                                ],
                                "status": "PASS",
                                "public_status": "PASS",
                                "hidden_status": "PASS",
                                "error_class": None,
                                "final_diff_hash": attempt_result["final_diff_hash"],
                                "duration_ms": 1,
                            },
                        },
                    }
                ],
            },
            indent=2,
        )
        + "\n"
    )

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")

    replay_manifest = json.loads((tmp_path / "replay_run/manifest.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "PASS"
    assert replay_run.replay_run_id.startswith("replay_run_")
    assert replay_manifest["replay_run_id"] == replay_run.replay_run_id
    assert "replay_id" not in replay_manifest
    assert replay_manifest["artifacts"]["attempts"] == "attempts"
    assert "agent_task_run" not in replay_manifest["artifacts"]
    assert replay_records[0]["comparison_type"] == "agent_task_run"
    assert replay_records[0]["source_eval_attempt_id"] == "eval_attempt_agent_001"
    assert replay_records[0]["source_agent_attempt_id"].startswith("agent_attempt_")
    assert replay_records[0]["replayed_agent_attempt_id"].startswith("agent_attempt_")
    assert "source_id" not in replay_records[0]
    assert "replay_id" not in replay_records[0]
    assert (
        replay_records[0]["source_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert (
        replay_records[0]["replay_artifact_ref"]
        == "attempts/toy_python_fix_001__attempt_001"
    )
    assert (
        tmp_path
        / "replay_run/attempts/toy_python_fix_001__attempt_001/agent_task_run.json"
    ).is_file()
    validate_trace_file(tmp_path / "replay_run/trace.jsonl")
    trace_events = load_trace_events(tmp_path / "replay_run/trace.jsonl")
    source_attempt_provenance = trace_events[2].provenance_config
    assert isinstance(source_attempt_provenance, ReplayTraceProvenance)
    assert source_attempt_provenance.source_eval_attempt_id == "eval_attempt_agent_001"


def test_run_replay_rejects_eval_child_attempt_with_bad_schema(
    tmp_path: Path,
) -> None:
    source_eval_dir = _write_eval_with_child_attempt_manifest(
        tmp_path,
        child_artifact_type="scorer_attempt",
        child_artifact_schema_version="scorer_attempt_artifact_v999",
    )

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")
    replay_manifest = json.loads((tmp_path / "replay_run/manifest.json").read_text())

    assert replay_run.status == "REPLAY_ERROR"
    assert replay_manifest["source_eval_run_id"] == "eval_run_child_validation_001"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "artifact_schema_version must be 'scorer_attempt_artifact_v0'" in trace_text


def test_run_replay_rejects_malformed_empty_eval_source_manifest(
    tmp_path: Path,
) -> None:
    source_eval_dir = tmp_path / "source_eval"
    source_eval_dir.mkdir()
    (source_eval_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "eval_run",
                "artifact_schema_version": "eval_run_artifact_v0",
                "attempts": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")
    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())

    assert replay_run.status == "REPLAY_ERROR"
    assert replay_result["status"] == "REPLAY_ERROR"
    assert replay_result["attempt_count"] == 0
    assert replay_result["error_count"] == 1


def test_run_replay_rejects_eval_child_attempt_with_unsupported_type(
    tmp_path: Path,
) -> None:
    source_eval_dir = _write_eval_with_child_attempt_manifest(
        tmp_path,
        child_artifact_type="eval_suite",
        child_artifact_schema_version="eval_suite_artifact_v0",
    )

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")

    assert replay_run.status == "REPLAY_ERROR"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "Expected scorer or agent attempt manifest" in trace_text


def test_run_replay_rejects_eval_attempt_record_with_bad_schema(
    tmp_path: Path,
) -> None:
    source_eval_dir = _write_eval_with_child_attempt_manifest(
        tmp_path,
        child_artifact_type="scorer_attempt",
        child_artifact_schema_version="scorer_attempt_artifact_v0",
        parent_artifact_schema_version="scorer_attempt_artifact_v999",
    )

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")

    assert replay_run.status == "REPLAY_ERROR"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "artifact_schema_version does not match artifact_type" in trace_text


def test_run_replay_rejects_eval_attempt_record_child_manifest_mismatch(
    tmp_path: Path,
) -> None:
    source_eval_dir = _write_eval_with_child_attempt_manifest(
        tmp_path,
        child_artifact_type="agent_attempt",
        child_artifact_schema_version="agent_attempt_artifact_v0",
        parent_artifact_type="scorer_attempt",
        parent_artifact_schema_version="scorer_attempt_artifact_v0",
    )

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")

    assert replay_run.status == "REPLAY_ERROR"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "Eval run child artifact_type mismatch" in trace_text


def test_run_replay_rejects_eval_child_manifest_task_id_mismatch(
    tmp_path: Path,
) -> None:
    source_eval_dir = _write_eval_with_child_attempt_manifest(
        tmp_path,
        child_artifact_type="scorer_attempt",
        child_artifact_schema_version="scorer_attempt_artifact_v0",
    )
    child_manifest_path = (
        source_eval_dir / "attempts/toy_python_fix_001__attempt_001/manifest.json"
    )
    child_manifest = json.loads(child_manifest_path.read_text())
    child_manifest["task_id"] = "different_task"
    child_manifest_path.write_text(json.dumps(child_manifest, indent=2) + "\n")

    replay_run = run_replay(source_eval_dir, tmp_path / "replay_run")

    assert replay_run.status == "REPLAY_ERROR"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "Eval run child task_id mismatch" in trace_text


def test_run_replay_rejects_eval_parent_agent_attempt_id_mismatch(
    tmp_path: Path,
) -> None:
    source_run = run_eval_config(
        Path("configs/eval/agent_control_policies.yaml"),
        "agent-happy",
        tmp_path / "source_agent_eval",
    )
    manifest_path = source_run.out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["attempts"][0]["agent"]["agent_attempt_id"] = "agent_attempt_wrong"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    replay_run = run_replay(source_run.out_dir, tmp_path / "replay_run")

    assert replay_run.status == "REPLAY_ERROR"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "agent_attempt_id mismatch" in trace_text


def test_run_replay_rejects_eval_parent_nested_scorer_summary_mismatch(
    tmp_path: Path,
) -> None:
    source_run = run_eval_config(
        Path("configs/eval/agent_control_policies.yaml"),
        "agent-happy",
        tmp_path / "source_agent_eval",
    )
    manifest_path = source_run.out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["attempts"][0]["agent"]["scorer_attempt"]["final_diff_hash"] = (
        "xxh64:wrong"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    replay_run = run_replay(source_run.out_dir, tmp_path / "replay_run")

    assert replay_run.status == "REPLAY_ERROR"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "final_diff_hash mismatch" in trace_text


def test_run_replay_detects_agent_trajectory_artifact_mismatch(
    tmp_path: Path,
) -> None:
    source_agent_dir = tmp_path / "source_agent"
    _write_agent_control_source_artifact(TOY_HAPPY_AGENT_CONTROL, source_agent_dir)
    prompt_loop_path = source_agent_dir / "prompt_loop_result.json"
    prompt_loop_result = json.loads(prompt_loop_path.read_text())
    prompt_loop_result["messages"][0]["content"] += "\ndeterministic tamper"
    prompt_loop_path.write_text(json.dumps(prompt_loop_result, indent=2) + "\n")

    replay_run = run_replay(source_agent_dir, tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "MISMATCH"
    assert replay_result["status"] == "MISMATCH"
    assert replay_result["matched_attempts"] == 0
    assert replay_result["mismatched_attempts"] == 1
    assert replay_records[0]["comparison_type"] == "agent_task_run"
    assert replay_records[0]["matched"] is False
    assert replay_records[0]["field_matches"] == AGENT_FIELD_MATCHES
    assert replay_records[0]["artifact_matches"]["prompt_loop_result.json"] is False


def test_run_replay_marks_missing_declared_agent_artifact_mismatch(
    tmp_path: Path,
) -> None:
    source_agent_dir = tmp_path / "source_agent"
    _write_agent_control_source_artifact(TOY_HAPPY_AGENT_CONTROL, source_agent_dir)
    (source_agent_dir / "candidate.patch").unlink()

    replay_run = run_replay(source_agent_dir, tmp_path / "replay_run")

    replay_result = json.loads((tmp_path / "replay_run/replay_result.json").read_text())
    replay_records = [
        json.loads(line)
        for line in (tmp_path / "replay_run/replay_results.jsonl")
        .read_text()
        .splitlines()
    ]

    assert replay_run.status == "MISMATCH"
    assert replay_result["status"] == "MISMATCH"
    assert replay_records[0]["comparison_type"] == "agent_task_run"
    assert replay_records[0]["matched"] is False
    assert replay_records[0]["artifact_matches"]["candidate.patch"] is False


def test_run_replay_rejects_unversioned_decoding_config_artifact(
    tmp_path: Path,
) -> None:
    source_agent_dir = tmp_path / "source_agent"
    _write_agent_control_source_artifact(TOY_HAPPY_AGENT_CONTROL, source_agent_dir)
    decoding_path = source_agent_dir / "decoding_config.json"
    decoding_provenance = json.loads(decoding_path.read_text())
    decoding_path.write_text(
        json.dumps(decoding_provenance["config"], indent=2, sort_keys=True) + "\n"
    )

    replay_run = run_replay(source_agent_dir, tmp_path / "replay_run")
    replay_manifest = json.loads((tmp_path / "replay_run/manifest.json").read_text())

    assert replay_run.status == "REPLAY_ERROR"
    assert replay_manifest["source_agent_attempt_id"].startswith("agent_attempt_")
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "schema_version" in trace_text


def test_run_replay_rejects_malformed_prompt_loop_artifact(
    tmp_path: Path,
) -> None:
    source_agent_dir = tmp_path / "source_agent"
    _write_agent_control_source_artifact(TOY_HAPPY_AGENT_CONTROL, source_agent_dir)
    prompt_loop_path = source_agent_dir / "prompt_loop_result.json"
    prompt_loop = json.loads(prompt_loop_path.read_text())
    del prompt_loop["status"]
    prompt_loop_path.write_text(json.dumps(prompt_loop, indent=2) + "\n")

    replay_run = run_replay(source_agent_dir, tmp_path / "replay_run")

    assert replay_run.status == "REPLAY_ERROR"
    trace_text = (tmp_path / "replay_run/trace.jsonl").read_text()
    assert "PromptLoopResult at" in trace_text


def test_run_replay_rejects_replay_artifact_input(tmp_path: Path) -> None:
    run_eval_config(CONTROL_EVAL_CONFIG, "oracle", tmp_path / "source_run")
    run_replay(tmp_path / "source_run", tmp_path / "replay_run")

    replay_run = run_replay(tmp_path / "replay_run", tmp_path / "nested_replay")
    replay_result = json.loads(
        (tmp_path / "nested_replay/replay_result.json").read_text()
    )

    assert replay_run.status == "REPLAY_ERROR"
    assert replay_result["status"] == "REPLAY_ERROR"
    assert replay_result["error_count"] == 1
