from json_pointer import resolve_pointer


def test_resolves_simple_mapping_key() -> None:
    assert resolve_pointer({"name": "Ada"}, "/name") == "Ada"
