import copy
import json
from pathlib import Path

import pytest

import agentenv.training.repair_export as repair_export_module
from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
    load_training_candidate_repair_export_manifest,
    load_trajectory_export_manifest,
)
from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.export import (
    export_training_candidate_records,
    load_training_candidate_export_artifact,
)
from agentenv.training.repair_export import (
    export_training_candidate_repairs,
    load_repaired_transcript_artifact,
    load_training_candidate_repair_export_artifact,
)
from agentenv.trajectories.export import (
    export_trajectory_records_from_eval_artifact,
    hash_file,
    write_trajectory_records_jsonl,
)
from agentenv.trajectories.review import (
    initialize_trajectory_review_artifact,
    write_trajectory_review_records_jsonl,
)
from agentenv.trajectories.schema import ArtifactRef, TrajectoryRecord


AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")
HARNESS_AUDIT_DIR = Path("/unit/harness-audit")
CONTROL_CALIBRATION_DIR = Path("/unit/control-calibration")


@pytest.fixture(autouse=True)
def _stub_repair_calibration_loading(
    monkeypatch: pytest.MonkeyPatch,
    stub_training_export_gates,
) -> None:
    assert stub_training_export_gates.control_calibration_gate.overall_match
    monkeypatch.setattr(
        repair_export_module,
        "_load_source_public_check_calibrations",
        lambda _candidate_export: (),
    )


def test_export_training_candidate_repairs_writes_validated_transcript(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )

    export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )

    assert export.manifest.artifact_type == "training_candidate_repair_export"
    assert (
        export.manifest.artifact_schema_version
        == TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION
    )
    assert export.manifest.record_count == 1
    assert export.manifest.completed_count == 1
    assert export.manifest.cannot_complete_count == 0
    assert export.manifest.repair_error_count == 0
    assert len(export.records) == 1
    record = export.records[0]
    assert record.repair_status == "completed"
    assert record.repaired_artifact_ref is not None
    repaired_path = export.out_dir / record.repaired_artifact_ref.path
    transcript = load_repaired_transcript_artifact(repaired_path)
    tool_call_ids = [message.tool_call_id for message in transcript.root]
    assert "tool_call_redundant_0001" not in tool_call_ids
    assert "tool_call_0001" in tool_call_ids
    assert record.repair.after_repair_mechanical_redundancy_assessment is not None
    assert record.repair.after_repair_mechanical_redundancy_assessment.blocks == []

    source_export = load_training_candidate_export_artifact(candidate_export_dir)
    assert record.source_training_candidate_record_hash == (
        repair_export_module.hash_training_candidate_record(source_export.records[0])
    )
    manifest = load_training_candidate_repair_export_manifest(
        export.out_dir / MANIFEST_FILENAME
    )
    assert manifest.source_training_candidate_export.artifact_dir == str(
        candidate_export_dir.resolve()
    )
    assert manifest.source_training_candidate_export.manifest_hash == hash_file(
        candidate_export_dir / MANIFEST_FILENAME
    )


def test_export_training_candidate_repairs_allows_empty_noop_free_artifact(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=False,
    )

    export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )

    assert export.manifest.record_count == 0
    assert export.records == ()
    records_path = export.out_dir / export.manifest.artifacts["repair_records"]
    assert records_path.read_text() == ""
    assert not (export.out_dir / "transcripts").exists()


