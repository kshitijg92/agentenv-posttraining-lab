import copy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import (
    TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION,
    load_training_candidate_repair_export_manifest,
    load_trajectory_export_manifest,
)
from agentenv.evals.schema import AGENT_MODEL_POLICY_TYPE
from agentenv.ids import new_message_id
from agentenv.orchestrators.eval_run import run_eval_config
from agentenv.training.candidates.export import (
    export_training_candidate_records,
    load_training_candidate_export_artifact,
)
from agentenv.training.positive_sft.export import (
    export_positive_sft_examples,
    load_positive_sft_export_artifact,
)
from agentenv.training.repairs.export import (
    export_training_candidate_repairs,
    load_repaired_transcript_artifact,
    load_training_candidate_repair_export_artifact,
)
from agentenv.training.candidates.hashing import hash_training_candidate_record
from agentenv.training.repairs.redundancy_repair import (
    hash_training_candidate_repair_record,
    hash_training_candidate_repair_review_record,
)
from agentenv.training.repairs.review import (
    TrainingCandidateRepairReviewArtifact,
    initialize_training_candidate_repair_review_artifact,
    load_training_candidate_repair_review_artifact,
    validate_training_candidate_repair_review_artifact,
    write_training_candidate_repair_review_records_jsonl,
)
from agentenv.training.repairs.schema import (
    TrainingCandidateRepairRecord,
    TrainingCandidateRepairReviewRecord,
)
from agentenv.training.positive_sft.review import (
    PositiveSFTReviewArtifact,
    build_positive_sft_review_selections,
    initialize_positive_sft_review_artifact,
    validate_positive_sft_review_artifact,
    write_positive_sft_review_records_jsonl,
)
from agentenv.training.positive_sft.schema import PositiveSFTReviewRecord
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
        hash_training_candidate_record(source_export.records[0])
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


def test_positive_sft_review_initializes_exact_original_source(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=False,
    )

    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    assert artifact.manifest.artifact_type == "positive_sft_review"
    assert artifact.manifest.record_count == 1
    assert artifact.manifest.original_record_count == 1
    assert artifact.manifest.repaired_record_count == 0
    review = artifact.reviews[0]
    assert review.review_status == "not_reviewed"
    assert review.efficiency_judgment is None
    assert review.source.source_type == "original"
    assert review.source.source_artifact_ref.content_hash is not None
    queue = (artifact.out_dir / artifact.manifest.artifacts["review_queue"]).read_text()
    assert "Prefix And Action-Efficiency Rubric" in queue
    assert "positive_sft_action_efficiency_v0" in queue
    assert '"role": "assistant"' in queue


def test_positive_sft_review_accepts_existing_assistant_boundary(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=False,
    )
    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    initial_validation = validate_positive_sft_review_artifact(artifact.out_dir)
    selections = build_positive_sft_review_selections(
        initial_validation.source_candidate_export,
        repair_validation=None,
        selected_repair_ids=(),
    )
    assistant_ids = [
        message.message_id
        for message in selections[0].messages
        if message.role == "assistant"
    ]
    accepted = artifact.reviews[0].model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "positive_sft_review_001",
            "reviewer_id": "reviewer_001",
            "review_decision": "accepted",
            "last_approved_assistant_message_id": assistant_ids[-1],
        }
    )
    write_positive_sft_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        (accepted,),
    )

    validation = validate_positive_sft_review_artifact(artifact.out_dir)

    assert validation.review_artifact.reviews[0].review_decision == "accepted"
    assert (
        validation.review_artifact.reviews[0].last_approved_assistant_message_id
        == assistant_ids[-1]
    )


def test_positive_sft_review_rejects_non_assistant_boundary(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=False,
    )
    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    initial_validation = validate_positive_sft_review_artifact(artifact.out_dir)
    selections = build_positive_sft_review_selections(
        initial_validation.source_candidate_export,
        repair_validation=None,
        selected_repair_ids=(),
    )
    user_message_id = next(
        message.message_id
        for message in selections[0].messages
        if message.role == "user"
    )
    invalid = artifact.reviews[0].model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "positive_sft_review_001",
            "reviewer_id": "reviewer_001",
            "review_decision": "accepted",
            "last_approved_assistant_message_id": user_message_id,
        }
    )
    write_positive_sft_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        (invalid,),
    )

    with pytest.raises(ValueError, match="must identify an assistant message"):
        validate_positive_sft_review_artifact(artifact.out_dir)


