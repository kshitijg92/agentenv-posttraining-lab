from chunking import chunk_records


def test_chunks_a_list_and_keeps_short_tail() -> None:
    assert chunk_records([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
