from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TRACE_SCHEMA_VERSION = "trace_v0"
TraceSchemaVersion = Literal["trace_v0"]
TraceEventType = Literal[
    "attempt_started",
    "command_finished",
    "attempt_finished",
    "replay_started",
    "source_run_manifest_loaded",
    "source_attempt_loaded",
    "fresh_attempt_started",
    "fresh_attempt_finished",
    "comparison_recorded",
    "replay_finished",
    "replay_error",
]


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: TraceSchemaVersion
    event_index: int = Field(ge=0)
    timestamp_utc: str = Field(min_length=1)
    event_type: TraceEventType
    provenance_config: dict[str, Any]
    input_payload: dict[str, Any] | None = None
    output_payload: dict[str, Any] | None = None
    payload_refs: dict[str, str] | None = None
    payload_hashes: dict[str, str] | None = None
