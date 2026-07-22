import pytest

from env_assignments import parse_env_assignments


def test_decodes_quoted_escapes() -> None:
    text = 'MESSAGE="line\\nnext\\t\\"quoted\\"\\\\tail"'
    assert parse_env_assignments(text) == {
        "MESSAGE": 'line\nnext\t"quoted"\\tail'
    }


def test_unquoted_values_keep_equals_and_hash() -> None:
    assert parse_env_assignments("TOKEN=a=b#literal") == {
        "TOKEN": "a=b#literal"
    }


def test_empty_values_and_assignment_order() -> None:
    result = parse_env_assignments("Z=\nA=\"\"\nM=value")
    assert result == {"Z": "", "A": "", "M": "value"}
    assert list(result) == ["Z", "A", "M"]


@pytest.mark.parametrize(
    "text",
    [
        "missing",
        "lower=value",
        "1A=value",
        "A-B=value",
        "A=one\nA=two",
        'A=bad"quote',
        'A="bad"quote"',
        'A="unterminated',
        'A="value"tail',
        'A="bad\\q"',
        'A="bad\\"',
    ],
)
def test_malformed_assignments_raise_value_error(text: str) -> None:
    with pytest.raises(ValueError):
        parse_env_assignments(text)


def test_non_string_input_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_env_assignments(None)  # type: ignore[arg-type]
