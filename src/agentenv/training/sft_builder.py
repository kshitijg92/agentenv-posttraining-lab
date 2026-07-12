from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import TRAJECTORY_REVIEW_ARTIFACT_REFS
from agentenv.artifacts.payloads import load_agent_task_view, load_prompt_loop_result
from agentenv.hashing import hash_file
from agentenv.security.leakage import LeakageScanText, scan_texts_for_leakage
from agentenv.tasks.validate import load_task_manifest
from agentenv.training.export import (
    TrainingCandidateExport,
    hash_source_trajectories_jsonl,
    load_training_candidate_export_artifact,
)
from agentenv.training.schema import (
    OriginalPositiveSFTSourceProvenance,
    PositiveSFTExampleRecord,
    PositiveSFTMessage,
    PositiveSFTPromptProvenance,
    PositiveSFTProvenanceIds,
    PositiveSFTTaskInput,
    RepairedPositiveSFTSourceProvenance,
    TrainingCandidateRecord,
)
from agentenv.training.repair import (
    MECHANICAL_REDUNDANCY_REPAIR_METHOD,
    hash_training_candidate_record,
    hash_training_candidate_repair_record,
    hash_training_candidate_repair_review_record,
)
from agentenv.training.repair_schema import (
    TrainingCandidateRepairRecord,
    TrainingCandidateRepairReviewRecord,
)
from agentenv.training.sft_identity import build_positive_sft_example_id
from agentenv.trajectories.export import (
    TrajectoryExport,
    load_trajectory_export_artifact,
)
from agentenv.trajectories.schema import ArtifactRef, TrajectoryRecord

if TYPE_CHECKING:
    from agentenv.training.repair_review import (
        TrainingCandidateRepairReviewValidation,
    )


MECHANICAL_REDUNDANCY_TASK_OUTCOME_INHERITANCE_BASIS = (
    "mechanical_redundancy_state_and_observation_preserving_deletion"
)


@dataclass(frozen=True)
class _SelectedPositiveSFTRepair:
    repair_export_dir: Path
    record: TrainingCandidateRepairRecord
    review: TrainingCandidateRepairReviewRecord


def build_positive_sft_examples(
    training_candidate_export_dir: Path,
    *,
    repair_export_dir: Path | None = None,
    repair_review_dir: Path | None = None,
    selected_repair_ids: Sequence[str] = (),
) -> tuple[PositiveSFTExampleRecord, ...]:
    training_candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    repair_validation = load_positive_sft_repair_sources(
        training_candidate_export,
        repair_export_dir=repair_export_dir,
        repair_review_dir=repair_review_dir,
        selected_repair_ids=selected_repair_ids,
    )
    return build_positive_sft_examples_from_training_candidate_export(
        training_candidate_export,
        repair_validation=repair_validation,
        selected_repair_ids=selected_repair_ids,
    )


def build_positive_sft_examples_from_training_candidate_export(
    training_candidate_export: TrainingCandidateExport,
    *,
    repair_validation: TrainingCandidateRepairReviewValidation | None = None,
    selected_repair_ids: Sequence[str] = (),
) -> tuple[PositiveSFTExampleRecord, ...]:
    validate_pinned_source_review_artifact(training_candidate_export)
    trajectory_export = load_pinned_source_trajectory_export(training_candidate_export)
    trajectory_by_id = build_trajectory_record_index(trajectory_export.records)
    selected_repairs = build_selected_positive_sft_repair_index(
        training_candidate_export,
        repair_validation=repair_validation,
        selected_repair_ids=selected_repair_ids,
    )

    examples: list[PositiveSFTExampleRecord] = []
    for candidate in training_candidate_export.records:
        if not candidate.training_eligibility.positive_sft_allowed:
            continue
        assessment = candidate.mechanical_redundancy_assessment
        if assessment.evaluation_status != "complete":
            continue
        candidate_hash = hash_training_candidate_record(candidate)
        selected_repair = selected_repairs.get(candidate_hash)
        if assessment.blocks and selected_repair is None:
            continue
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
            )
        )
    return tuple(examples)


