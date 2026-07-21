from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import cast

from agentenv.agents.schema import PromptLoopResult
from agentenv.agents.tool_messages import render_tool_result_message
from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.manifests import load_eval_run_manifest
from agentenv.artifacts.payloads import SelectedEvalTaskHash, load_prompt_loop_result
from agentenv.hashing import hash_directory, hash_file, hash_json
from agentenv.security.leakage import LeakageScanText, scan_texts_for_leakage
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest
from agentenv.training.candidates.export import (
    TrainingCandidateExport,
    load_training_candidate_export_artifact,
)
from agentenv.training.candidates.hashing import hash_training_candidate_record
from agentenv.training.candidates.source_integrity import (
    build_trajectory_record_index,
    load_pinned_candidate_trajectory_export,
    resolve_trajectory_artifact_path,
    validate_artifact_ref_hash,
    validate_pinned_candidate_source_review,
)
from agentenv.training.candidates.schema import TrainingCandidateRecord
from agentenv.training.preferences.hashing import (
    PREFERENCE_ACTION_PROJECTION_VERSION,
    PREFERENCE_MESSAGE_PROJECTION_VERSION,
    build_preference_alternative_id,
    build_preference_comparison_candidate_id,
    build_preference_rollout_evidence_id,
    build_preference_shared_context_id,
    hash_preference_action,
    hash_preference_context_message,
)
from agentenv.training.preferences.schema import (
    PreferenceActionAlternative,
    PreferenceComparisonCandidateRecord,
    PreferenceDiscoveryProvenance,
    PreferenceRolloutEvidence,
    PreferenceSharedContext,
    PreferenceTaskProvenance,
    PreferenceTrainingSplit,
)
from agentenv.trajectories.builder import select_eval_task_hash_record
from agentenv.trajectories.schema import ArtifactRef, TrajectoryRecord


PREFERENCE_DISCOVERY_VERSION = "preference_comparison_discovery_v0"
PREFERENCE_DISCOVERY_METHOD = "exact_shared_context_distinct_assistant_actions"


@dataclass(frozen=True)
class _SourceTaskContext:
    provenance: PreferenceTaskProvenance
    harness_runtime_hash: str
    task_manifest: TaskManifest


@dataclass(frozen=True)
class _ActionOccurrence:
    shared_context: PreferenceSharedContext
    action_hash: str
    assistant_content: str
    rollout_evidence: PreferenceRolloutEvidence
    task_manifest: TaskManifest


def compute_preference_discovery_code_hash() -> str:
    return hash_file(Path(__file__))


def discover_preference_comparison_candidates(
    training_candidate_export_dir: Path,
) -> tuple[PreferenceComparisonCandidateRecord, ...]:
    candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    return discover_preference_comparison_candidates_from_export(candidate_export)


def discover_preference_comparison_candidates_from_export(
    candidate_export: TrainingCandidateExport,
) -> tuple[PreferenceComparisonCandidateRecord, ...]:
    validate_pinned_candidate_source_review(candidate_export)
    trajectory_export = load_pinned_candidate_trajectory_export(candidate_export)
    return discover_preference_comparison_candidates_from_records(
        candidate_export.records,
        trajectory_export.records,
    )


def discover_preference_comparison_candidates_from_records(
    candidates: Sequence[TrainingCandidateRecord],
    trajectories: Sequence[TrajectoryRecord],
) -> tuple[PreferenceComparisonCandidateRecord, ...]:
    trajectory_by_id = build_trajectory_record_index(tuple(trajectories))
    _validate_unique_candidate_sources(candidates)

    occurrences: list[_ActionOccurrence] = []
    for candidate in candidates:
        trajectory = trajectory_by_id.get(candidate.trajectory_id)
        if trajectory is None:
            raise ValueError(
                "Preference discovery candidate references unknown trajectory: "
                f"{candidate.trajectory_id}"
            )
        _validate_candidate_matches_trajectory(candidate, trajectory)
        if not candidate.content_eligibility.preference_discovery_eligible:
            continue
        occurrences.extend(_load_action_occurrences(candidate, trajectory))

    return _build_comparison_candidates(occurrences)


def _load_action_occurrences(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
) -> tuple[_ActionOccurrence, ...]:
    prompt_loop_ref = _require_hash_pinned_prompt_loop_ref(trajectory)
    prompt_loop_path = resolve_trajectory_artifact_path(trajectory, prompt_loop_ref)
    validate_artifact_ref_hash(prompt_loop_path, prompt_loop_ref)
    prompt_loop = load_prompt_loop_result(prompt_loop_path)
    if prompt_loop.task_id != trajectory.identity.task_id:
        raise ValueError("Preference source prompt loop task_id mismatch")

    source_task = _load_source_task_context(trajectory)
    return _extract_action_occurrences(
        candidate,
        trajectory,
        prompt_loop_ref=prompt_loop_ref,
        prompt_loop=prompt_loop,
        source_task=source_task,
    )


