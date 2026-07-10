from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from agentenv.controls.public_check_idempotency_schema import (
    PUBLIC_CHECK_IDEMPOTENCY_CALIBRATION_SCHEMA_VERSION,
    CompletedPublicCheckRun,
    FailedPublicCheckRun,
    PublicCheckIdempotencyCalibration,
    derive_non_idempotency_reasons,
    derive_public_check_idempotency_status,
)


def _artifact_ref(path: str) -> dict[str, str]:
    return {
        "path": path,
        "content_hash": f"xxh64:{path}",
    }


def _completed_run(
    run_index: int,
    *,
    workspace_before: str = "xxh64:workspace",
    workspace_after: str = "xxh64:workspace",
    result_hash: str = "xxh64:result",
) -> dict[str, Any]:
    return {
        "run_index": run_index,
        "status": "COMPLETED",
        "canonical_workspace_hash_before": workspace_before,
        "canonical_workspace_hash_after": workspace_after,
        "exit_code": 0,
        "stdout": _artifact_ref(f"public_checks/run_{run_index}/stdout.txt"),
        "stderr": _artifact_ref(f"public_checks/run_{run_index}/stderr.txt"),
        "normalized_result_hash": result_hash,
    }


def _failed_run(
    run_index: int,
    *,
    workspace_before: str = "xxh64:workspace",
    workspace_after: str = "xxh64:workspace",
) -> dict[str, Any]:
    return {
        "run_index": run_index,
        "status": "FAILURE",
        "failure_mode": "TIMEOUT",
        "canonical_workspace_hash_before": workspace_before,
        "canonical_workspace_hash_after": workspace_after,
        "error_class": "TimeoutExpired",
        "error_message": "Public check timed out.",
    }


def _calibration_payload(
    *,
    status: str = "IDEMPOTENT",
    runs: list[dict[str, Any]] | None = None,
    repeat_count: int | None = None,
    non_idempotency_reasons: list[str] | None = None,
) -> dict[str, Any]:
    effective_runs = (
        [_completed_run(0), _completed_run(1)] if runs is None else runs
    )
    return {
        "schema_version": PUBLIC_CHECK_IDEMPOTENCY_CALIBRATION_SCHEMA_VERSION,
        "task_id": "task_001",
        "task_manifest_hash": "xxh64:task-manifest",
        "public_check_index": 0,
        "command": "uv run pytest tests/test_public.py",
        "normalizer_version": "public_check_output_normalizer_v0",
        "normalizer_code_hash": "xxh64:normalizer-code",
        "repeat_count": (
            len(effective_runs) if repeat_count is None else repeat_count
        ),
        "status": status,
        "non_idempotency_reasons": (
            _expected_non_idempotency_reasons(effective_runs)
            if non_idempotency_reasons is None
            else non_idempotency_reasons
        ),
        "runs": effective_runs,
    }


def _expected_non_idempotency_reasons(
    runs: list[dict[str, Any]],
) -> list[str]:
    workspace_hashes = {
        str(workspace_hash)
        for run in runs
        for workspace_hash in (
            run["canonical_workspace_hash_before"],
            run["canonical_workspace_hash_after"],
        )
    }
    completed_result_hashes = {
        str(run["normalized_result_hash"])
        for run in runs
        if run["status"] == "COMPLETED"
    }
    reasons: list[str] = []
    if len(workspace_hashes) > 1:
        reasons.append("WORKSPACE_STATE_DRIFT")
    if len(completed_result_hashes) > 1:
        reasons.append("NORMALIZED_RESULT_DRIFT")
    return reasons


def test_idempotent_calibration_accepts_completed_stable_runs() -> None:
    calibration = PublicCheckIdempotencyCalibration.model_validate(
        _calibration_payload()
    )

    assert calibration.status == "IDEMPOTENT"
    assert calibration.idempotent is True
    assert calibration.task_id == "task_001"
    assert calibration.non_idempotency_reasons == []
    assert all(isinstance(run, CompletedPublicCheckRun) for run in calibration.runs)
    assert "idempotent" not in calibration.model_dump(mode="json")


def test_non_idempotent_calibration_accepts_workspace_drift() -> None:
    calibration = PublicCheckIdempotencyCalibration.model_validate(
        _calibration_payload(
            status="NON_IDEMPOTENT",
            runs=[
                _completed_run(0),
                _completed_run(1, workspace_after="xxh64:mutated-workspace"),
            ],
        )
    )

    assert calibration.idempotent is False
    assert calibration.non_idempotency_reasons == ["WORKSPACE_STATE_DRIFT"]


