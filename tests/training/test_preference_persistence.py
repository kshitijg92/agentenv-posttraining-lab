import json
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

import agentenv.training.preferences.export as preference_export_module
from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import TrainingCandidateExportManifest
from agentenv.cli import app
from agentenv.hashing import hash_file
from agentenv.training.candidates.export import TrainingCandidateExport
from agentenv.training.preferences.builder import (
    PREFERENCE_DISCOVERY_METHOD,
    PREFERENCE_DISCOVERY_VERSION,
    compute_preference_discovery_code_hash,
)
from agentenv.training.preferences.export import (
    export_preference_comparison_candidates,
    load_preference_comparison_export_artifact,
)
from agentenv.training.preferences.hashing import (
    PREFERENCE_ACTION_PROJECTION_VERSION,
    PREFERENCE_MESSAGE_PROJECTION_VERSION,
    build_preference_alternative_id,
    build_preference_comparison_candidate_id,
    build_preference_rollout_evidence_id,
    build_preference_shared_context_id,
    hash_preference_adjudication_record,
    hash_preference_action,
    hash_preference_comparison_candidate_record,
)
from agentenv.training.preferences.pair_export import (
    export_preference_pairs,
    load_preference_pair_export_artifact,
)
from agentenv.training.preferences.review import (
    initialize_preference_adjudication_review_artifact,
    load_preference_adjudication_review_artifact,
    validate_preference_adjudication_review_artifact,
    write_preference_adjudication_records_jsonl,
)
from agentenv.training.preferences.schema import (
    PreferenceAdjudicationRecord,
    PreferenceComparisonCandidateRecord,
)


RUBRIC_PATH = Path(
    "configs/training/preference_rubrics/overall_action_preference_v0.md"
)


def test_preference_comparison_and_adjudication_artifacts_preserve_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _comparison_candidate()
    source_export = _stub_candidate_export(
        tmp_path,
        monkeypatch,
        discovered_records=(candidate,),
    )

    comparison_export = export_preference_comparison_candidates(
        source_export.out_dir,
        tmp_path / "preference-comparisons",
    )

    assert comparison_export.records == (candidate,)
    assert comparison_export.manifest.artifact_type == "preference_comparison_export"
    assert comparison_export.manifest.record_count == 1
    assert comparison_export.manifest.shared_context_count == 1
    assert comparison_export.manifest.training_authorization == "not_authorized"
    assert comparison_export.manifest.discovery_method == PREFERENCE_DISCOVERY_METHOD
    assert comparison_export.manifest.discovery_version == PREFERENCE_DISCOVERY_VERSION
    assert comparison_export.manifest.discovery_code_hash == (
        compute_preference_discovery_code_hash()
    )
    assert (
        comparison_export.manifest.source_training_candidate_export.manifest_hash
        == hash_file(source_export.out_dir / MANIFEST_FILENAME)
    )

    review = initialize_preference_adjudication_review_artifact(
        comparison_export.out_dir,
        RUBRIC_PATH,
        tmp_path / "preference-review",
    )

    assert review.manifest.artifact_type == "preference_adjudication_review"
    assert review.manifest.training_authorization == "not_authorized"
    assert review.manifest.record_count == 1
    assert review.adjudications[0].review_status == "not_reviewed"
    rubric_ref = review.manifest.rubric_provenance.rubric_ref
    copied_rubric_path = review.out_dir / rubric_ref.path
    assert copied_rubric_path.read_bytes() == RUBRIC_PATH.read_bytes()
    assert rubric_ref.content_hash == hash_file(copied_rubric_path)
    queue = (review.out_dir / review.manifest.artifacts["review_queue"]).read_text()
    assert json.dumps(candidate.alternative_a.assistant_content) in queue
    assert json.dumps(candidate.alternative_b.assistant_content) in queue

    reviewed_payload = review.adjudications[0].model_dump(mode="json")
    reviewed_payload.update(
        {
            "review_status": "reviewed",
            "review_id": "preference_review_001",
            "reviewer_provenance": {
                "reviewer_type": "human",
                "reviewer_id": "reviewer_001",
            },
            "review_decision": "preferred",
            "preferred_alternative_id": candidate.alternative_a.alternative_id,
            "decision_reason": (
                "Alternative A advances the task while B repeats known work."
            ),
            "reviewed_at_utc": "2026-07-21T20:00:00Z",
        }
    )
    reviewed = PreferenceAdjudicationRecord.model_validate(reviewed_payload)
    write_preference_adjudication_records_jsonl(
        review.out_dir / review.manifest.artifacts["adjudications"],
        (reviewed,),
    )

    validation = validate_preference_adjudication_review_artifact(review.out_dir)

    assert validation.review_status_counts == {"not_reviewed": 0, "reviewed": 1}
    assert validation.review_decision_counts == {
        "preferred": 1,
        "tie": 0,
        "ambiguous": 0,
        "invalid": 0,
    }


