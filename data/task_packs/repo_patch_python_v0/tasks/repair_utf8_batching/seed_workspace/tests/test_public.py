from record_batches import batch_records


def test_batches_ascii_records_by_both_limits() -> None:
    assert batch_records(["aa", "b", "ccc"], 2, 4) == [
        ["aa", "b"],
        ["ccc"],
    ]
