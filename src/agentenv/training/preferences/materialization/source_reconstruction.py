from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from agentenv.artifacts.payloads import load_prompt_loop_result
from agentenv.hashing import hash_json
from agentenv.models.schema import Message, MessageWithoutMetadata
from agentenv.training.candidates.hashing import hash_training_candidate_record
from agentenv.training.candidates.source_integrity import (
    build_trajectory_record_index,
    load_pinned_candidate_trajectory_export,
    resolve_trajectory_artifact_path,
    validate_artifact_ref_hash,
)
from agentenv.training.candidates.schema import TrainingCandidateRecord
from agentenv.training.preferences.hashing import (
    hash_preference_action,
    hash_preference_adjudication_record,
    hash_preference_comparison_candidate_record,
    hash_preference_context_message,
)
from agentenv.training.preferences.pair_export import PreferencePairExport
from agentenv.training.preferences.schema import (
    PreferenceActionAlternative,
    PreferenceAdjudicationRecord,
    PreferenceComparisonCandidateRecord,
    PreferencePairRecord,
    PreferenceRolloutEvidence,
)
from agentenv.trajectories.schema import TrajectoryRecord


@dataclass(frozen=True)
class DPOPreferencePairMaterializationInput:
    source_pair: PreferencePairRecord
    context_messages: tuple[MessageWithoutMetadata, ...]
    chosen_action: MessageWithoutMetadata
    rejected_action: MessageWithoutMetadata


@dataclass(frozen=True)
class _ReconstructedOccurrence:
    evidence_id: str
    context_messages: tuple[MessageWithoutMetadata, ...]
    action: MessageWithoutMetadata


def reconstruct_dpo_preference_pair_inputs(
    pair_export: PreferencePairExport,
) -> tuple[DPOPreferencePairMaterializationInput, ...]:
    comparison_export = pair_export.source_comparison_export
    candidate_export = comparison_export.source_training_candidate_export
    trajectory_export = load_pinned_candidate_trajectory_export(candidate_export)
    return reconstruct_dpo_preference_pair_inputs_from_records(
        pairs=pair_export.records,
        comparisons=comparison_export.records,
        adjudications=(
            pair_export.source_adjudication_review.review_artifact.adjudications
        ),
        training_candidates=candidate_export.records,
        trajectories=trajectory_export.records,
    )


def reconstruct_dpo_preference_pair_inputs_from_records(
    *,
    pairs: Sequence[PreferencePairRecord],
    comparisons: Sequence[PreferenceComparisonCandidateRecord],
    adjudications: Sequence[PreferenceAdjudicationRecord],
    training_candidates: Sequence[TrainingCandidateRecord],
    trajectories: Sequence[TrajectoryRecord],
) -> tuple[DPOPreferencePairMaterializationInput, ...]:
    comparison_by_id = _index_comparisons(comparisons)
    adjudication_by_id = _index_adjudications(adjudications)
    candidate_by_hash = _index_training_candidates(training_candidates)
    trajectory_by_id = build_trajectory_record_index(tuple(trajectories))

    materialization_inputs: list[DPOPreferencePairMaterializationInput] = []
    for pair in pairs:
        candidate_id = pair.source.comparison_candidate_id
        comparison = comparison_by_id.get(candidate_id)
        if comparison is None:
            raise ValueError(
                "Preference pair references an unknown comparison candidate: "
                f"{candidate_id}"
            )
        adjudication = adjudication_by_id.get(candidate_id)
        if adjudication is None:
            raise ValueError(
                "Preference pair references a comparison without adjudication: "
                f"{candidate_id}"
            )
        _validate_pair_source_records(pair, comparison, adjudication)
        chosen, rejected = _resolve_preferred_alternatives(
            comparison,
            adjudication,
        )

        chosen_occurrences = _reconstruct_alternative_occurrences(
            chosen,
            shared_context_hashes=comparison.shared_context.ordered_message_hashes,
            candidate_by_hash=candidate_by_hash,
            trajectory_by_id=trajectory_by_id,
        )
        rejected_occurrences = _reconstruct_alternative_occurrences(
            rejected,
            shared_context_hashes=comparison.shared_context.ordered_message_hashes,
            candidate_by_hash=candidate_by_hash,
            trajectory_by_id=trajectory_by_id,
        )
        all_occurrences = tuple(
            sorted(
                (*chosen_occurrences, *rejected_occurrences),
                key=lambda occurrence: occurrence.evidence_id,
            )
        )
        canonical_context = all_occurrences[0].context_messages
        canonical_projection = _model_visible_projection(canonical_context)
        for occurrence in all_occurrences[1:]:
            if _model_visible_projection(occurrence.context_messages) != (
                canonical_projection
            ):
                raise ValueError(
                    "Aggregated preference evidence reconstructs different "
                    "model-visible contexts"
                )

        materialization_inputs.append(
            DPOPreferencePairMaterializationInput(
                source_pair=pair,
                context_messages=canonical_context,
                chosen_action=chosen_occurrences[0].action,
                rejected_action=rejected_occurrences[0].action,
            )
        )
    return tuple(materialization_inputs)


