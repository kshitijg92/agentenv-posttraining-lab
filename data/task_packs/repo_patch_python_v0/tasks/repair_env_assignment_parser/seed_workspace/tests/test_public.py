from env_assignments import parse_env_assignments


def test_parses_simple_assignments_and_comments() -> None:
    assert parse_env_assignments("A=one\n# ignored\nB = two\n") == {
        "A": "one",
        "B": "two",
    }
