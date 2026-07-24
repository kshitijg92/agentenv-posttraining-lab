import json
from pathlib import Path
from typing import Sequence

import pytest
from pydantic import ValidationError

from agentenv.artifacts import MANIFEST_FILENAME, ArtifactType
from agentenv.artifacts.manifests import (
    POSITIVE_SFT_EXPORT_ARTIFACT_REFS,
    POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION,
    POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_REFS,
    POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION,
    PositiveSFTExportManifest,
    PositiveSFTTrainingMaterializationManifest,
)
from agentenv.hashing import hash_file, hash_json
from agentenv.training.positive_sft.efficiency_review import (
    POSITIVE_SFT_EFFICIENCY_RUBRIC,
    initialize_positive_sft_efficiency_review_artifact,
    load_positive_sft_efficiency_review_inventory,
    validate_positive_sft_efficiency_review_artifact,
    validate_positive_sft_efficiency_review_records,
    write_positive_sft_efficiency_review_records_jsonl,
)
from agentenv.training.positive_sft.export import (
    write_positive_sft_example_records_jsonl,
)
from agentenv.training.positive_sft.identity import build_positive_sft_example_id
from agentenv.training.positive_sft.materialization.export import (
    write_positive_sft_training_materialization_records_jsonl,
)
from agentenv.training.positive_sft.materialization.schema import (
    CompletedPositiveSFTTrainingMaterializationRecord,
)
from agentenv.training.positive_sft.schema import (
    PositiveSFTEfficiencyReviewRecord,
    PositiveSFTExampleRecord,
)


def test_efficiency_review_record_enforces_review_state_and_rejection_evidence() -> (
    None
):
    source = {
        "source_positive_sft_example_id": ("positive_sft_example_aaaaaaaaaaaaaaaa"),
        "source_positive_sft_example_record_hash": "xxh64:1111111111111111",
    }

    not_reviewed = PositiveSFTEfficiencyReviewRecord.model_validate(
        {**source, "review_status": "not_reviewed"}
    )
    assert not_reviewed.review_decision is None

    with pytest.raises(
        ValidationError,
        match="rejected efficiency reviews require at least one exact",
    ):
        PositiveSFTEfficiencyReviewRecord.model_validate(
            {
                **source,
                "review_status": "reviewed",
                "review_id": "review_1",
                "reviewer_id": "human_1",
                "review_decision": "rejected",
                "decision_reason": "One read was redundant.",
            }
        )

    with pytest.raises(
        ValidationError,
        match="only rejected efficiency reviews can identify avoidable",
    ):
        PositiveSFTEfficiencyReviewRecord.model_validate(
            {
                **source,
                "review_status": "reviewed",
                "review_id": "review_1",
                "reviewer_id": "human_1",
                "review_decision": "accepted",
                "decision_reason": "Every action was useful.",
                "avoidable_assistant_message_ids": [
                    "message_00000000000000000000000000000003"
                ],
            }
        )

    needs_followup = PositiveSFTEfficiencyReviewRecord.model_validate(
        {
            **source,
            "review_status": "reviewed",
            "review_id": "review_2",
            "reviewer_id": "llm_1",
            "review_decision": "needs_followup",
            "decision_reason": "The available context does not establish redundancy.",
        }
    )
    assert needs_followup.review_decision == "needs_followup"


def test_initialize_and_validate_efficiency_review_queue_from_materializations(
    tmp_path: Path,
) -> None:
    examples = (_example(identity_suffix="3"), _example(identity_suffix="0"))
    materialization_dir = _materialization_artifact(
        tmp_path,
        name="source",
        examples=examples,
    )

    artifact = initialize_positive_sft_efficiency_review_artifact(
        [materialization_dir],
        tmp_path / "reviews",
    )

    assert artifact.manifest.record_count == 2
    assert len(artifact.manifest.source_positive_sft_training_materializations) == 1
    assert [review.source_positive_sft_example_id for review in artifact.reviews] == (
        sorted(example.example_id for example in examples)
    )
    assert all(review.review_status == "not_reviewed" for review in artifact.reviews)
    queue = (artifact.out_dir / artifact.manifest.artifacts["review_queue"]).read_text()
    assert "supervised_token_count: `2`" in queue
    assert "assistant_action_count: `2`" in queue
    assert '"role": "tool"' in queue
    assert json.dumps(examples[0].messages[-1].content) in queue
    assert (
        artifact.out_dir / artifact.manifest.artifacts["rubric"]
    ).read_text() == POSITIVE_SFT_EFFICIENCY_RUBRIC

    validation = validate_positive_sft_efficiency_review_artifact(artifact.out_dir)
    assert validation.review_status_counts == {
        "not_reviewed": 2,
        "reviewed": 0,
    }
    assert validation.review_decision_counts == {
        "accepted": 0,
        "rejected": 0,
        "needs_followup": 0,
    }


