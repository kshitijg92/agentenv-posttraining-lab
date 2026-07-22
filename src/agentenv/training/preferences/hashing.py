from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from agentenv.hashing import hash_json
from agentenv.models.schema import MessageWithoutMetadata

if TYPE_CHECKING:
    from agentenv.training.preferences.schema import (
        PreferenceAdjudicationRecord,
        PreferenceComparisonCandidateRecord,
        PreferencePairRecord,
    )


PREFERENCE_MESSAGE_PROJECTION_VERSION = "preference_message_projection_v0"
PREFERENCE_ACTION_PROJECTION_VERSION = "preference_action_projection_v0"


def hash_preference_comparison_candidate_record(
    record: PreferenceComparisonCandidateRecord,
) -> str:
    return hash_json(record.model_dump(mode="json"))


def hash_preference_adjudication_record(
    record: PreferenceAdjudicationRecord,
) -> str:
    return hash_json(record.model_dump(mode="json"))


def hash_preference_pair_record(record: PreferencePairRecord) -> str:
    return hash_json(record.model_dump(mode="json"))


def hash_preference_context_message(message: MessageWithoutMetadata) -> str:
    payload: dict[str, object] = {
        "projection_version": PREFERENCE_MESSAGE_PROJECTION_VERSION,
        "role": message.role,
        "content": message.content,
    }
    if message.role == "tool":
        payload["tool_name"] = message.name
        payload["tool_call_id"] = message.tool_call_id
    return hash_json(payload)


def hash_preference_action(content: str) -> str:
    return hash_json(
        {
            "projection_version": PREFERENCE_ACTION_PROJECTION_VERSION,
            "role": "assistant",
            "content": content,
        }
    )


def build_preference_shared_context_id(
    *,
    task_provenance: object,
    harness_runtime_hash: str,
    ordered_message_hashes: Sequence[str],
    canonical_workspace_hash_before_action: str,
) -> str:
    identity_hash = hash_json(
        {
            "message_projection_version": PREFERENCE_MESSAGE_PROJECTION_VERSION,
            "task_provenance": task_provenance,
            "harness_runtime_hash": harness_runtime_hash,
            "ordered_message_hashes": list(ordered_message_hashes),
            "canonical_workspace_hash_before_action": (
                canonical_workspace_hash_before_action
            ),
        }
    )
    return f"preference_context_{identity_hash.removeprefix('xxh64:')}"


def build_preference_rollout_evidence_id(
    *,
    source_training_candidate_record_hash: str,
    source_trajectory_record_hash: str,
    assistant_message_id: str,
) -> str:
    identity_hash = hash_json(
        {
            "source_training_candidate_record_hash": (
                source_training_candidate_record_hash
            ),
            "source_trajectory_record_hash": source_trajectory_record_hash,
            "assistant_message_id": assistant_message_id,
        }
    )
    return f"preference_rollout_evidence_{identity_hash.removeprefix('xxh64:')}"


def build_preference_alternative_id(
    *,
    shared_context_id: str,
    action_hash: str,
) -> str:
    identity_hash = hash_json(
        {
            "shared_context_id": shared_context_id,
            "action_hash": action_hash,
        }
    )
    return f"preference_alternative_{identity_hash.removeprefix('xxh64:')}"


def build_preference_comparison_candidate_id(
    *,
    shared_context_id: str,
    alternative_a_id: str,
    alternative_b_id: str,
) -> str:
    identity_hash = hash_json(
        {
            "shared_context_id": shared_context_id,
            "alternative_a_id": alternative_a_id,
            "alternative_b_id": alternative_b_id,
        }
    )
    return f"preference_comparison_{identity_hash.removeprefix('xxh64:')}"


def build_preference_pair_id(
    *,
    comparison_candidate_id: str,
    source_preference_comparison_candidate_record_hash: str,
    source_preference_adjudication_record_hash: str,
) -> str:
    identity_hash = hash_json(
        {
            "comparison_candidate_id": comparison_candidate_id,
            "source_preference_comparison_candidate_record_hash": (
                source_preference_comparison_candidate_record_hash
            ),
            "source_preference_adjudication_record_hash": (
                source_preference_adjudication_record_hash
            ),
        }
    )
    return f"preference_pair_{identity_hash.removeprefix('xxh64:')}"