def test_load_training_candidate_repair_export_rejects_transcript_tamper(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repaired_ref = export.records[0].repaired_artifact_ref
    assert repaired_ref is not None
    repaired_path = export.out_dir / repaired_ref.path
    repaired_path.write_text(repaired_path.read_text() + "\n")

    with pytest.raises(ValueError, match="Repaired transcript hash mismatch"):
        load_training_candidate_repair_export_artifact(export.out_dir)


def test_load_training_candidate_repair_export_rejects_candidate_rebinding(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    records_path = export.out_dir / export.manifest.artifacts["repair_records"]
    payload = json.loads(records_path.read_text())
    payload["source_training_candidate_record_hash"] = "xxh64:ffffffffffffffff"
    records_path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    manifest_path = export.out_dir / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["repair_records_jsonl_hash"] = hash_file(records_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(
        ValueError,
        match="source training candidate hash mismatch",
    ):
        load_training_candidate_repair_export_artifact(export.out_dir)


def test_load_training_candidate_repair_export_rejects_source_manifest_drift(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    candidate_manifest_path = candidate_export_dir / MANIFEST_FILENAME
    candidate_manifest_path.write_text(candidate_manifest_path.read_text() + "\n")

    with pytest.raises(
        ValueError,
        match="Source training candidate manifest hash mismatch",
    ):
        load_training_candidate_repair_export_artifact(export.out_dir)


def _build_candidate_export(
    tmp_path: Path,
    *,
    add_redundancy: bool,
) -> Path:
    eval_run = run_eval_config(
        AGENT_CONTROL_CONFIG,
        "agent-happy",
        tmp_path / "eval-run",
    )
    trajectory_export = export_trajectory_records_from_eval_artifact(
        eval_run.out_dir,
        tmp_path / "trajectory-export",
    )
    trajectory = _as_agent_model_trajectory(trajectory_export.records[0])
    if add_redundancy:
        trajectory = _add_redundant_read(trajectory)
    _rewrite_trajectory_export(trajectory_export.out_dir, (trajectory,))

    review_artifact = initialize_trajectory_review_artifact(
        trajectory_export.out_dir,
        tmp_path / "trajectory-review",
    )
    review = review_artifact.reviews[0].model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "review_001",
            "reviewer_id": "reviewer",
            "review_decision": "accepted",
        }
    )
    write_trajectory_review_records_jsonl(
        review_artifact.out_dir / review_artifact.manifest.artifacts["reviews"],
        (review,),
    )
    candidate_export = export_training_candidate_records(
        trajectory_export.out_dir,
        review_artifact.out_dir,
        tmp_path / "training-candidates",
        harness_audit_dir=HARNESS_AUDIT_DIR,
        control_calibration_dir=CONTROL_CALIBRATION_DIR,
    )
    expected_block_count = 1 if add_redundancy else 0
    assert (
        len(candidate_export.records[0].mechanical_redundancy_assessment.blocks)
        == expected_block_count
    )
    return candidate_export.out_dir


def _as_agent_model_trajectory(trajectory: TrajectoryRecord) -> TrajectoryRecord:
    payload = trajectory.model_dump(mode="json")
    payload["identity"]["policy_id"] = "local-model"
    payload["policy"] = {
        "policy_id": "local-model",
        "policy_name": "local-model",
        "policy_spec": {
            "type": AGENT_MODEL_POLICY_TYPE,
            "model_config": "configs/models/local_model.yaml",
            "decoding_config": "configs/decoding/local_model.yaml",
            "attempts": 1,
            "replay": {"repeats": 0},
        },
    }
    return TrajectoryRecord.model_validate(payload)


def _add_redundant_read(trajectory: TrajectoryRecord) -> TrajectoryRecord:
    prompt_loop_ref = _require_prompt_loop_ref(trajectory)
    prompt_loop_path = Path(trajectory.artifacts.eval_run_path) / prompt_loop_ref.path
    payload = json.loads(prompt_loop_path.read_text())
    assistant_index = next(
        index
        for index, message in enumerate(payload["messages"])
        if message["role"] == "assistant"
        and json.loads(message["content"]).get("tool_name") == "read_file"
    )
    tool_index = assistant_index + 1
    assistant_message = payload["messages"][assistant_index]
    tool_message = payload["messages"][tool_index]
    assert tool_message["role"] == "tool"
    assert assistant_message["tool_call_id"] == tool_message["tool_call_id"]

    redundant_id = "tool_call_redundant_0001"
    redundant_assistant = copy.deepcopy(assistant_message)
    redundant_assistant["tool_call_id"] = redundant_id
    redundant_tool = copy.deepcopy(tool_message)
    redundant_tool["tool_call_id"] = redundant_id
    payload["messages"][tool_index + 1 : tool_index + 1] = [
        redundant_assistant,
        redundant_tool,
    ]

    tool_result_index = sum(
        message["role"] == "tool" for message in payload["messages"][:tool_index]
    )
    read_result = payload["tool_results"][tool_result_index]
    assert (
        read_result["canonical_workspace_hash_before"]
        == read_result["canonical_workspace_hash_after"]
    )
    payload["tool_results"].insert(
        tool_result_index + 1,
        copy.deepcopy(read_result),
    )
    response_index = sum(
        message["role"] == "assistant"
        for message in payload["messages"][:assistant_index]
    )
    payload["model_responses"].insert(
        response_index + 1,
        copy.deepcopy(payload["model_responses"][response_index]),
    )
    payload["turns_executed"] += 1
    prompt_loop_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    trajectory_payload = trajectory.model_dump(mode="json")
    trajectory_payload["artifacts"]["prompt_loop_result_json"]["content_hash"] = (
        hash_file(prompt_loop_path)
    )
    return TrajectoryRecord.model_validate(trajectory_payload)


def _rewrite_trajectory_export(
    trajectory_export_dir: Path,
    records: tuple[TrajectoryRecord, ...],
) -> None:
    trajectories_path = trajectory_export_dir / "trajectories.jsonl"
    write_trajectory_records_jsonl(trajectories_path, list(records))
    manifest = load_trajectory_export_manifest(
        trajectory_export_dir / MANIFEST_FILENAME
    )
    updated_manifest = manifest.model_copy(
        update={
            "record_count": len(records),
            "trajectories_jsonl_hash": hash_file(trajectories_path),
        }
    )
    (trajectory_export_dir / MANIFEST_FILENAME).write_text(
        json.dumps(
            updated_manifest.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _require_prompt_loop_ref(trajectory: TrajectoryRecord) -> ArtifactRef:
    prompt_loop_ref = trajectory.artifacts.prompt_loop_result_json
    if prompt_loop_ref is None:
        raise AssertionError("expected prompt-loop artifact ref")
    return prompt_loop_ref
