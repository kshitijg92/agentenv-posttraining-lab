import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xxhash

from agentenv.artifacts import MANIFEST_FILENAME, ArtifactType
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    AgentTaskRunManifest,
    EvalRunAgentAttemptSummary,
    EvalRunAttemptManifestRecord,
    EvalRunManifest,
    EvalRunScorerAttemptSummary,
    EvalSuiteManifest,
    EvalSuitePolicyRunManifestRecord,
    ScorerAttemptManifest,
    load_attempt_manifest,
    load_eval_run_manifest,
    load_eval_suite_manifest,
    load_scorer_attempt_manifest,
)
from agentenv.artifacts.payloads import (
    SelectedEvalTaskHash,
    load_agent_control_script_artifact,
    load_agent_task_run_result,
    load_agent_task_view,
    load_attempt_result,
    load_decoding_config_provenance,
    load_model_config_provenance,
    load_prompt_loop_result,
)
from agentenv.evals.resolve import resolve_task_pack_path, select_policy
from agentenv.evals.schema import AGENT_EVAL_POLICY_TYPES
from agentenv.evals.validate import load_eval_config
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.security.leakage import (
    LEAKAGE_CHECK_VERSION,
    scan_agent_visible_artifacts,
    scan_files_for_leakage,
)
from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import load_task_manifest, load_task_pack_manifest
from agentenv.trajectories.schema import (
    ArtifactRef,
    GradeState,
    LeakageEvidence,
    RewardComponents,
    SourceProvenance,
    TrainingEligibility,
    TrajectoryArtifacts,
    TrajectoryIdentity,
    TrajectoryPolicy,
    TrajectoryRecord,
    TrajectoryReview,
    TrajectoryStatuses,
    list_reward_component_signal_field_names,
)


REWARD_COMPONENT_DERIVATION_VERSION = "trajectory_reward_components_derivation_v0"


@dataclass(frozen=True)
class ScorerArtifactRefs:
    attempt_json: ArtifactRef | None
    trace_jsonl: ArtifactRef | None
    stdout: ArtifactRef | None
    stderr: ArtifactRef | None
    final_diff: ArtifactRef | None


def build_trajectory_records_from_eval_suite(
    eval_suite_dir: Path,
) -> list[TrajectoryRecord]:
    eval_suite_dir = eval_suite_dir.resolve()
    eval_suite_manifest_path = eval_suite_dir / MANIFEST_FILENAME
    eval_suite_manifest = load_eval_suite_manifest(eval_suite_manifest_path)

    records: list[TrajectoryRecord] = []
    for policy_run in eval_suite_manifest.policy_runs:
        eval_run_manifest_path = resolve_relative_artifact_ref(
            eval_suite_dir,
            policy_run.manifest,
        )
        eval_run_manifest = load_eval_run_manifest(eval_run_manifest_path)
        validate_eval_run_manifest_matches_suite_policy_run(
            eval_suite_manifest=eval_suite_manifest,
            policy_run=policy_run,
            eval_run_manifest=eval_run_manifest,
            source_path=eval_run_manifest_path,
        )
        eval_run_dir = eval_run_manifest_path.parent
        for attempt_record in eval_run_manifest.attempts:
            record = build_trajectory_record_from_eval_attempt(
                eval_run_dir,
                eval_attempt_id=attempt_record.eval_attempt_id,
            )
            records.append(
                build_trajectory_record_with_eval_suite_id(
                    record,
                    eval_suite_manifest.eval_suite_id,
                )
            )
    return records


def build_trajectory_records_from_eval_run(
    eval_run_dir: Path,
) -> list[TrajectoryRecord]:
    eval_run_dir = eval_run_dir.resolve()
    eval_run_manifest = load_eval_run_manifest(eval_run_dir / MANIFEST_FILENAME)
    return [
        build_trajectory_record_from_eval_attempt(
            eval_run_dir,
            eval_attempt_id=attempt_record.eval_attempt_id,
        )
        for attempt_record in eval_run_manifest.attempts
    ]