def test_non_idempotent_calibration_accepts_normalized_result_drift() -> None:
    calibration = PublicCheckIdempotencyCalibration.model_validate(
        _calibration_payload(
            status="NON_IDEMPOTENT",
            runs=[
                _completed_run(0),
                _completed_run(1, result_hash="xxh64:different-result"),
            ],
        )
    )

    assert calibration.idempotent is False
    assert calibration.non_idempotency_reasons == ["NORMALIZED_RESULT_DRIFT"]


def test_non_idempotent_calibration_preserves_both_drift_reasons() -> None:
    calibration = PublicCheckIdempotencyCalibration.model_validate(
        _calibration_payload(
            status="NON_IDEMPOTENT",
            runs=[
                _completed_run(0),
                _completed_run(
                    1,
                    workspace_after="xxh64:mutated-workspace",
                    result_hash="xxh64:different-result",
                ),
            ],
        )
    )

    assert calibration.non_idempotency_reasons == [
        "WORKSPACE_STATE_DRIFT",
        "NORMALIZED_RESULT_DRIFT",
    ]


def test_inconclusive_calibration_accepts_failure_without_observed_drift() -> None:
    calibration = PublicCheckIdempotencyCalibration.model_validate(
        _calibration_payload(
            status="INCONCLUSIVE",
            runs=[_completed_run(0), _failed_run(1)],
        )
    )

    assert calibration.idempotent is None
    assert calibration.non_idempotency_reasons == []
    assert isinstance(calibration.runs[1], FailedPublicCheckRun)
    failed_run = calibration.runs[1]
    assert isinstance(failed_run, FailedPublicCheckRun)
    assert failed_run.stdout is None
    assert failed_run.stderr is None


def test_observed_drift_takes_precedence_over_failure() -> None:
    calibration = PublicCheckIdempotencyCalibration.model_validate(
        _calibration_payload(
            status="NON_IDEMPOTENT",
            runs=[
                _completed_run(0),
                _failed_run(1, workspace_after="xxh64:mutated-workspace"),
            ],
        )
    )

    assert calibration.status == "NON_IDEMPOTENT"
    assert calibration.non_idempotency_reasons == ["WORKSPACE_STATE_DRIFT"]


@pytest.mark.parametrize(
    ("runs", "incorrect_status"),
    [
        ([_completed_run(0), _completed_run(1)], "INCONCLUSIVE"),
        (
            [
                _completed_run(0),
                _completed_run(1, result_hash="xxh64:different-result"),
            ],
            "IDEMPOTENT",
        ),
        ([_completed_run(0), _failed_run(1)], "IDEMPOTENT"),
    ],
)
def test_calibration_rejects_status_that_disagrees_with_evidence(
    runs: list[dict[str, Any]],
    incorrect_status: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="status must reflect workspace and result evidence",
    ):
        PublicCheckIdempotencyCalibration.model_validate(
            _calibration_payload(status=incorrect_status, runs=runs)
        )


@pytest.mark.parametrize(
    ("runs", "incorrect_reasons"),
    [
        (
            [_completed_run(0), _completed_run(1)],
            ["WORKSPACE_STATE_DRIFT"],
        ),
        (
            [
                _completed_run(0),
                _completed_run(1, workspace_after="xxh64:mutated-workspace"),
            ],
            [],
        ),
        (
            [
                _completed_run(0),
                _completed_run(
                    1,
                    workspace_after="xxh64:mutated-workspace",
                    result_hash="xxh64:different-result",
                ),
            ],
            ["NORMALIZED_RESULT_DRIFT"],
        ),
        (
            [
                _completed_run(0),
                _completed_run(1, workspace_after="xxh64:mutated-workspace"),
            ],
            ["WORKSPACE_STATE_DRIFT", "WORKSPACE_STATE_DRIFT"],
        ),
    ],
)
def test_calibration_rejects_reasons_that_disagree_with_evidence(
    runs: list[dict[str, Any]],
    incorrect_reasons: list[str],
) -> None:
    with pytest.raises(
        ValidationError,
        match="non_idempotency_reasons must exactly reflect observed drift",
    ):
        PublicCheckIdempotencyCalibration.model_validate(
            _calibration_payload(
                status=(
                    "NON_IDEMPOTENT"
                    if _expected_non_idempotency_reasons(runs)
                    else "IDEMPOTENT"
                ),
                runs=runs,
                non_idempotency_reasons=incorrect_reasons,
            )
        )


