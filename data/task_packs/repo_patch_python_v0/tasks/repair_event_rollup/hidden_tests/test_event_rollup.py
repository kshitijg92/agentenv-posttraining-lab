import json

import pytest

from event_pipeline import Rollup, UserRollup, build_rollup


LEAKAGE_CANARY = "CANARY_REPAIR_EVENT_ROLLUP_PRIVATE"
START = "2025-01-01T00:00:00Z"
END = "2025-01-02T00:00:00Z"


def line(**overrides: object) -> str:
    payload = {
        "id": "event-1",
        "user": "user-1",
        "kind": "credit",
        "amount": "1.00",
        "timestamp": "2025-01-01T12:00:00Z",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_large_decimal_values_remain_exact() -> None:
    text = "\n".join(
        [
            line(id="a", amount="9007199254740992.01"),
            line(id="b", amount="0.02"),
        ]
    )
    assert build_rollup(text, START, END).users == (
        UserRollup("user-1", "9007199254740992.03", 2),
    )


def test_unbounded_integer_digits_do_not_depend_on_decimal_context() -> None:
    huge = "9" * 80
    text = "\n".join(
        [
            line(id="a", amount=f"{huge}.01"),
            line(id="b", amount="0.02"),
        ]
    )
    assert build_rollup(text, START, END).users == (
        UserRollup("user-1", f"{huge}.03", 2),
    )


def test_identical_duplicates_collapse_to_first_occurrence() -> None:
    event = line(id="same", user="zeta", amount="2.50")
    assert build_rollup(f"{event}\n{event}", START, END) == Rollup(
        1,
        (UserRollup("zeta", "2.50", 1),),
    )


def test_conflicting_duplicate_raises() -> None:
    text = "\n".join([line(id="same", amount="1.00"), line(id="same", amount="2.00")])
    with pytest.raises(ValueError):
        build_rollup(text, START, END)


def test_conflicting_duplicate_outside_window_still_raises() -> None:
    text = "\n".join(
        [
            line(id="same", amount="1.00", timestamp="2024-01-01T00:00:00Z"),
            line(id="same", amount="2.00", timestamp="2024-01-01T00:00:00Z"),
        ]
    )
    with pytest.raises(ValueError):
        build_rollup(text, START, END)


def test_user_order_is_first_in_window_appearance_not_alphabetical() -> None:
    text = "\n".join(
        [
            line(id="z1", user="zeta", amount="1.00"),
            line(id="a1", user="alpha", amount="2.00"),
            line(id="z2", user="zeta", kind="debit", amount="0.25"),
        ]
    )
    assert build_rollup(text, START, END).users == (
        UserRollup("zeta", "0.75", 2),
        UserRollup("alpha", "2.00", 1),
    )


def test_window_is_start_inclusive_and_end_exclusive() -> None:
    text = "\n".join(
        [
            line(id="at-start", timestamp=START),
            line(id="at-end", timestamp=END),
        ]
    )
    assert build_rollup(text, START, END).event_count == 1


def test_equal_window_bounds_are_valid_and_empty() -> None:
    assert build_rollup(line(), START, START) == Rollup(0, ())


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"id": "x"}),
        line(extra=True),
        line(id="bad id"),
        line(user=""),
        line(kind="refund"),
        line(amount=1),
        line(amount="0"),
        line(amount="-1.00"),
        line(amount="+1.00"),
        line(amount=".50"),
        line(amount="1.234"),
        line(amount="1e2"),
        line(timestamp="2025-02-30T00:00:00Z"),
        line(timestamp="2025-01-01T00:00:00+00:00"),
    ],
)
def test_malformed_event_lines_raise_value_error(text: object) -> None:
    with pytest.raises(ValueError):
        build_rollup(text, START, END)  # type: ignore[arg-type]


def test_malformed_event_outside_window_is_still_validated() -> None:
    text = "\n".join(
        [
            line(id="old", timestamp="2024-01-01T00:00:00Z"),
            line(id="bad", amount="not-a-decimal", timestamp="2024-01-01T00:00:00Z"),
        ]
    )
    with pytest.raises(ValueError):
        build_rollup(text, START, END)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2025-01-01", END),
        (START, "2025-01-02T00:00:00+00:00"),
        (END, START),
    ],
)
def test_invalid_window_raises(start: str, end: str) -> None:
    with pytest.raises(ValueError):
        build_rollup("", start, end)
