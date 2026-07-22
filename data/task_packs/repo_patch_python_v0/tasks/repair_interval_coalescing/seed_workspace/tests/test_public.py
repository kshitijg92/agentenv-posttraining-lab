from intervals import coalesce_intervals


def test_merges_sorted_overlapping_intervals() -> None:
    assert coalesce_intervals([(1, 3), (3, 5), (8, 9)]) == [(1, 5), (8, 9)]