def build_trajectory_record_from_eval_attempt(
    eval_run_dir: Path,
    *,
    eval_attempt_id: str,
) -> TrajectoryRecord:
    eval_run_dir = eval_run_dir.resolve()
    eval_run_manifest_path = eval_run_dir / MANIFEST_FILENAME
    eval_run_manifest = load_eval_run_manifest(eval_run_manifest_path)

    attempt_record = select_eval_attempt_record(eval_run_manifest, eval_attempt_id)
    attempt_dir = resolve_eval_run_artifact_path(
        eval_run_dir,
        attempt_record.artifact_dir,
    )
    attempt_manifest_path = attempt_dir / MANIFEST_FILENAME
    attempt_manifest = load_attempt_manifest(attempt_manifest_path)
    validate_attempt_manifest_matches_eval_record(
        attempt_record,
        attempt_manifest,
        attempt_manifest_path,
    )
    validate_attempt_payloads_match_eval_record(
        attempt_record,
        attempt_manifest,
        attempt_dir,
    )

    config_path = Path(eval_run_manifest.config_path)
    eval_config = load_eval_config(config_path)
    policy_id = eval_run_manifest.policy
    policy_spec = select_policy(eval_config, policy_id)

    task_id = attempt_record.task_id
    task_manifest_path = Path(attempt_manifest.task_manifest_path)
    task_manifest = load_task_manifest(task_manifest_path)
    if task_manifest.id != task_id:
        raise ValueError(
            f"Attempt task_id {task_id!r} does not match task manifest id "
            f"{task_manifest.id!r}"
        )

    task_pack_path = resolve_task_pack_path(eval_config, config_path)
    task_pack_manifest = load_task_pack_manifest(task_pack_path / "manifest.yaml")
    splits_lock_path = (task_pack_path / task_pack_manifest.split_lock).resolve()
    selected_task_hash = select_eval_task_hash_record(
        eval_run_manifest,
        task_id,
    )
    validate_live_task_manifest_matches_eval_hash(
        task_manifest=task_manifest,
        task_manifest_path=task_manifest_path,
        selected_task_hash=selected_task_hash,
    )
    agent_summary = attempt_record.agent
    scorer_summary = select_scorer_summary(attempt_record)
    statuses = build_statuses(agent_summary, scorer_summary)
    leakage = build_leakage_evidence(
        attempt_dir=attempt_dir,
        attempt_artifact_type=attempt_record.artifact_type,
        task_manifest=task_manifest,
    )
    reward_components = build_reward_components(statuses, agent_summary)

    return TrajectoryRecord(
        identity=TrajectoryIdentity(
            trajectory_id=build_trajectory_id(eval_attempt_id),
            eval_suite_id=None,
            eval_run_id=eval_run_manifest.eval_run_id,
            eval_attempt_id=eval_attempt_id,
            task_id=task_id,
            policy_id=policy_id,
            attempt_index=attempt_record.attempt_index,
            agent_attempt_id=select_agent_attempt_id(agent_summary),
            scorer_attempt_id=select_scorer_attempt_id(scorer_summary),
            replay_run_id=None,
        ),
        source_provenance=SourceProvenance(
            task_id=task_id,
            split=selected_task_hash.split,
            scoring_contract=task_pack_manifest.scoring_contract,
            task_manifest_path=str(task_manifest_path),
            task_manifest_hash=selected_task_hash.task_yaml_hash,
            splits_lock_path=str(splits_lock_path),
            splits_lock_hash=hash_file(splits_lock_path),
            eval_config_path=str(config_path),
            eval_config_hash=eval_run_manifest.config_hash,
        ),
        policy=TrajectoryPolicy(
            policy_id=policy_id,
            policy_name=policy_id,
            policy_spec=policy_spec,
        ),
        statuses=statuses,
        artifacts=build_trajectory_artifacts(
            eval_run_dir=eval_run_dir,
            attempt_dir_ref=attempt_record.artifact_dir,
            attempt_manifest=attempt_manifest,
        ),
        reward_components=reward_components,
        leakage=leakage,
        training_eligibility=build_training_eligibility(
            policy_type=policy_spec.type,
            split=selected_task_hash.split,
            statuses=statuses,
            reward_components=reward_components,
            leakage=leakage,
        ),
        review=TrajectoryReview(review_status="not_reviewed"),
    )


def validate_eval_run_manifest_matches_suite_policy_run(
    *,
    eval_suite_manifest: EvalSuiteManifest,
    policy_run: EvalSuitePolicyRunManifestRecord,
    eval_run_manifest: EvalRunManifest,
    source_path: Path,
) -> None:
    compared_fields = (
        ("eval_run_id", policy_run.eval_run_id, eval_run_manifest.eval_run_id),
        ("policy", policy_run.policy, eval_run_manifest.policy),
        ("config_path", eval_suite_manifest.config_path, eval_run_manifest.config_path),
        ("config_hash", eval_suite_manifest.config_hash, eval_run_manifest.config_hash),
        ("config_name", eval_suite_manifest.config_name, eval_run_manifest.config_name),
        ("task_pack", eval_suite_manifest.task_pack, eval_run_manifest.task_pack),
        ("split", eval_suite_manifest.split, eval_run_manifest.split),
        ("policy_type", policy_run.policy_type, eval_run_manifest.policy_type),
        ("policy_family", policy_run.policy_family, eval_run_manifest.policy_family),
        ("control_layer", policy_run.control_layer, eval_run_manifest.control_layer),
        ("control_name", policy_run.control_name, eval_run_manifest.control_name),
        (
            "model_config",
            policy_run.model_config_ref,
            eval_run_manifest.model_config_ref,
        ),
        (
            "decoding_config",
            policy_run.decoding_config_ref,
            eval_run_manifest.decoding_config_ref,
        ),
        (
            "attempts_per_task",
            policy_run.attempts_per_task,
            eval_run_manifest.attempts_per_task,
        ),
        ("replay_repeats", policy_run.replay_repeats, eval_run_manifest.replay_repeats),
        ("attempt_count", policy_run.attempt_count, eval_run_manifest.attempt_count),
        ("layer_counts", policy_run.layer_counts, eval_run_manifest.layer_counts),
    )
    for field_name, suite_value, child_value in compared_fields:
        if suite_value != child_value:
            raise ValueError(
                f"Eval suite policy_run {field_name} mismatch at {source_path}: "
                f"{suite_value!r} != {child_value!r}"
            )

    if eval_suite_manifest.task_hashes.model_dump(
        mode="json"
    ) != eval_run_manifest.task_hashes.model_dump(mode="json"):
        raise ValueError(f"Eval suite policy_run task_hashes mismatch at {source_path}")


