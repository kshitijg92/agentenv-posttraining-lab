from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, TypeAlias, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from agentenv.agents.schema import PromptLoopStatus
from agentenv.artifacts.base import load_jsonl_objects, validate_relative_artifact_ref
from agentenv.audits.types import AgentAuditField
from agentenv.hashing import hash_json
from agentenv.orchestrators.agent_task_schema import AgentTaskRunStatus
from agentenv.orchestrators.attempt import (
    AttemptStatus,
    CheckStatus,
    validate_attempt_status_fields,
)
from agentenv.tools.schema import ToolResultStatus


HarnessAuditStatus = Literal["PASS", "FAIL", "INCONCLUSIVE"]
HarnessAuditLayer = Literal["agent", "scorer"]
HarnessAuditRecordStatus = Literal["COMPLETED", "AUDIT_ERROR"]
HarnessAuditStage = Literal[
    "CASE_PREPARATION",
    "HARNESS_EXECUTION",
    "EXPECTATION_COMPARISON",
    "RESULT_PERSISTENCE",
]
HarnessRuntimeProvenanceSchemaVersion = Literal["harness_runtime_provenance_v0"]
HarnessAuditRuntimeVersion = Literal["harness_audit_runtime_v0"]
AgentTaskAuditCaseSchemaVersion = Literal["agent_task_audit_case_v0"]
ScorerAuditCaseSchemaVersion = Literal["scorer_audit_case_v0"]
AgentTaskAuditRecordSchemaVersion = Literal["agent_task_audit_record_v0"]
ScorerAuditRecordSchemaVersion = Literal["scorer_audit_record_v0"]

HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION: HarnessRuntimeProvenanceSchemaVersion = (
    "harness_runtime_provenance_v0"
)
HARNESS_AUDIT_RUNTIME_VERSION: HarnessAuditRuntimeVersion = "harness_audit_runtime_v0"
AGENT_TASK_AUDIT_CASE_SCHEMA_VERSION: AgentTaskAuditCaseSchemaVersion = (
    "agent_task_audit_case_v0"
)
SCORER_AUDIT_CASE_SCHEMA_VERSION: ScorerAuditCaseSchemaVersion = "scorer_audit_case_v0"
AGENT_TASK_AUDIT_RECORD_SCHEMA_VERSION: AgentTaskAuditRecordSchemaVersion = (
    "agent_task_audit_record_v0"
)
SCORER_AUDIT_RECORD_SCHEMA_VERSION: ScorerAuditRecordSchemaVersion = (
    "scorer_audit_record_v0"
)

NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
ContentHash = Annotated[
    str,
    Field(pattern=r"^xxh64:[0-9a-f]{16}$", strict=True),
]


def _validate_relative_path(value: str) -> str:
    return validate_relative_artifact_ref(value)


class HarnessRuntimeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: HarnessRuntimeProvenanceSchemaVersion
    harness_source_root: Literal["src/agentenv"]
    harness_source_hash: ContentHash
    root_pyproject_path: Literal["pyproject.toml"]
    root_pyproject_hash: ContentHash
    root_uv_lock_path: Literal["uv.lock"]
    root_uv_lock_hash: ContentHash
    python_implementation: str = Field(min_length=1)
    python_version: str = Field(min_length=1)
    sys_platform: str = Field(min_length=1)
    platform_machine: str = Field(min_length=1)
    harness_runtime_hash: ContentHash

    @model_validator(mode="after")
    def validate_runtime_hash(self) -> "HarnessRuntimeProvenance":
        expected_hash = derive_harness_runtime_hash(
            harness_source_hash=self.harness_source_hash,
            root_pyproject_hash=self.root_pyproject_hash,
            root_uv_lock_hash=self.root_uv_lock_hash,
            python_implementation=self.python_implementation,
            python_version=self.python_version,
            sys_platform=self.sys_platform,
            platform_machine=self.platform_machine,
        )
        if self.harness_runtime_hash != expected_hash:
            raise ValueError(
                "harness_runtime_hash must reflect source, dependency, and "
                "interpreter provenance"
            )
        return self


