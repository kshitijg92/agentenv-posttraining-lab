import pytest

from mathlib import normalize_ratio


def test_zero_denominator_raises_value_error() -> None:
    with pytest.raises(ValueError, match="denominator"):
        normalize_ratio(1, 0)


def test_non_integer_ratio_preserves_precision() -> None:
    assert normalize_ratio(1, 2) == pytest.approx(0.5)


def test_negative_denominator_matches_python_division() -> None:
    assert normalize_ratio(6, -3) == pytest.approx(-2.0)


def test_negative_numerator_matches_python_division() -> None:
    assert normalize_ratio(-6, 3) == pytest.approx(-2.0)


def test_double_negative_matches_python_division() -> None:
    assert normalize_ratio(-6, -3) == pytest.approx(2.0)


def test_float_inputs_work() -> None:
    assert normalize_ratio(1.5, 0.5) == pytest.approx(3.0)


def test_large_integer_ratio() -> None:
    assert normalize_ratio(10**12 + 1, 10**6) == pytest.approx((10**12 + 1) / 10**6)