def test_review_validation_accepts_complete_decisions_and_checks_message_evidence(
    tmp_path: Path,
) -> None:
    examples = (_example(identity_suffix="0"), _example(identity_suffix="3"))
    materialization_dir = _materialization_artifact(
        tmp_path,
        name="source",
        examples=examples,
    )
    artifact = initialize_positive_sft_efficiency_review_artifact(
        [materialization_dir],
        tmp_path / "reviews",
    )
    rows_by_id = {
        review.source_positive_sft_example_id: review for review in artifact.reviews
    }
    accepted_example, rejected_example = examples
    accepted = _reviewed_record(
        rows_by_id[accepted_example.example_id],
        decision="accepted",
        reason="Both assistant actions acquire or report task-relevant state.",
    )
    rejected = _reviewed_record(
        rows_by_id[rejected_example.example_id],
        decision="rejected",
        reason="The first file read repeats information already in context.",
        avoidable_message_ids=("message_00000000000000000000000000000003",),
    )
    reviews_path = artifact.out_dir / artifact.manifest.artifacts["reviews"]
    write_positive_sft_efficiency_review_records_jsonl(
        reviews_path,
        (accepted, rejected),
    )

    validation = validate_positive_sft_efficiency_review_artifact(artifact.out_dir)
    assert validation.review_status_counts == {
        "not_reviewed": 0,
        "reviewed": 2,
    }
    assert validation.review_decision_counts == {
        "accepted": 1,
        "rejected": 1,
        "needs_followup": 0,
    }

    invalid_evidence = _reviewed_record(
        rows_by_id[rejected_example.example_id],
        decision="rejected",
        reason="Claims a non-assistant message as evidence.",
        avoidable_message_ids=("message_00000000000000000000000000000002",),
    )
    inventory = load_positive_sft_efficiency_review_inventory([materialization_dir])
    with pytest.raises(
        ValueError,
        match="avoidable evidence must identify assistant messages",
    ):
        validate_positive_sft_efficiency_review_records(
            (accepted, invalid_evidence),
            inventory.selections,
            review_dir=artifact.out_dir,
        )


def test_review_validation_rejects_duplicate_rows_and_source_drift(
    tmp_path: Path,
) -> None:
    examples = (_example(identity_suffix="0"), _example(identity_suffix="3"))
    materialization_dir = _materialization_artifact(
        tmp_path,
        name="source",
        examples=examples,
    )
    artifact = initialize_positive_sft_efficiency_review_artifact(
        [materialization_dir],
        tmp_path / "reviews",
    )
    reviews_path = artifact.out_dir / artifact.manifest.artifacts["reviews"]
    write_positive_sft_efficiency_review_records_jsonl(
        reviews_path,
        (artifact.reviews[0], artifact.reviews[0]),
    )
    with pytest.raises(
        ValueError,
        match="Duplicate positive-SFT efficiency review source examples",
    ):
        validate_positive_sft_efficiency_review_artifact(artifact.out_dir)

    write_positive_sft_efficiency_review_records_jsonl(
        reviews_path,
        artifact.reviews,
    )
    export_dir = materialization_dir.parent / "source_export"
    examples_path = (
        export_dir / POSITIVE_SFT_EXPORT_ARTIFACT_REFS["positive_sft_examples"]
    )
    examples_path.write_text(examples_path.read_text() + "\n")
    with pytest.raises(
        ValueError,
        match="Source positive-SFT examples JSONL hash mismatch",
    ):
        validate_positive_sft_efficiency_review_artifact(artifact.out_dir)


def test_review_validation_rejects_missing_and_unknown_source_rows(
    tmp_path: Path,
) -> None:
    examples = (_example(identity_suffix="0"), _example(identity_suffix="3"))
    materialization_dir = _materialization_artifact(
        tmp_path,
        name="source",
        examples=examples,
    )
    artifact = initialize_positive_sft_efficiency_review_artifact(
        [materialization_dir],
        tmp_path / "reviews",
    )
    inventory = load_positive_sft_efficiency_review_inventory([materialization_dir])

    with pytest.raises(
        ValueError,
        match="efficiency review is missing source examples",
    ):
        validate_positive_sft_efficiency_review_records(
            artifact.reviews[:1],
            inventory.selections,
            review_dir=artifact.out_dir,
        )

    unknown = PositiveSFTEfficiencyReviewRecord(
        source_positive_sft_example_id="positive_sft_example_ffffffffffffffff",
        source_positive_sft_example_record_hash="xxh64:ffffffffffffffff",
        review_status="not_reviewed",
    )
    with pytest.raises(
        ValueError,
        match="efficiency review contains unknown source examples",
    ):
        validate_positive_sft_efficiency_review_records(
            (*artifact.reviews, unknown),
            inventory.selections,
            review_dir=artifact.out_dir,
        )


