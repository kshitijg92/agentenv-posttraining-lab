from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agentenv.artifacts.payloads import load_agent_task_view, load_prompt_loop_result
from agentenv.hashing import hash_file
from agentenv.security.leakage import LeakageScanText, scan_texts_for_leakage
from agentenv.tasks.validate import load_task_manifest
from agentenv.training.candidates.export import (
    TrainingCandidateExport,
    load_training_candidate_export_artifact,
)
from agentenv.training.candidates.source_integrity import (
    build_trajectory_record_index,
    load_pinned_candidate_trajectory_export,
    resolve_trajectory_artifact_path,
    validate_artifact_ref_hash,
    validate_pinned_candidate_source_review,
)
from agentenv.training.candidates.schema import TrainingCandidateRecord
from agentenv.training.positive_sft.schema import (
    OriginalPositiveSFTSourceProvenance,
    PositiveSFTExampleRecord,
    PositiveSFTMessage,
    PositiveSFTPromptProvenance,
    PositiveSFTProvenanceIds,
    PositiveSFTReviewProvenance,
    PositiveSFTTaskInput,
    RepairedPositiveSFTSourceProvenance,
)
from agentenv.training.repairs.redundancy_repair import (
    hash_training_candidate_record,
    hash_training_candidate_repair_record,
    hash_training_candidate_repair_review_record,
)
from agentenv.training.positive_sft.identity import build_positive_sft_example_id
from agentenv.training.positive_sft.schema import (
    PositiveSFTReviewRecord,
    RepairedPositiveSFTReviewSource,
)
from agentenv.training.positive_sft.source_selection import (
    SelectedPositiveSFTRepair,
    build_selected_positive_sft_repair_index,
    load_selected_repaired_messages,
    require_artifact_ref,
    require_content_hash,
    validate_positive_sft_candidate_matches_trajectory,
    validate_positive_sft_review_matches_candidate_export,
)
from agentenv.trajectories.schema import TrajectoryRecord

if TYPE_CHECKING:
    from agentenv.training.positive_sft.review import PositiveSFTReviewValidation


MECHANICAL_REDUNDANCY_TASK_OUTCOME_INHERITANCE_BASIS = (
    "mechanical_redundancy_state_and_observation_preserving_deletion"
)


def build_positive_sft_examples(
    training_candidate_export_dir: Path,
    *,
    positive_sft_review_dir: Path,
) -> tuple[PositiveSFTExampleRecord, ...]:
    training_candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    from agentenv.training.positive_sft.review import (
        validate_positive_sft_review_artifact,
    )

    review_validation = validate_positive_sft_review_artifact(
        positive_sft_review_dir
    )
    validate_positive_sft_review_matches_candidate_export(
        training_candidate_export,
        review_validation,
    )
    return build_positive_sft_examples_from_training_candidate_export(
        training_candidate_export,
        positive_sft_review_validation=review_validation,
    )


def build_positive_sft_examples_from_training_candidate_export(
    training_candidate_export: TrainingCandidateExport,
    *,
    positive_sft_review_validation: PositiveSFTReviewValidation,
) -> tuple[PositiveSFTExampleRecord, ...]:
    validate_positive_sft_review_matches_candidate_export(
        training_candidate_export,
        positive_sft_review_validation,
    )
    validate_pinned_candidate_source_review(training_candidate_export)
    trajectory_export = load_pinned_candidate_trajectory_export(
        training_candidate_export
    )
    trajectory_by_id = build_trajectory_record_index(trajectory_export.records)
    review_records = positive_sft_review_validation.review_artifact.reviews
    selected_repair_ids = tuple(
        review.source.repair_id
        for review in review_records
        if isinstance(review.source, RepairedPositiveSFTReviewSource)
    )
    selected_repairs = build_selected_positive_sft_repair_index(
        training_candidate_export,
        repair_validation=positive_sft_review_validation.repair_validation,
        selected_repair_ids=selected_repair_ids,
    )
    review_by_candidate_hash = {
        review.source_training_candidate_record_hash: review
        for review in review_records
    }

    examples: list[PositiveSFTExampleRecord] = []
    for candidate in training_candidate_export.records:
        candidate_hash = hash_training_candidate_record(candidate)
        positive_sft_review = review_by_candidate_hash.get(candidate_hash)
        if positive_sft_review is None or (
            positive_sft_review.review_status != "reviewed"
            or positive_sft_review.review_decision != "accepted"
        ):
            continue
        if not candidate.training_eligibility.positive_sft_review_eligible:
            raise ValueError(
                "Accepted positive-SFT review references an ineligible candidate: "
                f"{candidate.trajectory_id}"
            )
        assessment = candidate.mechanical_redundancy_assessment
        if assessment.evaluation_status != "complete":
            raise ValueError(
                "Accepted positive-SFT review requires a complete mechanical-"
                "redundancy assessment"
            )
        selected_repair = selected_repairs.get(candidate_hash)
        if assessment.blocks and selected_repair is None:
            raise ValueError(
                "Accepted positive-SFT review for mechanical redundancy requires "
                "a repaired source"
            )
        if not assessment.blocks and selected_repair is not None:
            raise ValueError(
                "Positive SFT repair selected for a candidate with no mechanical "
                "redundancy blocks"
            )
        trajectory = trajectory_by_id.get(candidate.trajectory_id)
        if trajectory is None:
            raise ValueError(
                "Training candidate references unknown trajectory_id: "
                f"{candidate.trajectory_id}"
            )
        examples.append(
            build_positive_sft_example_record(
                candidate,
                trajectory,
                selected_repair=selected_repair,
                positive_sft_review=positive_sft_review,
            )
        )
    return tuple(examples)


