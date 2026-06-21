from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TRACE_SCHEMA_VERSION = "trace_v0"
TraceSchemaVersion = Literal["trace_v0"]
AttemptTraceEventType = Literal[
    "attempt_started",
    "command_finished",
    "attempt_finished",
]
EvalTraceEventType = Literal[
    "eval_started",
    "eval_task_started",
    "eval_attempt_started",
    "eval_attempt_finished",
    "eval_task_finished",
    "eval_finished",
]
ReplayTraceEventType = Literal[
    "replay_started",
    "source_run_manifest_loaded",
    "source_attempt_loaded",
    "fresh_attempt_started",
    "fresh_attempt_finished",
    "comparison_recorded",
    "replay_finished",
    "replay_error",
]
TraceEventType = AttemptTraceEventType | EvalTraceEventType | ReplayTraceEventType

ATTEMPT_TRACE_EVENT_TYPES = frozenset(
    {
        "attempt_started",
        "command_finished",
        "attempt_finished",
    }
)
EVAL_TRACE_EVENT_TYPES = frozenset(
    {
        "eval_started",
        "eval_task_started",
        "eval_attempt_started",
        "eval_attempt_finished",
        "eval_task_finished",
        "eval_finished",
    }
)
REPLAY_TRACE_EVENT_TYPES = frozenset(
    {
        "replay_started",
        "source_run_manifest_loaded",
        "source_attempt_loaded",
        "fresh_attempt_started",
        "fresh_attempt_finished",
        "comparison_recorded",
        "replay_finished",
        "replay_error",
    }
)


class AttemptTraceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    phase: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)


class EvalTraceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_run_id: str = Field(min_length=1)
    config_hash: str = Field(min_length=1)
    config_name: str = Field(min_length=1)
    policy: str | None = Field(default=None, min_length=1)
    task_id: str | None = Field(default=None, min_length=1)
    task_index: int | None = Field(default=None, ge=0)
    attempt_index: int | None = Field(default=None, ge=0)
    attempt_id: str | None = Field(default=None, min_length=1)


class ReplayTraceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_id: str = Field(min_length=1)
    source_eval_run_id: str | None = Field(default=None, min_length=1)
    task_id: str | None = Field(default=None, min_length=1)
    source_attempt_id: str | None = Field(default=None, min_length=1)
    replay_attempt_id: str | None = Field(default=None, min_length=1)


TraceProvenance = AttemptTraceProvenance | EvalTraceProvenance | ReplayTraceProvenance


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TraceSchemaVersion
    event_index: int = Field(ge=0)
    timestamp_utc: str = Field(min_length=1)
    event_type: TraceEventType
    provenance_config: TraceProvenance
    input_payload: dict[str, Any] | None = None
    output_payload: dict[str, Any] | None = None
    payload_refs: dict[str, str] | None = None
    payload_hashes: dict[str, str] | None = None

    @model_validator(mode="after")
    def validate_provenance_family(self) -> Self:
        if self.event_type in ATTEMPT_TRACE_EVENT_TYPES:
            if not isinstance(self.provenance_config, AttemptTraceProvenance):
                raise ValueError(f"{self.event_type} requires attempt trace provenance")
            _validate_attempt_event_provenance(self.event_type, self.provenance_config)
            return self

        if self.event_type in EVAL_TRACE_EVENT_TYPES:
            if not isinstance(self.provenance_config, EvalTraceProvenance):
                raise ValueError(f"{self.event_type} requires eval trace provenance")
            _validate_eval_event_provenance(self.event_type, self.provenance_config)
            return self

        if self.event_type in REPLAY_TRACE_EVENT_TYPES:
            if not isinstance(self.provenance_config, ReplayTraceProvenance):
                raise ValueError(f"{self.event_type} requires replay trace provenance")
            _validate_replay_event_provenance(self.event_type, self.provenance_config)
            return self

        raise ValueError(f"Unknown trace event type: {self.event_type}")


def _validate_attempt_event_provenance(
    event_type: TraceEventType,
    provenance: AttemptTraceProvenance,
) -> None:
    if event_type == "command_finished":
        _require_provenance_fields(event_type, provenance, ("phase", "name"))


def _validate_eval_event_provenance(
    event_type: TraceEventType,
    provenance: EvalTraceProvenance,
) -> None:
    if event_type in {"eval_task_started", "eval_task_finished"}:
        _require_provenance_fields(
            event_type,
            provenance,
            ("policy", "task_id", "task_index"),
        )
    if event_type == "eval_attempt_started":
        _require_provenance_fields(
            event_type,
            provenance,
            ("policy", "task_id", "task_index", "attempt_index"),
        )
    if event_type == "eval_attempt_finished":
        _require_provenance_fields(
            event_type,
            provenance,
            ("policy", "task_id", "task_index", "attempt_index", "attempt_id"),
        )


def _validate_replay_event_provenance(
    event_type: TraceEventType,
    provenance: ReplayTraceProvenance,
) -> None:
    if event_type == "source_run_manifest_loaded":
        _require_provenance_fields(event_type, provenance, ("source_eval_run_id",))
    if event_type in {"source_attempt_loaded", "fresh_attempt_started"}:
        _require_provenance_fields(
            event_type,
            provenance,
            ("source_eval_run_id", "task_id", "source_attempt_id"),
        )
    if event_type in {"fresh_attempt_finished", "comparison_recorded"}:
        _require_provenance_fields(
            event_type,
            provenance,
            (
                "source_eval_run_id",
                "task_id",
                "source_attempt_id",
                "replay_attempt_id",
            ),
        )


def _require_provenance_fields(
    event_type: TraceEventType,
    provenance: BaseModel,
    field_names: tuple[str, ...],
) -> None:
    missing = [
        field_name
        for field_name in field_names
        if getattr(provenance, field_name) is None
    ]
    if missing:
        missing_fields = ", ".join(missing)
        raise ValueError(
            f"{event_type} provenance is missing required field(s): {missing_fields}"
        )