def build_trajectory_record_with_eval_suite_id(
    record: TrajectoryRecord,
    eval_suite_id: str,
) -> TrajectoryRecord:
    payload = record.model_dump(mode="python")
    identity = record.identity.model_dump(mode="python")
    identity["eval_suite_id"] = eval_suite_id
    payload["identity"] = identity
    return TrajectoryRecord.model_validate(payload)


def select_eval_attempt_record(
    eval_run_manifest: EvalRunManifest,
    eval_attempt_id: str,
) -> EvalRunAttemptManifestRecord:
    matches = [
        attempt
        for attempt in eval_run_manifest.attempts
        if attempt.eval_attempt_id == eval_attempt_id
    ]
    if not matches:
        raise ValueError(f"Eval attempt not found: {eval_attempt_id}")
    if len(matches) > 1:
        raise ValueError(f"Duplicate eval_attempt_id in eval run: {eval_attempt_id}")
    return matches[0]


def select_eval_task_hash_record(
    eval_run_manifest: EvalRunManifest,
    task_id: str,
) -> SelectedEvalTaskHash:
    for task_hash in eval_run_manifest.task_hashes.selected_tasks:
        if task_hash.task_id == task_id:
            return task_hash
    raise ValueError(f"Task hash record not found for task_id: {task_id}")


def select_scorer_summary(
    attempt_record: EvalRunAttemptManifestRecord,
) -> EvalRunScorerAttemptSummary | None:
    if attempt_record.scorer is not None:
        return attempt_record.scorer
    if attempt_record.agent is None:
        return None
    return attempt_record.agent.scorer_attempt


def validate_live_task_manifest_matches_eval_hash(
    *,
    task_manifest: TaskManifest,
    task_manifest_path: Path,
    selected_task_hash: SelectedEvalTaskHash,
) -> None:
    if task_manifest.split != selected_task_hash.split:
        raise ValueError(
            f"Live task split mismatch at {task_manifest_path}: "
            f"{task_manifest.split!r} != {selected_task_hash.split!r}"
        )
    live_task_yaml_hash = hash_file(task_manifest_path)
    if live_task_yaml_hash != selected_task_hash.task_yaml_hash:
        raise ValueError(
            f"Live task manifest hash mismatch at {task_manifest_path}: "
            f"{live_task_yaml_hash!r} != {selected_task_hash.task_yaml_hash!r}"
        )


def validate_attempt_manifest_matches_eval_record(
    attempt_record: EvalRunAttemptManifestRecord,
    attempt_manifest: ScorerAttemptManifest | AgentTaskRunManifest,
    source_path: Path,
) -> None:
    if attempt_manifest.artifact_type != attempt_record.artifact_type:
        raise ValueError(
            f"Attempt manifest artifact_type mismatch at {source_path}: "
            f"{attempt_manifest.artifact_type!r} != {attempt_record.artifact_type!r}"
        )
    if (
        attempt_manifest.artifact_schema_version
        != attempt_record.artifact_schema_version
    ):
        raise ValueError(
            f"Attempt manifest artifact_schema_version mismatch at {source_path}"
        )
    if attempt_manifest.task_id != attempt_record.task_id:
        raise ValueError(
            f"Attempt manifest task_id mismatch at {source_path}: "
            f"{attempt_manifest.task_id!r} != {attempt_record.task_id!r}"
        )
    if isinstance(attempt_manifest, AgentTaskRunManifest):
        if attempt_record.agent is None:
            raise ValueError(
                f"Agent attempt record missing agent summary at {source_path}"
            )
        if attempt_manifest.agent_attempt_id != attempt_record.agent.agent_attempt_id:
            raise ValueError(
                f"Agent attempt id mismatch at {source_path}: "
                f"{attempt_manifest.agent_attempt_id!r} != "
                f"{attempt_record.agent.agent_attempt_id!r}"
            )
        return
    if attempt_record.scorer is None:
        raise ValueError(
            f"Scorer attempt record missing scorer summary at {source_path}"
        )
    if attempt_manifest.scorer_attempt_id != attempt_record.scorer.scorer_attempt_id:
        raise ValueError(
            f"Scorer attempt id mismatch at {source_path}: "
            f"{attempt_manifest.scorer_attempt_id!r} != "
            f"{attempt_record.scorer.scorer_attempt_id!r}"
        )


