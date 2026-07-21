from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.training.preferences.hashing import (
    PREFERENCE_ACTION_PROJECTION_VERSION,
    PREFERENCE_MESSAGE_PROJECTION_VERSION,
    build_preference_alternative_id,
    build_preference_comparison_candidate_id,
    build_preference_rollout_evidence_id,
    build_preference_shared_context_id,
    hash_preference_action,
)
from agentenv.training.preferences.adjudication import (
    build_pending_preference_adjudication_records,
    validate_preference_adjudication_records,
)
from agentenv.training.preferences.schema import (
    PREFERENCE_ADJUDICATION_RECORD_SCHEMA_VERSION,
    PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION,
    PreferenceAdjudicationRecord,
    PreferenceComparisonCandidateRecord,
    PreferenceRubricProvenance,
)


def _task_provenance() -> dict[str, str]:
    return {
        "task_id": "repair_jsonl_deduper",
        "split": "dev",
        "task_manifest_hash": "xxh64:1111111111111111",
        "task_record_hash": "xxh64:2222222222222222",
        "required_task_files_hash": "xxh64:3333333333333333",
        "full_task_dir_hash": "xxh64:4444444444444444",
        "seed_workspace_hash": "xxh64:5555555555555555",
    }


def _shared_context() -> dict[str, Any]:
    message_hashes = [
        "xxh64:6666666666666666",
        "xxh64:7777777777777777",
    ]
    context_id = build_preference_shared_context_id(
        task_provenance=_task_provenance(),
        harness_runtime_hash="xxh64:8888888888888888",
        ordered_message_hashes=message_hashes,
        canonical_workspace_hash_before_action="xxh64:9999999999999999",
    )
    return {
        "shared_context_id": context_id,
        "message_projection_version": PREFERENCE_MESSAGE_PROJECTION_VERSION,
        "task_provenance": _task_provenance(),
        "harness_runtime_hash": "xxh64:8888888888888888",
        "ordered_message_hashes": message_hashes,
        "canonical_workspace_hash_before_action": "xxh64:9999999999999999",
    }


def _evidence(index: int, *, reviewed: bool = True) -> dict[str, Any]:
    candidate_hash = f"xxh64:{index:016x}"
    trajectory_hash = f"xxh64:{index + 20:016x}"
    message_id = f"message_{index:032x}"
    evidence_id = build_preference_rollout_evidence_id(
        source_training_candidate_record_hash=candidate_hash,
        source_trajectory_record_hash=trajectory_hash,
        assistant_message_id=message_id,
    )
    return {
        "source_type": "original_rollout",
        "continuation_provenance": "executed_source_trajectory",
        "evidence_id": evidence_id,
        "source_training_candidate_record_hash": candidate_hash,
        "source_trajectory_record_hash": trajectory_hash,
        "trajectory_id": f"trajectory_{index}",
        "eval_suite_id": "eval_suite_001",
        "eval_run_id": f"eval_run_{index}",
        "eval_attempt_id": f"eval_attempt_{index}",
        "agent_attempt_id": f"agent_attempt_{index}",
        "source_policy_id": f"policy_{index}",
        "source_trajectory_review_status": ("reviewed" if reviewed else "not_reviewed"),
        "source_trajectory_review_decision": "accepted" if reviewed else None,
        "source_prompt_loop_result_ref": {
            "path": f"attempt_{index}/prompt_loop_result.json",
            "content_hash": f"xxh64:{index + 40:016x}",
        },
        "prompt_builder_version": "prompt_builder_v0",
        "prompt_builder_code_hash": f"xxh64:{index + 60:016x}",
        "assistant_message_id": message_id,
        "assistant_message_index": 2,
        "continuation_message_count": 4,
    }


def _candidate_payload() -> dict[str, Any]:
    context = _shared_context()
    context_id = context["shared_context_id"]
    assert isinstance(context_id, str)
    actions = [
        ('{"action":"final_answer","text":"done"}', [_evidence(1), _evidence(2)]),
        (
            '{"action":"tool_call","tool_name":"read_file",'
            '"arguments":{"path":"src/app.py"}}',
            [_evidence(3, reviewed=False)],
        ),
    ]
    ordered_actions = sorted(actions, key=lambda item: hash_preference_action(item[0]))
    alternatives: list[dict[str, Any]] = []
    for content, evidence in ordered_actions:
        action_hash = hash_preference_action(content)
        alternatives.append(
            {
                "alternative_id": build_preference_alternative_id(
                    shared_context_id=context_id,
                    action_hash=action_hash,
                ),
                "action_projection_version": PREFERENCE_ACTION_PROJECTION_VERSION,
                "action_hash": action_hash,
                "assistant_content": content,
                "rollout_evidence": evidence,
            }
        )
    candidate_id = build_preference_comparison_candidate_id(
        shared_context_id=context_id,
        alternative_a_id=alternatives[0]["alternative_id"],
        alternative_b_id=alternatives[1]["alternative_id"],
    )
    return {
        "schema_version": PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION,
        "comparison_candidate_id": candidate_id,
        "discovery_provenance": {
            "discovery_method": ("exact_shared_context_distinct_assistant_actions"),
            "discovery_version": "preference_comparison_discovery_v0",
            "discovery_code_hash": "xxh64:aaaaaaaaaaaaaaaa",
        },
        "shared_context": context,
        "alternative_a": alternatives[0],
        "alternative_b": alternatives[1],
    }


