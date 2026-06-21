import json
from pathlib import Path

from agentenv.tracing.schema import TraceEvent


def load_trace_events(path: Path) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"Blank trace line at {path}:{line_number}")
        raw_event = json.loads(line)
        if not isinstance(raw_event, dict):
            raise ValueError(f"Expected trace event object at {path}:{line_number}")
        events.append(TraceEvent.model_validate(raw_event))
    return events


def validate_trace_events(events: list[TraceEvent]) -> None:
    for expected_index, event in enumerate(events):
        if event.event_index != expected_index:
            raise ValueError(
                f"Trace event index mismatch: expected {expected_index}, "
                f"got {event.event_index}"
            )


def validate_trace_file(path: Path) -> None:
    validate_trace_events(load_trace_events(path))