def validate_attempt_payloads_match_eval_record(
    attempt_record: EvalRunAttemptManifestRecord,
    attempt_manifest: ScorerAttemptManifest | AgentTaskRunManifest,
    attempt_dir: Path,
) -> None:
    if isinstance(attempt_manifest, AgentTaskRunManifest):
        agent_result = load_agent_task_run_result(
            resolve_manifest_artifact_path(
                attempt_dir,
                attempt_manifest.artifacts,
                "agent_task_run",
            )
        )
        validate_agent_result_matches_manifest(
            agent_result, attempt_manifest, attempt_dir
        )
        validate_agent_payload_refs_match_manifest(
            attempt_manifest,
            attempt_dir,
        )
        if attempt_record.agent is None:
            raise ValueError(
                f"Agent attempt record missing agent summary at {attempt_dir}"
            )
        validate_agent_result_matches_eval_summary(
            agent_result,
            attempt_record,
            attempt_dir,
        )
        nested_attempt_ref = attempt_manifest.artifacts.get("attempt")
        if nested_attempt_ref is not None:
            nested_attempt_dir = resolve_relative_artifact_ref(
                attempt_dir,
                nested_attempt_ref.rstrip("/"),
            )
            nested_attempt_manifest = load_scorer_attempt_manifest(
                nested_attempt_dir / MANIFEST_FILENAME
            )
            nested_attempt_result = load_attempt_result(
                resolve_manifest_artifact_path(
                    nested_attempt_dir,
                    nested_attempt_manifest.artifacts,
                    "attempt",
                )
            )
            if agent_result.attempt_result is None:
                raise ValueError(
                    f"Agent result missing nested attempt_result at {attempt_dir}"
                )
            validate_scorer_result_matches_manifest(
                nested_attempt_result,
                nested_attempt_manifest,
                nested_attempt_dir,
            )
            validate_scorer_result_matches_summary(
                nested_attempt_result,
                agent_result.attempt_result,
                attempt_dir,
                context="agent_task_run nested attempt_result",
            )
        return

    scorer_result = load_attempt_result(
        resolve_manifest_artifact_path(
            attempt_dir, attempt_manifest.artifacts, "attempt"
        )
    )
    validate_scorer_result_matches_manifest(
        scorer_result, attempt_manifest, attempt_dir
    )
    if attempt_record.scorer is None:
        raise ValueError(
            f"Scorer attempt record missing scorer summary at {attempt_dir}"
        )
    validate_scorer_result_matches_summary(
        scorer_result,
        attempt_record.scorer,
        attempt_dir,
        context="eval parent scorer summary",
    )


def validate_agent_payload_refs_match_manifest(
    attempt_manifest: AgentTaskRunManifest,
    attempt_dir: Path,
) -> None:
    artifacts = attempt_manifest.artifacts
    load_decoding_config_provenance(
        resolve_manifest_artifact_path(attempt_dir, artifacts, "decoding_config")
    )

    if attempt_manifest.prompt_loop_status is not None:
        task_view = load_agent_task_view(
            resolve_manifest_artifact_path(attempt_dir, artifacts, "agent_task_view")
        )
        if task_view.task_id != attempt_manifest.task_id:
            raise ValueError(f"Agent task view task_id mismatch at {attempt_dir}")

        prompt_loop = load_prompt_loop_result(
            resolve_manifest_artifact_path(
                attempt_dir,
                artifacts,
                "prompt_loop_result",
            )
        )
        if prompt_loop.task_id != attempt_manifest.task_id:
            raise ValueError(f"Prompt loop task_id mismatch at {attempt_dir}")
        if prompt_loop.status != attempt_manifest.prompt_loop_status:
            raise ValueError(f"Prompt loop status mismatch at {attempt_dir}")

    if "model_config" in artifacts:
        load_model_config_provenance(
            resolve_manifest_artifact_path(attempt_dir, artifacts, "model_config")
        )
    if "agent_control_script" in artifacts:
        load_agent_control_script_artifact(
            resolve_manifest_artifact_path(
                attempt_dir,
                artifacts,
                "agent_control_script",
            )
        )


def resolve_manifest_artifact_path(
    artifact_dir: Path,
    artifacts: Mapping[str, str],
    artifact_name: str,
) -> Path:
    artifact_ref = artifacts.get(artifact_name)
    if artifact_ref is None:
        raise ValueError(f"Missing artifact ref {artifact_name!r} in {artifact_dir}")
    return resolve_relative_artifact_ref(artifact_dir, artifact_ref)