def _extract_action_occurrences(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
    *,
    prompt_loop_ref: ArtifactRef,
    prompt_loop: PromptLoopResult,
    source_task: _SourceTaskContext,
) -> tuple[_ActionOccurrence, ...]:
    source_candidate_hash = hash_training_candidate_record(candidate)
    source_trajectory_hash = hash_json(trajectory.model_dump(mode="json"))
    agent_attempt_id = trajectory.identity.agent_attempt_id
    if agent_attempt_id is None:
        raise ValueError("Preference discovery requires agent_attempt_id")

    current_workspace_hash = source_task.provenance.seed_workspace_hash
    ordered_message_hashes: list[str] = []
    tool_result_index = 0
    occurrences: list[_ActionOccurrence] = []
    for message_index, message in enumerate(prompt_loop.messages):
        if message.role == "assistant":
            if len(ordered_message_hashes) < 2:
                raise ValueError(
                    "Preference assistant actions require system and user context"
                )
            context_id = build_preference_shared_context_id(
                task_provenance=source_task.provenance.model_dump(mode="json"),
                harness_runtime_hash=source_task.harness_runtime_hash,
                ordered_message_hashes=ordered_message_hashes,
                canonical_workspace_hash_before_action=current_workspace_hash,
            )
            shared_context = PreferenceSharedContext(
                shared_context_id=context_id,
                message_projection_version=PREFERENCE_MESSAGE_PROJECTION_VERSION,
                task_provenance=source_task.provenance,
                harness_runtime_hash=source_task.harness_runtime_hash,
                ordered_message_hashes=list(ordered_message_hashes),
                canonical_workspace_hash_before_action=current_workspace_hash,
            )
            evidence_id = build_preference_rollout_evidence_id(
                source_training_candidate_record_hash=source_candidate_hash,
                source_trajectory_record_hash=source_trajectory_hash,
                assistant_message_id=message.message_id,
            )
            evidence = PreferenceRolloutEvidence(
                source_type="original_rollout",
                continuation_provenance="executed_source_trajectory",
                evidence_id=evidence_id,
                source_training_candidate_record_hash=source_candidate_hash,
                source_trajectory_record_hash=source_trajectory_hash,
                trajectory_id=trajectory.identity.trajectory_id,
                eval_suite_id=trajectory.identity.eval_suite_id,
                eval_run_id=trajectory.identity.eval_run_id,
                eval_attempt_id=trajectory.identity.eval_attempt_id,
                agent_attempt_id=agent_attempt_id,
                source_policy_id=trajectory.identity.policy_id,
                source_trajectory_review_status=candidate.review_status,
                source_trajectory_review_decision=candidate.review_decision,
                source_prompt_loop_result_ref=prompt_loop_ref,
                prompt_builder_version=prompt_loop.prompt_builder_version,
                prompt_builder_code_hash=prompt_loop.prompt_builder_code_hash,
                assistant_message_id=message.message_id,
                assistant_message_index=message_index,
                continuation_message_count=(
                    len(prompt_loop.messages) - message_index - 1
                ),
            )
            occurrences.append(
                _ActionOccurrence(
                    shared_context=shared_context,
                    action_hash=hash_preference_action(message.content),
                    assistant_content=message.content,
                    rollout_evidence=evidence,
                    task_manifest=source_task.task_manifest,
                )
            )

        if message.role == "tool":
            current_workspace_hash, tool_result_index = _consume_tool_observation(
                prompt_loop,
                message_index=message_index,
                tool_result_index=tool_result_index,
                current_workspace_hash=current_workspace_hash,
            )
        ordered_message_hashes.append(hash_preference_context_message(message))

    if tool_result_index != len(prompt_loop.tool_results):
        raise ValueError("Preference source prompt loop contains unlinked tool results")
    return tuple(occurrences)


def _consume_tool_observation(
    prompt_loop: PromptLoopResult,
    *,
    message_index: int,
    tool_result_index: int,
    current_workspace_hash: str,
) -> tuple[str, int]:
    if tool_result_index >= len(prompt_loop.tool_results):
        raise ValueError("Preference source contains a tool message without a result")
    if message_index == 0:
        raise ValueError("Preference source cannot start with a tool message")
    message = prompt_loop.messages[message_index]
    previous_message = prompt_loop.messages[message_index - 1]
    if previous_message.role != "assistant" or (
        previous_message.tool_call_id != message.tool_call_id
    ):
        raise ValueError("Preference source tool message linkage is invalid")
    if message.tool_call_id is None:
        raise ValueError("Preference source tool message requires tool_call_id")

    tool_result = prompt_loop.tool_results[tool_result_index]
    expected_message = render_tool_result_message(tool_result, message.tool_call_id)
    compared_fields = (
        ("role", message.role, expected_message.role),
        ("name", message.name, expected_message.name),
        ("tool_call_id", message.tool_call_id, expected_message.tool_call_id),
        ("content", message.content, expected_message.content),
        ("metadata", message.metadata, expected_message.metadata),
    )
    for field_name, observed, expected in compared_fields:
        if observed != expected:
            raise ValueError(
                "Preference source tool observation does not match ToolResult "
                f"field {field_name}"
            )
    if tool_result.canonical_workspace_hash_before != current_workspace_hash:
        raise ValueError(
            "Preference source workspace chain differs before a tool observation"
        )
    return tool_result.canonical_workspace_hash_after, tool_result_index + 1