def derive_harness_runtime_hash(
    *,
    harness_source_hash: str,
    root_pyproject_hash: str,
    root_uv_lock_hash: str,
    python_implementation: str,
    python_version: str,
    sys_platform: str,
    platform_machine: str,
) -> str:
    return hash_json(
        {
            "schema_version": HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
            "harness_source_root": "src/agentenv",
            "harness_source_hash": harness_source_hash,
            "root_pyproject_path": "pyproject.toml",
            "root_pyproject_hash": root_pyproject_hash,
            "root_uv_lock_path": "uv.lock",
            "root_uv_lock_hash": root_uv_lock_hash,
            "python_implementation": python_implementation,
            "python_version": python_version,
            "sys_platform": sys_platform,
            "platform_machine": platform_machine,
        }
    )


class HashPinnedDirectoryRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    content_hash: ContentHash

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class HarnessAuditCaseProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_case_path: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    case_source_hash: ContentHash
    task_id: str = Field(min_length=1)
    task_manifest_path: str = Field(min_length=1)
    task_manifest_hash: ContentHash
    task_record_hash: ContentHash

    @field_validator("source_case_path", "task_manifest_path")
    @classmethod
    def validate_source_path(cls, value: str) -> str:
        return _validate_relative_path(value)


class PartialHarnessAuditCaseProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_case_path: str = Field(min_length=1)
    case_source_hash: ContentHash | None
    case_id: str | None = Field(default=None, min_length=1)
    task_id: str | None = Field(default=None, min_length=1)
    task_manifest_path: str | None = Field(default=None, min_length=1)
    task_manifest_hash: ContentHash | None
    task_record_hash: ContentHash | None

    @field_validator("source_case_path", "task_manifest_path")
    @classmethod
    def validate_optional_source_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_relative_path(value)

    @model_validator(mode="after")
    def validate_progressive_task_identity(
        self,
    ) -> "PartialHarnessAuditCaseProvenance":
        if self.task_id is not None and self.task_manifest_path is None:
            raise ValueError("task_id requires task_manifest_path")
        if self.task_manifest_hash is not None and self.task_manifest_path is None:
            raise ValueError("task_manifest_hash requires task_manifest_path")
        if self.task_record_hash is not None and (
            self.task_id is None
            or self.task_manifest_path is None
            or self.task_manifest_hash is None
        ):
            raise ValueError("task_record_hash requires complete parsed task identity")
        return self


class HarnessAuditErrorEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_stage: HarnessAuditStage
    error_class: str = Field(min_length=1)
    error_message: str = Field(min_length=1)


class AgentAuditToolResultValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1)
    status: ToolResultStatus
    error_class: str | None = Field(default=None, min_length=1)


AgentAuditRecordValue: TypeAlias = (
    str | None | list[str] | list[AgentAuditToolResultValue]
)


class AgentAuditComparisonRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: AgentAuditField
    expected: AgentAuditRecordValue
    actual: AgentAuditRecordValue
    match: bool

    @model_validator(mode="after")
    def validate_match(self) -> "AgentAuditComparisonRecord":
        if self.match != (self.expected == self.actual):
            raise ValueError("match must reflect expected and actual values")
        return self


class AttemptStatusAuditComparisonRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["attempt_status"]
    expected: AttemptStatus
    actual: AttemptStatus
    match: bool

    @model_validator(mode="after")
    def validate_match(self) -> "AttemptStatusAuditComparisonRecord":
        if self.match != (self.expected == self.actual):
            raise ValueError("match must reflect expected and actual values")
        return self


class PublicStatusAuditComparisonRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["public_status"]
    expected: CheckStatus
    actual: CheckStatus
    match: bool

    @model_validator(mode="after")
    def validate_match(self) -> "PublicStatusAuditComparisonRecord":
        if self.match != (self.expected == self.actual):
            raise ValueError("match must reflect expected and actual values")
        return self


class HiddenStatusAuditComparisonRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["hidden_status"]
    expected: CheckStatus
    actual: CheckStatus
    match: bool

    @model_validator(mode="after")
    def validate_match(self) -> "HiddenStatusAuditComparisonRecord":
        if self.match != (self.expected == self.actual):
            raise ValueError("match must reflect expected and actual values")
        return self


ScorerAuditComparisonRecord: TypeAlias = Annotated[
    AttemptStatusAuditComparisonRecord
    | PublicStatusAuditComparisonRecord
    | HiddenStatusAuditComparisonRecord,
    Field(discriminator="field"),
]


class NestedScorerAuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scorer_attempt_id: str = Field(min_length=1)
    attempt_status: AttemptStatus
    public_status: CheckStatus
    hidden_status: CheckStatus
    error_class: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "NestedScorerAuditResult":
        validate_attempt_status_fields(
            self.attempt_status,
            public_status=self.public_status,
            hidden_status=self.hidden_status,
            error_class=self.error_class,
        )
        return self


class CompletedAgentTaskAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: AgentTaskAuditRecordSchemaVersion
    record_status: Literal["COMPLETED"]
    audit_layer: Literal["agent"]
    provenance: HarnessAuditCaseProvenance
    purpose: str = Field(min_length=1)
    agent_control_script: str = Field(min_length=1)
    case_artifact: HashPinnedDirectoryRef
    agent_attempt_id: str = Field(min_length=1)
    agent_run_status: AgentTaskRunStatus
    prompt_loop_status: PromptLoopStatus | None
    error_class: str | None = Field(default=None, min_length=1)
    scorer_result: NestedScorerAuditResult | None
    comparisons: list[AgentAuditComparisonRecord] = Field(min_length=1)
    overall_match: bool

    @field_validator("agent_control_script")
    @classmethod
    def validate_agent_control_script(cls, value: str) -> str:
        return _validate_relative_path(value)

    @model_validator(mode="after")
    def validate_agent_and_scorer_outcome(self) -> "CompletedAgentTaskAuditRecord":
        if self.agent_run_status == "scored":
            if self.prompt_loop_status != "completed":
                raise ValueError(
                    "scored agent audit records require completed prompt loop"
                )
            if self.error_class is not None:
                raise ValueError(
                    "scored agent audit records cannot include error_class"
                )
            if self.scorer_result is None:
                raise ValueError("scored agent audit records require scorer_result")
        else:
            if self.scorer_result is not None:
                raise ValueError(
                    "unscored agent audit records cannot include scorer_result"
                )
            if self.error_class is None:
                raise ValueError("unscored agent audit records require error_class")
            if self.agent_run_status == "agent_loop_failed" and (
                self.prompt_loop_status is None
                or self.prompt_loop_status == "completed"
            ):
                raise ValueError(
                    "agent loop failure audit records require a non-completed "
                    "prompt loop status"
                )
        if self.overall_match != all(
            comparison.match for comparison in self.comparisons
        ):
            raise ValueError("overall_match must reflect comparisons")
        return self


class AgentTaskAuditErrorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: AgentTaskAuditRecordSchemaVersion
    record_status: Literal["AUDIT_ERROR"]
    audit_layer: Literal["agent"]
    provenance: PartialHarnessAuditCaseProvenance
    error: HarnessAuditErrorEvidence


AgentTaskAuditRecord: TypeAlias = Annotated[
    CompletedAgentTaskAuditRecord | AgentTaskAuditErrorRecord,
    Field(discriminator="record_status"),
]


class CompletedScorerAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: ScorerAuditRecordSchemaVersion
    record_status: Literal["COMPLETED"]
    audit_layer: Literal["scorer"]
    provenance: HarnessAuditCaseProvenance
    purpose: str = Field(min_length=1)
    submission: str = Field(min_length=1)
    case_artifact: HashPinnedDirectoryRef
    scorer_attempt_id: str = Field(min_length=1)
    error_class: str | None = Field(default=None, min_length=1)
    manifest_override: dict[str, object] | None
    comparisons: list[ScorerAuditComparisonRecord] = Field(min_length=1)
    overall_match: bool

    @field_validator("submission")
    @classmethod
    def validate_submission(cls, value: str) -> str:
        return _validate_relative_path(value)

    @model_validator(mode="after")
    def validate_overall_match(self) -> "CompletedScorerAuditRecord":
        if self.overall_match != all(
            comparison.match for comparison in self.comparisons
        ):
            raise ValueError("overall_match must reflect comparisons")
        return self


class ScorerAuditErrorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: ScorerAuditRecordSchemaVersion
    record_status: Literal["AUDIT_ERROR"]
    audit_layer: Literal["scorer"]
    provenance: PartialHarnessAuditCaseProvenance
    error: HarnessAuditErrorEvidence


ScorerAuditRecord: TypeAlias = Annotated[
    CompletedScorerAuditRecord | ScorerAuditErrorRecord,
    Field(discriminator="record_status"),
]

