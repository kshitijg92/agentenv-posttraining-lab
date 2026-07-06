from pathlib import Path

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import TRAJECTORY_REVIEW_ARTIFACT_REFS
from agentenv.artifacts.payloads import load_agent_task_view, load_prompt_loop_result
from agentenv.security.leakage import LeakageScanText, scan_texts_for_leakage
from agentenv.tasks.validate import load_task_manifest
from agentenv.training.export import (
    TrainingCandidateExport,
    hash_source_trajectories_jsonl,
    load_training_candidate_export_artifact,
)
from agentenv.training.schema import (
    PositiveSFTExampleRecord,
    PositiveSFTMessage,
    PositiveSFTPromptProvenance,
    PositiveSFTProvenanceIds,
    PositiveSFTTaskInput,
    TrainingCandidateRecord,
    build_positive_sft_example_id,
)
from agentenv.trajectories.export import (
    TrajectoryExport,
    hash_file,
    load_trajectory_export_artifact,
)
from agentenv.trajectories.schema import ArtifactRef, TrajectoryRecord


def build_positive_sft_examples(
    training_candidate_export_dir: Path,
) -> tuple[PositiveSFTExampleRecord, ...]:
    training_candidate_export = load_training_candidate_export_artifact(
        training_candidate_export_dir
    )
    return build_positive_sft_examples_from_training_candidate_export(
        training_candidate_export
    )


def build_positive_sft_examples_from_training_candidate_export(
    training_candidate_export: TrainingCandidateExport,
) -> tuple[PositiveSFTExampleRecord, ...]:
    validate_pinned_source_review_artifact(training_candidate_export)
    trajectory_export = load_pinned_source_trajectory_export(training_candidate_export)
    trajectory_by_id = build_trajectory_record_index(trajectory_export.records)

    examples: list[PositiveSFTExampleRecord] = []
    for candidate in training_candidate_export.records:
        if not candidate.final_eligibility.positive_sft_allowed:
            continue
        trajectory = trajectory_by_id.get(candidate.trajectory_id)
        if trajectory is None:
            raise ValueError(
                "Training candidate references unknown trajectory_id: "
                f"{candidate.trajectory_id}"
            )
        examples.append(build_positive_sft_example_record(candidate, trajectory))
    return tuple(examples)


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
) -> PositiveSFTExampleRecord:
    validate_positive_sft_candidate_matches_trajectory(candidate, trajectory)
    if not trajectory.training_eligibility.positive_sft_allowed:
        raise ValueError(
            "Positive SFT candidate source trajectory is not mechanically "
            f"positive-SFT eligible: {trajectory.identity.trajectory_id}"
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
    messages = tuple(
        PositiveSFTMessage(
            role=message.role,
            content=message.content,
            name=message.name,
            tool_call_id=message.tool_call_id,
        )
        for message in prompt_loop_result.messages
    )
    task_manifest_path = Path(trajectory.source_provenance.task_manifest_path)
    validate_task_manifest_hash(trajectory, task_manifest_path=task_manifest_path)
    record = PositiveSFTExampleRecord(
        example_id=build_positive_sft_example_id(trajectory.identity.trajectory_id),
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
        task_input=task_input,
        messages=list(messages),
    )
    validate_positive_sft_record_has_no_leakage(
        record,
        task_manifest_path=task_manifest_path,
    )
    return record


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