def build_positive_sft_example_record(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
    *,
    selected_repair: SelectedPositiveSFTRepair | None = None,
    positive_sft_review: PositiveSFTReviewRecord,
) -> PositiveSFTExampleRecord:
    validate_positive_sft_candidate_matches_trajectory(candidate, trajectory)
    if not candidate.training_eligibility.positive_sft_review_eligible:
        raise ValueError(
            "Training candidate is not positive-SFT eligible: "
            f"{candidate.trajectory_id}"
        )
    assessment = candidate.mechanical_redundancy_assessment
    if assessment.evaluation_status != "complete":
        raise ValueError(
            "Positive SFT requires a complete mechanical-redundancy assessment"
        )
    if assessment.blocks and selected_repair is None:
        raise ValueError(
            "Positive SFT candidates with mechanical redundancy require a selected "
            "repair"
        )
    if not assessment.blocks and selected_repair is not None:
        raise ValueError(
            "Positive SFT repair selected for a candidate with no mechanical "
            "redundancy blocks"
        )

    agent_task_view_ref = require_artifact_ref(
        trajectory.artifacts.agent_task_view_json,
        "agent_task_view_json",
        trajectory,
    )
    prompt_loop_result_ref = require_artifact_ref(
        trajectory.artifacts.prompt_loop_result_json,
        "prompt_loop_result_json",
        trajectory,
    )
    agent_task_view_path = resolve_trajectory_artifact_path(
        trajectory,
        agent_task_view_ref,
    )
    prompt_loop_result_path = resolve_trajectory_artifact_path(
        trajectory,
        prompt_loop_result_ref,
    )
    validate_artifact_ref_hash(agent_task_view_path, agent_task_view_ref)
    validate_artifact_ref_hash(prompt_loop_result_path, prompt_loop_result_ref)

    agent_task_view = load_agent_task_view(agent_task_view_path)
    prompt_loop_result = load_prompt_loop_result(prompt_loop_result_path)
    if prompt_loop_result.task_id != trajectory.identity.task_id:
        raise ValueError(
            "PromptLoopResult task_id does not match trajectory task_id: "
            f"{prompt_loop_result.task_id!r} != {trajectory.identity.task_id!r}"
        )

    task_input = PositiveSFTTaskInput(
        task_id=agent_task_view.task_id,
        instruction=agent_task_view.instruction,
        allowed_tools=agent_task_view.allowed_tools,
        public_checks=agent_task_view.public_checks,
        max_turns=agent_task_view.max_turns,
        timeout_seconds=agent_task_view.timeout_seconds,
        network=agent_task_view.network,
    )
    source_candidate_hash = hash_training_candidate_record(candidate)
    if selected_repair is None:
        source_provenance = OriginalPositiveSFTSourceProvenance(
            source_type="original",
            source_training_candidate_record_hash=source_candidate_hash,
            source_artifact_ref=prompt_loop_result_ref,
            task_outcome_provenance="executed_source_trajectory",
        )
        source_messages = prompt_loop_result.messages
    else:
        repair = selected_repair.record
        review = selected_repair.review
        repaired_ref = repair.repaired_artifact_ref
        if repair.repair_status != "completed" or repaired_ref is None:
            raise ValueError("Positive SFT selected repair is not completed")
        if review.review_status != "reviewed" or review.review_decision != "accepted":
            raise ValueError("Positive SFT selected repair review is not accepted")
        if review.review_id is None:
            raise ValueError("Positive SFT selected repair review is missing review_id")
        if repair.source_training_candidate_record_hash != source_candidate_hash:
            raise ValueError(
                "Positive SFT selected repair source candidate hash mismatch"
            )
        source_messages = load_selected_repaired_messages(selected_repair)
        source_provenance = RepairedPositiveSFTSourceProvenance(
            source_type="repaired",
            source_training_candidate_record_hash=source_candidate_hash,
            source_artifact_ref=repaired_ref,
            repair_id=repair.repair_id,
            source_training_candidate_repair_record_hash=(
                hash_training_candidate_repair_record(repair)
            ),
            source_training_candidate_repair_review_record_hash=(
                hash_training_candidate_repair_review_record(review)
            ),
            repair_review_id=review.review_id,
            task_outcome_provenance="inherited_from_source_trajectory",
            task_outcome_inheritance_basis=(
                MECHANICAL_REDUNDANCY_TASK_OUTCOME_INHERITANCE_BASIS
            ),
        )

    if positive_sft_review.review_status != "reviewed" or (
        positive_sft_review.review_decision != "accepted"
        or positive_sft_review.review_id is None
        or positive_sft_review.last_approved_assistant_message_id is None
    ):
        raise ValueError("Positive SFT examples require an accepted prefix review")
    boundary_indexes = [
        index
        for index, message in enumerate(source_messages)
        if message.message_id
        == positive_sft_review.last_approved_assistant_message_id
    ]
    if len(boundary_indexes) != 1:
        raise ValueError(
            "Positive SFT approved boundary must identify exactly one source message"
        )
    boundary_index = boundary_indexes[0]
    if source_messages[boundary_index].role != "assistant":
        raise ValueError("Positive SFT approved boundary must be an assistant message")
    source_messages = source_messages[: boundary_index + 1]

    from agentenv.training.positive_sft.review import hash_positive_sft_review_record

    positive_sft_review_hash = hash_positive_sft_review_record(positive_sft_review)

    messages = tuple(
        PositiveSFTMessage(
            message_id=message.message_id,
            role=message.role,
            content=message.content,
            name=message.name,
            tool_call_id=message.tool_call_id,
        )
        for message in source_messages
    )
    task_manifest_path = Path(trajectory.source_provenance.task_manifest_path)
    validate_task_manifest_hash(trajectory, task_manifest_path=task_manifest_path)
    record = PositiveSFTExampleRecord(
        example_id=build_positive_sft_example_id(
            source_type=source_provenance.source_type,
            source_training_candidate_record_hash=(
                source_provenance.source_training_candidate_record_hash
            ),
            source_artifact_content_hash=require_content_hash(
                source_provenance.source_artifact_ref,
                field_name="positive SFT source artifact",
            ),
            source_positive_sft_review_record_hash=positive_sft_review_hash,
            source_training_candidate_repair_record_hash=(
                source_provenance.source_training_candidate_repair_record_hash
                if isinstance(
                    source_provenance,
                    RepairedPositiveSFTSourceProvenance,
                )
                else None
            ),
        ),
        provenance_ids=PositiveSFTProvenanceIds(
            trajectory_id=trajectory.identity.trajectory_id,
            eval_suite_id=trajectory.identity.eval_suite_id,
            eval_run_id=trajectory.identity.eval_run_id,
            eval_attempt_id=trajectory.identity.eval_attempt_id,
            agent_attempt_id=require_agent_attempt_id(trajectory),
            task_id=trajectory.identity.task_id,
            policy_id=trajectory.identity.policy_id,
        ),
        prompt_provenance=PositiveSFTPromptProvenance(
            prompt_builder_version=prompt_loop_result.prompt_builder_version,
            prompt_builder_code_hash=prompt_loop_result.prompt_builder_code_hash,
        ),
        review_provenance=PositiveSFTReviewProvenance(
            source_positive_sft_review_record_hash=positive_sft_review_hash,
            positive_sft_review_id=positive_sft_review.review_id,
            last_approved_assistant_message_id=(
                positive_sft_review.last_approved_assistant_message_id
            ),
        ),
        source_provenance=source_provenance,
        task_input=task_input,
        messages=list(messages),
    )
    validate_positive_sft_record_has_no_leakage(
        record,
        task_manifest_path=task_manifest_path,
    )
    return record


