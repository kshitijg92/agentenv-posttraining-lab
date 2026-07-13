import pytest

from record_batches import batch_records


def test_uses_utf8_bytes_instead_of_character_count() -> None:
    assert batch_records(["é", "a", "🙂", "b"], 3, 4) == [
        ["é", "a"],
        ["🙂"],
        ["b"],
    ]


def test_count_limit_can_split_before_byte_limit() -> None:
    assert batch_records(["a", "b", "c"], 2, 100) == [["a", "b"], ["c"]]


def test_accepts_generator_and_empty_input() -> None:
    assert batch_records((value for value in ["a", "bb"]), 5, 3) == [["a", "bb"]]
    assert batch_records(iter(()), 1, 1) == []


def test_does_not_mutate_source() -> None:
    source = ["a", "b"]
    assert batch_records(source, 1, 1) == [["a"], ["b"]]
    assert source == ["a", "b"]


@pytest.mark.parametrize(
    ("records", "max_items", "max_bytes"),
    [
        (["toolong"], 2, 3),
                    ([1], 2, 3),
                    (["\ud800"], 2, 3),
                    ("abc", 2, 3),
        (None, 2, 3),
        ([], 0, 3),
        ([], -1, 3),
        ([], True, 3),
        ([], 2, 0),
        ([], 2, False),
        ([], 2.0, 3),
    ],
)
def test_invalid_inputs_raise_value_error(
    records: object,
    max_items: object,
    max_bytes: object,
) -> None:
    with pytest.raises(ValueError):
        batch_records(records, max_items, max_bytes)  # type: ignore[arg-type]
