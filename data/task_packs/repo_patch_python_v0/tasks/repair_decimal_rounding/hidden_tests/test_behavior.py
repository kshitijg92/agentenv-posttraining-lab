import pytest

from decimal_format import round_decimal


def test_avoids_binary_float_rounding_error() -> None:
    assert round_decimal("2.675", 2) == "2.68"


def test_uses_half_even_ties() -> None:
    assert round_decimal("2.345", 2) == "2.34"
    assert round_decimal("2.355", 2) == "2.36"


def test_preserves_fixed_width_and_large_integer_precision() -> None:
    assert round_decimal("12345678901234567890.1", 3) == "12345678901234567890.100"
    assert round_decimal("12.9", 0) == "13"


def test_normalizes_negative_zero() -> None:
    assert round_decimal("-0.004", 2) == "0.00"
    assert round_decimal("-0", 0) == "0"


@pytest.mark.parametrize(
    ("value", "places"),
    [
        (" 1.0", 2),
        ("1.", 2),
        (".5", 2),
        ("1e3", 2),
        ("NaN", 2),
        ("Infinity", 2),
        ("", 2),
        (None, 2),
        ("1.0", True),
        ("1.0", -1),
        ("1.0", 7),
        ("1.0", 2.0),
    ],
)
def test_invalid_inputs_raise_value_error(value: object, places: object) -> None:
    with pytest.raises(ValueError):
        round_decimal(value, places)  # type: ignore[arg-type]
