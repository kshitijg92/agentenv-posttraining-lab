from collections import defaultdict

from event_models import Event, Rollup, UserRollup


def rollup_events(events: list[Event]) -> Rollup:
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        direction = 1 if event.kind == "credit" else -1
        totals[event.user] += direction * event.amount_cents
        counts[event.user] += 1
    users = tuple(
        UserRollup(
            user=user,
            net_amount=f"{totals[user] / 100:.2f}",
            event_count=counts[user],
        )
        for user in sorted(totals)
    )
    return Rollup(event_count=len(events), users=users)
