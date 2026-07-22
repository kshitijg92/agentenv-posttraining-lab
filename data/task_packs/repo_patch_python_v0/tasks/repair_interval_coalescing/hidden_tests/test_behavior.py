import pytest

from intervals import coalesce_intervals


def test_sorts_then_merges_overlaps_and_shared_endpoints() -> None:
    assert coalesce_intervals([(5, 7), (1, 3), (3, 4), (6, 8)]) == [
        (1, 4),
        (5, 8),
    ]


def test_merges_contained_and_zero_width_intervals() -> None:
    assert coalesce_intervals([(1, 10), (2, 3), (10, 10)]) == [(1, 10)]


def test_does_not_merge_merely_adjacent_integer_ranges() -> None:
    assert coalesce_intervals([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]


def test_accepts_generators_and_does_not_mutate_input() -> None:
    source = [[4, 5], [1, 2], [2, 3]]
    original = [item.copy() for item in source]
    pairs = ((value for value in item) for item in source)
    assert coalesce_intervals(pairs) == [(1, 3), (4, 5)]  # type: ignore[arg-type]
    assert source == original


def test_empty_iterable_returns_empty_list() -> None:
    assert coalesce_intervals(iter(())) == []  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "intervals",
    [
        None,
        1,
        "1,2",
        [(1,)],
        [(1, 2, 3)],
        [(True, 2)],
        [(1, False)],
        [(1.0, 2)],
        [(3, 2)],
        [None],
    ],
)
def test_invalid_intervals_raise_value_error(intervals: object) -> None:
    with pytest.raises(ValueError):
        coalesce_intervals(intervals)  # type: ignore[arg-type]
