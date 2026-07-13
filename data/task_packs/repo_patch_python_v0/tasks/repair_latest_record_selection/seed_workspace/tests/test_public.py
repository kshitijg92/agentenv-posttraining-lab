from record_versions import select_latest


def test_keeps_latest_when_versions_arrive_in_order() -> None:
    records = [
        {"id": "a", "version": 1, "payload": "old"},
        {"id": "a", "version": 2, "payload": "new"},
    ]
    assert select_latest(records) == [
        {"id": "a", "version": 2, "payload": "new"}
    ]
