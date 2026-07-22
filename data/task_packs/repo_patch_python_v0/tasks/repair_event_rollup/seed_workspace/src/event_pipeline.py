from event_dedupe import dedupe_events
from event_models import Rollup, UserRollup
from event_parser import parse_jsonl
from event_rollup import rollup_events
from event_time import parse_timestamp


def build_rollup(jsonl_text: str, start: str, end: str) -> Rollup:
    start_time = parse_timestamp(start)
    end_time = parse_timestamp(end)
    if start_time > end_time:
        raise ValueError("start must not follow end")
    events = parse_jsonl(jsonl_text)
    in_window = [
        event for event in events if start_time <= event.timestamp < end_time
    ]
    return rollup_events(dedupe_events(in_window))


__all__ = ["Rollup", "UserRollup", "build_rollup"]
