import pytest

from semver import compare_semver


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("1.10.0", "1.2.0", 1),
        ("2.0.0", "10.0.0", -1),
        ("1.0.1", "1.0.0", 1),
        ("999999999999999999999.0.0", "2.0.0", 1),
        ("1.0.0", "1.0.0-alpha", 1),
        ("1.0.0-alpha", "1.0.0-alpha.1", -1),
        ("1.0.0-alpha.2", "1.0.0-alpha.10", -1),
        ("1.0.0-1", "1.0.0-alpha", -1),
        ("1.0.0-beta", "1.0.0-alpha", 1),
        ("1.0.0-x-y", "1.0.0-x-y", 0),
    ],
)
def test_semver_precedence(left: str, right: str, expected: int) -> None:
    assert compare_semver(left, right) == expected
    assert compare_semver(right, left) == -expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1",
        "1.0",
        "01.0.0",
        "1.00.0",
        "1.0.00",
        "1.0.0-",
        "1.0.0-alpha..1",
        "1.0.0-01",
        "1.0.0+build",
        "1.0.0-α",
        " 1.0.0",
        "1.0.0 ",
    ],
)
def test_invalid_versions_raise_value_error(value: str) -> None:
    with pytest.raises(ValueError):
        compare_semver(value, "1.0.0")
    with pytest.raises(ValueError):
        compare_semver("1.0.0", value)


@pytest.mark.parametrize("value", [None, 1, ["1.0.0"]])
def test_non_string_versions_raise_value_error(value: object) -> None:
    with pytest.raises(ValueError):
        compare_semver(value, "1.0.0")  # type: ignore[arg-type]
