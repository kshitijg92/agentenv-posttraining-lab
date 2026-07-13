import pytest

from duration import parse_duration


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0ms", 0.0),
        ("250ms", 0.25),
        ("1.5s", 1.5),
        ("2m", 120.0),
        ("1.25h", 4500.0),
    ],
)
def test_converts_supported_units(value: str, expected: float) -> None:
    assert parse_duration(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        " 1s",
        "1s ",
        "+1s",
        "-1s",
        "1e3s",
        ".5s",
        "1.s",
        "1",
        "s",
        "NaNs",
        "infs",
        "1d",
        1,
        None,
    ],
)
def test_invalid_values_raise_value_error(value: object) -> None:
    with pytest.raises(ValueError):
        parse_duration(value)  # type: ignore[arg-type]


def test_numeric_overflow_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_duration(("9" * 400) + "s")
