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
from agentenv.training.preferences.schema import (
    PREFERENCE_COMPARISON_CANDIDATE_RECORD_SCHEMA_VERSION,
    PreferenceComparisonCandidateRecord,
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