def _load_source_task_context(trajectory: TrajectoryRecord) -> _SourceTaskContext:
    eval_run_dir = Path(trajectory.artifacts.eval_run_path).resolve()
    eval_manifest = load_eval_run_manifest(eval_run_dir / MANIFEST_FILENAME)
    if eval_manifest.eval_run_id != trajectory.identity.eval_run_id:
        raise ValueError("Preference source eval run identity mismatch")
    selected_task_hash = select_eval_task_hash_record(
        eval_manifest,
        trajectory.identity.task_id,
    )
    _validate_selected_task_hash_matches_trajectory(selected_task_hash, trajectory)

    task_manifest_path = Path(trajectory.source_provenance.task_manifest_path)
    task_manifest = load_task_manifest(task_manifest_path)
    if task_manifest.id != trajectory.identity.task_id:
        raise ValueError("Preference source task manifest identity mismatch")
    observed_manifest_hash = hash_file(task_manifest_path)
    if observed_manifest_hash != selected_task_hash.task_yaml_hash:
        raise ValueError("Preference source task manifest hash mismatch")

    seed_workspace_hash = _select_seed_workspace_hash(
        selected_task_hash,
        seed_workspace_ref=task_manifest.seed_workspace,
    )
    seed_workspace_path = task_manifest_path.parent / task_manifest.seed_workspace
    observed_seed_hash = hash_directory(seed_workspace_path)
    if observed_seed_hash != seed_workspace_hash:
        raise ValueError("Preference source seed workspace has drifted")
    if selected_task_hash.split not in {"practice", "dev"}:
        raise ValueError("Preference discovery requires a training-eligible split")

    return _SourceTaskContext(
        provenance=PreferenceTaskProvenance(
            task_id=selected_task_hash.task_id,
            split=cast(PreferenceTrainingSplit, selected_task_hash.split),
            task_manifest_hash=selected_task_hash.task_yaml_hash,
            task_record_hash=selected_task_hash.task_record_hash,
            required_task_files_hash=selected_task_hash.required_task_files_hash,
            full_task_dir_hash=selected_task_hash.full_task_dir_hash,
            seed_workspace_hash=seed_workspace_hash,
        ),
        harness_runtime_hash=eval_manifest.runtime_provenance.harness_runtime_hash,
        task_manifest=task_manifest,
    )


def _select_seed_workspace_hash(
    selected_task_hash: SelectedEvalTaskHash,
    *,
    seed_workspace_ref: str,
) -> str:
    matches = [
        record
        for record in selected_task_hash.required_task_files
        if record.path == seed_workspace_ref
    ]
    if len(matches) != 1:
        raise ValueError(
            "Preference source task hashes require exactly one seed workspace"
        )
    if matches[0].kind != "directory":
        raise ValueError("Preference source seed workspace hash must cover a directory")
    return matches[0].hash


def _validate_selected_task_hash_matches_trajectory(
    selected_task_hash: SelectedEvalTaskHash,
    trajectory: TrajectoryRecord,
) -> None:
    if selected_task_hash.task_id != trajectory.identity.task_id:
        raise ValueError("Preference source task hash identity mismatch")
    if selected_task_hash.split != trajectory.source_provenance.split:
        raise ValueError("Preference source task split mismatch")
    if (
        selected_task_hash.task_yaml_hash
        != trajectory.source_provenance.task_manifest_hash
    ):
        raise ValueError("Preference source task hash differs from trajectory")