def test_positive_sft_review_rejects_efficiency_evidence_after_prefix_boundary(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=False,
    )
    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )
    initial_validation = validate_positive_sft_review_artifact(artifact.out_dir)
    selections = build_positive_sft_review_selections(
        initial_validation.source_candidate_export,
        repair_validation=None,
        selected_repair_ids=(),
    )
    assistant_ids = [
        message.message_id
        for message in selections[0].messages
        if message.role == "assistant"
    ]
    payload = artifact.reviews[0].model_dump(mode="json")
    payload.update(
        {
            "review_status": "reviewed",
            "review_id": "positive_sft_review_001",
            "reviewer_id": "reviewer_001",
            "review_decision": "accepted",
            "last_approved_assistant_message_id": assistant_ids[0],
            "efficiency_judgment": {
                "review_id": "efficiency_review_001",
                "reviewer_id": "reviewer_002",
                "review_decision": "rejected",
                "decision_reason": "A later action was avoidable.",
                "review_notes_ref": None,
                "avoidable_assistant_message_ids": [assistant_ids[-1]],
            },
        }
    )
    invalid = PositiveSFTReviewRecord.model_validate(payload)
    write_positive_sft_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        (invalid,),
    )

    with pytest.raises(
        ValueError,
        match="efficiency evidence must identify a retained prefix message",
    ):
        validate_positive_sft_review_artifact(artifact.out_dir)


def test_positive_sft_review_pins_selected_repaired_source(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    repair_export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repair_review = _initialize_accepted_repair_review(
        repair_export.out_dir,
        tmp_path / "repair-review",
    )
    repair = repair_export.records[0]

    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
        repair_export_dir=repair_export.out_dir,
        repair_review_dir=repair_review.out_dir,
        selected_repair_ids=(repair.repair_id,),
    )

    assert artifact.manifest.original_record_count == 0
    assert artifact.manifest.repaired_record_count == 1
    assert artifact.manifest.source_training_candidate_repair_export is not None
    assert artifact.manifest.source_training_candidate_repair_review is not None
    source = artifact.reviews[0].source
    assert source.source_type == "repaired"
    assert source.repair_id == repair.repair_id
    assert source.source_artifact_ref == repair.repaired_artifact_ref
    validation = validate_positive_sft_review_artifact(artifact.out_dir)
    assert validation.repair_validation is not None


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


def test_positive_sft_uses_explicit_accepted_completed_repair(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    repair_export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repair_review = _initialize_accepted_repair_review(
        repair_export.out_dir,
        tmp_path / "repair-review",
    )
    repair = repair_export.records[0]
    sft_review = _initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
        repair_export_dir=repair_export.out_dir,
        repair_review_dir=repair_review.out_dir,
        selected_repair_ids=(repair.repair_id,),
    )

    sft_export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )

    assert sft_export.manifest.record_count == 1
    assert sft_export.manifest.original_record_count == 0
    assert sft_export.manifest.repaired_record_count == 1
    assert sft_export.manifest.source_positive_sft_review.manifest_hash == hash_file(
        sft_review.out_dir / MANIFEST_FILENAME
    )
    example = sft_export.records[0]
    assert example.source_provenance.source_type == "repaired"
    assert example.source_provenance.repair_id == repair.repair_id
    assert (
        example.source_provenance.source_training_candidate_repair_record_hash
        == hash_training_candidate_repair_record(repair)
    )
    assert (
        example.source_provenance.source_training_candidate_repair_review_record_hash
        == hash_training_candidate_repair_review_record(repair_review.reviews[0])
    )
    assert (
        example.source_provenance.task_outcome_provenance
        == "inherited_from_source_trajectory"
    )
    assert (
        example.source_provenance.task_outcome_inheritance_basis
        == "mechanical_redundancy_state_and_observation_preserving_deletion"
    )
    assert "tool_call_redundant_0001" not in {
        message.tool_call_id for message in example.messages
    }
    assert "tool_call_0001" in {message.tool_call_id for message in example.messages}