def validate_agent_result_matches_manifest(
    agent_result: AgentTaskRunResult,
    attempt_manifest: AgentTaskRunManifest,
    source_path: Path,
) -> None:
    if agent_result.agent_attempt_id != attempt_manifest.agent_attempt_id:
        raise ValueError(f"Agent result id mismatch at {source_path}")
    if agent_result.task_id != attempt_manifest.task_id:
        raise ValueError(f"Agent result task_id mismatch at {source_path}")
    if agent_result.task_manifest_path != attempt_manifest.task_manifest_path:
        raise ValueError(f"Agent result task_manifest_path mismatch at {source_path}")
    if agent_result.status != attempt_manifest.status:
        raise ValueError(f"Agent result status mismatch at {source_path}")
    if agent_result.prompt_loop_status != attempt_manifest.prompt_loop_status:
        raise ValueError(f"Agent result prompt_loop_status mismatch at {source_path}")
    attempt_status = (
        agent_result.attempt_result.status
        if agent_result.attempt_result is not None
        else None
    )
    if attempt_status != attempt_manifest.attempt_status:
        raise ValueError(f"Agent result attempt_status mismatch at {source_path}")


def validate_agent_result_matches_eval_summary(
    agent_result: AgentTaskRunResult,
    attempt_record: EvalRunAttemptManifestRecord,
    source_path: Path,
) -> None:
    agent_summary = attempt_record.agent
    if agent_summary is None:
        raise ValueError(f"Agent attempt record missing agent summary at {source_path}")
    if agent_result.agent_attempt_id != agent_summary.agent_attempt_id:
        raise ValueError(f"Agent result id mismatch with eval summary at {source_path}")
    if agent_result.task_id != attempt_record.task_id:
        raise ValueError(
            f"Agent result task_id mismatch with eval summary at {source_path}"
        )
    if agent_result.status != agent_summary.status:
        raise ValueError(
            f"Agent result status mismatch with eval summary at {source_path}"
        )
    if agent_result.prompt_loop_status != agent_summary.prompt_loop_status:
        raise ValueError(
            f"Agent result prompt_loop_status mismatch with eval summary at {source_path}"
        )
    if agent_result.candidate_patch_hash != agent_summary.candidate_patch_hash:
        raise ValueError(
            f"Agent result candidate_patch_hash mismatch with eval summary at {source_path}"
        )
    scorer_summary = agent_summary.scorer_attempt
    if agent_result.attempt_result is None:
        if scorer_summary is not None:
            raise ValueError(f"Agent result missing scorer payload at {source_path}")
        return
    if scorer_summary is None:
        raise ValueError(f"Eval summary missing nested scorer summary at {source_path}")
    validate_scorer_result_matches_summary(
        agent_result.attempt_result,
        scorer_summary,
        source_path,
        context="eval parent nested scorer summary",
    )


def validate_scorer_result_matches_manifest(
    scorer_result: AttemptResult,
    attempt_manifest: ScorerAttemptManifest,
    source_path: Path,
) -> None:
    if scorer_result.scorer_attempt_id != attempt_manifest.scorer_attempt_id:
        raise ValueError(f"Scorer result id mismatch at {source_path}")
    if scorer_result.task_id != attempt_manifest.task_id:
        raise ValueError(f"Scorer result task_id mismatch at {source_path}")
    if scorer_result.task_manifest_path != attempt_manifest.task_manifest_path:
        raise ValueError(f"Scorer result task_manifest_path mismatch at {source_path}")
    if scorer_result.submission_path != attempt_manifest.submission_path:
        raise ValueError(f"Scorer result submission_path mismatch at {source_path}")
    if scorer_result.status != attempt_manifest.status:
        raise ValueError(f"Scorer result status mismatch at {source_path}")


def validate_scorer_result_matches_summary(
    scorer_result: AttemptResult,
    scorer_summary: AttemptResult | EvalRunScorerAttemptSummary,
    source_path: Path,
    *,
    context: str,
) -> None:
    compared_fields = (
        "scorer_attempt_id",
        "status",
        "public_status",
        "hidden_status",
        "error_class",
        "final_diff_hash",
    )
    for field_name in compared_fields:
        if getattr(scorer_result, field_name) != getattr(scorer_summary, field_name):
            raise ValueError(
                f"Scorer result {field_name} mismatch with {context} at {source_path}"
            )


def select_agent_attempt_id(
    agent_summary: EvalRunAgentAttemptSummary | None,
) -> str | None:
    if agent_summary is None:
        return None
    return agent_summary.agent_attempt_id


def select_scorer_attempt_id(
    scorer_summary: EvalRunScorerAttemptSummary | None,
) -> str | None:
    if scorer_summary is None:
        return None
    return scorer_summary.scorer_attempt_id


