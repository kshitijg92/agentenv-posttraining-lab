import pytest

from json_pointer import resolve_pointer


def test_empty_pointer_returns_original_document() -> None:
    document = {"items": [1, 2]}
    assert resolve_pointer(document, "") is document


def test_decodes_escapes_and_empty_mapping_keys() -> None:
    document = {"a/b": {"m~n": {"": "value"}}}
    assert resolve_pointer(document, "/a~1b/m~0n/") == "value"


def test_traverses_lists_with_canonical_indexes() -> None:
    document = {"items": [{"id": "first"}, {"id": "second"}]}
    assert resolve_pointer(document, "/items/1/id") == "second"


def test_does_not_mutate_document() -> None:
    document = {"items": ["a", "b"]}
    assert resolve_pointer(document, "/items/0") == "a"
    assert document == {"items": ["a", "b"]}


@pytest.mark.parametrize(
    "pointer",
    [
        "name",
        "/missing",
        "/a~",
        "/a~2b",
        "/items/-",
        "/items/01",
        "/items/-1",
        "/items/2",
        "/items/one",
        "/scalar/next",
    ],
)
def test_invalid_pointers_raise_value_error(pointer: str) -> None:
    document = {"name": "Ada", "items": ["a", "b"], "scalar": 3}
    with pytest.raises(ValueError):
        resolve_pointer(document, pointer)


def test_non_string_pointer_raises_value_error() -> None:
    with pytest.raises(ValueError):
        resolve_pointer({}, None)  # type: ignore[arg-type]
