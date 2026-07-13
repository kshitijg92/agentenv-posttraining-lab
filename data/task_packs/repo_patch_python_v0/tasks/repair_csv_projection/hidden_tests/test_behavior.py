import pytest

from csv_projection import project_csv


def test_handles_quoted_commas_and_requested_order() -> None:
    source = 'name,note\nAda,"hello,world"\n'
    assert project_csv(source, ["note", "name"]) == (
        'note,name\n"hello,world",Ada\n'
    )


def test_handles_newlines_inside_quoted_fields() -> None:
    source = 'name,note\nAda,"line one\nline two"\n'
    assert project_csv(source, ["note"]) == 'note\n"line one\nline two"\n'


def test_accepts_header_only_and_generator_columns() -> None:
    columns = (column for column in ["b", "a"])
    assert project_csv("a,b\n", columns) == "b,a\n"  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "columns"),
    [
        ("", ["a"]),
        (",b\n1,2\n", ["b"]),
        ("a,a\n1,2\n", ["a"]),
        ("a,b\n1\n", ["a"]),
        ("a,b\n1,2,3\n", ["a"]),
        ("a,b\n1,2\n", []),
        ("a,b\n1,2\n", ["a", "a"]),
        ("a,b\n1,2\n", ["missing"]),
        ("a,b\n1,2\n", "a"),
        ("a,b\n1,2\n", [""]),
        ("a,b\n1,2\n", [1]),
        ('a,b\n"unterminated,2\n', ["a"]),
        ("a,b\n1,\x002\n", ["a"]),
    ],
)
def test_invalid_inputs_raise_value_error(text: str, columns: object) -> None:
    with pytest.raises(ValueError):
        project_csv(text, columns)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", [None, b"a,b\n1,2\n", 1])
def test_non_string_text_raises_value_error(text: object) -> None:
    with pytest.raises(ValueError):
        project_csv(text, ["a"])  # type: ignore[arg-type]
