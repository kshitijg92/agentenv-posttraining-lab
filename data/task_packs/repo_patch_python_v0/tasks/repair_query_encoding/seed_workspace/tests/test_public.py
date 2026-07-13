from query import encode_query


def test_encodes_simple_ascii_scalars() -> None:
    assert encode_query({"a": "1", "b": "two"}) == "a=1&b=two"