def _reconstruct_alternative_occurrences(
    alternative: PreferenceActionAlternative,
    *,
    shared_context_hashes: Sequence[str],
    candidate_by_hash: dict[str, TrainingCandidateRecord],
    trajectory_by_id: dict[str, TrajectoryRecord],
) -> tuple[_ReconstructedOccurrence, ...]:
    occurrences = tuple(
        _reconstruct_occurrence(
            evidence,
            expected_alternative=alternative,
            shared_context_hashes=shared_context_hashes,
            candidate_by_hash=candidate_by_hash,
            trajectory_by_id=trajectory_by_id,
        )
        for evidence in sorted(
            alternative.rollout_evidence,
            key=lambda record: record.evidence_id,
        )
    )
    canonical_action = _model_visible_projection((occurrences[0].action,))
    for occurrence in occurrences[1:]:
        if _model_visible_projection((occurrence.action,)) != canonical_action:
            raise ValueError(
                "Aggregated preference evidence reconstructs different "
                "model-visible actions"
            )
    return occurrences


def _reconstruct_occurrence(
    evidence: PreferenceRolloutEvidence,
    *,
    expected_alternative: PreferenceActionAlternative,
    shared_context_hashes: Sequence[str],
    candidate_by_hash: dict[str, TrainingCandidateRecord],
    trajectory_by_id: dict[str, TrajectoryRecord],
) -> _ReconstructedOccurrence:
    candidate = candidate_by_hash.get(evidence.source_training_candidate_record_hash)
    if candidate is None:
        raise ValueError(
            "Preference rollout evidence references an unknown training candidate"
        )
    trajectory = trajectory_by_id.get(evidence.trajectory_id)
    if trajectory is None:
        raise ValueError(
            "Preference rollout evidence references an unknown trajectory: "
            f"{evidence.trajectory_id}"
        )
    if hash_json(trajectory.model_dump(mode="json")) != (
        evidence.source_trajectory_record_hash
    ):
        raise ValueError("Preference rollout evidence trajectory hash mismatch")
    _validate_evidence_identity(evidence, candidate, trajectory)

    prompt_loop_ref = trajectory.artifacts.prompt_loop_result_json
    if prompt_loop_ref is None or prompt_loop_ref != (
        evidence.source_prompt_loop_result_ref
    ):
        raise ValueError("Preference rollout evidence prompt-loop ref mismatch")
    prompt_loop_path = resolve_trajectory_artifact_path(trajectory, prompt_loop_ref)
    validate_artifact_ref_hash(prompt_loop_path, prompt_loop_ref)
    prompt_loop = load_prompt_loop_result(prompt_loop_path)
    if prompt_loop.task_id != trajectory.identity.task_id:
        raise ValueError("Preference source prompt-loop task identity mismatch")
    if (
        prompt_loop.prompt_builder_version,
        prompt_loop.prompt_builder_code_hash,
    ) != (
        evidence.prompt_builder_version,
        evidence.prompt_builder_code_hash,
    ):
        raise ValueError("Preference source prompt-builder provenance mismatch")

    action_index = evidence.assistant_message_index
    if action_index >= len(prompt_loop.messages):
        raise ValueError("Preference assistant message index is out of range")
    if evidence.continuation_message_count != (
        len(prompt_loop.messages) - action_index - 1
    ):
        raise ValueError("Preference continuation message count mismatch")
    action = prompt_loop.messages[action_index]
    if action.role != "assistant" or action.message_id != evidence.assistant_message_id:
        raise ValueError("Preference evidence does not identify its assistant action")
    if (
        action.content != expected_alternative.assistant_content
        or hash_preference_action(action.content) != expected_alternative.action_hash
    ):
        raise ValueError("Preference evidence action differs from its alternative")

    context = prompt_loop.messages[:action_index]
    observed_context_hashes = tuple(
        hash_preference_context_message(message) for message in context
    )
    if observed_context_hashes != tuple(shared_context_hashes):
        raise ValueError(
            "Preference evidence context differs from the shared-context record"
        )
    return _ReconstructedOccurrence(
        evidence_id=evidence.evidence_id,
        context_messages=tuple(_without_metadata(message) for message in context),
        action=_without_metadata(action),
    )