def test_inventory_rejects_same_example_from_multiple_materializations(
    tmp_path: Path,
) -> None:
    example = _example(identity_suffix="0")
    first = _materialization_artifact(
        tmp_path,
        name="first",
        examples=(example,),
    )
    second = _materialization_artifact(
        tmp_path,
        name="second",
        examples=(example,),
    )

    with pytest.raises(
        ValueError,
        match="source examples appear in multiple materializations",
    ):
        load_positive_sft_efficiency_review_inventory([first, second])


def _reviewed_record(
    source: PositiveSFTEfficiencyReviewRecord,
    *,
    decision: str,
    reason: str,
    avoidable_message_ids: tuple[str, ...] = (),
) -> PositiveSFTEfficiencyReviewRecord:
    payload = source.model_dump(mode="json")
    payload.update(
        {
            "review_status": "reviewed",
            "review_id": f"review_{source.source_positive_sft_example_id}",
            "reviewer_id": "test_reviewer",
            "review_decision": decision,
            "decision_reason": reason,
            "avoidable_assistant_message_ids": list(avoidable_message_ids),
        }
    )
    return PositiveSFTEfficiencyReviewRecord.model_validate(payload)


def _materialization_artifact(
    tmp_path: Path,
    *,
    name: str,
    examples: Sequence[PositiveSFTExampleRecord],
) -> Path:
    export_dir = tmp_path / f"{name}_export"
    export_dir.mkdir()
    examples_path = (
        export_dir / POSITIVE_SFT_EXPORT_ARTIFACT_REFS["positive_sft_examples"]
    )
    example_tuple = tuple(examples)
    write_positive_sft_example_records_jsonl(examples_path, example_tuple)
    export_manifest = PositiveSFTExportManifest.model_validate(
        {
            "artifact_type": ArtifactType.POSITIVE_SFT_EXPORT,
            "artifact_schema_version": POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION,
            "created_at": "2026-07-22T00:00:00Z",
            "training_authorization": "not_authorized",
            "source_positive_sft_review": {
                "artifact_dir": "/tmp/not-read-by-efficiency-review",
                "manifest_hash": "xxh64:1111111111111111",
                "reviews_jsonl_hash": "xxh64:2222222222222222",
            },
            "positive_sft_review_record_schema_version": (
                "positive_sft_review_record_v0"
            ),
            "positive_sft_example_record_schema_version": (
                "positive_sft_example_record_v0"
            ),
            "record_count": len(example_tuple),
            "original_record_count": len(example_tuple),
            "repaired_record_count": 0,
            "positive_sft_examples_jsonl_hash": hash_file(examples_path),
            "artifacts": dict(POSITIVE_SFT_EXPORT_ARTIFACT_REFS),
        }
    )
    export_manifest_path = export_dir / MANIFEST_FILENAME
    _write_manifest(export_manifest_path, export_manifest.model_dump(mode="json"))

    materialization_dir = tmp_path / f"{name}_materialization"
    materialization_dir.mkdir()
    records = tuple(
        CompletedPositiveSFTTrainingMaterializationRecord(
            source_positive_sft_example_id=example.example_id,
            source_positive_sft_example_record_hash=hash_json(
                example.model_dump(mode="json")
            ),
            model_input_protocol_id="test_protocol",
            model_input_protocol_hash="xxh64:aaaaaaaaaaaaaaaa",
            serialization_mode="completed_transcript",
            max_sequence_length=8,
            materializer_version="test_materializer_v0",
            materializer_code_hash="xxh64:bbbbbbbbbbbbbbbb",
            status="completed",
            input_ids=[1, 2, 3],
            labels=[-100, 2, 3],
            sequence_length=3,
            supervised_token_count=2,
            ignored_token_count=1,
        )
        for example in example_tuple
    )
    records_path = (
        materialization_dir
        / (POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_REFS["materializations"])
    )
    write_positive_sft_training_materialization_records_jsonl(records_path, records)
    materialization_manifest = (
        PositiveSFTTrainingMaterializationManifest.model_validate(
            {
                "artifact_type": ArtifactType.POSITIVE_SFT_TRAINING_MATERIALIZATION,
                "artifact_schema_version": (
                    POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_SCHEMA_VERSION
                ),
                "created_at": "2026-07-22T00:00:00Z",
                "training_authorization": "not_authorized",
                "training_authorization_override": None,
                "source_positive_sft_export": {
                    "artifact_dir": str(export_dir),
                    "manifest_hash": hash_file(export_manifest_path),
                    "positive_sft_examples_jsonl_hash": hash_file(examples_path),
                },
                "model_input_protocol_path": "/tmp/not-read-by-efficiency-review.yaml",
                "model_input_protocol_id": "test_protocol",
                "model_input_protocol_hash": "xxh64:aaaaaaaaaaaaaaaa",
                "serialization_mode": "completed_transcript",
                "max_sequence_length": 8,
                "materializer_version": "test_materializer_v0",
                "materializer_code_hash": "xxh64:bbbbbbbbbbbbbbbb",
                "positive_sft_training_materialization_record_schema_version": (
                    "positive_sft_training_materialization_record_v0"
                ),
                "record_count": len(records),
                "completed_count": len(records),
                "failed_count": 0,
                "sequence_length_exceeded_count": 0,
                "materialization_error_count": 0,
                "materializations_jsonl_hash": hash_file(records_path),
                "artifacts": dict(POSITIVE_SFT_TRAINING_MATERIALIZATION_ARTIFACT_REFS),
            }
        )
    )
    _write_manifest(
        materialization_dir / MANIFEST_FILENAME,
        materialization_manifest.model_dump(mode="json"),
    )
    return materialization_dir


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _example(*, identity_suffix: str) -> PositiveSFTExampleRecord:
    candidate_hash = f"xxh64:{identity_suffix * 16}"
    source_artifact_hash = f"xxh64:{chr(ord(identity_suffix) + 1) * 16}"
    review_hash = f"xxh64:{chr(ord(identity_suffix) + 2) * 16}"
    example_id = build_positive_sft_example_id(
        source_type="original",
        source_training_candidate_record_hash=candidate_hash,
        source_artifact_content_hash=source_artifact_hash,
        source_positive_sft_review_record_hash=review_hash,
    )
    final_message_id = "message_00000000000000000000000000000005"
    return PositiveSFTExampleRecord.model_validate(
        {
            "example_id": example_id,
            "provenance_ids": {
                "trajectory_id": f"trajectory_{identity_suffix}",
                "eval_suite_id": None,
                "eval_run_id": f"eval_run_{identity_suffix}",
                "eval_attempt_id": f"eval_attempt_{identity_suffix}",
                "agent_attempt_id": f"agent_attempt_{identity_suffix}",
                "task_id": f"task_{identity_suffix}",
                "policy_id": f"policy_{identity_suffix}",
            },
            "prompt_provenance": {
                "prompt_builder_version": "prompt_builder_v0",
                "prompt_builder_code_hash": "xxh64:aaaaaaaaaaaaaaaa",
            },
            "review_provenance": {
                "source_positive_sft_review_record_hash": review_hash,
                "positive_sft_review_id": f"review_{identity_suffix}",
                "last_approved_assistant_message_id": final_message_id,
            },
            "source_provenance": {
                "source_type": "original",
                "source_training_candidate_record_hash": candidate_hash,
                "source_artifact_ref": {
                    "path": "prompt_loop_result.json",
                    "content_hash": source_artifact_hash,
                },
                "task_outcome_provenance": "executed_source_trajectory",
            },
            "task_input": {
                "task_id": f"task_{identity_suffix}",
                "instruction": "Inspect and fix the code.",
                "allowed_tools": ["read_file"],
                "public_checks": ["pytest -q"],
                "max_turns": 8,
                "timeout_seconds": 120,
                "network": "off",
            },
            "messages": [
                {
                    "message_id": "message_00000000000000000000000000000001",
                    "role": "system",
                    "content": "Use one JSON action per turn.",
                },
                {
                    "message_id": "message_00000000000000000000000000000002",
                    "role": "user",
                    "content": "Inspect and fix the code.",
                },
                {
                    "message_id": "message_00000000000000000000000000000003",
                    "role": "assistant",
                    "content": (
                        '{"action":"tool_call","tool_name":"read_file",'
                        '"arguments":{"path":"src/a.py"}}'
                    ),
                    "tool_call_id": "tool_call_001",
                },
                {
                    "message_id": "message_00000000000000000000000000000004",
                    "role": "tool",
                    "content": '{"status":"ok"}',
                    "name": "read_file",
                    "tool_call_id": "tool_call_001",
                },
                {
                    "message_id": final_message_id,
                    "role": "assistant",
                    "content": '{"action":"final_answer","text":"done"}',
                },
            ],
        }
    )
