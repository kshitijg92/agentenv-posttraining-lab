from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, TypeVar, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from agentenv.agents.schema import PromptLoopStatus
from agentenv.audits.schema import (
    AGENT_TASK_AUDIT_CASE_SCHEMA_VERSION,
    AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION,
    HARNESS_AUDIT_RUNTIME_VERSION,
    SCORER_AUDIT_CASE_SCHEMA_VERSION,
    SCORER_AUDIT_RECORD_SCHEMA_VERSION,
    AgentTaskAuditCaseSchemaVersion,
    AgentTaskAuditRecordSchemaVersion,
    ContentHash,
    HarnessAuditRuntimeVersion,
    HarnessAuditLayerSummary,
    HarnessAuditStatus,
    HarnessRuntimeProvenance,
    ScorerAuditCaseSchemaVersion,
    ScorerAuditRecordSchemaVersion,
    derive_harness_audit_status,
)
from agentenv.artifacts.base import (
    MANIFEST_FILENAME,
    ArtifactType,
    load_json_object,
    validate_relative_artifact_ref,
)
from agentenv.artifacts.payloads import (
    TASK_HASH_REPORT_SCHEMA_VERSION,
    ControlCalibrationResultRecord,
    ControlFlakeDetection,
    EvalTaskHashes,
    ReplayStatus,
    TaskHashReportSchemaVersion,
    validate_replay_status_counts,
)
from agentenv.evals.schema import (
    AGENT_CONTROL_LAYER,
    AGENT_CONTROL_SCRIPT_POLICY_TYPE,
    AGENT_MODEL_POLICY_TYPE,
    AGENT_POLICY_FAMILY,
    CONTROL_POLICY_FAMILY,
    SCORER_CONTROL_LAYER,
    SCORER_CONTROL_PATCH_POLICY_TYPE,
    ControlLayer,
    PolicyFamily,
    PolicyType,
)
from agentenv.orchestrators.agent_task_schema import AgentTaskRunStatus
from agentenv.orchestrators.attempt import (
    AttemptStatus,
    CheckStatus,
    validate_attempt_status_fields,
)
from agentenv.tasks.schema import TaskSplit
from agentenv.training.schema import (
    POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION,
    TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION,
    PositiveSFTExampleRecordSchemaVersion,
    TrainingCandidateRecordSchemaVersion,
)
from agentenv.training.repair_schema import (
    TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION,
    TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION,
    TrainingCandidateRepairReviewRecordSchemaVersion,
    TrainingCandidateRepairRecordSchemaVersion,
)
from agentenv.trajectories.schema import (
    TRAJECTORY_RECORD_SCHEMA_VERSION,
    TRAJECTORY_REVIEW_SCHEMA_VERSION,
    TrajectoryRecordSchemaVersion,
    TrajectoryReviewSchemaVersion,
)

NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
LayerCounts = dict[str, dict[str, NonNegativeInt]]
ManifestModel = TypeVar("ManifestModel", bound=BaseModel)

SCORER_ATTEMPT_ARTIFACT_REFS = {
    "attempt": "attempt.json",
    "stdout": "stdout.txt",
    "stderr": "stderr.txt",
    "error": "error.txt",
    "trace": "trace.jsonl",
    "final_diff": "final.diff",
}
AGENT_ATTEMPT_ARTIFACT_REFS = {
    "agent_task_run": "agent_task_run.json",
    "error": "error.txt",
    "decoding_config": "decoding_config.json",
    "model_config": "model_config.json",
    "agent_control_script": "agent_control_script.json",
    "agent_task_view": "agent_task_view.json",
    "prompt_loop_result": "prompt_loop_result.json",
    "candidate_patch": "candidate.patch",
    "attempt": "attempt",
}
SCORER_ATTEMPT_REQUIRED_ARTIFACTS = frozenset(SCORER_ATTEMPT_ARTIFACT_REFS)
AGENT_ATTEMPT_REQUIRED_ARTIFACTS = frozenset(
    {"agent_task_run", "error", "decoding_config"}
)
AGENT_ATTEMPT_PROMPT_LOOP_REQUIRED_ARTIFACTS = frozenset(
    {"agent_task_view", "prompt_loop_result"}
)
EVAL_RUN_ARTIFACT_REFS = {
    "trace": "trace.jsonl",
    "attempts": "attempts",
}
EVAL_SUITE_ARTIFACT_REFS = {
    "policies": "policies",
    "replays": "replays",
}
CONTROL_CALIBRATION_ARTIFACT_REFS = {
    "agent_control_scripts": "agent_control_scripts",
    "scorer_control_patches": "scorer_control_patches",
    "report": "control_report.md",
    "results": "control_results.jsonl",
    "public_check_idempotency": "public_check_idempotency",
}
REPLAY_RUN_ARTIFACT_REFS = {
    "replay_result": "replay_result.json",
    "replay_results": "replay_results.jsonl",
    "trace": "trace.jsonl",
    "attempts": "attempts",
    "agent_task_run": "agent_task_run",
}
TRAJECTORY_EXPORT_ARTIFACT_REFS = {
    "trajectories": "trajectories.jsonl",
}
TRAJECTORY_REVIEW_ARTIFACT_REFS = {
    "reviews": "reviews.jsonl",
    "review_queue": "review_queue.md",
}
TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS = {
    "training_candidates": "training_candidates.jsonl",
}
TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS = {
    "repair_records": "repair_records.jsonl",
}
TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS = {
    "reviews": "reviews.jsonl",
    "review_queue": "review_queue.md",
}
POSITIVE_SFT_EXPORT_ARTIFACT_REFS = {
    "positive_sft_examples": "positive_sft_examples.jsonl",
}
REWARD_HACK_AUDIT_ARTIFACT_REFS = {
    "results": "reward_hack_audit_results.jsonl",
    "case_runs": "case_runs",
}
SCORER_AUDIT_ARTIFACT_REFS = {
    "results": "results.jsonl",
    "case_artifacts": "cases",
}
AGENT_TASK_AUDIT_ARTIFACT_REFS = {
    "results": "results.jsonl",
    "case_artifacts": "cases",
}
HARNESS_AUDIT_ARTIFACT_REFS = {
    "agent_audit": "agent",
    "scorer_audit": "scorer",
    "report": "harness_audit.md",
}
EVAL_RUN_REQUIRED_ARTIFACTS = frozenset(EVAL_RUN_ARTIFACT_REFS)
EVAL_SUITE_REQUIRED_ARTIFACTS = frozenset({"policies"})
CONTROL_CALIBRATION_REQUIRED_ARTIFACTS = frozenset(CONTROL_CALIBRATION_ARTIFACT_REFS)
REPLAY_RUN_BASE_REQUIRED_ARTIFACTS = frozenset(
    {"replay_result", "replay_results", "trace"}
)
TRAJECTORY_EXPORT_REQUIRED_ARTIFACTS = frozenset(TRAJECTORY_EXPORT_ARTIFACT_REFS)
TRAJECTORY_REVIEW_REQUIRED_ARTIFACTS = frozenset(TRAJECTORY_REVIEW_ARTIFACT_REFS)
TRAINING_CANDIDATE_EXPORT_REQUIRED_ARTIFACTS = frozenset(
    TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS
)
TRAINING_CANDIDATE_REPAIR_EXPORT_REQUIRED_ARTIFACTS = frozenset(
    TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS
)
TRAINING_CANDIDATE_REPAIR_REVIEW_REQUIRED_ARTIFACTS = frozenset(
    TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS
)
POSITIVE_SFT_EXPORT_REQUIRED_ARTIFACTS = frozenset(POSITIVE_SFT_EXPORT_ARTIFACT_REFS)
REWARD_HACK_AUDIT_REQUIRED_ARTIFACTS = frozenset(REWARD_HACK_AUDIT_ARTIFACT_REFS)
SCORER_AUDIT_REQUIRED_ARTIFACTS = frozenset(SCORER_AUDIT_ARTIFACT_REFS)
AGENT_TASK_AUDIT_REQUIRED_ARTIFACTS = frozenset(AGENT_TASK_AUDIT_ARTIFACT_REFS)
HARNESS_AUDIT_REQUIRED_ARTIFACTS = frozenset(HARNESS_AUDIT_ARTIFACT_REFS)


ScorerAttemptArtifactSchemaVersion = Literal["scorer_attempt_artifact_v0"]
AgentAttemptArtifactSchemaVersion = Literal["agent_attempt_artifact_v0"]
EvalRunArtifactSchemaVersion = Literal["eval_run_artifact_v0"]
EvalSuiteArtifactSchemaVersion = Literal["eval_suite_artifact_v0"]
ControlCalibrationArtifactSchemaVersion = Literal["control_calibration_artifact_v3"]
ReplayRunArtifactSchemaVersion = Literal["replay_run_artifact_v0"]
TrajectoryExportArtifactSchemaVersion = Literal["trajectory_export_artifact_v0"]
TrajectoryReviewArtifactSchemaVersion = Literal["trajectory_review_artifact_v0"]
TrainingCandidateExportArtifactSchemaVersion = Literal[
    "training_candidate_export_artifact_v1"
]
TrainingCandidateRepairExportArtifactSchemaVersion = Literal[
    "training_candidate_repair_export_artifact_v0"
]
TrainingCandidateRepairReviewArtifactSchemaVersion = Literal[
    "training_candidate_repair_review_artifact_v0"
]
PositiveSFTExportArtifactSchemaVersion = Literal["positive_sft_export_artifact_v0"]
RewardHackAuditArtifactSchemaVersion = Literal["reward_hack_audit_artifact_v2"]
ScorerAuditArtifactSchemaVersion = Literal["scorer_audit_artifact_v0"]
AgentTaskAuditArtifactSchemaVersion = Literal["agent_task_audit_artifact_v0"]
HarnessAuditArtifactSchemaVersion = Literal["harness_audit_artifact_v0"]
TrajectoryExportSourceArtifactType = Literal["eval_run", "eval_suite"]
TrajectoryReviewSourceArtifactType = Literal["trajectory_export"]

SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION: ScorerAttemptArtifactSchemaVersion = (
    "scorer_attempt_artifact_v0"
)
AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION: AgentAttemptArtifactSchemaVersion = (
    "agent_attempt_artifact_v0"
)
EVAL_RUN_ARTIFACT_SCHEMA_VERSION: EvalRunArtifactSchemaVersion = "eval_run_artifact_v0"
EVAL_SUITE_ARTIFACT_SCHEMA_VERSION: EvalSuiteArtifactSchemaVersion = (
    "eval_suite_artifact_v0"
)
CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION: ControlCalibrationArtifactSchemaVersion = (
    "control_calibration_artifact_v3"
)
REPLAY_RUN_ARTIFACT_SCHEMA_VERSION: ReplayRunArtifactSchemaVersion = (
    "replay_run_artifact_v0"
)
TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION: TrajectoryExportArtifactSchemaVersion = (
    "trajectory_export_artifact_v0"
)
TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION: TrajectoryReviewArtifactSchemaVersion = (
    "trajectory_review_artifact_v0"
)
TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION: TrainingCandidateExportArtifactSchemaVersion = "training_candidate_export_artifact_v1"
TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION: TrainingCandidateRepairExportArtifactSchemaVersion = "training_candidate_repair_export_artifact_v0"
TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_SCHEMA_VERSION: TrainingCandidateRepairReviewArtifactSchemaVersion = "training_candidate_repair_review_artifact_v0"
POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION: PositiveSFTExportArtifactSchemaVersion = (
    "positive_sft_export_artifact_v0"
)
REWARD_HACK_AUDIT_ARTIFACT_SCHEMA_VERSION: RewardHackAuditArtifactSchemaVersion = (
    "reward_hack_audit_artifact_v2"
)
SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION: ScorerAuditArtifactSchemaVersion = (
    "scorer_audit_artifact_v0"
)
AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION: AgentTaskAuditArtifactSchemaVersion = (
    "agent_task_audit_artifact_v0"
)
HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION: HarnessAuditArtifactSchemaVersion = (
    "harness_audit_artifact_v0"
)


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_artifact_type: ClassVar[str | None] = None
    expected_artifact_schema_version: ClassVar[str | None] = None

    artifact_type: str = Field(min_length=1)
    artifact_schema_version: str = Field(min_length=1)

    @staticmethod
    def validate_artifacts_map(artifacts: dict[str, str]) -> None:
        for artifact_name, artifact_ref in artifacts.items():
            if not artifact_name:
                raise ValueError("artifact names must be non-empty")
            validate_relative_artifact_ref(artifact_ref)

    @model_validator(mode="after")
    def validate_artifact_identity(self) -> "ArtifactManifest":
        if (
            self.expected_artifact_type is not None
            and self.artifact_type != self.expected_artifact_type
        ):
            raise ValueError(f"artifact_type must be {self.expected_artifact_type!r}")
        if (
            self.expected_artifact_schema_version is not None
            and self.artifact_schema_version != self.expected_artifact_schema_version
        ):
            raise ValueError(
                "artifact_schema_version must be "
                f"{self.expected_artifact_schema_version!r}"
            )
        return self


class ScorerAttemptManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.SCORER_ATTEMPT.value
    expected_artifact_schema_version = SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION

    orchestrator_version: str = Field(min_length=1)
    scorer_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    submission_path: str = Field(min_length=1)
    status: AttemptStatus
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_artifact_refs(self) -> "ScorerAttemptManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=SCORER_ATTEMPT_ARTIFACT_REFS,
            owner="scorer attempt manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=SCORER_ATTEMPT_REQUIRED_ARTIFACTS,
            owner="scorer attempt manifests",
        )
        return self


class AgentTaskRunManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.AGENT_ATTEMPT.value
    expected_artifact_schema_version = AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION

    orchestrator_version: str = Field(min_length=1)
    agent_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus | None
    attempt_status: AttemptStatus | None
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_agent_terminal_state(self) -> "AgentTaskRunManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=AGENT_ATTEMPT_ARTIFACT_REFS,
            owner="agent task run manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=AGENT_ATTEMPT_REQUIRED_ARTIFACTS,
            owner="agent task run manifests",
        )
        if self.prompt_loop_status is not None:
            _require_artifacts(
                self.artifacts,
                required_artifacts=AGENT_ATTEMPT_PROMPT_LOOP_REQUIRED_ARTIFACTS,
                owner="agent task run manifests with prompt loop results",
            )
        if self.status == "scored":
            if self.prompt_loop_status != "completed":
                raise ValueError("scored agent attempts require completed prompt loop")
            if self.attempt_status is None:
                raise ValueError("scored agent attempts require attempt_status")
            if "prompt_loop_result" not in self.artifacts:
                raise ValueError(
                    "scored agent attempts require prompt_loop_result artifact ref"
                )
            if "attempt" not in self.artifacts:
                raise ValueError("scored agent attempts require attempt artifact ref")
            if "candidate_patch" not in self.artifacts:
                raise ValueError(
                    "scored agent attempts require candidate_patch artifact ref"
                )
            return self

        if self.attempt_status is not None:
            raise ValueError("unscored agent attempts cannot include attempt_status")
        if self.status == "agent_loop_failed":
            if self.prompt_loop_status is None:
                raise ValueError("agent loop failures require prompt_loop_status")
            if self.prompt_loop_status == "completed":
                raise ValueError(
                    "agent loop failures cannot have completed prompt loop"
                )
            if "prompt_loop_result" not in self.artifacts:
                raise ValueError(
                    "agent loop failures require prompt_loop_result artifact ref"
                )
        return self


class EvalRunScorerAttemptSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer_attempt_id: str = Field(min_length=1)
    status: AttemptStatus
    public_status: CheckStatus
    hidden_status: CheckStatus
    error_class: str | None
    final_diff_hash: str | None
    duration_ms: NonNegativeInt

    @model_validator(mode="after")
    def validate_scorer_terminal_state(self) -> "EvalRunScorerAttemptSummary":
        validate_attempt_status_fields(
            self.status,
            public_status=self.public_status,
            hidden_status=self.hidden_status,
            error_class=self.error_class,
        )
        if self.status == "PASS" and self.final_diff_hash is None:
            raise ValueError("PASS scorer summaries require final_diff_hash")
        return self


class EvalRunAgentAttemptSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_attempt_id: str = Field(min_length=1)
    status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus | None
    error_class: str | None
    candidate_patch_hash: str | None
    duration_ms: NonNegativeInt
    scorer_attempt: EvalRunScorerAttemptSummary | None

    @model_validator(mode="after")
    def validate_agent_terminal_state(self) -> "EvalRunAgentAttemptSummary":
        if self.status == "scored":
            if self.prompt_loop_status != "completed":
                raise ValueError("scored agent attempts require completed prompt loop")
            if self.scorer_attempt is None:
                raise ValueError("scored agent attempts require scorer_attempt")
            if self.error_class is not None:
                raise ValueError("scored agent attempts cannot include error_class")
            if self.candidate_patch_hash is None:
                raise ValueError("scored agent attempts require candidate_patch_hash")
            return self

        if self.scorer_attempt is not None:
            raise ValueError("unscored agent attempts cannot include scorer_attempt")
        if self.error_class is None:
            raise ValueError("unscored agent attempts require error_class")
        if self.status == "agent_loop_failed":
            if self.prompt_loop_status is None:
                raise ValueError("agent loop failures require prompt_loop_status")
            if self.prompt_loop_status == "completed":
                raise ValueError(
                    "agent loop failures cannot have completed prompt loop"
                )
        return self


class EvalRunAttemptManifestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    attempt_index: NonNegativeInt
    artifact_dir: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    artifact_schema_version: str = Field(min_length=1)
    scorer: EvalRunScorerAttemptSummary | None
    agent: EvalRunAgentAttemptSummary | None

    @field_validator("artifact_dir")
    @classmethod
    def validate_artifact_dir(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @model_validator(mode="after")
    def validate_child_attempt_identity(self) -> "EvalRunAttemptManifestRecord":
        expected_schema_versions = {
            ArtifactType.SCORER_ATTEMPT.value: SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
            ArtifactType.AGENT_ATTEMPT.value: AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        }
        expected_schema_version = expected_schema_versions.get(self.artifact_type)
        if expected_schema_version is None:
            raise ValueError("eval attempts must reference scorer or agent attempts")
        if self.artifact_schema_version != expected_schema_version:
            raise ValueError(
                "eval attempt artifact_schema_version does not match artifact_type"
            )
        if self.artifact_type == ArtifactType.SCORER_ATTEMPT.value:
            if self.scorer is None or self.agent is not None:
                raise ValueError("scorer attempts require scorer summary only")
        if self.artifact_type == ArtifactType.AGENT_ATTEMPT.value:
            if self.agent is None or self.scorer is not None:
                raise ValueError("agent attempts require agent summary only")
        return self


class PolicyMetadataFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_type: PolicyType
    policy_family: PolicyFamily
    control_layer: ControlLayer | None
    control_name: str | None = Field(default=None, min_length=1)
    model_config_ref: str | None = Field(
        default=None,
        alias="model_config",
        min_length=1,
    )
    decoding_config_ref: str | None = Field(
        default=None,
        alias="decoding_config",
        min_length=1,
    )
    attempts_per_task: PositiveInt
    replay_repeats: NonNegativeInt

    @model_validator(mode="after")
    def validate_policy_metadata(self) -> "PolicyMetadataFields":
        if self.policy_type == SCORER_CONTROL_PATCH_POLICY_TYPE:
            _require_control_policy(
                self,
                policy_family=CONTROL_POLICY_FAMILY,
                control_layer=SCORER_CONTROL_LAYER,
            )
        elif self.policy_type == AGENT_CONTROL_SCRIPT_POLICY_TYPE:
            _require_control_policy(
                self,
                policy_family=CONTROL_POLICY_FAMILY,
                control_layer=AGENT_CONTROL_LAYER,
            )
        elif self.policy_type == AGENT_MODEL_POLICY_TYPE:
            if self.policy_family != AGENT_POLICY_FAMILY:
                raise ValueError(
                    f"{AGENT_MODEL_POLICY_TYPE} policy_family must be "
                    f"{AGENT_POLICY_FAMILY!r}"
                )
            if self.control_layer is not None or self.control_name is not None:
                raise ValueError(
                    f"{AGENT_MODEL_POLICY_TYPE} policies cannot include "
                    "control metadata"
                )
            if self.model_config_ref is None or self.decoding_config_ref is None:
                raise ValueError(
                    f"{AGENT_MODEL_POLICY_TYPE} policies require model_config "
                    "and decoding_config"
                )
        else:
            raise AssertionError(f"Unhandled eval policy type: {self.policy_type}")
        return self


class EvalRunManifest(ArtifactManifest, PolicyMetadataFields):
    expected_artifact_type = ArtifactType.EVAL_RUN.value
    expected_artifact_schema_version = EVAL_RUN_ARTIFACT_SCHEMA_VERSION

    eval_run_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    config_path: str = Field(min_length=1)
    config_hash: str = Field(min_length=1)
    config_name: str = Field(min_length=1)
    task_pack: str = Field(min_length=1)
    split: TaskSplit
    task_hashes: EvalTaskHashes
    policy: str = Field(min_length=1)
    attempt_count: NonNegativeInt
    layer_counts: LayerCounts
    artifacts: dict[str, str]
    attempts: list[EvalRunAttemptManifestRecord]

    @model_validator(mode="after")
    def validate_attempts(self) -> "EvalRunManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=EVAL_RUN_ARTIFACT_REFS,
            owner="eval run manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=EVAL_RUN_REQUIRED_ARTIFACTS,
            owner="eval run manifests",
        )
        _validate_unique_eval_attempt_ids(self.attempts)
        _validate_unique_eval_attempt_artifact_dirs(self.attempts)
        if self.attempt_count != len(self.attempts):
            raise ValueError("attempt_count must equal number of attempts")
        _validate_attempt_artifact_type_for_policy(self.policy_type, self.attempts)
        _validate_selected_task_splits(self.split, self.task_hashes)
        selected_task_ids = _selected_task_ids(self.task_hashes)
        unknown_task_ids = sorted(
            {
                attempt.task_id
                for attempt in self.attempts
                if attempt.task_id not in selected_task_ids
            }
        )
        if unknown_task_ids:
            raise ValueError(
                "eval attempts reference task ids outside selected task hashes: "
                + ", ".join(unknown_task_ids)
            )
        _validate_eval_attempt_coverage(
            self.attempts,
            selected_task_ids=selected_task_ids,
            attempts_per_task=self.attempts_per_task,
        )
        if self.layer_counts != _count_eval_attempt_layers(self.attempts):
            raise ValueError("layer_counts must reflect eval attempts")
        return self


class EvalSuitePolicyRunManifestRecord(PolicyMetadataFields):
    policy: str = Field(min_length=1)
    eval_run_id: str = Field(min_length=1)
    artifact_dir: str = Field(min_length=1)
    manifest: str = Field(min_length=1)
    attempt_count: NonNegativeInt
    layer_counts: LayerCounts

    @field_validator("artifact_dir", "manifest")
    @classmethod
    def validate_artifact_refs(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @model_validator(mode="after")
    def validate_manifest_ref(self) -> "EvalSuitePolicyRunManifestRecord":
        _validate_ref_under_artifact_dir(
            self.artifact_dir,
            self.manifest,
            field_name="manifest",
        )
        return self


class EvalSuiteReplayRunManifestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: str = Field(min_length=1)
    replay_index: NonNegativeInt
    replay_run_id: str = Field(min_length=1)
    status: ReplayStatus
    artifact_dir: str = Field(min_length=1)
    manifest: str = Field(min_length=1)
    replay_result: str = Field(min_length=1)
    attempt_count: NonNegativeInt
    matched_attempts: NonNegativeInt
    mismatched_attempts: NonNegativeInt
    error_count: NonNegativeInt

    @field_validator("artifact_dir", "manifest", "replay_result")
    @classmethod
    def validate_artifact_refs(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @model_validator(mode="after")
    def validate_attempt_counts(self) -> "EvalSuiteReplayRunManifestRecord":
        _validate_ref_under_artifact_dir(
            self.artifact_dir,
            self.manifest,
            field_name="manifest",
        )
        _validate_ref_under_artifact_dir(
            self.artifact_dir,
            self.replay_result,
            field_name="replay_result",
        )
        if self.matched_attempts + self.mismatched_attempts != self.attempt_count:
            raise ValueError(
                "matched_attempts + mismatched_attempts must equal attempt_count"
            )
        validate_replay_status_counts(
            self.status,
            attempt_count=self.attempt_count,
            mismatched_attempts=self.mismatched_attempts,
            error_count=self.error_count,
        )
        return self


class EvalSuiteManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.EVAL_SUITE.value
    expected_artifact_schema_version = EVAL_SUITE_ARTIFACT_SCHEMA_VERSION

    eval_suite_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    config_path: str = Field(min_length=1)
    config_hash: str = Field(min_length=1)
    config_name: str = Field(min_length=1)
    task_pack: str = Field(min_length=1)
    split: TaskSplit
    task_hashes: EvalTaskHashes
    tasks: list[str] = Field(min_length=1)
    task_count: NonNegativeInt
    policy_count: PositiveInt
    attempt_count: NonNegativeInt
    layer_counts: LayerCounts
    artifacts: dict[str, str]
    policy_runs: list[EvalSuitePolicyRunManifestRecord] = Field(min_length=1)
    replay_run_count: NonNegativeInt
    replay_policy_count: NonNegativeInt
    replay_run_success_summary: str = Field(min_length=1)
    replay_runs: list[EvalSuiteReplayRunManifestRecord]

    @model_validator(mode="after")
    def validate_suite_counts(self) -> "EvalSuiteManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=EVAL_SUITE_ARTIFACT_REFS,
            owner="eval suite manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=EVAL_SUITE_REQUIRED_ARTIFACTS,
            owner="eval suite manifests",
        )
        if self.task_count != len(self.tasks):
            raise ValueError("task_count must equal number of tasks")
        _validate_selected_task_splits(self.split, self.task_hashes)
        selected_task_ids = [task.task_id for task in self.task_hashes.selected_tasks]
        if self.tasks != selected_task_ids:
            raise ValueError("tasks must match selected task hash order")
        if self.policy_count != len(self.policy_runs):
            raise ValueError("policy_count must equal number of policy runs")
        if self.replay_run_count != len(self.replay_runs):
            raise ValueError("replay_run_count must equal number of replay runs")
        if self.replay_run_count > 0 and "replays" not in self.artifacts:
            raise ValueError("eval suite manifests require replays artifact ref")
        if self.replay_run_count == 0 and "replays" in self.artifacts:
            raise ValueError("eval suite manifests cannot include unused replays ref")
        _validate_policy_attempt_counts(
            self.policy_runs,
            task_count=self.task_count,
        )
        _validate_policy_layer_counts(self.policy_runs)
        _validate_eval_suite_policy_refs(self.policy_runs)
        _validate_eval_suite_replay_refs(self.replay_runs)
        _validate_replay_coverage(self.policy_runs, self.replay_runs)
        replay_policy_count = len(
            {replay_run.policy for replay_run in self.replay_runs}
        )
        if self.replay_policy_count != replay_policy_count:
            raise ValueError("replay_policy_count must equal replay run policy count")
        passed_replay_runs = sum(
            1 for replay_run in self.replay_runs if replay_run.status == "PASS"
        )
        expected_replay_summary = f"{passed_replay_runs}/{len(self.replay_runs)}"
        if self.replay_run_success_summary != expected_replay_summary:
            raise ValueError("replay_run_success_summary must reflect replay runs")
        attempt_count = sum(policy_run.attempt_count for policy_run in self.policy_runs)
        if self.attempt_count != attempt_count:
            raise ValueError("attempt_count must equal policy attempt counts")
        if self.layer_counts != _count_eval_suite_layers(self.policy_runs):
            raise ValueError("layer_counts must reflect policy runs")
        return self


ControlCalibrationManifestRecord = ControlCalibrationResultRecord


class ControlCalibrationManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.CONTROL_CALIBRATION.value
    expected_artifact_schema_version = CONTROL_CALIBRATION_ARTIFACT_SCHEMA_VERSION

    control_run_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    task_pack_path: str = Field(min_length=1)
    runtime_provenance: HarnessRuntimeProvenance
    task_hashes: EvalTaskHashes
    repeats: PositiveInt
    record_count: NonNegativeInt
    overall_match: bool
    flake_detection: ControlFlakeDetection
    artifacts: dict[str, str]
    records: list[ControlCalibrationManifestRecord]

    @model_validator(mode="after")
    def validate_record_count(self) -> "ControlCalibrationManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=CONTROL_CALIBRATION_ARTIFACT_REFS,
            owner="control calibration manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=CONTROL_CALIBRATION_REQUIRED_ARTIFACTS,
            owner="control calibration manifests",
        )
        if self.record_count != len(self.records):
            raise ValueError("record_count must equal number of records")
        if not self.records:
            raise ValueError("control calibration manifests require records")
        if self.flake_detection.repeats != self.repeats:
            raise ValueError("flake_detection repeats must match control repeats")
        selected_task_hashes = {
            task.task_id: task for task in self.task_hashes.selected_tasks
        }
        selected_task_ids = set(selected_task_hashes)
        record_task_ids = {record.task_id for record in self.records}
        if record_task_ids != selected_task_ids:
            raise ValueError(
                "control record task ids must match the calibrated task hash set"
            )
        record_identities = [
            (
                record.control_layer,
                record.task_id,
                record.control_name,
                record.repeat_index,
            )
            for record in self.records
        ]
        if len(record_identities) != len(set(record_identities)):
            raise ValueError("control calibration record identities must be unique")
        expected_repeat_indexes = set(range(self.repeats))
        for layer_name, groups in (
            ("scorer", self.flake_detection.groups.scorer),
            ("agent", self.flake_detection.groups.agent),
        ):
            group_task_ids = {group.task_id for group in groups}
            if group_task_ids != selected_task_ids:
                raise ValueError(
                    f"{layer_name} flake-group task ids must match the calibrated "
                    "task hash set"
                )
            record_group_identities = {
                (record.task_id, record.control_name)
                for record in self.records
                if record.control_layer == layer_name
            }
            flake_group_identities = {
                (group.task_id, group.control_name) for group in groups
            }
            if flake_group_identities != record_group_identities:
                raise ValueError(
                    f"{layer_name} flake groups must exactly match control record "
                    "groups"
                )
            for task_id, control_name in sorted(record_group_identities):
                repeat_indexes = {
                    record.repeat_index
                    for record in self.records
                    if record.control_layer == layer_name
                    and record.task_id == task_id
                    and record.control_name == control_name
                }
                if repeat_indexes != expected_repeat_indexes:
                    raise ValueError(
                        "control record groups must cover every declared repeat "
                        f"index: {(layer_name, task_id, control_name)!r}"
                    )
        for calibration in self.flake_detection.public_check_idempotency:
            task_hash = selected_task_hashes.get(calibration.task_id)
            if task_hash is None:
                raise ValueError(
                    "public-check idempotency task ids must be in the calibrated "
                    "task hash set"
                )
            if calibration.task_manifest_hash != task_hash.task_yaml_hash:
                raise ValueError(
                    "public-check idempotency task manifest hash must match the "
                    "calibrated task hash"
                )
        for record in self.records:
            if record.control_run_id != self.control_run_id:
                raise ValueError("control records must match control_run_id")
            if record.repeat_index >= self.repeats:
                raise ValueError(
                    "control record repeat_index must be less than repeats"
                )
        expected_overall_match = all(record.match for record in self.records) and (
            self.flake_detection.status == "stable"
        )
        if self.overall_match != expected_overall_match:
            raise ValueError("overall_match must reflect records and flake detection")
        return self


class ReplayRunManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.REPLAY_RUN.value
    expected_artifact_schema_version = REPLAY_RUN_ARTIFACT_SCHEMA_VERSION

    replay_run_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    source_run_dir: str = Field(min_length=1)
    source_eval_run_id: str | None = Field(default=None, min_length=1)
    source_agent_attempt_id: str | None = Field(default=None, min_length=1)
    source_artifact_type: str | None = Field(default=None, min_length=1)
    source_artifact_schema_version: str | None = Field(default=None, min_length=1)
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_source_identity(self) -> "ReplayRunManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=REPLAY_RUN_ARTIFACT_REFS,
            owner="replay run manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=REPLAY_RUN_BASE_REQUIRED_ARTIFACTS,
            owner="replay run manifests",
        )
        if self.source_artifact_type is None:
            if (
                self.source_artifact_schema_version is not None
                or self.source_eval_run_id is not None
                or self.source_agent_attempt_id is not None
            ):
                raise ValueError("source identity fields require source_artifact_type")
            if "attempts" in self.artifacts or "agent_task_run" in self.artifacts:
                raise ValueError(
                    "source-less replay manifests cannot include source refs"
                )
            return self

        expected_schema_versions = {
            ArtifactType.EVAL_RUN.value: EVAL_RUN_ARTIFACT_SCHEMA_VERSION,
            ArtifactType.AGENT_ATTEMPT.value: AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION,
        }
        expected_schema_version = expected_schema_versions.get(
            self.source_artifact_type
        )
        if expected_schema_version is None:
            raise ValueError("unsupported replay source_artifact_type")
        if self.source_artifact_schema_version != expected_schema_version:
            raise ValueError(
                "source_artifact_schema_version does not match source_artifact_type"
            )
        if self.source_artifact_type == ArtifactType.EVAL_RUN.value:
            if self.source_eval_run_id is None:
                raise ValueError("eval run replay sources require source_eval_run_id")
            if self.source_agent_attempt_id is not None:
                raise ValueError(
                    "eval run replay sources cannot include source_agent_attempt_id"
                )
            if "attempts" not in self.artifacts:
                raise ValueError(
                    "eval run replay manifests require attempts artifact ref"
                )
            if "agent_task_run" in self.artifacts:
                raise ValueError(
                    "eval run replay manifests cannot include agent_task_run ref"
                )
        if self.source_artifact_type == ArtifactType.AGENT_ATTEMPT.value:
            if self.source_agent_attempt_id is None:
                raise ValueError(
                    "agent attempt replay sources require source_agent_attempt_id"
                )
            if self.source_eval_run_id is not None:
                raise ValueError(
                    "agent attempt replay sources cannot include source_eval_run_id"
                )
            if "attempts" in self.artifacts:
                raise ValueError(
                    "agent attempt replay manifests cannot include attempts ref"
                )
        return self


class TrajectoryExportManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.TRAJECTORY_EXPORT.value
    expected_artifact_schema_version = TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION

    created_at: str = Field(min_length=1)
    source_artifact_type: TrajectoryExportSourceArtifactType
    source_artifact_schema_version: str = Field(min_length=1)
    source_artifact_dir: str = Field(min_length=1)
    source_manifest_path: str = Field(min_length=1)
    source_manifest_hash: str = Field(min_length=1)
    source_eval_run_id: str | None = Field(default=None, min_length=1)
    source_eval_suite_id: str | None = Field(default=None, min_length=1)
    trajectory_record_schema_version: TrajectoryRecordSchemaVersion
    record_count: PositiveInt
    trajectories_jsonl_hash: str = Field(min_length=1)
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_export_contract(self) -> "TrajectoryExportManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=TRAJECTORY_EXPORT_ARTIFACT_REFS,
            owner="trajectory export manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=TRAJECTORY_EXPORT_REQUIRED_ARTIFACTS,
            owner="trajectory export manifests",
        )
        if self.trajectory_record_schema_version != TRAJECTORY_RECORD_SCHEMA_VERSION:
            raise ValueError(
                "trajectory_record_schema_version must be "
                f"{TRAJECTORY_RECORD_SCHEMA_VERSION!r}"
            )
        if self.source_artifact_type == ArtifactType.EVAL_RUN.value:
            if self.source_artifact_schema_version != EVAL_RUN_ARTIFACT_SCHEMA_VERSION:
                raise ValueError(
                    "eval_run trajectory exports require matching "
                    "source_artifact_schema_version"
                )
            if self.source_eval_run_id is None:
                raise ValueError(
                    "eval_run trajectory exports require source_eval_run_id"
                )
            if self.source_eval_suite_id is not None:
                raise ValueError(
                    "eval_run trajectory exports cannot include source_eval_suite_id"
                )
            return self

        if self.source_artifact_schema_version != EVAL_SUITE_ARTIFACT_SCHEMA_VERSION:
            raise ValueError(
                "eval_suite trajectory exports require matching "
                "source_artifact_schema_version"
            )
        if self.source_eval_suite_id is None:
            raise ValueError(
                "eval_suite trajectory exports require source_eval_suite_id"
            )
        if self.source_eval_run_id is not None:
            raise ValueError(
                "eval_suite trajectory exports cannot include source_eval_run_id"
            )
        return self


class TrajectoryReviewManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.TRAJECTORY_REVIEW.value
    expected_artifact_schema_version = TRAJECTORY_REVIEW_ARTIFACT_SCHEMA_VERSION

    created_at: str = Field(min_length=1)
    source_artifact_type: TrajectoryReviewSourceArtifactType
    source_artifact_schema_version: str = Field(min_length=1)
    source_artifact_dir: str = Field(min_length=1)
    source_manifest_path: str = Field(min_length=1)
    source_manifest_hash: str = Field(min_length=1)
    source_eval_run_id: str | None = Field(default=None, min_length=1)
    source_eval_suite_id: str | None = Field(default=None, min_length=1)
    source_trajectories_jsonl_hash: str = Field(min_length=1)
    trajectory_record_schema_version: TrajectoryRecordSchemaVersion
    trajectory_review_schema_version: TrajectoryReviewSchemaVersion
    record_count: PositiveInt
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_review_contract(self) -> "TrajectoryReviewManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=TRAJECTORY_REVIEW_ARTIFACT_REFS,
            owner="trajectory review manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=TRAJECTORY_REVIEW_REQUIRED_ARTIFACTS,
            owner="trajectory review manifests",
        )
        if (
            self.source_artifact_schema_version
            != TRAJECTORY_EXPORT_ARTIFACT_SCHEMA_VERSION
        ):
            raise ValueError(
                "trajectory review artifacts require trajectory export source "
                "artifact schema version"
            )
        if self.trajectory_record_schema_version != TRAJECTORY_RECORD_SCHEMA_VERSION:
            raise ValueError(
                "trajectory_record_schema_version must be "
                f"{TRAJECTORY_RECORD_SCHEMA_VERSION!r}"
            )
        if self.trajectory_review_schema_version != TRAJECTORY_REVIEW_SCHEMA_VERSION:
            raise ValueError(
                "trajectory_review_schema_version must be "
                f"{TRAJECTORY_REVIEW_SCHEMA_VERSION!r}"
            )
        if (self.source_eval_run_id is None) == (self.source_eval_suite_id is None):
            raise ValueError(
                "trajectory review manifests require exactly one source eval id"
            )
        return self


class TrainingCandidateHarnessAuditManifestRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["harness_audit"]
    artifact_schema_version: HarnessAuditArtifactSchemaVersion
    artifact_dir: str = Field(min_length=1)
    manifest_hash: ContentHash
    harness_audit_run_id: str = Field(min_length=1)
    harness_runtime_hash: ContentHash
    status: Literal["PASS"]


class TrainingCandidateControlCalibrationManifestRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["control_calibration"]
    artifact_schema_version: ControlCalibrationArtifactSchemaVersion
    artifact_dir: str = Field(min_length=1)
    manifest_hash: ContentHash
    control_run_id: str = Field(min_length=1)
    harness_runtime_hash: ContentHash
    task_pack_id: str = Field(min_length=1)
    selected_task_hash_set: ContentHash
    overall_match: Literal[True]
    flake_detection_status: Literal["stable"]


class TrainingCandidateExportManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.TRAINING_CANDIDATE_EXPORT.value
    expected_artifact_schema_version = TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION

    created_at: str = Field(min_length=1)
    source_trajectory_export_dir: str = Field(min_length=1)
    source_trajectory_export_manifest_hash: str = Field(min_length=1)
    source_trajectories_jsonl_hash: str = Field(min_length=1)
    source_review_dir: str = Field(min_length=1)
    source_review_manifest_hash: str = Field(min_length=1)
    source_reviews_jsonl_hash: str = Field(min_length=1)
    harness_audit_gate: TrainingCandidateHarnessAuditManifestRef
    control_calibration_gate: TrainingCandidateControlCalibrationManifestRef
    trajectory_record_schema_version: TrajectoryRecordSchemaVersion
    trajectory_review_schema_version: TrajectoryReviewSchemaVersion
    training_candidate_record_schema_version: TrainingCandidateRecordSchemaVersion
    record_count: PositiveInt
    training_candidates_jsonl_hash: str = Field(min_length=1)
    analysis_allowed_count: NonNegativeInt
    positive_sft_allowed_count: NonNegativeInt
    negative_example_allowed_count: NonNegativeInt
    preference_data_allowed_count: NonNegativeInt
    trainable_count: NonNegativeInt
    analysis_only_count: NonNegativeInt
    not_trainable_count: NonNegativeInt
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_training_candidate_export_contract(
        self,
    ) -> "TrainingCandidateExportManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=TRAINING_CANDIDATE_EXPORT_ARTIFACT_REFS,
            owner="training candidate export manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=TRAINING_CANDIDATE_EXPORT_REQUIRED_ARTIFACTS,
            owner="training candidate export manifests",
        )
        if self.trajectory_record_schema_version != TRAJECTORY_RECORD_SCHEMA_VERSION:
            raise ValueError(
                "trajectory_record_schema_version must be "
                f"{TRAJECTORY_RECORD_SCHEMA_VERSION!r}"
            )
        if self.trajectory_review_schema_version != TRAJECTORY_REVIEW_SCHEMA_VERSION:
            raise ValueError(
                "trajectory_review_schema_version must be "
                f"{TRAJECTORY_REVIEW_SCHEMA_VERSION!r}"
            )
        if (
            self.training_candidate_record_schema_version
            != TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
        ):
            raise ValueError(
                "training_candidate_record_schema_version must be "
                f"{TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION!r}"
            )
        if (
            self.harness_audit_gate.harness_runtime_hash
            != self.control_calibration_gate.harness_runtime_hash
        ):
            raise ValueError(
                "harness audit and control calibration gates must use the same "
                "harness runtime"
            )

        bounded_counts = (
            self.analysis_allowed_count,
            self.positive_sft_allowed_count,
            self.negative_example_allowed_count,
            self.preference_data_allowed_count,
            self.trainable_count,
            self.analysis_only_count,
            self.not_trainable_count,
        )
        if any(count > self.record_count for count in bounded_counts):
            raise ValueError("training candidate summary counts cannot exceed records")
        if (
            self.trainable_count + self.analysis_only_count + self.not_trainable_count
            != self.record_count
        ):
            raise ValueError(
                "trainable, analysis_only, and not_trainable counts must sum to "
                "record_count"
            )
        return self


class TrainingCandidateExportManifestRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_dir: str = Field(min_length=1)
    manifest_hash: ContentHash


class TrainingCandidateRepairExportManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.TRAINING_CANDIDATE_REPAIR_EXPORT.value
    expected_artifact_schema_version = (
        TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_SCHEMA_VERSION
    )

    created_at: str = Field(min_length=1)
    source_training_candidate_export: TrainingCandidateExportManifestRef
    training_candidate_repair_record_schema_version: (
        TrainingCandidateRepairRecordSchemaVersion
    )
    record_count: NonNegativeInt
    completed_count: NonNegativeInt
    cannot_complete_count: NonNegativeInt
    repair_error_count: NonNegativeInt
    repair_records_jsonl_hash: ContentHash
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_training_candidate_repair_export_contract(
        self,
    ) -> "TrainingCandidateRepairExportManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=TRAINING_CANDIDATE_REPAIR_EXPORT_ARTIFACT_REFS,
            owner="training candidate repair export manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=(TRAINING_CANDIDATE_REPAIR_EXPORT_REQUIRED_ARTIFACTS),
            owner="training candidate repair export manifests",
        )
        if (
            self.training_candidate_repair_record_schema_version
            != TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION
        ):
            raise ValueError(
                "training_candidate_repair_record_schema_version must be "
                f"{TRAINING_CANDIDATE_REPAIR_RECORD_SCHEMA_VERSION!r}"
            )
        if (
            self.completed_count + self.cannot_complete_count + self.repair_error_count
            != self.record_count
        ):
            raise ValueError("repair status counts must sum to record_count")
        return self


class TrainingCandidateRepairExportManifestRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_dir: str = Field(min_length=1)
    manifest_hash: ContentHash


class TrainingCandidateRepairReviewManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.TRAINING_CANDIDATE_REPAIR_REVIEW.value
    expected_artifact_schema_version = (
        TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_SCHEMA_VERSION
    )

    created_at: str = Field(min_length=1)
    source_training_candidate_repair_export: TrainingCandidateRepairExportManifestRef
    training_candidate_repair_review_record_schema_version: (
        TrainingCandidateRepairReviewRecordSchemaVersion
    )
    record_count: NonNegativeInt
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_training_candidate_repair_review_contract(
        self,
    ) -> "TrainingCandidateRepairReviewManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=TRAINING_CANDIDATE_REPAIR_REVIEW_ARTIFACT_REFS,
            owner="training candidate repair review manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=(TRAINING_CANDIDATE_REPAIR_REVIEW_REQUIRED_ARTIFACTS),
            owner="training candidate repair review manifests",
        )
        if (
            self.training_candidate_repair_review_record_schema_version
            != TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION
        ):
            raise ValueError(
                "training_candidate_repair_review_record_schema_version must be "
                f"{TRAINING_CANDIDATE_REPAIR_REVIEW_RECORD_SCHEMA_VERSION!r}"
            )
        return self


class PositiveSFTExportManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.POSITIVE_SFT_EXPORT.value
    expected_artifact_schema_version = POSITIVE_SFT_EXPORT_ARTIFACT_SCHEMA_VERSION

    created_at: str = Field(min_length=1)
    source_training_candidate_export_dir: str = Field(min_length=1)
    source_training_candidate_export_artifact_schema_version: (
        TrainingCandidateExportArtifactSchemaVersion
    )
    source_training_candidate_export_manifest_hash: str = Field(min_length=1)
    source_training_candidates_jsonl_hash: str = Field(min_length=1)
    training_candidate_record_schema_version: TrainingCandidateRecordSchemaVersion
    positive_sft_example_record_schema_version: PositiveSFTExampleRecordSchemaVersion
    record_count: NonNegativeInt
    positive_sft_examples_jsonl_hash: str = Field(min_length=1)
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_positive_sft_export_contract(self) -> "PositiveSFTExportManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=POSITIVE_SFT_EXPORT_ARTIFACT_REFS,
            owner="positive SFT export manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=POSITIVE_SFT_EXPORT_REQUIRED_ARTIFACTS,
            owner="positive SFT export manifests",
        )
        if (
            self.source_training_candidate_export_artifact_schema_version
            != TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION
        ):
            raise ValueError(
                "source_training_candidate_export_artifact_schema_version must be "
                f"{TRAINING_CANDIDATE_EXPORT_ARTIFACT_SCHEMA_VERSION!r}"
            )
        if (
            self.training_candidate_record_schema_version
            != TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION
        ):
            raise ValueError(
                "training_candidate_record_schema_version must be "
                f"{TRAINING_CANDIDATE_RECORD_SCHEMA_VERSION!r}"
            )
        if (
            self.positive_sft_example_record_schema_version
            != POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION
        ):
            raise ValueError(
                "positive_sft_example_record_schema_version must be "
                f"{POSITIVE_SFT_EXAMPLE_RECORD_SCHEMA_VERSION!r}"
            )
        return self


class ScorerAuditManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.SCORER_AUDIT.value
    expected_artifact_schema_version = SCORER_AUDIT_ARTIFACT_SCHEMA_VERSION

    scorer_audit_run_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    git_sha_or_unknown: str = Field(min_length=1)
    runtime_version: HarnessAuditRuntimeVersion
    runtime_provenance: HarnessRuntimeProvenance
    scorer_audit_case_schema_version: ScorerAuditCaseSchemaVersion
    scorer_audit_record_schema_version: ScorerAuditRecordSchemaVersion
    task_hash_report_schema_version: TaskHashReportSchemaVersion
    scorer_attempt_artifact_schema_version: ScorerAttemptArtifactSchemaVersion
    summary: HarnessAuditLayerSummary
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_scorer_audit_contract(self) -> "ScorerAuditManifest":
        _validate_harness_audit_layer_manifest(
            self,
            artifact_refs=SCORER_AUDIT_ARTIFACT_REFS,
            required_artifacts=SCORER_AUDIT_REQUIRED_ARTIFACTS,
            owner="scorer audit manifests",
            expected_layer="scorer",
        )
        if self.scorer_audit_case_schema_version != SCORER_AUDIT_CASE_SCHEMA_VERSION:
            raise ValueError(
                "scorer_audit_case_schema_version must match the current case contract"
            )
        if (
            self.scorer_audit_record_schema_version
            != SCORER_AUDIT_RECORD_SCHEMA_VERSION
        ):
            raise ValueError(
                "scorer_audit_record_schema_version must match the current record "
                "contract"
            )
        if self.task_hash_report_schema_version != TASK_HASH_REPORT_SCHEMA_VERSION:
            raise ValueError(
                "task_hash_report_schema_version must match the current task hash "
                "contract"
            )
        if self.scorer_attempt_artifact_schema_version != (
            SCORER_ATTEMPT_ARTIFACT_SCHEMA_VERSION
        ):
            raise ValueError(
                "scorer_attempt_artifact_schema_version must match the current "
                "scorer attempt contract"
            )
        return self


class AgentTaskAuditManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.AGENT_TASK_AUDIT.value
    expected_artifact_schema_version = AGENT_TASK_AUDIT_ARTIFACT_SCHEMA_VERSION

    agent_task_audit_run_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    git_sha_or_unknown: str = Field(min_length=1)
    runtime_version: HarnessAuditRuntimeVersion
    runtime_provenance: HarnessRuntimeProvenance
    agent_task_audit_case_schema_version: AgentTaskAuditCaseSchemaVersion
    agent_task_audit_record_schema_version: AgentTaskAuditRecordSchemaVersion
    task_hash_report_schema_version: TaskHashReportSchemaVersion
    agent_attempt_artifact_schema_version: AgentAttemptArtifactSchemaVersion
    summary: HarnessAuditLayerSummary
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_agent_task_audit_contract(self) -> "AgentTaskAuditManifest":
        _validate_harness_audit_layer_manifest(
            self,
            artifact_refs=AGENT_TASK_AUDIT_ARTIFACT_REFS,
            required_artifacts=AGENT_TASK_AUDIT_REQUIRED_ARTIFACTS,
            owner="agent-task audit manifests",
            expected_layer="agent",
        )
        if (
            self.agent_task_audit_case_schema_version
            != AGENT_TASK_AUDIT_CASE_SCHEMA_VERSION
        ):
            raise ValueError(
                "agent_task_audit_case_schema_version must match the current case "
                "contract"
            )
        if (
            self.agent_task_audit_record_schema_version
            != AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION
        ):
            raise ValueError(
                "agent_task_audit_record_schema_version must match the current "
                "record contract"
            )
        if self.task_hash_report_schema_version != TASK_HASH_REPORT_SCHEMA_VERSION:
            raise ValueError(
                "task_hash_report_schema_version must match the current task hash "
                "contract"
            )
        if self.agent_attempt_artifact_schema_version != (
            AGENT_ATTEMPT_ARTIFACT_SCHEMA_VERSION
        ):
            raise ValueError(
                "agent_attempt_artifact_schema_version must match the current agent "
                "attempt contract"
            )
        return self


class AgentTaskAuditManifestRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["agent_task_audit"]
    artifact_schema_version: AgentTaskAuditArtifactSchemaVersion
    agent_task_audit_run_id: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    manifest_hash: ContentHash
    harness_runtime_hash: ContentHash
    status: HarnessAuditStatus

    @field_validator("manifest_path")
    @classmethod
    def validate_manifest_path(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)


class ScorerAuditManifestRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["scorer_audit"]
    artifact_schema_version: ScorerAuditArtifactSchemaVersion
    scorer_audit_run_id: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    manifest_hash: ContentHash
    harness_runtime_hash: ContentHash
    status: HarnessAuditStatus

    @field_validator("manifest_path")
    @classmethod
    def validate_manifest_path(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)


def _validate_harness_audit_layer_manifest(
    manifest: ScorerAuditManifest | AgentTaskAuditManifest,
    *,
    artifact_refs: dict[str, str],
    required_artifacts: frozenset[str],
    owner: str,
    expected_layer: Literal["agent", "scorer"],
) -> None:
    manifest.validate_artifacts_map(manifest.artifacts)
    _validate_artifact_ref_contract(
        manifest.artifacts,
        artifact_refs=artifact_refs,
        owner=owner,
    )
    _require_artifacts(
        manifest.artifacts,
        required_artifacts=required_artifacts,
        owner=owner,
    )
    if manifest.runtime_version != HARNESS_AUDIT_RUNTIME_VERSION:
        raise ValueError(f"runtime_version must be {HARNESS_AUDIT_RUNTIME_VERSION!r}")
    if manifest.summary.audit_layer != expected_layer:
        raise ValueError(f"summary must describe the {expected_layer} audit layer")
    if manifest.summary.results_jsonl != manifest.artifacts["results"]:
        raise ValueError("summary results_jsonl must match the results artifact ref")
    if manifest.summary.case_artifacts != manifest.artifacts["case_artifacts"]:
        raise ValueError(
            "summary case_artifacts must match the case_artifacts artifact ref"
        )


class HarnessAuditManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.HARNESS_AUDIT.value
    expected_artifact_schema_version = HARNESS_AUDIT_ARTIFACT_SCHEMA_VERSION

    harness_audit_run_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    git_sha_or_unknown: str = Field(min_length=1)
    runtime_version: HarnessAuditRuntimeVersion
    runtime_provenance: HarnessRuntimeProvenance
    status: HarnessAuditStatus
    agent_audit: AgentTaskAuditManifestRef
    scorer_audit: ScorerAuditManifestRef
    report_hash: ContentHash
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_harness_audit_contract(self) -> "HarnessAuditManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=HARNESS_AUDIT_ARTIFACT_REFS,
            owner="harness audit manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=HARNESS_AUDIT_REQUIRED_ARTIFACTS,
            owner="harness audit manifests",
        )
        if self.runtime_version != HARNESS_AUDIT_RUNTIME_VERSION:
            raise ValueError(
                f"runtime_version must be {HARNESS_AUDIT_RUNTIME_VERSION!r}"
            )
        expected_agent_manifest_path = (
            f"{self.artifacts['agent_audit']}/{MANIFEST_FILENAME}"
        )
        if self.agent_audit.manifest_path != expected_agent_manifest_path:
            raise ValueError(
                "agent_audit manifest_path must match the agent artifact directory"
            )
        expected_scorer_manifest_path = (
            f"{self.artifacts['scorer_audit']}/{MANIFEST_FILENAME}"
        )
        if self.scorer_audit.manifest_path != expected_scorer_manifest_path:
            raise ValueError(
                "scorer_audit manifest_path must match the scorer artifact directory"
            )
        runtime_hash = self.runtime_provenance.harness_runtime_hash
        if self.agent_audit.harness_runtime_hash != runtime_hash:
            raise ValueError("agent_audit must use the root harness runtime")
        if self.scorer_audit.harness_runtime_hash != runtime_hash:
            raise ValueError("scorer_audit must use the root harness runtime")
        expected_status = derive_harness_audit_status(
            self.agent_audit.status,
            self.scorer_audit.status,
        )
        if self.status != expected_status:
            raise ValueError("status must reflect agent and scorer audit statuses")
        return self