def load_positive_sft_repair_sources(
    training_candidate_export: TrainingCandidateExport,
    *,
    repair_export_dir: Path | None,
    repair_review_dir: Path | None,
    selected_repair_ids: Sequence[str],
) -> TrainingCandidateRepairReviewValidation | None:
    selected_ids = tuple(selected_repair_ids)
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Positive SFT repair selections contain duplicate repair_id")
    if not selected_ids:
        if repair_export_dir is not None or repair_review_dir is not None:
            raise ValueError(
                "Positive SFT repair sources require at least one selected repair_id"
            )
        return None
    if repair_export_dir is None or repair_review_dir is None:
        raise ValueError(
            "Selected positive SFT repairs require repair export and review artifacts"
        )

    from agentenv.training.repair_review import (
        validate_training_candidate_repair_review_artifact,
    )

    validation = validate_training_candidate_repair_review_artifact(
        repair_export_dir,
        repair_review_dir,
    )
    validate_positive_sft_repair_source_matches_candidate_export(
        training_candidate_export,
        validation,
    )
    return validation


def validate_positive_sft_repair_source_matches_candidate_export(
    training_candidate_export: TrainingCandidateExport,
    repair_validation: TrainingCandidateRepairReviewValidation,
) -> None:
    repair_export = repair_validation.source_export
    source_ref = repair_export.manifest.source_training_candidate_export
    source_dir = Path(source_ref.artifact_dir)
    if not source_dir.is_absolute():
        source_dir = repair_export.out_dir / source_dir
    if source_dir.resolve() != training_candidate_export.out_dir.resolve():
        raise ValueError(
            "Positive SFT repair export references a different training candidate "
            "export"
        )
    candidate_manifest_hash = hash_file(
        training_candidate_export.out_dir / MANIFEST_FILENAME
    )
    if source_ref.manifest_hash != candidate_manifest_hash:
        raise ValueError(
            "Positive SFT repair export source training candidate manifest hash "
            "mismatch"
        )


def build_selected_positive_sft_repair_index(
    training_candidate_export: TrainingCandidateExport,
    *,
    repair_validation: TrainingCandidateRepairReviewValidation | None,
    selected_repair_ids: Sequence[str],
) -> dict[str, _SelectedPositiveSFTRepair]:
    selected_ids = tuple(selected_repair_ids)
    if not selected_ids:
        if repair_validation is not None:
            raise ValueError(
                "Positive SFT repair validation is unused without selected repair ids"
            )
        return {}
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Positive SFT repair selections contain duplicate repair_id")
    if repair_validation is None:
        raise ValueError("Positive SFT repair selections require validated artifacts")

    repairs_by_id = {
        record.repair_id: record for record in repair_validation.source_export.records
    }
    reviews_by_id = {
        review.repair_id: review for review in repair_validation.review_artifact.reviews
    }
    candidates_by_hash = {
        hash_training_candidate_record(candidate): candidate
        for candidate in training_candidate_export.records
    }
    selected_by_candidate_hash: dict[str, _SelectedPositiveSFTRepair] = {}
    for repair_id in selected_ids:
        repair = repairs_by_id.get(repair_id)
        if repair is None:
            raise ValueError(f"Positive SFT selected unknown repair_id: {repair_id}")
        review = reviews_by_id[repair_id]
        if repair.repair_status != "completed":
            raise ValueError(
                "Positive SFT selected repair is not completed: "
                f"{repair_id} ({repair.repair_status})"
            )
        if review.review_status != "reviewed" or review.review_decision != "accepted":
            raise ValueError(
                "Positive SFT selected repair does not have an accepted review: "
                f"{repair_id}"
            )
        if repair.repair.repair_method != MECHANICAL_REDUNDANCY_REPAIR_METHOD:
            raise ValueError(
                "Positive SFT cannot inherit task outcome for unsupported repair "
                f"method: {repair.repair.repair_method}"
            )

        candidate_hash = repair.source_training_candidate_record_hash
        candidate = candidates_by_hash.get(candidate_hash)
        if candidate is None:
            raise ValueError(
                "Positive SFT selected repair references an unknown training "
                f"candidate: {repair_id}"
            )
        if not candidate.training_eligibility.positive_sft_allowed:
            raise ValueError(
                "Positive SFT selected repair belongs to an ineligible candidate: "
                f"{repair_id}"
            )
        assessment = candidate.mechanical_redundancy_assessment
        if assessment.evaluation_status != "complete" or not assessment.blocks:
            raise ValueError(
                "Positive SFT selected repair requires a complete source assessment "
                f"with redundancy blocks: {repair_id}"
            )
        if candidate_hash in selected_by_candidate_hash:
            raise ValueError(
                "Positive SFT selected multiple repairs for one training candidate: "
                f"{candidate.trajectory_id} / {candidate.eval_attempt_id}"
            )
        selected_by_candidate_hash[candidate_hash] = _SelectedPositiveSFTRepair(
            repair_export_dir=repair_validation.source_export.out_dir,
            record=repair,
            review=review,
        )
    return selected_by_candidate_hash


