import json

import pytest

from jsonl_tools import dedupe_jsonl


def _rows(blob: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in blob.splitlines()]


def test_uses_caller_supplied_dedupe_key() -> None:
    blob = "\n".join(
        [
            '{"id": "1", "email": "a@example.com", "name": "first"}',
            '{"id": "2", "email": "b@example.com", "name": "second"}',
            '{"id": "3", "email": "a@example.com", "name": "duplicate"}',
        ]
    )

    result = dedupe_jsonl(blob, dedupe_key="email")

    assert _rows(result) == [
        {"id": "1", "email": "a@example.com", "name": "first"},
        {"id": "2", "email": "b@example.com", "name": "second"},
    ]


def test_preserves_first_seen_order_for_non_adjacent_duplicates() -> None:
    blob = "\n".join(
        [
            '{"request_id": "r1", "step": 1}',
            '{"request_id": "r2", "step": 2}',
            '{"request_id": "r3", "step": 3}',
            '{"request_id": "r2", "step": 4}',
            '{"request_id": "r1", "step": 5}',
        ]
    )

    result = dedupe_jsonl(blob, dedupe_key="request_id")

    assert _rows(result) == [
        {"request_id": "r1", "step": 1},
        {"request_id": "r2", "step": 2},
        {"request_id": "r3", "step": 3},
    ]


def test_missing_dedupe_key_raises_value_error() -> None:
    blob = "\n".join(
        [
            '{"id": "1", "email": "a@example.com"}',
            '{"id": "2"}',
        ]
    )

    with pytest.raises(ValueError):
        dedupe_jsonl(blob, dedupe_key="email")


def test_malformed_json_line_raises_value_error() -> None:
    blob = "\n".join(
        [
            '{"id": "1"}',
            '{"id":',
        ]
    )

    with pytest.raises(ValueError):
        dedupe_jsonl(blob, dedupe_key="id")


def test_non_object_json_line_raises_value_error() -> None:
    blob = "\n".join(
        [
            '{"id": "1"}',
            '["not", "an", "object"]',
        ]
    )

    with pytest.raises(ValueError):
        dedupe_jsonl(blob, dedupe_key="id")
