import json

from event_pipeline import Rollup, UserRollup, build_rollup


def line(**payload: object) -> str:
    return json.dumps(payload)


def test_simple_credit_and_debit_rollup() -> None:
    text = "\n".join(
        [
            line(id="e1", user="alice", kind="credit", amount="10.25", timestamp="2025-01-01T01:00:00Z"),
            line(id="e2", user="alice", kind="debit", amount="2.00", timestamp="2025-01-01T02:00:00Z"),
            line(id="e3", user="bob", kind="credit", amount="3", timestamp="2025-01-01T03:00:00Z"),
        ]
    )
    assert build_rollup(text, "2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z") == Rollup(
        event_count=3,
        users=(
            UserRollup("alice", "8.25", 2),
            UserRollup("bob", "3.00", 1),
        ),
    )


def test_blank_lines_are_ignored_and_window_filters() -> None:
    text = "\n\n" + line(
        id="old",
        user="alice",
        kind="credit",
        amount="1.00",
        timestamp="2024-12-31T23:59:59Z",
    )
    assert build_rollup(text, "2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z") == Rollup(0, ())