def build_statuses(
    agent_summary: EvalRunAgentAttemptSummary | None,
    scorer_summary: EvalRunScorerAttemptSummary | None,
) -> TrajectoryStatuses:
    attempt_status = scorer_summary.status if scorer_summary is not None else None
    public_status = scorer_summary.public_status if scorer_summary is not None else None
    hidden_status = scorer_summary.hidden_status if scorer_summary is not None else None
    task_success = is_task_success(agent_summary, scorer_summary)
    return TrajectoryStatuses.model_validate(
        {
            "agent_task_run_status": (
                agent_summary.status if agent_summary is not None else None
            ),
            "prompt_loop_status": (
                agent_summary.prompt_loop_status if agent_summary is not None else None
            ),
            "attempt_status": attempt_status,
            "public_status": public_status,
            "hidden_status": hidden_status,
            "grade_state": derive_grade_state(
                task_success=task_success,
                scorer_summary=scorer_summary,
            ),
            "task_success": task_success,
        }
    )


def is_task_success(
    agent_summary: EvalRunAgentAttemptSummary | None,
    scorer_summary: EvalRunScorerAttemptSummary | None,
) -> bool:
    if scorer_summary is None:
        return False

    scorer_passed = (
        scorer_summary.status == "PASS"
        and scorer_summary.public_status == "PASS"
        and scorer_summary.hidden_status == "PASS"
    )
    if not scorer_passed:
        return False
    if agent_summary is None:
        return True

    return (
        agent_summary.status == "scored"
        and agent_summary.prompt_loop_status == "completed"
    )


def derive_grade_state(
    *,
    task_success: bool,
    scorer_summary: EvalRunScorerAttemptSummary | None,
) -> GradeState:
    if task_success:
        return "scored_pass"
    if scorer_summary is None:
        return "cannot_grade"
    return "scored_fail"


def build_leakage_evidence(
    *,
    attempt_dir: Path,
    attempt_artifact_type: str,
    task_manifest: TaskManifest,
) -> LeakageEvidence:
    if attempt_artifact_type == ArtifactType.AGENT_ATTEMPT.value:
        scan = scan_agent_visible_artifacts(attempt_dir, task_manifest)
    else:
        scan = scan_files_for_leakage([], task_manifest)

    return LeakageEvidence(
        canary_hash=scan.canary_hash,
        canary_leaked=scan.canary_leaked,
        hidden_validators_visible_to_model=scan.hidden_validators_visible_to_model,
        leakage_check_version=LEAKAGE_CHECK_VERSION,
    )


def build_reward_components(
    statuses: TrajectoryStatuses,
    agent_summary: EvalRunAgentAttemptSummary | None,
) -> RewardComponents:
    return RewardComponents(
        reward_config_hash=hash_json(build_reward_component_derivation_config()),
        reward_code_hash=hash_file(Path(__file__)),
        public_validator_success=derive_validator_success(statuses.public_status),
        hidden_validator_success=derive_validator_success(statuses.hidden_status),
        model_output_format_valid=derive_model_output_format_valid(
            agent_summary,
            statuses.prompt_loop_status,
        ),
        model_tool_usage_valid=derive_model_tool_usage_valid(
            agent_summary,
            statuses.prompt_loop_status,
        ),
        orchestration_failure=has_orchestration_failure(statuses),
        reward_hack_flag=derive_reward_hack_flag(statuses.attempt_status),
    )


def derive_validator_success(status: object) -> bool | None:
    if status is None:
        return None
    return status == "PASS"


def build_reward_component_derivation_config() -> dict[str, object]:
    return {
        "version": REWARD_COMPONENT_DERIVATION_VERSION,
        "components": list(list_reward_component_signal_field_names()),
    }


def derive_model_output_format_valid(
    agent_summary: EvalRunAgentAttemptSummary | None,
    prompt_loop_status: object,
) -> bool | None:
    if agent_summary is None or prompt_loop_status is None:
        return None
    return prompt_loop_status != "invalid_model_output"


def derive_model_tool_usage_valid(
    agent_summary: EvalRunAgentAttemptSummary | None,
    prompt_loop_status: object,
) -> bool | None:
    if agent_summary is None or prompt_loop_status is None:
        return None
    if prompt_loop_status == "terminal_tool_error":
        return False
    if prompt_loop_status in {"completed", "max_turns_exceeded"}:
        return True
    return None


def has_orchestration_failure(statuses: TrajectoryStatuses) -> bool:
    return (
        statuses.agent_task_run_status == "orchestrator_error"
        or statuses.attempt_status == "ORCHESTRATOR_ERROR"
    )


def derive_reward_hack_flag(attempt_status: object) -> bool | None:
    if attempt_status is None:
        return None
    return attempt_status in {
        "INVALID_SHORTCUT",
        "HIDDEN_VALIDATOR_ACCESS_ATTEMPT",
    }


