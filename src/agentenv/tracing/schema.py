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
    "source_manifest_loaded",
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
        "source_manifest_loaded",
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

    scorer_attempt_id: str = Field(min_length=1)
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
    eval_attempt_id: str | None = Field(default=None, min_length=1)
    scorer_attempt_id: str | None = Field(default=None, min_length=1)
    agent_attempt_id: str | None = Field(default=None, min_length=1)


class ReplayTraceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    replay_run_id: str = Field(min_length=1)
    source_eval_run_id: str | None = Field(default=None, min_length=1)
    source_eval_attempt_id: str | None = Field(default=None, min_length=1)
    task_id: str | None = Field(default=None, min_length=1)
    source_scorer_attempt_id: str | None = Field(default=None, min_length=1)
    replayed_scorer_attempt_id: str | None = Field(default=None, min_length=1)
    source_agent_attempt_id: str | None = Field(default=None, min_length=1)
    replayed_agent_attempt_id: str | None = Field(default=None, min_length=1)


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
            _validate_eval_event_provenance(
                self.event_type,
                self.provenance_config,
                self.output_payload,
            )
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
    output_payload: dict[str, Any] | None,
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
            (
                "policy",
                "task_id",
                "task_index",
                "attempt_index",
                "eval_attempt_id",
            ),
        )
    if event_type == "eval_attempt_finished":
        _require_provenance_fields(
            event_type,
            provenance,
            (
                "policy",
                "task_id",
                "task_index",
                "attempt_index",
                "eval_attempt_id",
            ),
        )
        _require_any_provenance_field(
            event_type,
            provenance,
            ("scorer_attempt_id", "agent_attempt_id"),
        )
        _validate_eval_attempt_finished_payload_provenance(
            event_type,
            provenance,
            output_payload,
        )


def _validate_replay_event_provenance(
    event_type: TraceEventType,
    provenance: ReplayTraceProvenance,
) -> None:
    if event_type == "source_manifest_loaded":
        _require_exactly_one_provenance_field(
            event_type,
            provenance,
            (
                "source_eval_run_id",
                "source_agent_attempt_id",
            ),
        )
        _forbid_provenance_fields(
            event_type,
            provenance,
            (
                "source_eval_attempt_id",
                "source_scorer_attempt_id",
                "replayed_scorer_attempt_id",
                "replayed_agent_attempt_id",
            ),
        )
    if event_type in {"source_attempt_loaded", "fresh_attempt_started"}:
        _require_provenance_fields(event_type, provenance, ("task_id",))
        if provenance.source_eval_run_id is not None:
            _require_provenance_fields(
                event_type,
                provenance,
                ("source_eval_attempt_id",),
            )
        _require_any_provenance_field(
            event_type,
            provenance,
            ("source_scorer_attempt_id", "source_agent_attempt_id"),
        )
    if event_type in {"fresh_attempt_finished", "comparison_recorded"}:
        _require_provenance_fields(event_type, provenance, ("task_id",))
        if provenance.source_eval_run_id is not None:
            _require_provenance_fields(
                event_type,
                provenance,
                ("source_eval_attempt_id",),
            )
        _require_any_provenance_field(
            event_type,
            provenance,
            ("source_scorer_attempt_id", "source_agent_attempt_id"),
        )
        _require_any_provenance_field(
            event_type,
            provenance,
            ("replayed_scorer_attempt_id", "replayed_agent_attempt_id"),
        )
        _require_replayed_attempt_id_pairs(event_type, provenance)


