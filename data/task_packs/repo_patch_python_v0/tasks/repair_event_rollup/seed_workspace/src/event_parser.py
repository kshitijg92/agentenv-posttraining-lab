import json

from event_models import Event
from event_time import parse_timestamp


def parse_jsonl(text: str) -> list[Event]:
    if not isinstance(text, str):
        raise ValueError("jsonl_text must be a string")
    events: list[Event] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            events.append(
                Event(
                    event_id=str(raw["id"]),
                    user=str(raw["user"]),
                    kind=str(raw["kind"]),
                    amount_cents=round(float(raw["amount"]) * 100),
                    timestamp=parse_timestamp(raw["timestamp"]),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid event line") from exc
    return events
