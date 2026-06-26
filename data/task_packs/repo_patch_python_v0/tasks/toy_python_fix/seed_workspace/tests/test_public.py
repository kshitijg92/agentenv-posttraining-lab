from mathlib import normalize_ratio


def test_simple_positive_ratio() -> None:
    assert normalize_ratio(6, 3) == 2.0