def test_positive_sft_skips_redundant_candidate_without_selected_repair(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    sft_review = _initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
    )

    sft_export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )

    assert sft_export.records == ()
    assert sft_export.manifest.record_count == 0


def test_positive_sft_rejects_selected_repair_without_accepted_review(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    repair_export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repair_review = initialize_training_candidate_repair_review_artifact(
        repair_export.out_dir,
        tmp_path / "repair-review",
    )

    with pytest.raises(ValueError, match="does not have an accepted review"):
        initialize_positive_sft_review_artifact(
            candidate_export_dir,
            tmp_path / "positive-sft-review",
            repair_export_dir=repair_export.out_dir,
            repair_review_dir=repair_review.out_dir,
            selected_repair_ids=(repair_export.records[0].repair_id,),
        )


def test_positive_sft_rejects_accepted_cannot_complete_repair(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    candidate_export = load_training_candidate_export_artifact(candidate_export_dir)
    repair_export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repair_review = _initialize_accepted_repair_review(
        repair_export.out_dir,
        tmp_path / "repair-review",
    )
    validation = validate_training_candidate_repair_review_artifact(
        repair_export.out_dir,
        repair_review.out_dir,
    )
    repair_payload = repair_export.records[0].model_dump(mode="json")
    repair_payload["repair_status"] = "cannot_complete"
    repair_payload["repaired_artifact_ref"] = None
    repair_details = repair_payload["repair"]
    assert isinstance(repair_details, dict)
    repair_details["after_repair_mechanical_redundancy_assessment"] = None
    repair_details["cannot_complete_reason"] = "safe deletion was unavailable"
    cannot_complete = TrainingCandidateRepairRecord.model_validate(repair_payload)
    accepted_review = TrainingCandidateRepairReviewRecord.model_validate(
        {
            **repair_review.reviews[0].model_dump(mode="json"),
            "source_training_candidate_repair_record_hash": (
                hash_training_candidate_repair_record(cannot_complete)
            ),
        }
    )
    synthetic_validation = replace(
        validation,
        source_export=replace(
            validation.source_export,
            records=(cannot_complete,),
        ),
        review_artifact=replace(
            validation.review_artifact,
            reviews=(accepted_review,),
        ),
    )

    with pytest.raises(ValueError, match="selected repair is not completed"):
        build_positive_sft_review_selections(
            candidate_export,
            repair_validation=synthetic_validation,
            selected_repair_ids=(cannot_complete.repair_id,),
        )


def test_positive_sft_rejects_unknown_selected_repair_id(tmp_path: Path) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    repair_export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repair_review = _initialize_accepted_repair_review(
        repair_export.out_dir,
        tmp_path / "repair-review",
    )

    with pytest.raises(ValueError, match="selected unknown repair_id"):
        initialize_positive_sft_review_artifact(
            candidate_export_dir,
            tmp_path / "positive-sft-review",
            repair_export_dir=repair_export.out_dir,
            repair_review_dir=repair_review.out_dir,
            selected_repair_ids=("repair_unknown",),
        )


def test_positive_sft_reload_rejects_repair_review_drift(tmp_path: Path) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    repair_export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repair_review = _initialize_accepted_repair_review(
        repair_export.out_dir,
        tmp_path / "repair-review",
    )
    sft_review = _initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
        repair_export_dir=repair_export.out_dir,
        repair_review_dir=repair_review.out_dir,
        selected_repair_ids=(repair_export.records[0].repair_id,),
    )
    sft_export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )
    rejected_review = repair_review.reviews[0].model_copy(
        update={
            "review_status": "reviewed",
            "review_id": "repair_review_changed",
            "reviewer_id": "reviewer",
            "review_decision": "rejected",
        }
    )
    write_training_candidate_repair_review_records_jsonl(
        repair_review.out_dir / repair_review.manifest.artifacts["reviews"],
        (rejected_review,),
    )

    with pytest.raises(ValueError, match="source repair reviews hash mismatch"):
        load_positive_sft_export_artifact(sft_export.out_dir)


