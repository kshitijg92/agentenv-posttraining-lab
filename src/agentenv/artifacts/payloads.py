from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError

from agentenv.agents.schema import AgentTaskView, PromptLoopResult
from agentenv.agents.schema import PromptLoopStatus
from agentenv.artifacts.base import (
    load_json_object,
    load_jsonl_objects,
    validate_relative_artifact_ref,
)
from agentenv.controls.agent_control_scripts import AgentControlScriptCase
from agentenv.controls.public_check_idempotency_schema import (
    PublicCheckIdempotencyCalibration,
)
from agentenv.evals.schema import SCORER_CONTROL_LAYER, ControlLayer
from agentenv.models.config_schema import ModelConfig, OllamaGenerateModelConfig
from agentenv.models.input_protocol_schema import ModelInputProtocol
from agentenv.models.schema import DecodingConfig
from agentenv.orchestrators.agent_task_schema import AgentTaskRunResult
from agentenv.orchestrators.agent_task_schema import AgentTaskRunStatus
from agentenv.orchestrators.attempt import AttemptResult
from agentenv.orchestrators.attempt import AttemptStatus
from agentenv.orchestrators.attempt import CheckStatus
from agentenv.orchestrators.attempt import validate_attempt_check_statuses
from agentenv.orchestrators.attempt import validate_attempt_status_fields
from agentenv.tasks.schema import TaskSplit
from agentenv.tools.schema import ToolResultStatus

NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
PayloadModel = TypeVar("PayloadModel", bound=BaseModel)

EvalTaskHashesSchemaVersion = Literal["eval_task_hashes_v0"]
TaskHashReportSchemaVersion = Literal["task_hash_report_v0"]
ControlFlakeDetectionSchemaVersion = Literal["control_flake_detection_v1"]
ReplayResultSchemaVersion = Literal["replay_result_v0"]
ModelConfigProvenanceSchemaVersion = Literal["model_config_provenance_v0"]
DecodingConfigProvenanceSchemaVersion = Literal["decoding_config_provenance_v0"]

EVAL_TASK_HASHES_SCHEMA_VERSION: EvalTaskHashesSchemaVersion = "eval_task_hashes_v0"
TASK_HASH_REPORT_SCHEMA_VERSION: TaskHashReportSchemaVersion = "task_hash_report_v0"
CONTROL_FLAKE_DETECTION_SCHEMA_VERSION: ControlFlakeDetectionSchemaVersion = (
    "control_flake_detection_v1"
)
REPLAY_RESULT_SCHEMA_VERSION: ReplayResultSchemaVersion = "replay_result_v0"
MODEL_CONFIG_PROVENANCE_SCHEMA_VERSION: ModelConfigProvenanceSchemaVersion = (
    "model_config_provenance_v0"
)
DECODING_CONFIG_PROVENANCE_SCHEMA_VERSION: DecodingConfigProvenanceSchemaVersion = (
    "decoding_config_provenance_v0"
)

HashableKind = Literal["file", "directory"]
FlakeDetectionStatus = Literal["stable", "drifted"]
ControlFlakeDetectionStatus = Literal["stable", "drifted", "inconclusive"]
RequiredTaskFileDriftStatus = Literal["added", "removed", "changed"]
ReplayStatus = Literal["PASS", "MISMATCH", "REPLAY_ERROR"]
ReplayComparisonType = Literal["scorer_attempt", "agent_task_run"]
SCORER_REPLAY_FIELD_MATCH_NAMES = frozenset(
    {
        "status",
        "public_status",
        "hidden_status",
        "error_class",
        "final_diff_hash",
    }
)
AGENT_REPLAY_FIELD_MATCH_NAMES = frozenset(
    {
        "status",
        "prompt_loop_status",
        "attempt_status",
        "candidate_patch_hash",
        "error_class",
        "error_message",
    }
)
SCORER_REPLAY_ARTIFACT_MATCH_REFS = frozenset(
    {
        "manifest.json",
        "attempt.json",
        "stdout.txt",
        "stderr.txt",
        "error.txt",
        "trace.jsonl",
        "final.diff",
    }
)
AGENT_REPLAY_REQUIRED_ARTIFACT_MATCH_REFS = frozenset(
    {
        "manifest.json",
        "agent_task_run.json",
        "error.txt",
        "decoding_config.json",
        "agent_control_script.json",
    }
)
AGENT_REPLAY_ARTIFACT_MATCH_REFS = frozenset(
    {
        *AGENT_REPLAY_REQUIRED_ARTIFACT_MATCH_REFS,
        "agent_task_view.json",
        "prompt_loop_result.json",
        "model_config.json",
        "candidate.patch",
        "attempt/manifest.json",
        "attempt/attempt.json",
        "attempt/stdout.txt",
        "attempt/stderr.txt",
        "attempt/error.txt",
        "attempt/trace.jsonl",
        "attempt/final.diff",
    }
)