def build_training_eligibility(
    *,
    policy_type: str,
    split: str,
    statuses: TrajectoryStatuses,
    reward_components: RewardComponents,
    leakage: LeakageEvidence,
) -> TrainingEligibility:
    is_agent_policy = policy_type in AGENT_EVAL_POLICY_TYPES
    has_leakage = leakage.canary_leaked or leakage.hidden_validators_visible_to_model
    has_orchestration_failure = reward_components.orchestration_failure
    is_trainable_split = split not in {"heldout_private", "public_calibration"}
    task_success = statuses.task_success
    grade_state = statuses.grade_state

    positive_sft_allowed = (
        is_agent_policy
        and task_success
        and is_trainable_split
        and not has_leakage
        and not has_orchestration_failure
    )
    negative_example_allowed = (
        is_agent_policy
        and not task_success
        and is_trainable_split
        and not has_leakage
        and not has_orchestration_failure
    )
    preference_data_allowed = (
        is_agent_policy
        and grade_state != "cannot_grade"
        and is_trainable_split
        and not has_leakage
        and not has_orchestration_failure
    )

    return TrainingEligibility(
        analysis_allowed=True,
        positive_sft_allowed=positive_sft_allowed,
        negative_example_allowed=negative_example_allowed,
        preference_data_allowed=preference_data_allowed,
        eligibility_reason=build_training_eligibility_reason(
            is_agent_policy=is_agent_policy,
            is_trainable_split=is_trainable_split,
            has_leakage=has_leakage,
            has_orchestration_failure=has_orchestration_failure,
            task_success=task_success,
            grade_state=grade_state,
        ),
    )


def build_training_eligibility_reason(
    *,
    is_agent_policy: bool,
    is_trainable_split: bool,
    has_leakage: bool,
    has_orchestration_failure: bool,
    task_success: bool,
    grade_state: object,
) -> str:
    if has_leakage:
        return "leakage detected; analysis only"
    if has_orchestration_failure:
        return "orchestration failure; analysis only"
    if not is_agent_policy:
        return "scorer-control trajectory has no agent behavior to imitate"
    if not is_trainable_split:
        return "split is not eligible for training"
    if task_success:
        return "agent trajectory passed public and hidden validators"
    if grade_state == "cannot_grade":
        return "agent trajectory cannot be graded"
    return "agent trajectory failed one or more validators"


def build_trajectory_artifacts(
    *,
    eval_run_dir: Path,
    attempt_dir_ref: str,
    attempt_manifest: ScorerAttemptManifest | AgentTaskRunManifest,
) -> TrajectoryArtifacts:
    attempt_artifacts = attempt_manifest.artifacts
    artifact_type = attempt_manifest.artifact_type
    scorer_artifact_refs = ScorerArtifactRefs(
        attempt_json=None,
        trace_jsonl=None,
        stdout=None,
        stderr=None,
        final_diff=None,
    )
    if artifact_type == ArtifactType.AGENT_ATTEMPT.value:
        scorer_artifact_refs = build_nested_scorer_artifact_refs(
            eval_run_dir=eval_run_dir,
            attempt_dir_ref=attempt_dir_ref,
            attempt_artifacts=attempt_artifacts,
        )
    elif artifact_type == ArtifactType.SCORER_ATTEMPT.value:
        scorer_artifact_refs = build_scorer_artifact_refs(
            eval_run_dir=eval_run_dir,
            scorer_dir_ref=attempt_dir_ref,
            scorer_artifacts=attempt_artifacts,
        )
    return TrajectoryArtifacts(
        eval_run_path=str(eval_run_dir),
        eval_suite_json=None,
        manifest_json=build_required_artifact_ref(
            eval_run_dir,
            f"{attempt_dir_ref}/{MANIFEST_FILENAME}",
        ),
        agent_task_run_json=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "agent_task_run",
        ),
        agent_task_view_json=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "agent_task_view",
        ),
        prompt_loop_result_json=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "prompt_loop_result",
        ),
        decoding_config_json=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "decoding_config",
        ),
        model_config_json=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "model_config",
        ),
        agent_control_script_json=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "agent_control_script",
        ),
        candidate_patch=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "candidate_patch",
        ),
        attempt_json=scorer_artifact_refs.attempt_json,
        trace_jsonl=scorer_artifact_refs.trace_jsonl,
        stdout=scorer_artifact_refs.stdout,
        stderr=scorer_artifact_refs.stderr,
        error_txt=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            attempt_dir_ref,
            attempt_artifacts,
            "error",
        ),
        final_diff=scorer_artifact_refs.final_diff,
    )


