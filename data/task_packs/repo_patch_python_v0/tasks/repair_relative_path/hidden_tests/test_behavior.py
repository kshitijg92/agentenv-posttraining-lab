import pytest

from relative_path import normalize_relative_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a/b/../c", "a/c"),
        ("a//b///c/", "a/b/c"),
        ("a/./b", "a/b"),
        ("a/b/../../c", "c"),
        ("..hidden/file", "..hidden/file"),
    ],
)
def test_normalizes_valid_relative_paths(path: str, expected: str) -> None:
    assert normalize_relative_path(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "./",
        "a/..",
        "../secret",
        "a/../../secret",
        "/absolute/path",
        "//server/path",
        "a\\b",
        "a/\x00b",
    ],
)
def test_invalid_paths_raise_value_error(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_relative_path(path)


@pytest.mark.parametrize("path", [None, 1, b"a/b"])
def test_non_string_paths_raise_value_error(path: object) -> None:
    with pytest.raises(ValueError):
        normalize_relative_path(path)  # type: ignore[arg-type]