def test_calibration_rejects_repeat_count_mismatch() -> None:
    with pytest.raises(
        ValidationError,
        match="repeat_count must equal number of runs",
    ):
        PublicCheckIdempotencyCalibration.model_validate(
            _calibration_payload(repeat_count=3)
        )


@pytest.mark.parametrize(
    "run_indexes",
    [
        [1, 0],
        [0, 0],
        [0, 2],
    ],
)
def test_calibration_requires_ordered_gap_free_run_indexes(
    run_indexes: list[int],
) -> None:
    runs = [_completed_run(run_index) for run_index in run_indexes]

    with pytest.raises(ValidationError, match="runs must be ordered by run_index"):
        PublicCheckIdempotencyCalibration.model_validate(
            _calibration_payload(runs=runs)
        )


@pytest.mark.parametrize("repeat_count", [0, 1, True, "2"])
def test_calibration_requires_strict_repeat_count_of_at_least_two(
    repeat_count: object,
) -> None:
    payload = _calibration_payload()
    payload["repeat_count"] = repeat_count

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(payload)


def test_completed_run_requires_hash_pinned_stdout_and_stderr() -> None:
    payload = _calibration_payload()
    del payload["runs"][0]["stdout"]

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(payload)


def test_failed_run_allows_hash_pinned_partial_output() -> None:
    failed_run = _failed_run(1)
    failed_run["stdout"] = _artifact_ref("public_checks/run_1/stdout.txt")
    calibration = PublicCheckIdempotencyCalibration.model_validate(
        _calibration_payload(
            status="INCONCLUSIVE",
            runs=[_completed_run(0), failed_run],
        )
    )

    parsed_run = calibration.runs[1]
    assert isinstance(parsed_run, FailedPublicCheckRun)
    assert parsed_run.stdout is not None


@pytest.mark.parametrize(
    "invalid_ref",
    [
        {"path": "/tmp/stdout.txt", "content_hash": "xxh64:stdout"},
        {"path": "../stdout.txt", "content_hash": "xxh64:stdout"},
        {"path": "stdout.txt", "content_hash": ""},
        {"path": "stdout.txt"},
    ],
)
def test_output_artifact_refs_must_be_relative_and_hash_pinned(
    invalid_ref: dict[str, str],
) -> None:
    payload = _calibration_payload()
    payload["runs"][0]["stdout"] = invalid_ref

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(payload)


def test_completed_run_rejects_failure_only_fields() -> None:
    payload = _calibration_payload()
    payload["runs"][0]["failure_mode"] = "TIMEOUT"

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(payload)


def test_failed_run_rejects_completed_result_fields() -> None:
    failed_run = _failed_run(1)
    failed_run["exit_code"] = 1
    failed_run["normalized_result_hash"] = "xxh64:partial-result"

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(
            _calibration_payload(
                status="INCONCLUSIVE",
                runs=[_completed_run(0), failed_run],
            )
        )


@pytest.mark.parametrize("missing_field", ["failure_mode", "error_class", "error_message"])
def test_failed_run_requires_typed_error_details(missing_field: str) -> None:
    failed_run = _failed_run(1)
    del failed_run[missing_field]

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(
            _calibration_payload(
                status="INCONCLUSIVE",
                runs=[_completed_run(0), failed_run],
            )
        )


def test_calibration_rejects_serialized_idempotent_boolean() -> None:
    payload = _calibration_payload()
    payload["idempotent"] = True

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(payload)


def test_status_derivation_requires_at_least_two_runs() -> None:
    run = CompletedPublicCheckRun.model_validate(_completed_run(0))

    with pytest.raises(ValueError, match="requires at least two runs"):
        derive_public_check_idempotency_status([run])

    with pytest.raises(ValueError, match="requires at least two runs"):
        derive_non_idempotency_reasons([run])


@pytest.mark.parametrize("task_id", [None, ""])
def test_calibration_requires_non_empty_task_id(task_id: object) -> None:
    payload = _calibration_payload()
    if task_id is None:
        del payload["task_id"]
    else:
        payload["task_id"] = task_id

    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(payload)


def test_schema_rejects_unknown_fields_and_versions() -> None:
    extra_payload = _calibration_payload()
    extra_payload["unexpected_field"] = "unexpected"
    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(extra_payload)

    wrong_version_payload = deepcopy(_calibration_payload())
    wrong_version_payload["schema_version"] = "future_version"
    with pytest.raises(ValidationError):
        PublicCheckIdempotencyCalibration.model_validate(wrong_version_payload)