HarnessAuditCaseRecord: TypeAlias = (
    CompletedAgentTaskAuditRecord
    | AgentTaskAuditErrorRecord
    | CompletedScorerAuditRecord
    | ScorerAuditErrorRecord
)


class HarnessAuditLayerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_layer: HarnessAuditLayer
    status: HarnessAuditStatus
    case_root: str = Field(min_length=1)
    case_root_hash: ContentHash
    discovered_case_count: PositiveInt
    record_count: PositiveInt
    completed_count: NonNegativeInt
    matched_count: NonNegativeInt
    mismatched_count: NonNegativeInt
    audit_error_count: NonNegativeInt
    artifact_dir_hash: ContentHash
    results_jsonl: str = Field(min_length=1)
    results_jsonl_hash: ContentHash
    case_artifacts: str = Field(min_length=1)
    case_artifacts_hash: ContentHash

    @field_validator("case_root", "results_jsonl", "case_artifacts")
    @classmethod
    def validate_paths(cls, value: str) -> str:
        return _validate_relative_path(value)

    @model_validator(mode="after")
    def validate_counts_and_status(self) -> "HarnessAuditLayerSummary":
        if self.record_count != self.discovered_case_count:
            raise ValueError("record_count must equal discovered_case_count")
        if self.completed_count + self.audit_error_count != self.record_count:
            raise ValueError(
                "completed_count and audit_error_count must sum to record_count"
            )
        if self.matched_count + self.mismatched_count != self.completed_count:
            raise ValueError(
                "matched_count and mismatched_count must sum to completed_count"
            )
        expected_status = derive_harness_audit_layer_status_from_counts(
            mismatched_count=self.mismatched_count,
            audit_error_count=self.audit_error_count,
        )
        if self.status != expected_status:
            raise ValueError("status must reflect mismatches and audit errors")
        return self


def derive_harness_audit_layer_status(
    records: Sequence[HarnessAuditCaseRecord],
) -> HarnessAuditStatus:
    if not records:
        raise ValueError("harness audit layers require at least one record")
    if any(
        isinstance(
            record,
            CompletedAgentTaskAuditRecord | CompletedScorerAuditRecord,
        )
        and not record.overall_match
        for record in records
    ):
        return "FAIL"
    if any(
        isinstance(record, AgentTaskAuditErrorRecord | ScorerAuditErrorRecord)
        for record in records
    ):
        return "INCONCLUSIVE"
    return "PASS"


def derive_harness_audit_layer_status_from_counts(
    *,
    mismatched_count: int,
    audit_error_count: int,
) -> HarnessAuditStatus:
    if mismatched_count:
        return "FAIL"
    if audit_error_count:
        return "INCONCLUSIVE"
    return "PASS"


def derive_harness_audit_status(
    agent_status: HarnessAuditStatus,
    scorer_status: HarnessAuditStatus,
) -> HarnessAuditStatus:
    statuses = {agent_status, scorer_status}
    if "FAIL" in statuses:
        return "FAIL"
    if "INCONCLUSIVE" in statuses:
        return "INCONCLUSIVE"
    return "PASS"


_AGENT_TASK_AUDIT_RECORD_ADAPTER = TypeAdapter(AgentTaskAuditRecord)
_SCORER_AUDIT_RECORD_ADAPTER = TypeAdapter(ScorerAuditRecord)


def load_agent_task_audit_records(path: Path) -> tuple[AgentTaskAuditRecord, ...]:
    return tuple(
        _validate_record(
            _AGENT_TASK_AUDIT_RECORD_ADAPTER,
            "AgentTaskAuditRecord",
            path,
            payload,
        )
        for payload in load_jsonl_objects(path)
    )


def load_scorer_audit_records(path: Path) -> tuple[ScorerAuditRecord, ...]:
    return tuple(
        _validate_record(
            _SCORER_AUDIT_RECORD_ADAPTER,
            "ScorerAuditRecord",
            path,
            payload,
        )
        for payload in load_jsonl_objects(path)
    )


def _validate_record(
    adapter: TypeAdapter[Any],
    record_name: str,
    path: Path,
    payload: dict[str, object],
) -> Any:
    try:
        return adapter.validate_python(payload)
    except ValidationError as exc:
        raise ValidationError.from_exception_data(
            f"{record_name} at {path}",
            cast(Any, exc.errors()),
        ) from exc