def test_positive_sft_reload_rejects_rebound_repair_review_record_hash(
    tmp_path: Path,
) -> None:
    candidate_export_dir = _build_candidate_export(
        tmp_path,
        add_redundancy=True,
    )
    repair_export = export_training_candidate_repairs(
        candidate_export_dir,
        tmp_path / "repair-export",
    )
    repair_review = _initialize_accepted_repair_review(
        repair_export.out_dir,
        tmp_path / "repair-review",
    )
    sft_review = _initialize_accepted_positive_sft_review(
        candidate_export_dir,
        tmp_path / "positive-sft-review",
        repair_export_dir=repair_export.out_dir,
        repair_review_dir=repair_review.out_dir,
        selected_repair_ids=(repair_export.records[0].repair_id,),
    )
    sft_export = export_positive_sft_examples(
        candidate_export_dir,
        sft_review.out_dir,
        tmp_path / "positive-sft-export",
    )
    examples_path = (
        sft_export.out_dir / sft_export.manifest.artifacts["positive_sft_examples"]
    )
    payload = json.loads(examples_path.read_text())
    payload["source_provenance"][
        "source_training_candidate_repair_review_record_hash"
    ] = "xxh64:ffffffffffffffff"
    examples_path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    manifest_path = sft_export.out_dir / MANIFEST_FILENAME
    manifest_payload = json.loads(manifest_path.read_text())
    manifest_payload["positive_sft_examples_jsonl_hash"] = hash_file(examples_path)
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n"
    )

    with pytest.raises(
        ValueError,
        match="do not match records rebuilt from their pinned sources",
    ):
        load_positive_sft_export_artifact(sft_export.out_dir)


def _initialize_accepted_repair_review(
    repair_export_dir: Path,
    out_dir: Path,
) -> TrainingCandidateRepairReviewArtifact:
    artifact = initialize_training_candidate_repair_review_artifact(
        repair_export_dir,
        out_dir,
    )
    accepted = tuple(
        review.model_copy(
            update={
                "review_status": "reviewed",
                "review_id": f"repair_review_{index:04d}",
                "reviewer_id": "reviewer",
                "review_decision": "accepted",
            }
        )
        for index, review in enumerate(artifact.reviews, start=1)
    )
    write_training_candidate_repair_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        accepted,
    )
    return load_training_candidate_repair_review_artifact(artifact.out_dir)


def _initialize_accepted_positive_sft_review(
    candidate_export_dir: Path,
    out_dir: Path,
    *,
    repair_export_dir: Path | None = None,
    repair_review_dir: Path | None = None,
    selected_repair_ids: tuple[str, ...] = (),
) -> PositiveSFTReviewArtifact:
    artifact = initialize_positive_sft_review_artifact(
        candidate_export_dir,
        out_dir,
        repair_export_dir=repair_export_dir,
        repair_review_dir=repair_review_dir,
        selected_repair_ids=selected_repair_ids,
    )
    validation = validate_positive_sft_review_artifact(artifact.out_dir)
    selections = build_positive_sft_review_selections(
        validation.source_candidate_export,
        repair_validation=validation.repair_validation,
        selected_repair_ids=selected_repair_ids,
    )
    selection_by_candidate = {
        selection.candidate_hash: selection for selection in selections
    }
    accepted = tuple(
        review.model_copy(
            update={
                "review_status": "reviewed",
                "review_id": f"positive_sft_review_{index:04d}",
                "reviewer_id": "reviewer",
                "review_decision": "accepted",
                "last_approved_assistant_message_id": next(
                    message.message_id
                    for message in reversed(
                        selection_by_candidate[
                            review.source_training_candidate_record_hash
                        ].messages
                    )
                    if message.role == "assistant"
                ),
            }
        )
        for index, review in enumerate(artifact.reviews, start=1)
    )
    write_positive_sft_review_records_jsonl(
        artifact.out_dir / artifact.manifest.artifacts["reviews"],
        accepted,
    )
    return artifact


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
    redundant_assistant["message_id"] = new_message_id()
    redundant_assistant["tool_call_id"] = redundant_id
    redundant_tool = copy.deepcopy(tool_message)
    redundant_tool["message_id"] = new_message_id()
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