def test_preference_adjudication_rejects_missing_comparison_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _comparison_candidate()
    source_export = _stub_candidate_export(
        tmp_path,
        monkeypatch,
        discovered_records=(candidate,),
    )
    comparison_export = export_preference_comparison_candidates(
        source_export.out_dir,
        tmp_path / "preference-comparisons",
    )
    review = initialize_preference_adjudication_review_artifact(
        comparison_export.out_dir,
        RUBRIC_PATH,
        tmp_path / "preference-review",
    )
    write_preference_adjudication_records_jsonl(
        review.out_dir / review.manifest.artifacts["adjudications"],
        (),
    )

    with pytest.raises(ValueError, match="record count mismatch"):
        validate_preference_adjudication_review_artifact(review.out_dir)


def test_preference_adjudication_rejects_rubric_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _stub_candidate_export(
        tmp_path,
        monkeypatch,
        discovered_records=(_comparison_candidate(),),
    )
    comparison_export = export_preference_comparison_candidates(
        source_export.out_dir,
        tmp_path / "preference-comparisons",
    )
    review = initialize_preference_adjudication_review_artifact(
        comparison_export.out_dir,
        RUBRIC_PATH,
        tmp_path / "preference-review",
    )
    rubric_path = review.out_dir / review.manifest.artifacts["rubric"]
    rubric_path.write_text(rubric_path.read_text() + "\nchanged\n")

    with pytest.raises(ValueError, match="rubric hash mismatch"):
        load_preference_adjudication_review_artifact(review.out_dir)


def test_preference_persistence_allows_empty_discovery_and_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _stub_candidate_export(
        tmp_path,
        monkeypatch,
        discovered_records=(),
    )
    comparison_export = export_preference_comparison_candidates(
        source_export.out_dir,
        tmp_path / "preference-comparisons",
    )
    review = initialize_preference_adjudication_review_artifact(
        comparison_export.out_dir,
        RUBRIC_PATH,
        tmp_path / "preference-review",
    )
    validation = validate_preference_adjudication_review_artifact(review.out_dir)
    pair_export = export_preference_pairs(
        comparison_export.out_dir,
        review.out_dir,
        tmp_path / "preference-pairs",
    )

    assert comparison_export.records == ()
    assert comparison_export.manifest.record_count == 0
    assert comparison_export.manifest.shared_context_count == 0
    assert review.adjudications == ()
    assert validation.review_status_counts == {"not_reviewed": 0, "reviewed": 0}
    assert pair_export.records == ()
    assert pair_export.manifest.record_count == 0
    assert pair_export.manifest.source_adjudication_record_count == 0


def test_training_preferences_cli_exposes_persistence_workflow() -> None:
    result = CliRunner().invoke(app, ["training", "preferences", "--help"])

    assert result.exit_code == 0, result.output
    assert "discover" in result.output
    assert "review-init" in result.output
    assert "review-validate" in result.output
    assert "export" in result.output


def test_preference_comparison_load_rejects_payload_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_export = _stub_candidate_export(
        tmp_path,
        monkeypatch,
        discovered_records=(_comparison_candidate(),),
    )
    comparison_export = export_preference_comparison_candidates(
        source_export.out_dir,
        tmp_path / "preference-comparisons",
    )
    records_path = (
        comparison_export.out_dir
        / comparison_export.manifest.artifacts["comparison_candidates"]
    )
    records_path.write_text(records_path.read_text() + "\n")

    with pytest.raises(ValueError, match="JSONL hash mismatch"):
        load_preference_comparison_export_artifact(comparison_export.out_dir)