def _validate_eval_attempt_finished_payload_provenance(
    event_type: TraceEventType,
    provenance: EvalTraceProvenance,
    output_payload: dict[str, Any] | None,
) -> None:
    if output_payload is None:
        return

    artifact_type = output_payload.get("artifact_type")
    if artifact_type == "scorer_attempt":
        _require_provenance_fields(event_type, provenance, ("scorer_attempt_id",))
        if provenance.agent_attempt_id is not None:
            raise ValueError(
                "scorer eval attempt payload cannot include agent_attempt_id"
            )
        return

    if artifact_type != "agent_attempt":
        return

    _require_provenance_fields(event_type, provenance, ("agent_attempt_id",))
    agent_payload = output_payload.get("agent")
    if not isinstance(agent_payload, dict):
        return
    scorer_payload = agent_payload.get("scorer_attempt")
    if scorer_payload is None:
        if agent_payload.get("status") == "scored":
            raise ValueError(
                "scored agent attempt payload requires agent.scorer_attempt"
            )
        return
    if not isinstance(scorer_payload, dict):
        raise ValueError("agent scorer_attempt payload must be an object")

    nested_scorer_attempt_id = scorer_payload.get("scorer_attempt_id")
    if not isinstance(nested_scorer_attempt_id, str) or not nested_scorer_attempt_id:
        raise ValueError("agent scorer_attempt payload requires scorer_attempt_id")
    _require_provenance_fields(event_type, provenance, ("scorer_attempt_id",))
    if provenance.scorer_attempt_id != nested_scorer_attempt_id:
        raise ValueError(
            "provenance.scorer_attempt_id must match "
            "agent.scorer_attempt.scorer_attempt_id"
        )


def _require_replayed_attempt_id_pairs(
    event_type: TraceEventType,
    provenance: ReplayTraceProvenance,
) -> None:
    if (
        provenance.source_scorer_attempt_id is not None
        and provenance.replayed_scorer_attempt_id is None
    ):
        raise ValueError(
            f"{event_type} provenance source_scorer_attempt_id requires "
            "replayed_scorer_attempt_id"
        )
    if (
        provenance.source_scorer_attempt_id is None
        and provenance.replayed_scorer_attempt_id is not None
    ):
        raise ValueError(
            f"{event_type} provenance replayed_scorer_attempt_id requires "
            "source_scorer_attempt_id"
        )
    if (
        provenance.source_agent_attempt_id is not None
        and provenance.replayed_agent_attempt_id is None
    ):
        raise ValueError(
            f"{event_type} provenance source_agent_attempt_id requires "
            "replayed_agent_attempt_id"
        )
    if (
        provenance.source_agent_attempt_id is None
        and provenance.replayed_agent_attempt_id is not None
    ):
        raise ValueError(
            f"{event_type} provenance replayed_agent_attempt_id requires "
            "source_agent_attempt_id"
        )

    scorer_pair = (
        provenance.source_scorer_attempt_id is not None
        and provenance.replayed_scorer_attempt_id is not None
    )
    agent_pair = (
        provenance.source_agent_attempt_id is not None
        and provenance.replayed_agent_attempt_id is not None
    )
    if scorer_pair == agent_pair:
        raise ValueError(
            f"{event_type} provenance must include exactly one complete "
            "source/replayed attempt id family"
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


def _forbid_provenance_fields(
    event_type: TraceEventType,
    provenance: BaseModel,
    field_names: tuple[str, ...],
) -> None:
    present = [
        field_name
        for field_name in field_names
        if getattr(provenance, field_name) is not None
    ]
    if not present:
        return
    present_fields = ", ".join(present)
    raise ValueError(f"{event_type} provenance forbids field(s): {present_fields}")


def _require_exactly_one_provenance_field(
    event_type: TraceEventType,
    provenance: BaseModel,
    field_names: tuple[str, ...],
) -> None:
    present = [
        field_name
        for field_name in field_names
        if getattr(provenance, field_name) is not None
    ]
    if len(present) == 1:
        return
    joined_fields = " or ".join(field_names)
    if not present:
        raise ValueError(
            f"{event_type} provenance is missing required field(s): {joined_fields}"
        )
    present_fields = ", ".join(present)
    raise ValueError(
        f"{event_type} provenance must include exactly one of {joined_fields}; "
        f"got {present_fields}"
    )


def _require_any_provenance_field(
    event_type: TraceEventType,
    provenance: BaseModel,
    field_names: tuple[str, ...],
) -> None:
    if any(getattr(provenance, field_name) is not None for field_name in field_names):
        return
    joined_fields = " or ".join(field_names)
    raise ValueError(
        f"{event_type} provenance is missing required field(s): {joined_fields}"
    )
