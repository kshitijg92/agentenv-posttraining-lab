from event_models import Event


def dedupe_events(events: list[Event]) -> list[Event]:
    seen: set[str] = set()
    unique: list[Event] = []
    for event in events:
        if event.event_id in seen:
            continue
        seen.add(event.event_id)
        unique.append(event)
    return unique
