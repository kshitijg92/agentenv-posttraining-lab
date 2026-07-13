import math

import pytest

from retry import retry_delays


def test_zero_attempts_returns_empty_schedule() -> None:
    assert retry_delays(1.0, 2.0, 0, 10.0) == []


def test_caps_immediately_and_handles_zero_and_unit_multiplier() -> None:
    assert retry_delays(20, 3, 3, 5) == [5.0, 5.0, 5.0]
    assert retry_delays(0, 1e300, 3, 5) == [0.0, 0.0, 0.0]
    assert retry_delays(2, 1, 3, 5) == [2.0, 2.0, 2.0]


def test_saturates_without_overflow() -> None:
    values = retry_delays(1e308, 2.0, 4, 1.7e308)
    assert values == [1e308, 1.7e308, 1.7e308, 1.7e308]
    assert all(math.isfinite(value) for value in values)


@pytest.mark.parametrize(
    ("base_delay", "multiplier", "attempts", "cap"),
    [
        (-1, 2, 3, 10),
        (1, 0.5, 3, 10),
        (1, 2, -1, 10),
        (True, 2, 3, 10),
        (1, True, 3, 10),
        (1, 2, True, 10),
        (1, 2, 3, True),
        (float("nan"), 2, 3, 10),
        (1, float("inf"), 3, 10),
        (1, 2, 3, float("inf")),
        (1, 2, 1.5, 10),
        ("1", 2, 3, 10),
        (10**400, 2, 3, 10),
    ],
)
def test_invalid_inputs_raise_value_error(
    base_delay: object,
    multiplier: object,
    attempts: object,
    cap: object,
) -> None:
    with pytest.raises(ValueError):
        retry_delays(base_delay, multiplier, attempts, cap)  # type: ignore[arg-type]