def load_pinned_source_trajectory_export(
    training_candidate_export: TrainingCandidateExport,
) -> TrajectoryExport:
    trajectory_export_dir = resolve_source_trajectory_export_dir(
        training_candidate_export
    )
    observed_manifest_hash = hash_file(trajectory_export_dir / MANIFEST_FILENAME)
    expected_manifest_hash = (
        training_candidate_export.manifest.source_trajectory_export_manifest_hash
    )
    if observed_manifest_hash != expected_manifest_hash:
        raise ValueError(
            "Source trajectory export manifest hash mismatch: "
            f"{observed_manifest_hash!r} != {expected_manifest_hash!r}"
        )

    observed_jsonl_hash = hash_source_trajectories_jsonl(trajectory_export_dir)
    expected_jsonl_hash = (
        training_candidate_export.manifest.source_trajectories_jsonl_hash
    )
    if observed_jsonl_hash != expected_jsonl_hash:
        raise ValueError(
            "Source trajectory JSONL hash mismatch: "
            f"{observed_jsonl_hash!r} != {expected_jsonl_hash!r}"
        )

    return load_trajectory_export_artifact(trajectory_export_dir)


def validate_pinned_source_review_artifact(
    training_candidate_export: TrainingCandidateExport,
) -> None:
    review_dir = resolve_source_review_dir(training_candidate_export)
    observed_manifest_hash = hash_file(review_dir / MANIFEST_FILENAME)
    expected_manifest_hash = (
        training_candidate_export.manifest.source_review_manifest_hash
    )
    if observed_manifest_hash != expected_manifest_hash:
        raise ValueError(
            "Source review manifest hash mismatch: "
            f"{observed_manifest_hash!r} != {expected_manifest_hash!r}"
        )

    reviews_path = resolve_relative_artifact_ref(
        review_dir,
        TRAJECTORY_REVIEW_ARTIFACT_REFS["reviews"],
    )
    observed_reviews_hash = hash_file(reviews_path)
    expected_reviews_hash = training_candidate_export.manifest.source_reviews_jsonl_hash
    if observed_reviews_hash != expected_reviews_hash:
        raise ValueError(
            "Source reviews JSONL hash mismatch: "
            f"{observed_reviews_hash!r} != {expected_reviews_hash!r}"
        )


def resolve_source_trajectory_export_dir(
    training_candidate_export: TrainingCandidateExport,
) -> Path:
    source_dir = Path(training_candidate_export.manifest.source_trajectory_export_dir)
    if not source_dir.is_absolute():
        source_dir = training_candidate_export.out_dir / source_dir
    return source_dir.resolve()


def resolve_source_review_dir(
    training_candidate_export: TrainingCandidateExport,
) -> Path:
    source_dir = Path(training_candidate_export.manifest.source_review_dir)
    if not source_dir.is_absolute():
        source_dir = training_candidate_export.out_dir / source_dir
    return source_dir.resolve()