def _validate_pair_source_records(
    pair: PreferencePairRecord,
    comparison: PreferenceComparisonCandidateRecord,
    adjudication: PreferenceAdjudicationRecord,
) -> None:
    if hash_preference_comparison_candidate_record(comparison) != (
        pair.source.source_preference_comparison_candidate_record_hash
    ):
        raise ValueError("Preference pair comparison-record hash mismatch")
    if hash_preference_adjudication_record(adjudication) != (
        pair.source.source_preference_adjudication_record_hash
    ):
        raise ValueError("Preference pair adjudication-record hash mismatch")
    if adjudication.review_status != "reviewed" or (
        adjudication.review_decision != "preferred"
    ):
        raise ValueError("Preference pair requires a reviewed preferred adjudication")


def _resolve_preferred_alternatives(
    comparison: PreferenceComparisonCandidateRecord,
    adjudication: PreferenceAdjudicationRecord,
) -> tuple[PreferenceActionAlternative, PreferenceActionAlternative]:
    if adjudication.preferred_alternative_id == comparison.alternative_a.alternative_id:
        return comparison.alternative_a, comparison.alternative_b
    if adjudication.preferred_alternative_id == comparison.alternative_b.alternative_id:
        return comparison.alternative_b, comparison.alternative_a
    raise ValueError("Preference adjudication does not select a source alternative")


def _validate_evidence_identity(
    evidence: PreferenceRolloutEvidence,
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
) -> None:
    candidate_identity = (
        candidate.trajectory_id,
        candidate.eval_attempt_id,
        candidate.policy_id,
    )
    trajectory_identity = (
        trajectory.identity.trajectory_id,
        trajectory.identity.eval_attempt_id,
        trajectory.identity.policy_id,
    )
    evidence_identity = (
        evidence.trajectory_id,
        evidence.eval_attempt_id,
        evidence.source_policy_id,
    )
    if candidate_identity != trajectory_identity or evidence_identity != (
        trajectory_identity
    ):
        raise ValueError("Preference rollout evidence source identity mismatch")
    if (
        trajectory.identity.eval_suite_id,
        trajectory.identity.eval_run_id,
        trajectory.identity.agent_attempt_id,
    ) != (
        evidence.eval_suite_id,
        evidence.eval_run_id,
        evidence.agent_attempt_id,
    ):
        raise ValueError("Preference rollout evidence run identity mismatch")


def _index_comparisons(
    records: Sequence[PreferenceComparisonCandidateRecord],
) -> dict[str, PreferenceComparisonCandidateRecord]:
    indexed = {record.comparison_candidate_id: record for record in records}
    if len(indexed) != len(records):
        raise ValueError("Preference comparison candidate ids must be unique")
    return indexed


def _index_adjudications(
    records: Sequence[PreferenceAdjudicationRecord],
) -> dict[str, PreferenceAdjudicationRecord]:
    indexed = {record.source.comparison_candidate_id: record for record in records}
    if len(indexed) != len(records):
        raise ValueError("Preference adjudications must be unique by comparison")
    return indexed


def _index_training_candidates(
    records: Sequence[TrainingCandidateRecord],
) -> dict[str, TrainingCandidateRecord]:
    indexed = {hash_training_candidate_record(record): record for record in records}
    if len(indexed) != len(records):
        raise ValueError("Training candidates must have unique record hashes")
    return indexed


def _without_metadata(message: Message) -> MessageWithoutMetadata:
    return MessageWithoutMetadata(
        message_id=message.message_id,
        role=message.role,
        content=message.content,
        name=message.name,
        tool_call_id=message.tool_call_id,
    )


def _model_visible_projection(
    messages: Sequence[MessageWithoutMetadata],
) -> tuple[tuple[str, str], ...]:
    return tuple((message.role, message.content) for message in messages)