def build_nested_scorer_artifact_refs(
    *,
    eval_run_dir: Path,
    attempt_dir_ref: str,
    attempt_artifacts: Mapping[str, Any],
) -> ScorerArtifactRefs:
    nested_ref = attempt_artifacts.get("attempt")
    if not isinstance(nested_ref, str):
        return empty_scorer_artifact_refs()

    nested_dir_ref = f"{attempt_dir_ref}/{nested_ref.rstrip('/')}"
    nested_manifest_path = resolve_eval_run_artifact_path(
        eval_run_dir,
        f"{nested_dir_ref}/{MANIFEST_FILENAME}",
    )
    if not nested_manifest_path.is_file():
        return empty_scorer_artifact_refs()
    nested_manifest = load_scorer_attempt_manifest(nested_manifest_path)
    return build_scorer_artifact_refs(
        eval_run_dir=eval_run_dir,
        scorer_dir_ref=nested_dir_ref,
        scorer_artifacts=nested_manifest.artifacts,
    )


def empty_scorer_artifact_refs() -> ScorerArtifactRefs:
    return ScorerArtifactRefs(
        attempt_json=None,
        trace_jsonl=None,
        stdout=None,
        stderr=None,
        final_diff=None,
    )


def build_scorer_artifact_refs(
    *,
    eval_run_dir: Path,
    scorer_dir_ref: str,
    scorer_artifacts: Mapping[str, Any],
) -> ScorerArtifactRefs:
    return ScorerArtifactRefs(
        attempt_json=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            scorer_dir_ref,
            scorer_artifacts,
            "attempt",
        ),
        trace_jsonl=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            scorer_dir_ref,
            scorer_artifacts,
            "trace",
        ),
        stdout=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            scorer_dir_ref,
            scorer_artifacts,
            "stdout",
        ),
        stderr=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            scorer_dir_ref,
            scorer_artifacts,
            "stderr",
        ),
        final_diff=build_optional_artifact_ref_from_manifest(
            eval_run_dir,
            scorer_dir_ref,
            scorer_artifacts,
            "final_diff",
        ),
    )


def build_optional_artifact_ref_from_manifest(
    eval_run_dir: Path,
    artifact_dir_ref: str,
    artifacts: Mapping[str, Any],
    artifact_name: str,
) -> ArtifactRef | None:
    artifact_ref = artifacts.get(artifact_name)
    if not isinstance(artifact_ref, str):
        return None
    return build_optional_artifact_ref(
        eval_run_dir,
        f"{artifact_dir_ref}/{artifact_ref}",
    )


def build_required_artifact_ref(
    eval_run_dir: Path,
    artifact_ref: str,
) -> ArtifactRef:
    artifact = build_optional_artifact_ref(eval_run_dir, artifact_ref)
    if artifact is None:
        raise ValueError(f"Missing required artifact: {artifact_ref}")
    return artifact


def build_optional_artifact_ref(
    eval_run_dir: Path,
    artifact_ref: str,
) -> ArtifactRef | None:
    path = resolve_eval_run_artifact_path(eval_run_dir, artifact_ref)
    if not path.is_file():
        return None
    return ArtifactRef(path=artifact_ref, content_hash=hash_file(path))


def resolve_eval_run_artifact_path(eval_run_dir: Path, artifact_ref: str) -> Path:
    raw_path = Path(artifact_ref)
    if raw_path.is_absolute():
        raise ValueError(f"Artifact ref must be relative: {artifact_ref}")
    resolved = (eval_run_dir / raw_path).resolve()
    if not resolved.is_relative_to(eval_run_dir.resolve()):
        raise ValueError(f"Artifact ref escapes eval run directory: {artifact_ref}")
    return resolved


def build_trajectory_id(eval_attempt_id: str) -> str:
    prefix = "eval_attempt_"
    suffix = (
        eval_attempt_id.removeprefix(prefix)
        if eval_attempt_id.startswith(prefix)
        else eval_attempt_id
    )
    return f"trajectory_{suffix}"


def read_optional_mapping(
    payload: Mapping[str, Any] | None,
    field_name: str,
    source_path: Path,
) -> dict[str, Any] | None:
    if payload is None:
        return None
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Expected object field {field_name!r} in {source_path}")
    return dict(value)


def read_required_mapping(
    payload: Mapping[str, Any],
    field_name: str,
    source_path: Path,
) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"Expected object field {field_name!r} in {source_path}")
    return dict(value)


def read_required_str(
    payload: Mapping[str, Any],
    field_name: str,
    source_path: Path,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"Expected non-empty string field {field_name!r} in {source_path}"
        )
    return value


def read_optional_str(
    payload: Mapping[str, Any] | None,
    field_name: str,
) -> str | None:
    if payload is None:
        return None
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected string field {field_name!r}")
    return value


def read_required_int(
    payload: Mapping[str, Any],
    field_name: str,
    source_path: Path,
) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int):
        raise ValueError(f"Expected integer field {field_name!r} in {source_path}")
    return value


def hash_file(path: Path) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(path.read_bytes())}"


def hash_json(value: object) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return f"xxh64:{xxhash.xxh64_hexdigest(payload.encode())}"