@pytest.mark.parametrize(
    ("decision", "expected_pair_count"),
    [
        (None, 0),
        ("preferred", 1),
        ("tie", 0),
        ("ambiguous", 0),
        ("invalid", 0),
    ],
)
def test_preference_pair_export_selects_only_preferred_adjudications(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str | None,
    expected_pair_count: int,
) -> None:
    candidate = _comparison_candidate()
    source_export = _stub_candidate_export(
        tmp_path,
        monkeypatch,
        discovered_records=(candidate,),
    )
    comparison_export = export_preference_comparison_candidates(
        source_export.out_dir,
        tmp_path / "preference-comparisons",
    )
    review = initialize_preference_adjudication_review_artifact(
        comparison_export.out_dir,
        RUBRIC_PATH,
        tmp_path / "preference-review",
    )
    adjudication = review.adjudications[0]
    if decision is not None:
        adjudication = _review_adjudication(
            adjudication,
            candidate=candidate,
            decision=decision,
        )
        write_preference_adjudication_records_jsonl(
            review.out_dir / review.manifest.artifacts["adjudications"],
            (adjudication,),
        )

    pair_export = export_preference_pairs(
        comparison_export.out_dir,
        review.out_dir,
        tmp_path / "preference-pairs",
    )

    assert pair_export.manifest.record_count == expected_pair_count
    assert len(pair_export.records) == expected_pair_count
    assert pair_export.manifest.shared_context_count == expected_pair_count
    assert pair_export.manifest.source_adjudication_record_count == 1
    assert pair_export.manifest.source_not_reviewed_count == (decision is None)
    assert pair_export.manifest.source_preferred_count == (decision == "preferred")
    assert pair_export.manifest.source_tie_count == (decision == "tie")
    assert pair_export.manifest.source_ambiguous_count == (decision == "ambiguous")
    assert pair_export.manifest.source_invalid_count == (decision == "invalid")
    assert pair_export.manifest.training_authorization == "not_authorized"
    if decision != "preferred":
        return

    pair = pair_export.records[0]
    assert pair.source.comparison_candidate_id == candidate.comparison_candidate_id
    assert pair.source.source_preference_comparison_candidate_record_hash == (
        hash_preference_comparison_candidate_record(candidate)
    )
    assert pair.source.source_preference_adjudication_record_hash == (
        hash_preference_adjudication_record(adjudication)
    )
    payload = pair.model_dump(mode="json")
    assert "assistant_content" not in json.dumps(payload)
    assert "preferred_alternative_id" not in json.dumps(payload)


def test_preference_pair_export_pins_mutable_adjudication_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _comparison_candidate()
    source_export = _stub_candidate_export(
        tmp_path,
        monkeypatch,
        discovered_records=(candidate,),
    )
    comparison_export = export_preference_comparison_candidates(
        source_export.out_dir,
        tmp_path / "preference-comparisons",
    )
    review = initialize_preference_adjudication_review_artifact(
        comparison_export.out_dir,
        RUBRIC_PATH,
        tmp_path / "preference-review",
    )
    preferred = _review_adjudication(
        review.adjudications[0],
        candidate=candidate,
        decision="preferred",
    )
    adjudications_path = review.out_dir / review.manifest.artifacts["adjudications"]
    write_preference_adjudication_records_jsonl(adjudications_path, (preferred,))
    pair_export = export_preference_pairs(
        comparison_export.out_dir,
        review.out_dir,
        tmp_path / "preference-pairs",
    )
    tie = _review_adjudication(
        review.adjudications[0],
        candidate=candidate,
        decision="tie",
    )
    write_preference_adjudication_records_jsonl(adjudications_path, (tie,))

    with pytest.raises(ValueError, match="source adjudication JSONL hash mismatch"):
        load_preference_pair_export_artifact(pair_export.out_dir)


def _review_adjudication(
    adjudication: PreferenceAdjudicationRecord,
    *,
    candidate: PreferenceComparisonCandidateRecord,
    decision: str,
) -> PreferenceAdjudicationRecord:
    payload = adjudication.model_dump(mode="json")
    payload.update(
        {
            "review_status": "reviewed",
            "review_id": f"preference_review_{decision}",
            "reviewer_provenance": {
                "reviewer_type": "human",
                "reviewer_id": "reviewer_001",
            },
            "review_decision": decision,
            "preferred_alternative_id": (
                candidate.alternative_a.alternative_id
                if decision == "preferred"
                else None
            ),
            "decision_reason": f"Fixture decision: {decision}.",
            "reviewed_at_utc": "2026-07-21T20:00:00Z",
        }
    )
    return PreferenceAdjudicationRecord.model_validate(payload)


def _stub_candidate_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    discovered_records: tuple[PreferenceComparisonCandidateRecord, ...],
) -> TrainingCandidateExport:
    source_dir = tmp_path / "training-candidates"
    source_dir.mkdir()
    (source_dir / MANIFEST_FILENAME).write_text('{"fixture":"candidate-export"}\n')
    source_export = TrainingCandidateExport(
        out_dir=source_dir.resolve(),
        manifest=cast(TrainingCandidateExportManifest, None),
        records=(),
    )
    monkeypatch.setattr(
        preference_export_module,
        "load_training_candidate_export_artifact",
        lambda _path: source_export,
    )
    monkeypatch.setattr(
        preference_export_module,
        "discover_preference_comparison_candidates_from_export",
        lambda _export: discovered_records,
    )
    return source_export


