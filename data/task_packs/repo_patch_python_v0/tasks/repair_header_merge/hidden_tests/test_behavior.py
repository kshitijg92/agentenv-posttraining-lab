import pytest

from header_tools import merge_headers


def test_case_insensitive_override_reuses_default_position() -> None:
    result = merge_headers(
        {"Accept": "json", "Content-Type": "text/plain", "X-Last": "1"},
        {"content-type": "application/json", "x-new": "2"},
    )

    assert list(result.items()) == [
        ("Accept", "json"),
        ("content-type", "application/json"),
        ("X-Last", "1"),
        ("x-new", "2"),
    ]


def test_inputs_are_not_mutated_and_output_is_fresh() -> None:
    defaults = {"A": "1"}
    overrides = {"a": "2"}

    result = merge_headers(defaults, overrides)
    result["extra"] = "3"

    assert defaults == {"A": "1"}
    assert overrides == {"a": "2"}


@pytest.mark.parametrize(
    ("defaults", "overrides"),
    [
        ({"A": "1", "a": "2"}, {}),
        ({}, {"B": "1", "b": "2"}),
        ({1: "value"}, {}),
        ({"A": 1}, {}),
        ([], {}),
    ],
)
def test_invalid_inputs_raise_value_error(defaults: object, overrides: object) -> None:
    with pytest.raises(ValueError):
        merge_headers(defaults, overrides)  # type: ignore[arg-type]
