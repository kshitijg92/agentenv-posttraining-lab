from decimal_format import round_decimal


def test_rounds_simple_decimal() -> None:
    assert round_decimal("1.26", 1) == "1.3"
