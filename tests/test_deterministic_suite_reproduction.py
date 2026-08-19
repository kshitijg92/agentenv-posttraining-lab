from pathlib import Path

import pytest

from agentenv.artifacts.manifests import (
    EvalSuiteReplayRunManifestRecord,
    load_eval_suite_manifest,
)
from agentenv.evals.validate import load_eval_config
from agentenv.orchestrators.eval_run import run_eval_config_all_policies
from agentenv.reproduction.deterministic_suite import (
    _control_trajectory_check,
    _replay_run_check,
    verify_eval_suite_operational_expectations,
)
from agentenv.trajectories.schema import (
    TrajectoryIdentity,
    TrajectoryRecord,
    TrajectoryStatuses,
)


SCORER_CONTROL_CONFIG = Path("configs/eval/scorer_control_policies.yaml")
AGENT_CONTROL_CONFIG = Path("configs/eval/agent_control_policies.yaml")


@pytest.fixture(scope="module")
def scorer_control_suite(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("deterministic_suite") / "eval_suite"
    return run_eval_config_all_policies(SCORER_CONTROL_CONFIG, out_dir).out_dir


def test_operational_verification_accepts_expected_controls_and_replays(
    scorer_control_suite: Path,
) -> None:
    verification = verify_eval_suite_operational_expectations(
        scorer_control_suite
    )

    assert verification.status == "PASS"
    assert len(verification.checks) == 6
    assert {check.check_id for check in verification.checks} == {
        "control.oracle.toy_python_fix_001.attempt_0",
        "control.bad-noop.toy_python_fix_001.attempt_0",
        "control.bad-public-only.toy_python_fix_001.attempt_0",
        "replay.oracle.repeat_0",
        "replay.bad-noop.repeat_0",
        "replay.bad-public-only.repeat_0",
    }


@pytest.mark.parametrize(
    ("policy_id", "statuses"),
    [
        (
            "agent-happy",
            TrajectoryStatuses(
                agent_task_run_status="scored",
                prompt_loop_status="completed",
                attempt_status="PASS",
                public_status="PASS",
                hidden_status="PASS",
                grade_state="scored_pass",
                task_success=True,
            ),
        ),
        (
            "agent-malformed",
            TrajectoryStatuses(
                agent_task_run_status="agent_loop_failed",
                prompt_loop_status="invalid_model_output",
                attempt_status=None,
                public_status=None,
                hidden_status=None,
                grade_state="cannot_grade",
                task_success=False,
            ),
        ),
        (
            "agent-recoverable",
            TrajectoryStatuses(
                agent_task_run_status="scored",
                prompt_loop_status="completed",
                attempt_status="PASS",
                public_status="PASS",
                hidden_status="PASS",
                grade_state="scored_pass",
                task_success=True,
            ),
        ),
    ],
)
def test_agent_control_expectations_are_executable(
    policy_id: str,
    statuses: TrajectoryStatuses,
) -> None:
    config = load_eval_config(AGENT_CONTROL_CONFIG)
    trajectory = _trajectory(policy_id, statuses)

    check = _control_trajectory_check(config, trajectory)

    assert check is not None
    assert check.status == "PASS"


def test_control_check_rejects_an_unexpected_valid_outcome() -> None:
    config = load_eval_config(SCORER_CONTROL_CONFIG)
    trajectory = _trajectory(
        "oracle",
        TrajectoryStatuses(
            attempt_status="HIDDEN_TEST_FAIL",
            public_status="PASS",
            hidden_status="FAIL",
            grade_state="scored_fail",
            task_success=False,
        ),
    )

    check = _control_trajectory_check(config, trajectory)

    assert check is not None
    assert check.status == "FAIL"
    assert "expected=('PASS', 'PASS', 'PASS')" in check.detail


def test_replay_check_rejects_non_pass_suite_result(
    scorer_control_suite: Path,
) -> None:
    manifest = load_eval_suite_manifest(scorer_control_suite / "manifest.json")
    replay_run = manifest.replay_runs[0]
    mismatched_replay_run = EvalSuiteReplayRunManifestRecord.model_validate(
        {
            **replay_run.model_dump(mode="json"),
            "status": "MISMATCH",
            "matched_attempts": 0,
            "mismatched_attempts": 1,
        }
    )

    check = _replay_run_check(
        scorer_control_suite,
        manifest.policy_runs[0],
        mismatched_replay_run,
    )

    assert check.status == "FAIL"
    assert "differs from child result" in check.detail


def _trajectory(
    policy_id: str,
    statuses: TrajectoryStatuses,
) -> TrajectoryRecord:
    identity = TrajectoryIdentity(
        trajectory_id=f"trajectory-{policy_id}",
        eval_run_id=f"eval-run-{policy_id}",
        eval_attempt_id=f"eval-attempt-{policy_id}",
        task_id="toy_python_fix_001",
        policy_id=policy_id,
        attempt_index=0,
    )
    return TrajectoryRecord.model_construct(
        identity=identity,
        statuses=statuses,
    )