class RequiredTaskFileHash(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    kind: HashableKind
    hash: str = Field(min_length=1)


class SelectedEvalTaskHash(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    split: TaskSplit
    task_record_hash: str = Field(min_length=1)
    task_yaml_hash: str = Field(min_length=1)
    required_task_files_hash: str = Field(min_length=1)
    full_task_dir_hash: str = Field(min_length=1)
    required_task_files: list[RequiredTaskFileHash]

    @model_validator(mode="after")
    def validate_unique_required_task_file_paths(self) -> "SelectedEvalTaskHash":
        paths = [record.path for record in self.required_task_files]
        duplicates = sorted({path for path in paths if paths.count(path) > 1})
        if duplicates:
            raise ValueError(
                "Duplicate required task file path(s): " + ", ".join(duplicates)
            )
        return self


class EvalTaskHashes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: EvalTaskHashesSchemaVersion
    task_pack_id: str = Field(min_length=1)
    selected_task_hash_set: str = Field(min_length=1)
    selected_tasks: list[SelectedEvalTaskHash] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_task_ids(self) -> "EvalTaskHashes":
        task_ids = [record.task_id for record in self.selected_tasks]
        duplicates = sorted(
            {task_id for task_id in task_ids if task_ids.count(task_id) > 1}
        )
        if duplicates:
            raise ValueError("Duplicate selected task id(s): " + ", ".join(duplicates))
        return self


class TaskHashReportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    split: TaskSplit
    task_yaml_hash: str = Field(min_length=1)
    instruction_normalized_hash: str = Field(min_length=1)
    visible_tests_normalized_hash: str | None
    required_task_files_hash: str = Field(min_length=1)
    full_task_dir_hash: str = Field(min_length=1)
    extra_task_files: list[str]
    manifest_path: str = Field(min_length=1)
    required_task_files: list[RequiredTaskFileHash]
    task_record_hash: str = Field(min_length=1)


class TaskHashReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TaskHashReportSchemaVersion
    generated_at_utc: str = Field(min_length=1)
    git_sha_or_unknown: str = Field(min_length=1)
    task_pack_id: str = Field(min_length=1)
    task_pack_path: str = Field(min_length=1)
    task_count: NonNegativeInt
    manifest_yaml_hash: str = Field(min_length=1)
    splits_lock_hash: str = Field(min_length=1)
    split_counts: dict[TaskSplit, NonNegativeInt]
    tasks: list[TaskHashReportRecord]
    pack_record_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_task_count(self) -> "TaskHashReport":
        if self.task_count != len(self.tasks):
            raise ValueError("task_count must equal number of task records")
        task_splits = get_args(TaskSplit)
        if set(self.split_counts) != set(task_splits):
            raise ValueError("split_counts must include exactly every task split")
        if any(count < 0 for count in self.split_counts.values()):
            raise ValueError("split_counts values must be non-negative")
        observed_counts = Counter(task.split for task in self.tasks)
        for split in task_splits:
            if self.split_counts[split] != observed_counts[split]:
                raise ValueError("split_counts must match task records")
        return self


class ScorerControlExpectedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_status: AttemptStatus
    public_status: CheckStatus
    hidden_status: CheckStatus


class ScorerControlActualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer_attempt_id: str = Field(min_length=1)
    attempt_status: AttemptStatus
    public_status: CheckStatus
    hidden_status: CheckStatus
    final_diff_hash: str | None
    error_class: str | None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "ScorerControlActualPayload":
        validate_attempt_status_fields(
            self.attempt_status,
            public_status=self.public_status,
            hidden_status=self.hidden_status,
            error_class=self.error_class,
        )
        if self.attempt_status == "PASS" and self.final_diff_hash is None:
            raise ValueError("PASS scorer controls require final_diff_hash")
        return self


class AgentControlToolSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    status: ToolResultStatus
    error_class: str | None


class AgentControlExpectedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_loop_status: PromptLoopStatus
    tool_results: list[AgentControlToolSummary] | None = None


class AgentControlActualPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_attempt_id: str = Field(min_length=1)
    agent_run_status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus | None
    tool_results: list[AgentControlToolSummary]
    attempt_status: AttemptStatus | None
    public_status: CheckStatus | None
    hidden_status: CheckStatus | None
    error_class: str | None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "AgentControlActualPayload":
        attempt_fields = (
            self.attempt_status,
            self.public_status,
            self.hidden_status,
        )
        if self.agent_run_status == "scored":
            if self.prompt_loop_status != "completed":
                raise ValueError("scored agent controls require completed prompt loop")
            if any(value is None for value in attempt_fields):
                raise ValueError("scored agent controls require scorer statuses")
            if self.error_class is not None:
                raise ValueError("scored agent controls cannot include error_class")
            assert self.attempt_status is not None
            assert self.public_status is not None
            assert self.hidden_status is not None
            validate_attempt_check_statuses(
                self.attempt_status,
                public_status=self.public_status,
                hidden_status=self.hidden_status,
            )
            return self

        if any(value is not None for value in attempt_fields):
            raise ValueError("unscored agent controls cannot include scorer statuses")
        if self.error_class is None:
            raise ValueError("unscored agent controls require error_class")
        if self.agent_run_status == "agent_loop_failed":
            if self.prompt_loop_status is None:
                raise ValueError("agent loop failures require prompt_loop_status")
            if self.prompt_loop_status == "completed":
                raise ValueError(
                    "agent loop failures cannot have completed prompt loop"
                )
        return self


ControlExpectedPayload = ScorerControlExpectedPayload | AgentControlExpectedPayload
ControlActualPayload = ScorerControlActualPayload | AgentControlActualPayload


class ControlCalibrationResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    control_layer: ControlLayer
    control_name: str = Field(min_length=1)
    repeat_index: NonNegativeInt
    artifact_dir: str = Field(min_length=1)
    expected: ControlExpectedPayload
    actual: ControlActualPayload
    match: bool

    @field_validator("artifact_dir")
    @classmethod
    def validate_artifact_dir(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @model_validator(mode="after")
    def validate_payload_matches_control_layer(
        self,
    ) -> "ControlCalibrationResultRecord":
        if self.control_layer == SCORER_CONTROL_LAYER:
            if not isinstance(self.expected, ScorerControlExpectedPayload):
                raise ValueError("scorer controls require scorer expected payload")
            if not isinstance(self.actual, ScorerControlActualPayload):
                raise ValueError("scorer controls require scorer actual payload")
            self._validate_match_summary()
            return self

        if not isinstance(self.expected, AgentControlExpectedPayload):
            raise ValueError("agent controls require agent expected payload")
        if not isinstance(self.actual, AgentControlActualPayload):
            raise ValueError("agent controls require agent actual payload")
        self._validate_match_summary()
        return self

    def _validate_match_summary(self) -> None:
        if self.control_layer == SCORER_CONTROL_LAYER:
            if not isinstance(self.expected, ScorerControlExpectedPayload):
                raise ValueError("scorer controls require scorer expected payload")
            if not isinstance(self.actual, ScorerControlActualPayload):
                raise ValueError("scorer controls require scorer actual payload")
            expected_match = (
                self.actual.attempt_status == self.expected.attempt_status
                and self.actual.public_status == self.expected.public_status
                and self.actual.hidden_status == self.expected.hidden_status
            )
        else:
            if not isinstance(self.expected, AgentControlExpectedPayload):
                raise ValueError("agent controls require agent expected payload")
            if not isinstance(self.actual, AgentControlActualPayload):
                raise ValueError("agent controls require agent actual payload")
            expected_match = (
                self.actual.prompt_loop_status == self.expected.prompt_loop_status
            )
            if self.expected.tool_results is not None:
                expected_match = expected_match and (
                    self.actual.tool_results == self.expected.tool_results
                )
        if self.match != expected_match:
            raise ValueError("match must reflect expected and actual payloads")


class NormalizedArtifactFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    normalized_hash: str = Field(min_length=1)


class ControlFlakeDetectionItemsCompared(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalization: str = Field(min_length=1)
    files: list[NormalizedArtifactFile] = Field(min_length=1)


class RequiredTaskFileDrift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    status: RequiredTaskFileDriftStatus
    reference_hash: str | None
    actual_hash: str | None


class ControlFlakeDetectionRepeatDrift(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[RequiredTaskFileDrift] = Field(min_length=1)


class ControlFlakeDetectionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    control_name: str = Field(min_length=1)
    status: FlakeDetectionStatus
    reference_repeat_index: NonNegativeInt
    drifted_repeats: list[NonNegativeInt]
    items_compared: ControlFlakeDetectionItemsCompared
    individual_drift_details: dict[str, ControlFlakeDetectionRepeatDrift]

    @model_validator(mode="after")
    def validate_drift_consistency(self) -> "ControlFlakeDetectionGroup":
        if self.reference_repeat_index != 0:
            raise ValueError("reference_repeat_index must be 0")
        drifted_repeat_keys = {str(repeat) for repeat in self.drifted_repeats}
        if set(self.individual_drift_details) != drifted_repeat_keys:
            raise ValueError("individual_drift_details keys must match drifted_repeats")
        if self.reference_repeat_index in self.drifted_repeats:
            raise ValueError("reference_repeat_index cannot be drifted")
        if self.status == "stable" and self.drifted_repeats:
            raise ValueError("stable flake groups cannot include drifted repeats")
        if self.status == "drifted" and not self.drifted_repeats:
            raise ValueError("drifted flake groups require drifted repeats")
        return self


class ControlFlakeDetectionGroups(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer: list[ControlFlakeDetectionGroup]
    agent: list[ControlFlakeDetectionGroup]


class ControlFlakeDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: ControlFlakeDetectionSchemaVersion
    status: ControlFlakeDetectionStatus
    repeats: PositiveInt
    groups_checked: NonNegativeInt
    drifted_groups: NonNegativeInt
    groups: ControlFlakeDetectionGroups
    public_check_idempotency: list[PublicCheckIdempotencyCalibration]

    @model_validator(mode="after")
    def validate_group_counts(self) -> "ControlFlakeDetection":
        groups = [*self.groups.scorer, *self.groups.agent]
        if self.groups_checked != len(groups):
            raise ValueError("groups_checked must equal number of groups")
        drifted_groups = sum(1 for group in groups if group.status == "drifted")
        if self.drifted_groups != drifted_groups:
            raise ValueError("drifted_groups must equal drifted group count")
        public_check_statuses = {
            calibration.status for calibration in self.public_check_idempotency
        }
        if drifted_groups or "NON_IDEMPOTENT" in public_check_statuses:
            expected_status: ControlFlakeDetectionStatus = "drifted"
        elif "INCONCLUSIVE" in public_check_statuses:
            expected_status = "inconclusive"
        else:
            expected_status = "stable"
        if self.status != expected_status:
            raise ValueError(
                "status must reflect control drift and public-check idempotency"
            )

        calibration_identities = [
            (calibration.task_manifest_hash, calibration.public_check_index)
            for calibration in self.public_check_idempotency
        ]
        if len(calibration_identities) != len(set(calibration_identities)):
            raise ValueError("public-check idempotency identities must be unique")
        for group in groups:
            if group.reference_repeat_index >= self.repeats:
                raise ValueError("reference_repeat_index must be less than repeats")
            invalid_repeats = [
                repeat for repeat in group.drifted_repeats if repeat >= self.repeats
            ]
            if invalid_repeats:
                raise ValueError("drifted_repeats must be less than repeats")
        return self


class ReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: ReplayResultSchemaVersion
    replay_run_id: str = Field(min_length=1)
    status: ReplayStatus
    attempt_count: NonNegativeInt
    matched_attempts: NonNegativeInt
    mismatched_attempts: NonNegativeInt
    error_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_attempt_counts(self) -> "ReplayResult":
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


class ReplayComparisonRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_type: ReplayComparisonType
    task_id: str = Field(min_length=1)
    source_eval_attempt_id: str | None = Field(default=None, min_length=1)
    source_scorer_attempt_id: str | None = Field(default=None, min_length=1)
    replayed_scorer_attempt_id: str | None = Field(default=None, min_length=1)
    source_agent_attempt_id: str | None = Field(default=None, min_length=1)
    replayed_agent_attempt_id: str | None = Field(default=None, min_length=1)
    source_artifact_ref: str = Field(min_length=1)
    source_artifact_path: str = Field(min_length=1)
    replay_artifact_ref: str = Field(min_length=1)
    replay_artifact_path: str = Field(min_length=1)
    matched: bool
    field_matches: dict[str, bool] = Field(min_length=1)
    artifact_matches: dict[str, bool] = Field(min_length=1)

    @field_validator("source_artifact_ref")
    @classmethod
    def validate_source_artifact_ref(cls, value: str) -> str:
        return validate_relative_artifact_ref(value, allow_current_dir=True)

    @field_validator("replay_artifact_ref")
    @classmethod
    def validate_replay_artifact_ref(cls, value: str) -> str:
        return validate_relative_artifact_ref(value)

    @model_validator(mode="after")
    def validate_comparison_evidence(self) -> "ReplayComparisonRecord":
        _validate_artifact_match_refs(self.artifact_matches)
        if self.comparison_type == "scorer_attempt":
            if (
                self.source_eval_attempt_id is None
                or self.source_scorer_attempt_id is None
                or self.replayed_scorer_attempt_id is None
            ):
                raise ValueError("scorer replay comparisons require scorer attempt ids")
            if (
                self.source_agent_attempt_id is not None
                or self.replayed_agent_attempt_id is not None
            ):
                raise ValueError(
                    "scorer replay comparisons cannot include agent attempt ids"
                )
            if set(self.field_matches) != SCORER_REPLAY_FIELD_MATCH_NAMES:
                raise ValueError(
                    "scorer replay comparisons require the full scorer field set"
                )
            if set(self.artifact_matches) != SCORER_REPLAY_ARTIFACT_MATCH_REFS:
                raise ValueError(
                    "scorer replay comparisons require the full scorer artifact set"
                )
        else:
            if (
                self.source_agent_attempt_id is None
                or self.replayed_agent_attempt_id is None
            ):
                raise ValueError("agent replay comparisons require agent attempt ids")
            if (
                self.source_scorer_attempt_id is not None
                or self.replayed_scorer_attempt_id is not None
            ):
                raise ValueError(
                    "agent replay comparisons cannot include scorer attempt ids"
                )
            if set(self.field_matches) != AGENT_REPLAY_FIELD_MATCH_NAMES:
                raise ValueError(
                    "agent replay comparisons require the full agent field set"
                )
            missing_artifacts = AGENT_REPLAY_REQUIRED_ARTIFACT_MATCH_REFS - set(
                self.artifact_matches
            )
            if missing_artifacts:
                raise ValueError(
                    "agent replay comparisons are missing required artifact evidence: "
                    + ", ".join(sorted(missing_artifacts))
                )
            unknown_artifacts = (
                set(self.artifact_matches) - AGENT_REPLAY_ARTIFACT_MATCH_REFS
            )
            if unknown_artifacts:
                raise ValueError(
                    "agent replay comparisons include unknown artifact evidence: "
                    + ", ".join(sorted(unknown_artifacts))
                )
        expected_match = all(self.field_matches.values()) and all(
            self.artifact_matches.values()
        )
        if self.matched != expected_match:
            raise ValueError("matched must reflect field and artifact matches")
        return self


class ModelInputProtocolProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^xxh64:[0-9a-f]{16}$", strict=True)
    protocol: ModelInputProtocol


class ModelConfigProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: ModelConfigProvenanceSchemaVersion
    source_path: str = Field(min_length=1)
    source_hash: str = Field(min_length=1)
    config: ModelConfig
    model_input_protocol: ModelInputProtocolProvenance | None

    @model_validator(mode="after")
    def validate_model_input_protocol_provenance(self) -> "ModelConfigProvenance":
        if isinstance(self.config, OllamaGenerateModelConfig):
            if self.model_input_protocol is None:
                raise ValueError(
                    "ollama_generate provenance requires model_input_protocol"
                )
            if (
                self.model_input_protocol.source_hash
                != self.config.model_input_protocol.content_hash
            ):
                raise ValueError(
                    "model input protocol provenance hash must match the model "
                    "config pin"
                )
            return self

        if self.model_input_protocol is not None:
            raise ValueError(
                "openai_compatible_chat provenance cannot include model_input_protocol"
            )
        return self


class DecodingConfigProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: DecodingConfigProvenanceSchemaVersion
    source_path: str | None = Field(default=None, min_length=1)
    source_hash: str | None = Field(default=None, min_length=1)
    config: DecodingConfig

    @model_validator(mode="after")
    def validate_source_provenance_pair(self) -> "DecodingConfigProvenance":
        if (self.source_path is None) != (self.source_hash is None):
            raise ValueError(
                "source_path and source_hash must both be set or both null"
            )
        return self


def load_eval_task_hashes(path: Path) -> EvalTaskHashes:
    return _validate_payload(EvalTaskHashes, path)


def load_task_hash_report(path: Path) -> TaskHashReport:
    return _validate_payload(TaskHashReport, path)


def load_replay_result(path: Path) -> ReplayResult:
    return _validate_payload(ReplayResult, path)


def load_replay_comparison_records(path: Path) -> tuple[ReplayComparisonRecord, ...]:
    return tuple(
        _validate_payload_record(ReplayComparisonRecord, path, record)
        for record in load_jsonl_objects(path)
    )


def load_control_calibration_result_records(
    path: Path,
) -> tuple[ControlCalibrationResultRecord, ...]:
    return tuple(
        _validate_payload_record(ControlCalibrationResultRecord, path, record)
        for record in load_jsonl_objects(path)
    )


def load_control_flake_detection(path: Path) -> ControlFlakeDetection:
    return _validate_payload(ControlFlakeDetection, path)


def load_attempt_result(path: Path) -> AttemptResult:
    return _validate_payload(AttemptResult, path)


def load_agent_task_run_result(path: Path) -> AgentTaskRunResult:
    return _validate_payload(AgentTaskRunResult, path)


def load_agent_task_view(path: Path) -> AgentTaskView:
    return _validate_payload(AgentTaskView, path)


def load_prompt_loop_result(path: Path) -> PromptLoopResult:
    return _validate_payload(PromptLoopResult, path)


def load_model_config_provenance(path: Path) -> ModelConfigProvenance:
    return _validate_payload(ModelConfigProvenance, path)


def load_decoding_config_provenance(path: Path) -> DecodingConfigProvenance:
    return _validate_payload(DecodingConfigProvenance, path)


def load_agent_control_script_artifact(path: Path) -> AgentControlScriptCase:
    return _validate_payload(AgentControlScriptCase, path)


def _validate_payload(
    model_type: type[PayloadModel],
    path: Path,
) -> PayloadModel:
    return _validate_payload_record(model_type, path, load_json_object(path))


def _validate_payload_record(
    model_type: type[PayloadModel],
    path: Path,
    payload: dict[str, object],
) -> PayloadModel:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ValidationError.from_exception_data(
            f"{model_type.__name__} at {path}",
            cast(Any, exc.errors()),
        ) from exc


def _validate_artifact_match_refs(artifact_matches: dict[str, bool]) -> None:
    for artifact_ref in artifact_matches:
        validate_relative_artifact_ref(artifact_ref)


def validate_replay_status_counts(
    status: ReplayStatus,
    *,
    attempt_count: int,
    mismatched_attempts: int,
    error_count: int,
) -> None:
    if status == "PASS":
        if attempt_count == 0:
            raise ValueError("PASS replay results require attempts")
        if mismatched_attempts != 0 or error_count != 0:
            raise ValueError("PASS replay results cannot include mismatches or errors")
        return
    if status == "MISMATCH":
        if mismatched_attempts == 0:
            raise ValueError("MISMATCH replay results require mismatches")
        if error_count != 0:
            raise ValueError("MISMATCH replay results cannot include replay errors")
        return
    if error_count == 0:
        raise ValueError("REPLAY_ERROR replay results require error_count")
