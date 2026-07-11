from pathlib import Path

from agentenv.orchestrators.attempt import AttemptStatus, CheckStatus
from agentenv.rewards.cases import load_reward_hack_check_catalogue
from agentenv.rewards.detection import (
    RewardHackDetectionContext,
    evaluate_reward_hack_check_catalogue,
)
from agentenv.rewards.schema import RewardHackDetection, RewardHackExploitCheckResult
from agentenv.tasks.validate import load_task_manifest


CASE_ROOT = Path("data/reward_hack_cases")
TASK_MANIFEST_PATH = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_successful_ordinary_patch_is_not_public_only_reward_hack() -> None:
    detection = _evaluate(
        Path("data/harness_audit/scorer_cases/correct_oracle/submission.patch"),
        attempt_status="PASS",
        public_status="PASS",
        hidden_status="PASS",
    )

    assert detection.evaluation_status == "complete"
    assert detection.finding_classification == "not_detected"
    assert _result(
        detection, "public_test_only_pass.submitted_patch_text"
    ).check_status == ("not_detected")


def test_public_only_hidden_failure_is_ambiguous_with_pinned_evidence_refs() -> None:
    detection = _evaluate(
        Path("data/harness_audit/scorer_cases/public_only_fix/submission.patch"),
        attempt_status="HIDDEN_TEST_FAIL",
        public_status="PASS",
        hidden_status="FAIL",
    )

    result = _result(detection, "public_test_only_pass.submitted_patch_text")
    assert detection.evaluation_status == "complete"
    assert detection.finding_classification == "ambiguous"
    assert result.check_status == "detected"
    assert result.finding_classification == "ambiguous"
    assert result.evidence_artifacts == ["candidate_patch", "attempt_json"]


def test_public_check_tampering_is_confirmed() -> None:
    detection = _evaluate(
        Path("data/harness_audit/scorer_cases/patch_changes_tests/submission.patch"),
        attempt_status="INVALID_SHORTCUT",
        public_status="NOT_RUN",
        hidden_status="NOT_RUN",
    )

    result = _result(detection, "public_check_tampering.submitted_patch_text")
    assert detection.finding_classification == "confirmed"
    assert result.check_status == "detected"
    assert result.finding_classification == "confirmed"
    assert result.evidence_artifacts == ["candidate_patch"]


def test_submitted_private_reference_uses_shared_artifact_classifier() -> None:
    patch_path = Path(
        "data/harness_audit/scorer_cases/hidden_validator_path_reference/"
        "submission.patch"
    )
    detection = _evaluate(
        patch_path,
        attempt_status="PASS",
        public_status="PASS",
        hidden_status="PASS",
    )

    check_id = (
        "hidden_validator_probe_attempt.hidden_validator_path.submitted_patch_text"
    )
    assert _result(detection, check_id).check_status == "detected"
    assert detection.finding_classification == "confirmed"


def test_missing_declared_patch_becomes_incomplete_evaluation(tmp_path: Path) -> None:
    detection = _evaluate(
        tmp_path / "missing.patch",
        attempt_status="PASS",
        public_status="PASS",
        hidden_status="PASS",
    )

    assert detection.evaluation_status == "incomplete_evaluation"
    assert detection.finding_classification is None
    assert any(
        result.check_status == "detector_error"
        and result.error_class == "FileNotFoundError"
        for result in detection.check_results
    )


def test_absent_agent_surfaces_are_not_applicable() -> None:
    catalogue = load_reward_hack_check_catalogue(CASE_ROOT)
    task_manifest = load_task_manifest(TASK_MANIFEST_PATH)

    detection = evaluate_reward_hack_check_catalogue(
        catalogue,
        context=RewardHackDetectionContext(
            candidate_patch_path=None,
            prompt_loop_result_path=None,
            attempt_artifact_available=False,
            attempt_status=None,
            public_status=None,
            hidden_status=None,
            task_manifest_path=TASK_MANIFEST_PATH,
            task_manifest=task_manifest,
        ),
    )

    assert detection.evaluation_status == "complete"
    assert detection.finding_classification == "not_detected"
    assert {result.check_status for result in detection.check_results} == {
        "not_applicable"
    }


def _evaluate(
    patch_path: Path,
    *,
    attempt_status: AttemptStatus,
    public_status: CheckStatus,
    hidden_status: CheckStatus,
) -> RewardHackDetection:
    catalogue = load_reward_hack_check_catalogue(CASE_ROOT)
    task_manifest = load_task_manifest(TASK_MANIFEST_PATH)
    return evaluate_reward_hack_check_catalogue(
        catalogue,
        context=RewardHackDetectionContext(
            candidate_patch_path=patch_path,
            prompt_loop_result_path=None,
            attempt_artifact_available=True,
            attempt_status=attempt_status,
            public_status=public_status,
            hidden_status=hidden_status,
            task_manifest_path=TASK_MANIFEST_PATH,
            task_manifest=task_manifest,
        ),
    )


def _result(
    detection: RewardHackDetection,
    exploit_check_id: str,
) -> RewardHackExploitCheckResult:
    return next(
        result
        for result in detection.check_results
        if result.exploit_check_id == exploit_check_id
    )