def _comparison_candidate() -> PreferenceComparisonCandidateRecord:
    task_provenance = {
        "task_id": "repair_jsonl_deduper",
        "split": "dev",
        "task_manifest_hash": "xxh64:1111111111111111",
        "task_record_hash": "xxh64:2222222222222222",
        "required_task_files_hash": "xxh64:3333333333333333",
        "full_task_dir_hash": "xxh64:4444444444444444",
        "seed_workspace_hash": "xxh64:5555555555555555",
    }
    message_hashes = ["xxh64:6666666666666666", "xxh64:7777777777777777"]
    context_id = build_preference_shared_context_id(
        task_provenance=task_provenance,
        harness_runtime_hash="xxh64:8888888888888888",
        ordered_message_hashes=message_hashes,
        canonical_workspace_hash_before_action="xxh64:9999999999999999",
    )
    context = {
        "shared_context_id": context_id,
        "message_projection_version": PREFERENCE_MESSAGE_PROJECTION_VERSION,
        "task_provenance": task_provenance,
        "harness_runtime_hash": "xxh64:8888888888888888",
        "ordered_message_hashes": message_hashes,
        "canonical_workspace_hash_before_action": "xxh64:9999999999999999",
    }
    actions = (
        '{"action":"final_answer","text":"done"}',
        (
            '{"action":"tool_call","tool_name":"read_file",'
            '"arguments":{"path":"src/app.py"}}'
        ),
    )
    alternatives = []
    for index, content in enumerate(
        sorted(actions, key=hash_preference_action),
        start=1,
    ):
        action_hash = hash_preference_action(content)
        candidate_hash = f"xxh64:{index:016x}"
        trajectory_hash = f"xxh64:{index + 10:016x}"
        message_id = f"message_{index:032x}"
        alternatives.append(
            {
                "alternative_id": build_preference_alternative_id(
                    shared_context_id=context_id,
                    action_hash=action_hash,
                ),
                "action_projection_version": PREFERENCE_ACTION_PROJECTION_VERSION,
                "action_hash": action_hash,
                "assistant_content": content,
                "rollout_evidence": [
                    {
                        "source_type": "original_rollout",
                        "continuation_provenance": "executed_source_trajectory",
                        "evidence_id": build_preference_rollout_evidence_id(
                            source_training_candidate_record_hash=candidate_hash,
                            source_trajectory_record_hash=trajectory_hash,
                            assistant_message_id=message_id,
                        ),
                        "source_training_candidate_record_hash": candidate_hash,
                        "source_trajectory_record_hash": trajectory_hash,
                        "trajectory_id": f"trajectory_{index}",
                        "eval_suite_id": "eval_suite_001",
                        "eval_run_id": f"eval_run_{index}",
                        "eval_attempt_id": f"eval_attempt_{index}",
                        "agent_attempt_id": f"agent_attempt_{index}",
                        "source_policy_id": f"policy_{index}",
                        "source_trajectory_review_status": "reviewed",
                        "source_trajectory_review_decision": "accepted",
                        "source_prompt_loop_result_ref": {
                            "path": f"attempt_{index}/prompt_loop_result.json",
                            "content_hash": f"xxh64:{index + 20:016x}",
                        },
                        "prompt_builder_version": "prompt_builder_v0",
                        "prompt_builder_code_hash": (f"xxh64:{index + 30:016x}"),
                        "assistant_message_id": message_id,
                        "assistant_message_index": 2,
                        "continuation_message_count": 1,
                    }
                ],
            }
        )
    candidate_id = build_preference_comparison_candidate_id(
        shared_context_id=context_id,
        alternative_a_id=alternatives[0]["alternative_id"],
        alternative_b_id=alternatives[1]["alternative_id"],
    )
    return PreferenceComparisonCandidateRecord.model_validate(
        {
            "comparison_candidate_id": candidate_id,
            "discovery_provenance": {
                "discovery_method": PREFERENCE_DISCOVERY_METHOD,
                "discovery_version": PREFERENCE_DISCOVERY_VERSION,
                "discovery_code_hash": compute_preference_discovery_code_hash(),
            },
            "shared_context": context,
            "alternative_a": alternatives[0],
            "alternative_b": alternatives[1],
        }
    )