def build_trajectory_record_index(
    records: tuple[TrajectoryRecord, ...],
) -> dict[str, TrajectoryRecord]:
    record_by_id: dict[str, TrajectoryRecord] = {}
    for record in records:
        trajectory_id = record.identity.trajectory_id
        if trajectory_id in record_by_id:
            raise ValueError(
                f"Duplicate trajectory_id in trajectory export: {trajectory_id}"
            )
        record_by_id[trajectory_id] = record
    return record_by_id


def build_positive_sft_example_record(
    candidate: TrainingCandidateRecord,
    trajectory: TrajectoryRecord,
    *,
    selected_repair: _SelectedPositiveSFTRepair | None = None,
) -> PositiveSFTExampleRecord:
    validate_positive_sft_candidate_matches_trajectory(candidate, trajectory)
    if not candidate.training_eligibility.positive_sft_allowed:
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
    if prompt_loop_result.status != "completed":
        raise ValueError(
            "Positive SFT examples require completed prompt loops: "
            f"{trajectory.identity.trajectory_id}"
        )
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

    messages = tuple(
        PositiveSFTMessage(
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
        source_provenance=source_provenance,
        task_input=task_input,
        messages=list(messages),
    )
    validate_positive_sft_record_has_no_leakage(
        record,
        task_manifest_path=task_manifest_path,
    )
    return record


def load_selected_repaired_messages(
    selected_repair: _SelectedPositiveSFTRepair,
) -> list:
    from agentenv.training.repair_export import load_repaired_transcript_artifact

    repaired_ref = selected_repair.record.repaired_artifact_ref
    if repaired_ref is None:
        raise ValueError("Positive SFT selected repair is missing repaired artifact")
    expected_hash = require_content_hash(
        repaired_ref,
        field_name="repaired transcript",
    )
    repaired_path = resolve_relative_artifact_ref(
        selected_repair.repair_export_dir,
        repaired_ref.path,
    )
    observed_hash = hash_file(repaired_path)
    if observed_hash != expected_hash:
        raise ValueError(
            "Positive SFT repaired transcript hash mismatch: "
            f"{observed_hash!r} != {expected_hash!r}"
        )
    transcript = load_repaired_transcript_artifact(repaired_path)
    if hash_file(repaired_path) != expected_hash:
        raise ValueError("Positive SFT repaired transcript changed while loading")
    return transcript.root


def require_content_hash(artifact_ref: ArtifactRef, *, field_name: str) -> str:
    if artifact_ref.content_hash is None:
        raise ValueError(f"{field_name} must be content-hash pinned")
    return artifact_ref.content_hash


def validate_positive_sft_candidate_matches_trajectory(
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
                f"Training candidate {field_name} does not match trajectory: "
                f"{candidate_value!r} != {trajectory_value!r}"
            )


def require_artifact_ref(
    artifact_ref: ArtifactRef | None,
    field_name: str,
    trajectory: TrajectoryRecord,
) -> ArtifactRef:
    if artifact_ref is None:
        raise ValueError(
            f"Positive SFT trajectory missing {field_name}: "
            f"{trajectory.identity.trajectory_id}"
        )
    return artifact_ref


def resolve_trajectory_artifact_path(
    trajectory: TrajectoryRecord,
    artifact_ref: ArtifactRef,
) -> Path:
    eval_run_dir = Path(trajectory.artifacts.eval_run_path).resolve()
    raw_path = Path(artifact_ref.path)
    if raw_path.is_absolute():
        raise ValueError(
            f"Trajectory artifact ref must be relative: {artifact_ref.path}"
        )
    resolved = (eval_run_dir / raw_path).resolve()
    if not resolved.is_relative_to(eval_run_dir):
        raise ValueError(
            f"Trajectory artifact ref escapes eval run dir: {artifact_ref.path}"
        )
    return resolved


def validate_artifact_ref_hash(path: Path, artifact_ref: ArtifactRef) -> None:
    if artifact_ref.content_hash is None:
        raise ValueError(
            f"Training artifact ref is missing content_hash: {artifact_ref.path}"
        )
    observed_hash = hash_file(path)
    if observed_hash != artifact_ref.content_hash:
        raise ValueError(
            f"Artifact hash mismatch for {artifact_ref.path}: "
            f"{observed_hash!r} != {artifact_ref.content_hash!r}"
        )


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
