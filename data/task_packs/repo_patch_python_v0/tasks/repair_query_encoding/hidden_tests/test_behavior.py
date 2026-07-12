import pytest

from query import encode_query


def test_sorts_keys_and_preserves_repeated_value_order() -> None:
    assert encode_query({"z": "last", "a": ["first", "second"]}) == (
        "a=first&a=second&z=last"
    )


def test_percent_encodes_rfc3986_and_unicode() -> None:
    assert encode_query({"a b": "x/y", "emoji": "☃"}) == (
        "a%20b=x%2Fy&emoji=%E2%98%83"
    )


def test_empty_mapping_and_sequence_emit_nothing() -> None:
    assert encode_query({}) == ""
    assert encode_query({"a": [], "b": "2"}) == "b=2"


@pytest.mark.parametrize(
    "params",
    [
        [],
        {1: "value"},
        {"a": "value", 1: "other"},
        {"a": 1},
        {"a": ["ok", 2]},
        {"a": {"unordered"}},
        {"a": b"bytes"},
    ],
)
def test_invalid_inputs_raise_value_error(params: object) -> None:
    with pytest.raises(ValueError):
        encode_query(params)  # type: ignore[arg-type]