def validate_task_manifest_hash(
    trajectory: TrajectoryRecord,
    *,
    task_manifest_path: Path,
) -> None:
    observed_hash = hash_file(task_manifest_path)
    if observed_hash != trajectory.source_provenance.task_manifest_hash:
        raise ValueError(
            "Task manifest hash mismatch for positive SFT trajectory: "
            f"{observed_hash!r} != {trajectory.source_provenance.task_manifest_hash!r}"
        )


def validate_positive_sft_record_has_no_leakage(
    record: PositiveSFTExampleRecord,
    *,
    task_manifest_path: Path,
) -> None:
    task_manifest = load_task_manifest(task_manifest_path)
    scan = scan_texts_for_leakage(
        (
            LeakageScanText(
                "positive_sft_example_record",
                record.model_dump_json(),
            ),
        ),
        task_manifest,
    )
    if scan.canary_leaked or scan.hidden_validators_visible_to_model:
        matches = (*scan.canary_matches, *scan.private_marker_matches)
        raise ValueError(
            "Positive SFT example record failed leakage scan: " + ", ".join(matches)
        )


def require_agent_attempt_id(trajectory: TrajectoryRecord) -> str:
    if trajectory.identity.agent_attempt_id is None:
        raise ValueError(
            "Positive SFT trajectory missing agent_attempt_id: "
            f"{trajectory.identity.trajectory_id}"
        )
    return trajectory.identity.agent_attempt_id
