import json
from pathlib import Path

import pytest

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION,
    load_trajectory_export_manifest,
)
from agentenv.orchestrators.eval_run import (
    run_eval_config,
    run_eval_config_all_policies,
)
from agentenv.trajectories.export import (
    export_trajectory_records_from_eval_artifact,
    load_trajectory_export_artifact,
    load_trajectory_records_jsonl,
)
from agentenv.trajectories.schema import TRAJECTORY_RECORD_SCHEMA_VERSION


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")


def test_export_trajectory_records_from_eval_run_writes_private_artifact(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "eval-run",
    )

    export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        tmp_path / "trajectory-export",
    )

    manifest = load_trajectory_export_manifest(export.out_dir / MANIFEST_FILENAME)
    assert manifest.artifact_type == "trajectory_export"
    assert manifest.artifact_schema_version == TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION
    assert manifest.source_artifact_type == "eval_run"
    assert manifest.source_artifact_schema_version == "eval_run_artifact_v0"
    assert manifest.source_eval_run_id == eval_run.eval_run_id
    assert manifest.source_eval_suite_id is None
    assert manifest.trajectory_record_schema_version == TRAJECTORY_RECORD_SCHEMA_VERSION
    assert manifest.record_count == len(eval_run.attempts)
    assert manifest.source_manifest_hash.startswith("xxh64:")
    assert manifest.trajectories_jsonl_hash.startswith("xxh64:")
    assert manifest.artifacts == {"trajectories": "trajectories.jsonl"}

    records = load_trajectory_records_jsonl(
        export.out_dir / manifest.artifacts["trajectories"]
    )
    assert len(records) == manifest.record_count
    assert records[0].identity.eval_run_id == eval_run.eval_run_id
    assert records[0].identity.eval_suite_id is None
    assert records[0].identity.replay_run_id is None


def test_load_trajectory_export_artifact_rejects_jsonl_hash_mismatch(
    tmp_path: Path,
) -> None:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "eval-run",
    )
    export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        tmp_path / "trajectory-export",
    )
    trajectories_path = export.out_dir / export.manifest.artifacts["trajectories"]
    trajectories_path.write_text(trajectories_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Trajectory JSONL hash mismatch"):
        load_trajectory_export_artifact(export.out_dir)


def test_export_trajectory_records_from_eval_suite_ignores_replay_sources(
    tmp_path: Path,
) -> None:
    eval_suite = run_eval_config_all_policies(
        AGENT_CONTROL_CONFIG,
        tmp_path / "eval-suite",
    )
    assert eval_suite.replay_runs

    export = export_trajectory_records_from_eval_artifact(
        eval_suite.out_dir,
        tmp_path / "trajectory-export",
    )

    manifest = load_trajectory_export_manifest(export.out_dir / MANIFEST_FILENAME)
    records = load_trajectory_records_jsonl(
        export.out_dir / manifest.artifacts["trajectories"]
    )

    expected_attempt_count = sum(len(run.attempts) for run in eval_suite.policy_runs)
    assert manifest.source_artifact_type == "eval_suite"
    assert manifest.source_artifact_schema_version == "eval_suite_artifact_v0"
    assert manifest.source_eval_run_id is None
    assert manifest.source_eval_suite_id == eval_suite.eval_suite_id
    assert manifest.record_count == expected_attempt_count
    assert len(records) == expected_attempt_count
    assert {record.identity.eval_suite_id for record in records} == {
        eval_suite.eval_suite_id
    }
    assert all(record.identity.replay_run_id is None for record in records)


def test_export_trajectory_records_rejects_non_eval_artifact(tmp_path: Path) -> None:
    source_dir = tmp_path / "not-eval"
    source_dir.mkdir()
    (source_dir / MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "artifact_type": "trajectory_export",
                "artifact_schema_version": "trajectory_export_artifact_v0",
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="Expected eval run or eval suite manifest"):
        export_trajectory_records_from_eval_artifact(
            source_dir,
            tmp_path / "trajectory-export",
        )