def test_comparison_candidate_accepts_unlabeled_aggregated_rollout_evidence() -> None:
    record = PreferenceComparisonCandidateRecord.model_validate(_candidate_payload())

    evidence_counts = sorted(
        (
            len(record.alternative_a.rollout_evidence),
            len(record.alternative_b.rollout_evidence),
        )
    )
    assert evidence_counts == [1, 2]
    assert record.alternative_a.action_hash < record.alternative_b.action_hash
    assert "chosen" not in record.model_dump(mode="json")
    assert "rejected" not in record.model_dump(mode="json")


def test_comparison_candidate_rejects_noncanonical_alternative_order() -> None:
    payload = _candidate_payload()
    payload["alternative_a"], payload["alternative_b"] = (
        payload["alternative_b"],
        payload["alternative_a"],
    )

    with pytest.raises(
        ValidationError,
        match="canonical action-hash ordering",
    ):
        PreferenceComparisonCandidateRecord.model_validate(payload)


def test_comparison_candidate_rejects_unpinned_rollout_evidence() -> None:
    payload = _candidate_payload()
    payload["alternative_a"]["rollout_evidence"][0]["source_prompt_loop_result_ref"][
        "content_hash"
    ] = None

    with pytest.raises(ValidationError, match="must be hash-pinned"):
        PreferenceComparisonCandidateRecord.model_validate(payload)


def test_comparison_candidate_rejects_context_identity_drift() -> None:
    payload = _candidate_payload()
    payload["shared_context"]["canonical_workspace_hash_before_action"] = (
        "xxh64:bbbbbbbbbbbbbbbb"
    )

    with pytest.raises(
        ValidationError,
        match="shared_context_id must be derived from the exact shared state",
    ):
        PreferenceComparisonCandidateRecord.model_validate(payload)


def _rubric_provenance(
    *,
    rubric_hash: str = "xxh64:bbbbbbbbbbbbbbbb",
) -> PreferenceRubricProvenance:
    return PreferenceRubricProvenance.model_validate(
        {
            "adjudication_scope": "overall_action_preference",
            "rubric_id": "agent_action_overall_preference",
            "rubric_version": "agent_action_overall_preference_v0",
            "rubric_ref": {
                "path": "rubrics/agent_action_overall_preference_v0.md",
                "content_hash": rubric_hash,
            },
        }
    )