class RewardHackAuditManifest(ArtifactManifest):
    expected_artifact_type = ArtifactType.REWARD_HACK_AUDIT.value
    expected_artifact_schema_version = REWARD_HACK_AUDIT_ARTIFACT_SCHEMA_VERSION

    created_at: str = Field(min_length=1)
    runtime_version: str = Field(min_length=1)
    case_root: str = Field(min_length=1)
    reward_hack_case_schema_version: str = Field(min_length=1)
    record_count: NonNegativeInt
    pass_count: NonNegativeInt
    fail_count: NonNegativeInt
    results_jsonl_hash: str = Field(min_length=1)
    artifacts: dict[str, str]

    @model_validator(mode="after")
    def validate_reward_hack_audit_contract(self) -> "RewardHackAuditManifest":
        self.validate_artifacts_map(self.artifacts)
        _validate_artifact_ref_contract(
            self.artifacts,
            artifact_refs=REWARD_HACK_AUDIT_ARTIFACT_REFS,
            owner="reward-hack audit manifests",
        )
        _require_artifacts(
            self.artifacts,
            required_artifacts=REWARD_HACK_AUDIT_REQUIRED_ARTIFACTS,
            owner="reward-hack audit manifests",
        )
        if self.pass_count + self.fail_count != self.record_count:
            raise ValueError("pass_count and fail_count must sum to record_count")
        return self


def load_scorer_attempt_manifest(path: Path) -> ScorerAttemptManifest:
    return _validate_manifest(ScorerAttemptManifest, path)


def load_agent_attempt_manifest(path: Path) -> AgentTaskRunManifest:
    return _validate_manifest(AgentTaskRunManifest, path)


def load_eval_run_manifest(path: Path) -> EvalRunManifest:
    return _validate_manifest(EvalRunManifest, path)


def load_eval_suite_manifest(path: Path) -> EvalSuiteManifest:
    return _validate_manifest(EvalSuiteManifest, path)


def load_control_calibration_manifest(path: Path) -> ControlCalibrationManifest:
    return _validate_manifest(ControlCalibrationManifest, path)


def load_replay_run_manifest(path: Path) -> ReplayRunManifest:
    return _validate_manifest(ReplayRunManifest, path)


def load_trajectory_export_manifest(path: Path) -> TrajectoryExportManifest:
    return _validate_manifest(TrajectoryExportManifest, path)


def load_trajectory_review_manifest(path: Path) -> TrajectoryReviewManifest:
    return _validate_manifest(TrajectoryReviewManifest, path)


def load_training_candidate_export_manifest(
    path: Path,
) -> TrainingCandidateExportManifest:
    return _validate_manifest(TrainingCandidateExportManifest, path)


def load_training_candidate_repair_export_manifest(
    path: Path,
) -> TrainingCandidateRepairExportManifest:
    return _validate_manifest(TrainingCandidateRepairExportManifest, path)


def load_training_candidate_repair_review_manifest(
    path: Path,
) -> TrainingCandidateRepairReviewManifest:
    return _validate_manifest(TrainingCandidateRepairReviewManifest, path)


def load_positive_sft_export_manifest(path: Path) -> PositiveSFTExportManifest:
    return _validate_manifest(PositiveSFTExportManifest, path)


def load_scorer_audit_manifest(path: Path) -> ScorerAuditManifest:
    return _validate_manifest(ScorerAuditManifest, path)


def load_agent_task_audit_manifest(path: Path) -> AgentTaskAuditManifest:
    return _validate_manifest(AgentTaskAuditManifest, path)


def load_harness_audit_manifest(path: Path) -> HarnessAuditManifest:
    return _validate_manifest(HarnessAuditManifest, path)


def load_reward_hack_audit_manifest(path: Path) -> RewardHackAuditManifest:
    return _validate_manifest(RewardHackAuditManifest, path)


def load_attempt_manifest(path: Path) -> ScorerAttemptManifest | AgentTaskRunManifest:
    payload = load_json_object(path)
    artifact_type = payload.get("artifact_type")
    if artifact_type == ArtifactType.SCORER_ATTEMPT.value:
        return _validate_manifest_payload(ScorerAttemptManifest, path, payload)
    if artifact_type == ArtifactType.AGENT_ATTEMPT.value:
        return _validate_manifest_payload(AgentTaskRunManifest, path, payload)
    raise ValueError(f"Expected scorer or agent attempt manifest at {path}")


def load_eval_artifact_manifest(path: Path) -> EvalRunManifest | EvalSuiteManifest:
    payload = load_json_object(path)
    artifact_type = payload.get("artifact_type")
    if artifact_type == ArtifactType.EVAL_RUN.value:
        return _validate_manifest_payload(EvalRunManifest, path, payload)
    if artifact_type == ArtifactType.EVAL_SUITE.value:
        return _validate_manifest_payload(EvalSuiteManifest, path, payload)
    raise ValueError(f"Expected eval run or eval suite manifest at {path}")


def load_report_artifact_manifest(
    path: Path,
) -> EvalRunManifest | EvalSuiteManifest | ReplayRunManifest | RewardHackAuditManifest:
    payload = load_json_object(path)
    artifact_type = payload.get("artifact_type")
    if artifact_type == ArtifactType.EVAL_RUN.value:
        return _validate_manifest_payload(EvalRunManifest, path, payload)
    if artifact_type == ArtifactType.EVAL_SUITE.value:
        return _validate_manifest_payload(EvalSuiteManifest, path, payload)
    if artifact_type == ArtifactType.REPLAY_RUN.value:
        return _validate_manifest_payload(ReplayRunManifest, path, payload)
    if artifact_type == ArtifactType.REWARD_HACK_AUDIT.value:
        return _validate_manifest_payload(RewardHackAuditManifest, path, payload)
    raise ValueError(f"Expected reportable artifact manifest at {path}")


def load_replay_source_manifest(path: Path) -> EvalRunManifest | AgentTaskRunManifest:
    payload = load_json_object(path)
    artifact_type = payload.get("artifact_type")
    if artifact_type == ArtifactType.EVAL_RUN.value:
        return _validate_manifest_payload(EvalRunManifest, path, payload)
    if artifact_type == ArtifactType.AGENT_ATTEMPT.value:
        return _validate_manifest_payload(AgentTaskRunManifest, path, payload)
    raise ValueError(f"Expected eval run or agent attempt manifest at {path}")


def _validate_manifest(
    model_type: type[ManifestModel],
    path: Path,
) -> ManifestModel:
    return _validate_manifest_payload(model_type, path, load_json_object(path))


def _validate_manifest_payload(
    model_type: type[ManifestModel],
    path: Path,
    payload: dict[str, object],
) -> ManifestModel:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValidationError.from_exception_data(
            f"{model_type.__name__} at {path}",
            cast(Any, exc.errors()),
        ) from exc


def _validate_unique_eval_attempt_ids(
    attempts: list[EvalRunAttemptManifestRecord],
) -> None:
    attempt_ids = [attempt.eval_attempt_id for attempt in attempts]
    duplicates = sorted(
        {attempt_id for attempt_id in attempt_ids if attempt_ids.count(attempt_id) > 1}
    )
    if duplicates:
        raise ValueError("Duplicate eval_attempt_id value(s): " + ", ".join(duplicates))


def _validate_unique_eval_attempt_artifact_dirs(
    attempts: list[EvalRunAttemptManifestRecord],
) -> None:
    artifact_dirs = [attempt.artifact_dir for attempt in attempts]
    duplicates = sorted(
        {
            artifact_dir
            for artifact_dir in artifact_dirs
            if artifact_dirs.count(artifact_dir) > 1
        }
    )
    if duplicates:
        raise ValueError(
            "Duplicate eval attempt artifact_dir value(s): " + ", ".join(duplicates)
        )


def _selected_task_ids(task_hashes: EvalTaskHashes) -> set[str]:
    return {task.task_id for task in task_hashes.selected_tasks}


def _validate_attempt_artifact_type_for_policy(
    policy_type: PolicyType,
    attempts: list[EvalRunAttemptManifestRecord],
) -> None:
    expected_artifact_type = (
        ArtifactType.SCORER_ATTEMPT.value
        if policy_type == SCORER_CONTROL_PATCH_POLICY_TYPE
        else ArtifactType.AGENT_ATTEMPT.value
    )
    mismatched_attempt_ids = sorted(
        attempt.eval_attempt_id
        for attempt in attempts
        if attempt.artifact_type != expected_artifact_type
    )
    if mismatched_attempt_ids:
        raise ValueError(
            "eval attempt artifact_type must match policy_type: "
            + ", ".join(mismatched_attempt_ids)
        )