def _build_comparison_candidates(
    occurrences: Sequence[_ActionOccurrence],
) -> tuple[PreferenceComparisonCandidateRecord, ...]:
    contexts: dict[str, PreferenceSharedContext] = {}
    task_manifests: dict[str, TaskManifest] = {}
    action_groups: dict[
        str,
        dict[str, tuple[str, list[PreferenceRolloutEvidence]]],
    ] = {}
    for occurrence in occurrences:
        context_id = occurrence.shared_context.shared_context_id
        existing_context = contexts.setdefault(context_id, occurrence.shared_context)
        if existing_context != occurrence.shared_context:
            raise ValueError("Preference shared-context hash collision")
        existing_manifest = task_manifests.setdefault(
            context_id,
            occurrence.task_manifest,
        )
        if existing_manifest != occurrence.task_manifest:
            raise ValueError(
                "Preference shared context has inconsistent task manifests"
            )

        by_action = action_groups.setdefault(context_id, {})
        existing_action = by_action.get(occurrence.action_hash)
        if existing_action is None:
            by_action[occurrence.action_hash] = (
                occurrence.assistant_content,
                [occurrence.rollout_evidence],
            )
        else:
            existing_content, evidence = existing_action
            if existing_content != occurrence.assistant_content:
                raise ValueError("Preference action hash collision")
            evidence.append(occurrence.rollout_evidence)

    discovery = PreferenceDiscoveryProvenance(
        discovery_method=PREFERENCE_DISCOVERY_METHOD,
        discovery_version=PREFERENCE_DISCOVERY_VERSION,
        discovery_code_hash=compute_preference_discovery_code_hash(),
    )
    records: list[PreferenceComparisonCandidateRecord] = []
    for context_id in sorted(action_groups):
        by_action = action_groups[context_id]
        for action_hash_a, action_hash_b in combinations(sorted(by_action), 2):
            alternative_a = _build_alternative(
                context_id,
                action_hash_a,
                by_action[action_hash_a],
            )
            alternative_b = _build_alternative(
                context_id,
                action_hash_b,
                by_action[action_hash_b],
            )
            candidate_id = build_preference_comparison_candidate_id(
                shared_context_id=context_id,
                alternative_a_id=alternative_a.alternative_id,
                alternative_b_id=alternative_b.alternative_id,
            )
            record = PreferenceComparisonCandidateRecord(
                comparison_candidate_id=candidate_id,
                discovery_provenance=discovery,
                shared_context=contexts[context_id],
                alternative_a=alternative_a,
                alternative_b=alternative_b,
            )
            _validate_candidate_action_content_has_no_leakage(
                record,
                task_manifest=task_manifests[context_id],
            )
            records.append(record)
    return tuple(sorted(records, key=lambda record: record.comparison_candidate_id))


def _build_alternative(
    context_id: str,
    action_hash: str,
    action_group: tuple[str, list[PreferenceRolloutEvidence]],
) -> PreferenceActionAlternative:
    content, evidence = action_group
    ordered_evidence = sorted(evidence, key=lambda record: record.evidence_id)
    return PreferenceActionAlternative(
        alternative_id=build_preference_alternative_id(
            shared_context_id=context_id,
            action_hash=action_hash,
        ),
        action_projection_version=PREFERENCE_ACTION_PROJECTION_VERSION,
        action_hash=action_hash,
        assistant_content=content,
        rollout_evidence=ordered_evidence,
    )


def _validate_candidate_action_content_has_no_leakage(
    record: PreferenceComparisonCandidateRecord,
    *,
    task_manifest: TaskManifest,
) -> None:
    scan = scan_texts_for_leakage(
        (
            LeakageScanText(
                ref=f"{record.comparison_candidate_id}:alternative_a",
                text=record.alternative_a.assistant_content,
            ),
            LeakageScanText(
                ref=f"{record.comparison_candidate_id}:alternative_b",
                text=record.alternative_b.assistant_content,
            ),
        ),
        task_manifest,
    )
    if scan.canary_leaked or scan.hidden_validators_visible_to_model:
        raise ValueError(
            "Preference comparison candidate contains private or hidden-validator "
            "content"
        )


def _require_hash_pinned_prompt_loop_ref(
    trajectory: TrajectoryRecord,
) -> ArtifactRef:
    ref = trajectory.artifacts.prompt_loop_result_json
    if ref is None or ref.content_hash is None:
        raise ValueError(
            "Preference discovery requires a hash-pinned original prompt loop"
        )
    return ref


def _validate_candidate_matches_trajectory(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
) -> None:
    compared_fields = (
        ("trajectory_id", candidate.trajectory_id, trajectory.identity.trajectory_id),
        (
            "eval_attempt_id",
            candidate.eval_attempt_id,
            trajectory.identity.eval_attempt_id,
        ),
        ("task_id", candidate.task_id, trajectory.identity.task_id),
        ("policy_id", candidate.policy_id, trajectory.identity.policy_id),
    )
    for field_name, candidate_value, trajectory_value in compared_fields:
        if candidate_value != trajectory_value:
            raise ValueError(
                f"Preference source {field_name} mismatch: "
                f"{candidate_value!r} != {trajectory_value!r}"
            )


def _validate_unique_candidate_sources(
    candidates: Sequence[TrainingCandidateRecord],
) -> None:
    identities = [
        (candidate.trajectory_id, candidate.eval_attempt_id) for candidate in candidates
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("Preference discovery source candidates must be unique")