def _reviewed_adjudication_payload(
    *,
    decision: str = "preferred",
    reviewer_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate = PreferenceComparisonCandidateRecord.model_validate(_candidate_payload())
    pending = build_pending_preference_adjudication_records(
        [candidate],
        rubric_provenance=_rubric_provenance(),
    )[0]
    payload = pending.model_dump(mode="json")
    payload.update(
        {
            "review_status": "reviewed",
            "review_id": "preference_review_001",
            "reviewer_provenance": reviewer_provenance
            or {
                "reviewer_type": "human",
                "reviewer_id": "reviewer_001",
            },
            "review_decision": decision,
            "preferred_alternative_id": (
                candidate.alternative_a.alternative_id
                if decision == "preferred"
                else None
            ),
            "decision_reason": "Alternative A is the better action under the rubric.",
            "reviewed_at_utc": "2026-07-21T18:30:00Z",
        }
    )
    return payload


def test_pending_adjudication_pins_candidate_and_rubric() -> None:
    candidate = PreferenceComparisonCandidateRecord.model_validate(_candidate_payload())
    rubric = _rubric_provenance()

    records = build_pending_preference_adjudication_records(
        [candidate],
        rubric_provenance=rubric,
    )

    assert len(records) == 1
    record = records[0]
    assert record.schema_version == PREFERENCE_ADJUDICATION_RECORD_SCHEMA_VERSION
    assert record.review_status == "not_reviewed"
    assert record.source.comparison_candidate_id == candidate.comparison_candidate_id
    assert record.source.alternative_a_id == candidate.alternative_a.alternative_id
    assert record.source.alternative_b_id == candidate.alternative_b.alternative_id
    validate_preference_adjudication_records(
        records,
        [candidate],
        rubric_provenance=rubric,
    )


@pytest.mark.parametrize("decision", ["tie", "ambiguous", "invalid"])
def test_non_directional_adjudications_do_not_select_an_alternative(
    decision: str,
) -> None:
    record = PreferenceAdjudicationRecord.model_validate(
        _reviewed_adjudication_payload(decision=decision)
    )

    assert record.review_decision == decision
    assert record.preferred_alternative_id is None


def test_preferred_adjudication_requires_source_alternative() -> None:
    payload = _reviewed_adjudication_payload()
    payload["preferred_alternative_id"] = "preference_alternative_unknown"

    with pytest.raises(ValidationError, match="select exactly one source alternative"):
        PreferenceAdjudicationRecord.model_validate(payload)


def test_non_directional_adjudication_rejects_selected_alternative() -> None:
    payload = _reviewed_adjudication_payload(decision="ambiguous")
    payload["preferred_alternative_id"] = payload["source"]["alternative_a_id"]

    with pytest.raises(ValidationError, match="cannot select a preferred alternative"):
        PreferenceAdjudicationRecord.model_validate(payload)


def test_reviewed_adjudication_requires_nonempty_reason_and_utc_timestamp() -> None:
    payload = _reviewed_adjudication_payload()
    payload["decision_reason"] = "   "
    with pytest.raises(ValidationError, match="nonempty decision_reason"):
        PreferenceAdjudicationRecord.model_validate(payload)

    payload = _reviewed_adjudication_payload()
    payload["reviewed_at_utc"] = "2026-07-21T18:30:00-07:00"
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        PreferenceAdjudicationRecord.model_validate(payload)


@pytest.mark.parametrize(
    "reviewer_provenance",
    [
        {
            "reviewer_type": "deterministic_auditor",
            "auditor_id": "mechanical_tool_efficiency_auditor",
            "auditor_version": "mechanical_tool_efficiency_auditor_v0",
            "auditor_code_hash": "xxh64:cccccccccccccccc",
            "auditor_configuration_hash": "xxh64:dddddddddddddddd",
        },
        {
            "reviewer_type": "llm_judge",
            "model_id": "judge-model",
            "model_revision": "revision-or-digest-001",
            "judge_prompt_ref": {
                "path": "judge/judge_prompt.json",
                "content_hash": "xxh64:eeeeeeeeeeeeeeee",
            },
            "model_input_protocol_ref": {
                "path": "judge/model_input_protocol.yaml",
                "content_hash": "xxh64:ffffffffffffffff",
            },
            "decoding_config_ref": {
                "path": "judge/decoding_config.json",
                "content_hash": "xxh64:1212121212121212",
            },
        },
    ],
)
def test_nonhuman_reviewer_provenance_is_explicit(
    reviewer_provenance: dict[str, Any],
) -> None:
    record = PreferenceAdjudicationRecord.model_validate(
        _reviewed_adjudication_payload(
            reviewer_provenance=reviewer_provenance,
        )
    )

    assert record.reviewer_provenance is not None
    assert (
        record.reviewer_provenance.reviewer_type == reviewer_provenance["reviewer_type"]
    )


def test_llm_reviewer_requires_hash_pinned_judge_inputs() -> None:
    reviewer = {
        "reviewer_type": "llm_judge",
        "model_id": "judge-model",
        "model_revision": "revision-or-digest-001",
        "judge_prompt_ref": {
            "path": "judge/judge_prompt.json",
            "content_hash": None,
        },
        "model_input_protocol_ref": {
            "path": "judge/model_input_protocol.yaml",
            "content_hash": "xxh64:ffffffffffffffff",
        },
        "decoding_config_ref": {
            "path": "judge/decoding_config.json",
            "content_hash": "xxh64:1212121212121212",
        },
    }

    with pytest.raises(ValidationError, match="judge_prompt_ref must be hash-pinned"):
        PreferenceAdjudicationRecord.model_validate(
            _reviewed_adjudication_payload(reviewer_provenance=reviewer)
        )


def test_adjudication_validation_rejects_source_hash_drift() -> None:
    candidate = PreferenceComparisonCandidateRecord.model_validate(_candidate_payload())
    rubric = _rubric_provenance()
    record = build_pending_preference_adjudication_records(
        [candidate],
        rubric_provenance=rubric,
    )[0]
    drifted_source = record.source.model_copy(
        update={
            "source_preference_comparison_candidate_record_hash": (
                "xxh64:abababababababab"
            )
        }
    )
    drifted_record = record.model_copy(update={"source": drifted_source})

    with pytest.raises(ValueError, match="source provenance mismatch"):
        validate_preference_adjudication_records(
            [drifted_record],
            [candidate],
            rubric_provenance=rubric,
        )


def test_adjudication_validation_requires_exact_candidate_coverage() -> None:
    candidate = PreferenceComparisonCandidateRecord.model_validate(_candidate_payload())

    with pytest.raises(ValueError, match="missing comparison candidates"):
        validate_preference_adjudication_records(
            [],
            [candidate],
            rubric_provenance=_rubric_provenance(),
        )