def _validate_eval_attempt_coverage(
    attempts: list[EvalRunAttemptManifestRecord],
    *,
    selected_task_ids: set[str],
    attempts_per_task: int,
) -> None:
    expected_indexes = set(range(attempts_per_task))
    for task_id in sorted(selected_task_ids):
        observed_indexes = [
            attempt.attempt_index for attempt in attempts if attempt.task_id == task_id
        ]
        if len(observed_indexes) != attempts_per_task:
            raise ValueError(
                "eval attempts must cover every selected task attempts_per_task times"
            )
        if set(observed_indexes) != expected_indexes:
            raise ValueError(
                "eval attempt indexes must cover 0..attempts_per_task-1 per task"
            )


def _validate_replay_coverage(
    policy_runs: list[EvalSuitePolicyRunManifestRecord],
    replay_runs: list[EvalSuiteReplayRunManifestRecord],
) -> None:
    expected_counts = {
        policy_run.policy: policy_run.replay_repeats for policy_run in policy_runs
    }
    observed_counts = {
        policy: sum(1 for replay_run in replay_runs if replay_run.policy == policy)
        for policy in expected_counts
    }
    unknown_policies = sorted(
        {
            replay_run.policy
            for replay_run in replay_runs
            if replay_run.policy not in expected_counts
        }
    )
    if unknown_policies:
        raise ValueError(
            "replay runs reference unknown policies: " + ", ".join(unknown_policies)
        )
    if observed_counts != expected_counts:
        raise ValueError("replay runs must match policy replay_repeats")
    for policy, expected_count in expected_counts.items():
        observed_indexes = sorted(
            replay_run.replay_index
            for replay_run in replay_runs
            if replay_run.policy == policy
        )
        if observed_indexes != list(range(expected_count)):
            raise ValueError("replay indexes must cover 0..replay_repeats-1")
    policy_attempt_counts = {
        policy_run.policy: policy_run.attempt_count for policy_run in policy_runs
    }
    partial_replays = sorted(
        replay_run.replay_run_id
        for replay_run in replay_runs
        if replay_run.status != "REPLAY_ERROR"
        and replay_run.attempt_count != policy_attempt_counts[replay_run.policy]
    )
    if partial_replays:
        raise ValueError(
            "non-error replay runs must cover the source policy attempt_count: "
            + ", ".join(partial_replays)
        )


def _validate_policy_attempt_counts(
    policy_runs: list[EvalSuitePolicyRunManifestRecord],
    *,
    task_count: int,
) -> None:
    invalid_policies = sorted(
        policy_run.policy
        for policy_run in policy_runs
        if policy_run.attempt_count != task_count * policy_run.attempts_per_task
    )
    if invalid_policies:
        raise ValueError(
            "policy attempt_count must equal task_count * attempts_per_task: "
            + ", ".join(invalid_policies)
        )


def _validate_policy_layer_counts(
    policy_runs: list[EvalSuitePolicyRunManifestRecord],
) -> None:
    invalid_policies: list[str] = []
    for policy_run in policy_runs:
        primary_layer = (
            "scorer_status"
            if policy_run.policy_type == SCORER_CONTROL_PATCH_POLICY_TYPE
            else "agent_status"
        )
        primary_counts = policy_run.layer_counts.get(primary_layer)
        if (
            primary_counts is None
            or sum(primary_counts.values()) != policy_run.attempt_count
        ):
            invalid_policies.append(policy_run.policy)
    if invalid_policies:
        raise ValueError(
            "policy layer_counts primary status totals must equal attempt_count: "
            + ", ".join(sorted(invalid_policies))
        )


def _validate_eval_suite_policy_refs(
    policy_runs: list[EvalSuitePolicyRunManifestRecord],
) -> None:
    _validate_unique_values(
        [policy_run.policy for policy_run in policy_runs],
        field_name="policy",
    )
    _validate_unique_values(
        [policy_run.eval_run_id for policy_run in policy_runs],
        field_name="eval_run_id",
    )
    _validate_unique_values(
        [policy_run.artifact_dir for policy_run in policy_runs],
        field_name="policy artifact_dir",
    )


def _validate_eval_suite_replay_refs(
    replay_runs: list[EvalSuiteReplayRunManifestRecord],
) -> None:
    _validate_unique_values(
        [replay_run.replay_run_id for replay_run in replay_runs],
        field_name="replay_run_id",
    )
    _validate_unique_values(
        [replay_run.artifact_dir for replay_run in replay_runs],
        field_name="replay artifact_dir",
    )


def _validate_unique_values(values: list[str], *, field_name: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {field_name} value(s): " + ", ".join(duplicates))


def _require_artifacts(
    artifacts: dict[str, str],
    *,
    required_artifacts: frozenset[str],
    owner: str,
) -> None:
    missing_artifacts = sorted(required_artifacts - set(artifacts))
    if missing_artifacts:
        raise ValueError(
            f"{owner} require artifact ref(s): " + ", ".join(missing_artifacts)
        )


def _validate_artifact_ref_contract(
    artifacts: dict[str, str],
    *,
    artifact_refs: dict[str, str],
    owner: str,
) -> None:
    unknown_artifacts = sorted(set(artifacts) - set(artifact_refs))
    if unknown_artifacts:
        raise ValueError(
            f"{owner} include unknown artifact ref(s): " + ", ".join(unknown_artifacts)
        )
    mismatched_refs = sorted(
        artifact_name
        for artifact_name, artifact_ref in artifacts.items()
        if artifact_ref != artifact_refs[artifact_name]
    )
    if mismatched_refs:
        details = ", ".join(
            f"{artifact_name}={artifacts[artifact_name]!r}, "
            f"expected {artifact_refs[artifact_name]!r}"
            for artifact_name in mismatched_refs
        )
        raise ValueError(f"{owner} artifact refs must be canonical: {details}")


def _validate_ref_under_artifact_dir(
    artifact_dir: str,
    artifact_ref: str,
    *,
    field_name: str,
) -> None:
    artifact_dir_parts = Path(artifact_dir).parts
    artifact_ref_parts = Path(artifact_ref).parts
    if not artifact_dir_parts or len(artifact_ref_parts) <= len(artifact_dir_parts):
        raise ValueError(f"{field_name} must be under artifact_dir")
    if artifact_ref_parts[: len(artifact_dir_parts)] != artifact_dir_parts:
        raise ValueError(f"{field_name} must be under artifact_dir")


def _count_eval_attempt_layers(
    attempts: list[EvalRunAttemptManifestRecord],
) -> dict[str, dict[str, int]]:
    layer_counts: dict[str, dict[str, int]] = {}
    for attempt in attempts:
        if attempt.scorer is not None:
            _increment_layer_count(layer_counts, "scorer_status", attempt.scorer.status)
            _increment_layer_count(
                layer_counts,
                "scorer_public_status",
                attempt.scorer.public_status,
            )
            _increment_layer_count(
                layer_counts,
                "scorer_hidden_status",
                attempt.scorer.hidden_status,
            )
        if attempt.agent is not None:
            _increment_layer_count(layer_counts, "agent_status", attempt.agent.status)
            if attempt.agent.prompt_loop_status is not None:
                _increment_layer_count(
                    layer_counts,
                    "prompt_loop_status",
                    attempt.agent.prompt_loop_status,
                )
            if attempt.agent.scorer_attempt is not None:
                _increment_layer_count(
                    layer_counts,
                    "agent_scorer_status",
                    attempt.agent.scorer_attempt.status,
                )
                _increment_layer_count(
                    layer_counts,
                    "agent_scorer_public_status",
                    attempt.agent.scorer_attempt.public_status,
                )
                _increment_layer_count(
                    layer_counts,
                    "agent_scorer_hidden_status",
                    attempt.agent.scorer_attempt.hidden_status,
                )
    return layer_counts


def _count_eval_suite_layers(
    policy_runs: list[EvalSuitePolicyRunManifestRecord],
) -> dict[str, dict[str, int]]:
    layer_counts: dict[str, dict[str, int]] = {}
    for policy_run in policy_runs:
        for layer_name, status_counts in policy_run.layer_counts.items():
            for status, count in status_counts.items():
                layer_counts.setdefault(layer_name, {})[status] = (
                    layer_counts.setdefault(layer_name, {}).get(status, 0) + count
                )
    return layer_counts


def _increment_layer_count(
    layer_counts: dict[str, dict[str, int]],
    layer_name: str,
    status: str,
) -> None:
    counts = layer_counts.setdefault(layer_name, {})
    counts[status] = counts.get(status, 0) + 1


def _validate_selected_task_splits(
    split: TaskSplit,
    task_hashes: EvalTaskHashes,
) -> None:
    mismatched_task_ids = sorted(
        task.task_id for task in task_hashes.selected_tasks if task.split != split
    )
    if mismatched_task_ids:
        raise ValueError(
            "selected task hashes contain tasks outside manifest split: "
            + ", ".join(mismatched_task_ids)
        )


def _require_control_policy(
    policy: PolicyMetadataFields,
    *,
    policy_family: PolicyFamily,
    control_layer: ControlLayer,
) -> None:
    if policy.policy_family != policy_family:
        raise ValueError(
            f"{policy.policy_type} policy_family must be {policy_family!r}"
        )
    if policy.control_layer != control_layer:
        raise ValueError(
            f"{policy.policy_type} control_layer must be {control_layer!r}"
        )
    if policy.control_name is None:
        raise ValueError(f"{policy.policy_type} policies require control_name")
    if policy.model_config_ref is not None or policy.decoding_config_ref is not None:
        raise ValueError(f"{policy.policy_type} policies cannot include model configs")
