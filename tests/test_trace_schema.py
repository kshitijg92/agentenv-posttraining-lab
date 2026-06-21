import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentenv.tracing.schema import (
    TRACE_SCHEMA_VERSION,
    AttemptTraceProvenance,
    ReplayTraceProvenance,
    TraceEvent,
)
from agentenv.tracing.validate import (
    load_trace_events,
    validate_trace_events,
    validate_trace_file,
)


def test_trace_event_schema_accepts_minimal_event() -> None:
    event = TraceEvent(
        schema_version=TRACE_SCHEMA_VERSION,
        event_index=0,
        timestamp_utc="2026-06-20T00:00:00Z",
        event_type="replay_started",
        provenance_config=ReplayTraceProvenance(replay_id="replay_001"),
    )

    assert event.schema_version == "trace_v0"
    assert event.event_index == 0
    assert event.input_payload is None
    assert isinstance(event.provenance_config, ReplayTraceProvenance)
    assert event.provenance_config.replay_id == "replay_001"


def test_trace_event_schema_accepts_optional_payloads() -> None:
    event = TraceEvent(
        schema_version=TRACE_SCHEMA_VERSION,
        event_index=1,
        timestamp_utc="2026-06-20T00:00:01Z",
        event_type="command_finished",
        provenance_config=AttemptTraceProvenance(
            run_id="run_001",
            attempt_id="attempt_001",
            task_id="task_001",
            phase="public_check",
            name="pytest_public",
        ),
        input_payload={"command": ["uv", "run", "pytest"]},
        output_payload={"returncode": 0},
        payload_refs={"stdout": "stdout.txt"},
        payload_hashes={"stdout": "xxh64:abc123"},
    )

    assert event.payload_refs == {"stdout": "stdout.txt"}
    assert event.payload_hashes == {"stdout": "xxh64:abc123"}
    assert isinstance(event.provenance_config, AttemptTraceProvenance)
    assert event.provenance_config.phase == "public_check"


def test_trace_event_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            {
                "schema_version": "trace_v999",
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "replay_started",
                "provenance_config": {"replay_id": "replay_001"},
            }
        )


def test_validate_trace_file_accepts_sequential_events(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    event_types = ["replay_started", "replay_finished"]
    trace_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "schema_version": TRACE_SCHEMA_VERSION,
                    "event_index": index,
                    "timestamp_utc": f"2026-06-20T00:00:0{index}Z",
                    "event_type": event_types[index],
                    "provenance_config": {"replay_id": "replay_001"},
                },
                sort_keys=True,
            )
            for index in range(2)
        )
        + "\n"
    )

    events = load_trace_events(trace_path)
    validate_trace_file(trace_path)

    assert [event.event_index for event in events] == [0, 1]


def test_validate_trace_events_rejects_nonsequential_indices() -> None:
    events = [
        TraceEvent(
            schema_version=TRACE_SCHEMA_VERSION,
            event_index=1,
            timestamp_utc="2026-06-20T00:00:00Z",
            event_type="replay_started",
            provenance_config=ReplayTraceProvenance(replay_id="replay_001"),
        )
    ]

    with pytest.raises(ValueError, match="Trace event index mismatch"):
        validate_trace_events(events)


def test_trace_event_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "typo_event",
                "provenance_config": {"replay_id": "replay_001"},
            }
        )


def test_trace_event_rejects_unknown_provenance_key() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "attempt_started",
                "provenance_config": {
                    "run_id": "run_001",
                    "attempt_id": "attempt_001",
                    "task_id": "task_001",
                    "surprise": "not_allowed",
                },
            }
        )


def test_trace_event_rejects_wrong_provenance_family() -> None:
    with pytest.raises(ValidationError, match="requires replay trace provenance"):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "replay_started",
                "provenance_config": {
                    "run_id": "run_001",
                    "attempt_id": "attempt_001",
                    "task_id": "task_001",
                },
            }
        )


def test_command_finished_requires_command_provenance() -> None:
    with pytest.raises(
        ValidationError,
        match="command_finished provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "command_finished",
                "provenance_config": {
                    "run_id": "run_001",
                    "attempt_id": "attempt_001",
                    "task_id": "task_001",
                },
            }
        )


def test_replay_attempt_event_requires_source_attempt_provenance() -> None:
    with pytest.raises(
        ValidationError,
        match="source_attempt_loaded provenance is missing required field",
    ):
        TraceEvent.model_validate(
            {
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_index": 0,
                "timestamp_utc": "2026-06-20T00:00:00Z",
                "event_type": "source_attempt_loaded",
                "provenance_config": {
                    "replay_id": "replay_001",
                    "source_eval_run_id": "eval_001",
                },
            }
        )
