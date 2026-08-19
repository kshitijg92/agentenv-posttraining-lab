from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.artifacts.manifests import (
    EvalRunManifest,
    EvalSuitePolicyRunManifestRecord,
    EvalSuiteReplayRunManifestRecord,
    ReplayRunManifest,
    load_eval_run_manifest,
    load_replay_run_manifest,
)
from agentenv.artifacts.payloads import (
    ReplayComparisonRecord,
    ReplayResult,
    load_replay_comparison_records,
    load_replay_result,
)
from agentenv.controls.expectations import (
    expected_agent_control_outcome,
    expected_scorer_control_outcome,
)
from agentenv.evals.schema import (
    AGENT_MODEL_POLICY_TYPE,
    AgentControlScriptPolicy,
    EvalConfig,
    ScorerControlPatchPolicy,
)
from agentenv.evals.suite_validation import load_validated_eval_suite_declaration
from agentenv.trajectories.builder import build_trajectory_records_from_eval_suite
from agentenv.trajectories.schema import TrajectoryRecord


OperationalVerificationStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class EvalSuiteOperationalCheck:
    check_id: str
    status: OperationalVerificationStatus
    detail: str


@dataclass(frozen=True)
class EvalSuiteOperationalVerification:
    eval_suite_id: str
    checks: tuple[EvalSuiteOperationalCheck, ...]

    @property
    def status(self) -> OperationalVerificationStatus:
        if all(check.status == "PASS" for check in self.checks):
            return "PASS"
        return "FAIL"


def requires_operational_verification(config: EvalConfig) -> bool:
    return any(
        policy.type != AGENT_MODEL_POLICY_TYPE or policy.replay.repeats > 0
        for policy in config.policies.values()
    )


def verify_eval_suite_operational_expectations(
    eval_suite_dir: Path,
) -> EvalSuiteOperationalVerification:
    """Require control outcomes and configured replays to match expectations."""

    declaration = load_validated_eval_suite_declaration(eval_suite_dir)
    trajectories = build_trajectory_records_from_eval_suite(
        declaration.eval_suite_dir
    )
    if len(trajectories) != declaration.manifest.attempt_count:
        raise ValueError(
            "Eval suite trajectory count does not match declared attempt count"
        )

    checks = [
        check
        for trajectory in trajectories
        if (
            check := _control_trajectory_check(
                declaration.config,
                trajectory,
            )
        )
        is not None
    ]
    policy_runs = {
        policy_run.policy: policy_run
        for policy_run in declaration.manifest.policy_runs
    }
    checks.extend(
        _replay_run_check(
            declaration.eval_suite_dir,
            policy_runs[replay_run.policy],
            replay_run,
        )
        for replay_run in declaration.manifest.replay_runs
    )
    return EvalSuiteOperationalVerification(
        eval_suite_id=declaration.manifest.eval_suite_id,
        checks=tuple(checks),
    )


def _control_trajectory_check(
    config: EvalConfig,
    trajectory: TrajectoryRecord,
) -> EvalSuiteOperationalCheck | None:
    policy_id = trajectory.identity.policy_id
    policy = config.policies[policy_id]
    check_id = (
        f"control.{policy_id}.{trajectory.identity.task_id}."
        f"attempt_{trajectory.identity.attempt_index}"
    )
    statuses = trajectory.statuses

    if isinstance(policy, ScorerControlPatchPolicy):
        expected = expected_scorer_control_outcome(policy.control)
        observed = (
            statuses.attempt_status,
            statuses.public_status,
            statuses.hidden_status,
        )
        declared = (
            expected.attempt_status,
            expected.public_status,
            expected.hidden_status,
        )
    elif isinstance(policy, AgentControlScriptPolicy):
        expected_agent = expected_agent_control_outcome(policy.control)
        observed = (
            statuses.agent_task_run_status,
            statuses.prompt_loop_status,
            statuses.attempt_status,
        )
        declared = (
            expected_agent.agent_status,
            expected_agent.prompt_loop_status,
            expected_agent.nested_scorer_status,
        )
    else:
        return None

    if observed != declared:
        return EvalSuiteOperationalCheck(
            check_id=check_id,
            status="FAIL",
            detail=f"observed={observed!r}; expected={declared!r}",
        )
    return EvalSuiteOperationalCheck(
        check_id=check_id,
        status="PASS",
        detail=f"observed={observed!r}",
    )


def _replay_run_check(
    eval_suite_dir: Path,
    policy_run: EvalSuitePolicyRunManifestRecord,
    replay_run: EvalSuiteReplayRunManifestRecord,
) -> EvalSuiteOperationalCheck:
    check_id = f"replay.{replay_run.policy}.repeat_{replay_run.replay_index}"
    try:
        detail = _validate_replay_run(
            eval_suite_dir,
            policy_run,
            replay_run,
        )
    except (OSError, ValueError) as exc:
        return EvalSuiteOperationalCheck(
            check_id=check_id,
            status="FAIL",
            detail=f"{type(exc).__name__}: {exc}",
        )
    return EvalSuiteOperationalCheck(
        check_id=check_id,
        status="PASS",
        detail=detail,
    )


