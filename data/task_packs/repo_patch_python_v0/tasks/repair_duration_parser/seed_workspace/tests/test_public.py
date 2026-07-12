from duration import parse_duration


def test_parses_integer_seconds() -> None:
    assert parse_duration("2s") == 2.0
