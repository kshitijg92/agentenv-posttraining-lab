import pytest

from template import expand_template


def test_expands_adjacent_and_repeated_placeholders() -> None:
    assert expand_template("${a}${b}-${a}", {"a": "A", "b": "B"}) == "AB-A"


def test_dollar_escape_is_literal_and_can_escape_placeholder_syntax() -> None:
    assert expand_template("cost: $$5", {}) == "cost: $5"
    assert expand_template("$${name}", {"name": "Ada"}) == "${name}"


def test_replacement_values_are_not_scanned_again() -> None:
    values = {"a": "${b}", "b": "expanded"}
    assert expand_template("${a}", values) == "${b}"


def test_empty_template_is_valid() -> None:
    assert expand_template("", {"unused": "value"}) == ""


@pytest.mark.parametrize(
    "template",
    ["$", "$name", "${}", "${bad-name}", "${missing}", "${name"],
)
def test_malformed_or_unknown_placeholders_raise_value_error(template: str) -> None:
    with pytest.raises(ValueError):
        expand_template(template, {"name": "Ada"})


@pytest.mark.parametrize(
    ("template", "values"),
    [
        (None, {}),
        (1, {}),
        ("text", None),
        ("text", [("name", "Ada")]),
        ("text", {1: "Ada"}),
        ("text", {"name": 1}),
        ("text", {"bad-name": "Ada"}),
        ("text", {"α": "Ada"}),
    ],
)
def test_invalid_input_contract_raises_value_error(
    template: object,
    values: object,
) -> None:
    with pytest.raises(ValueError):
        expand_template(template, values)  # type: ignore[arg-type]