def _validate_replay_run(
    eval_suite_dir: Path,
    policy_run: EvalSuitePolicyRunManifestRecord,
    replay_run: EvalSuiteReplayRunManifestRecord,
) -> str:
    replay_dir = resolve_relative_artifact_ref(
        eval_suite_dir,
        replay_run.artifact_dir,
    )
    replay_manifest_path = resolve_relative_artifact_ref(
        eval_suite_dir,
        replay_run.manifest,
    )
    replay_result_path = resolve_relative_artifact_ref(
        eval_suite_dir,
        replay_run.replay_result,
    )
    replay_manifest = load_replay_run_manifest(replay_manifest_path)
    replay_result = load_replay_result(replay_result_path)

    source_run_dir = resolve_relative_artifact_ref(
        eval_suite_dir,
        policy_run.artifact_dir,
    )
    source_manifest = load_eval_run_manifest(
        resolve_relative_artifact_ref(eval_suite_dir, policy_run.manifest)
    )
    _validate_replay_parent_child_identity(
        replay_dir=replay_dir,
        replay_manifest_path=replay_manifest_path,
        replay_result_path=replay_result_path,
        replay_manifest=replay_manifest,
        source_run_dir=source_run_dir,
        source_manifest=source_manifest,
        replay_run=replay_run,
        replay_result=replay_result,
    )

    comparison_path = resolve_relative_artifact_ref(
        replay_dir,
        replay_manifest.artifacts["replay_results"],
    )
    comparisons = load_replay_comparison_records(comparison_path)
    _validate_replay_comparison_coverage(
        source_run_dir,
        replay_dir,
        source_manifest,
        comparisons,
    )
    if replay_result.status != "PASS":
        raise ValueError(f"configured replay status is {replay_result.status}")
    if not all(comparison.matched for comparison in comparisons):
        raise ValueError("configured replay contains mismatched comparisons")
    return f"policy={replay_run.policy}; attempts={len(comparisons)}; status=PASS"


def _validate_replay_parent_child_identity(
    *,
    replay_dir: Path,
    replay_manifest_path: Path,
    replay_result_path: Path,
    replay_manifest: ReplayRunManifest,
    source_run_dir: Path,
    source_manifest: EvalRunManifest,
    replay_run: EvalSuiteReplayRunManifestRecord,
    replay_result: ReplayResult,
) -> None:
    if replay_manifest_path.parent != replay_dir:
        raise ValueError("replay manifest is not directly owned by replay directory")
    expected_result_path = resolve_relative_artifact_ref(
        replay_dir,
        replay_manifest.artifacts["replay_result"],
    )
    if replay_result_path != expected_result_path:
        raise ValueError("suite replay result ref differs from child manifest ref")
    if replay_manifest.replay_run_id != replay_run.replay_run_id:
        raise ValueError("suite and child replay ids differ")
    if replay_result.replay_run_id != replay_run.replay_run_id:
        raise ValueError("suite and replay-result ids differ")
    if Path(replay_manifest.source_run_dir).resolve() != source_run_dir:
        raise ValueError("replay source directory differs from policy run")
    if replay_manifest.source_eval_run_id != source_manifest.eval_run_id:
        raise ValueError("replay source eval-run id differs from policy run")

    compared_result_fields = (
        "status",
        "attempt_count",
        "matched_attempts",
        "mismatched_attempts",
        "error_count",
    )
    for field_name in compared_result_fields:
        suite_value = getattr(replay_run, field_name)
        result_value = getattr(replay_result, field_name)
        if suite_value != result_value:
            raise ValueError(
                f"suite replay field {field_name!r} differs from child result"
            )


def _validate_replay_comparison_coverage(
    source_run_dir: Path,
    replay_dir: Path,
    source_manifest: EvalRunManifest,
    comparisons: tuple[ReplayComparisonRecord, ...],
) -> None:
    expected_attempts = {
        attempt.eval_attempt_id: attempt.artifact_dir
        for attempt in source_manifest.attempts
    }
    observed_ids = tuple(
        comparison.source_eval_attempt_id for comparison in comparisons
    )
    expected_ids = tuple(attempt.eval_attempt_id for attempt in source_manifest.attempts)
    if observed_ids != expected_ids:
        raise ValueError("replay comparisons do not cover source attempts in order")

    for comparison in comparisons:
        source_attempt_id = comparison.source_eval_attempt_id
        if source_attempt_id is None:
            raise ValueError("eval-run replay comparison is missing source attempt id")
        expected_source_ref = expected_attempts[source_attempt_id]
        if comparison.source_artifact_ref != expected_source_ref:
            raise ValueError("replay comparison source artifact ref is incorrect")
        expected_source_path = resolve_relative_artifact_ref(
            source_run_dir,
            comparison.source_artifact_ref,
        )
        if not expected_source_path.is_dir():
            raise ValueError("replay comparison source artifact is missing")
        if Path(comparison.source_artifact_path).resolve() != expected_source_path:
            raise ValueError("replay comparison source artifact path is incorrect")
        expected_replay_path = resolve_relative_artifact_ref(
            replay_dir,
            comparison.replay_artifact_ref,
        )
        if not expected_replay_path.is_dir():
            raise ValueError("replay comparison replay artifact is missing")
        if Path(comparison.replay_artifact_path).resolve() != expected_replay_path:
            raise ValueError("replay comparison replay artifact path is incorrect")
