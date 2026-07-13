import pytest

from record_versions import select_latest


def test_selects_highest_version_when_input_is_out_of_order() -> None:
    records = [
        {"id": "a", "version": 3, "payload": "new"},
        {"id": "a", "version": 1, "payload": "old"},
    ]
    assert select_latest(records) == [
        {"id": "a", "version": 3, "payload": "new"}
    ]


def test_preserves_first_id_order_and_accepts_generator() -> None:
    records = [
        {"id": "b", "version": 1, "payload": "b1"},
        {"id": "a", "version": 2, "payload": "a2"},
        {"id": "b", "version": 4, "payload": "b4"},
    ]
    assert select_latest((record for record in records)) == [
        {"id": "b", "version": 4, "payload": "b4"},
        {"id": "a", "version": 2, "payload": "a2"},
    ]


def test_returns_fresh_dicts_without_mutating_inputs() -> None:
    record = {"id": "a", "version": 1, "payload": []}
    result = select_latest([record])
    assert result[0] is not record
    assert record == {"id": "a", "version": 1, "payload": []}


def test_empty_input_returns_empty_list() -> None:
    assert select_latest(iter(())) == []


@pytest.mark.parametrize(
    "records",
    [
        None,
        "records",
        [1],
        [{"id": "a", "version": 1}],
        [{"id": "a", "version": 1, "payload": None, "extra": 2}],
        [{"id": "", "version": 1, "payload": None}],
        [{"id": 1, "version": 1, "payload": None}],
        [{"id": "a", "version": True, "payload": None}],
        [{"id": "a", "version": -1, "payload": None}],
        [{"id": "a", "version": 1.0, "payload": None}],
        [
            {"id": "a", "version": 1, "payload": "first"},
            {"id": "a", "version": 1, "payload": "duplicate"},
        ],
    ],
)
def test_invalid_records_raise_value_error(records: object) -> None:
    with pytest.raises(ValueError):
        select_latest(records)  # type: ignore[arg-type]
