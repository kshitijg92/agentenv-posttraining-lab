from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentenv.artifacts.base import validate_relative_artifact_ref


PublicCheckIdempotencyCalibrationSchemaVersion = Literal[
    "public_check_idempotency_calibration_v0"
]
PublicCheckFailureMode = Literal["TIMEOUT", "RUNNER_FAILURE"]
PublicCheckIdempotencyStatus = Literal[
    "IDEMPOTENT",
    "NON_IDEMPOTENT",
    "INCONCLUSIVE",
]
NonIdempotencyReason = Literal[
    "WORKSPACE_STATE_DRIFT",
    "NORMALIZED_RESULT_DRIFT",
]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
AtLeastTwoInt = Annotated[int, Field(ge=2, strict=True)]

PUBLIC_CHECK_IDEMPOTENCY_CALIBRATION_SCHEMA_VERSION: (
    PublicCheckIdempotencyCalibrationSchemaVersion
) = "public_check_idempotency_calibration_v0"


class HashPinnedArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)


class _PublicCheckRunEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_index: NonNegativeInt
    canonical_workspace_hash_before: str = Field(min_length=1)
    canonical_workspace_hash_after: str = Field(min_length=1)


class CompletedPublicCheckRun(_PublicCheckRunEvidence):
    status: Literal["COMPLETED"]
    exit_code: int = Field(strict=True)
    stdout: HashPinnedArtifactRef
    stderr: HashPinnedArtifactRef
    normalized_result_hash: str = Field(min_length=1)


class FailedPublicCheckRun(_PublicCheckRunEvidence):
    status: Literal["FAILURE"]
    failure_mode: PublicCheckFailureMode
    stdout: HashPinnedArtifactRef | None = None
    stderr: HashPinnedArtifactRef | None = None
    error_class: str = Field(min_length=1)
    error_message: str = Field(min_length=1)


SinglePublicCheckRun: TypeAlias = Annotated[
    CompletedPublicCheckRun | FailedPublicCheckRun,
    Field(discriminator="status"),
]


class PublicCheckIdempotencyCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: PublicCheckIdempotencyCalibrationSchemaVersion
    task_id: str = Field(min_length=1)
    task_manifest_hash: str = Field(min_length=1)
    public_check_index: NonNegativeInt
    command: str = Field(min_length=1)
    normalizer_version: str = Field(min_length=1)
    normalizer_code_hash: str = Field(min_length=1)
    repeat_count: AtLeastTwoInt
    status: PublicCheckIdempotencyStatus
    non_idempotency_reasons: list[NonIdempotencyReason]
    runs: list[SinglePublicCheckRun] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_runs_and_status(self) -> "PublicCheckIdempotencyCalibration":
        if len(self.runs) != self.repeat_count:
            raise ValueError("repeat_count must equal number of runs")

        observed_indexes = [run.run_index for run in self.runs]
        expected_indexes = list(range(self.repeat_count))
        if observed_indexes != expected_indexes:
            raise ValueError(
                "runs must be ordered by run_index and cover every index from "
                "0 through repeat_count - 1"
            )

        expected_reasons = derive_non_idempotency_reasons(self.runs)
        if self.non_idempotency_reasons != expected_reasons:
            raise ValueError(
                "non_idempotency_reasons must exactly reflect observed drift"
            )

        expected_status = derive_public_check_idempotency_status(self.runs)
        if self.status != expected_status:
            raise ValueError("status must reflect workspace and result evidence")
        return self

    @property
    def idempotent(self) -> bool | None:
        if self.status == "IDEMPOTENT":
            return True
        if self.status == "NON_IDEMPOTENT":
            return False
        return None


def derive_public_check_idempotency_status(
    runs: list[SinglePublicCheckRun],
) -> PublicCheckIdempotencyStatus:
    if derive_non_idempotency_reasons(runs):
        return "NON_IDEMPOTENT"
    if any(isinstance(run, FailedPublicCheckRun) for run in runs):
        return "INCONCLUSIVE"
    return "IDEMPOTENT"


def derive_non_idempotency_reasons(
    runs: list[SinglePublicCheckRun],
) -> list[NonIdempotencyReason]:
    if len(runs) < 2:
        raise ValueError("idempotency status requires at least two runs")

    workspace_hashes = {
        workspace_hash
        for run in runs
        for workspace_hash in (
            run.canonical_workspace_hash_before,
            run.canonical_workspace_hash_after,
        )
    }
    completed_result_hashes = {
        run.normalized_result_hash
        for run in runs
        if isinstance(run, CompletedPublicCheckRun)
    }
    reasons: list[NonIdempotencyReason] = []
    if len(workspace_hashes) > 1:
        reasons.append("WORKSPACE_STATE_DRIFT")
    if len(completed_result_hashes) > 1:
        reasons.append("NORMALIZED_RESULT_DRIFT")
    return reasons
