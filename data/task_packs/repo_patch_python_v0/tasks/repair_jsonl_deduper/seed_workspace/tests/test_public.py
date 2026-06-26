import json

from jsonl_tools import dedupe_jsonl


def test_dedupes_duplicate_ids_and_keeps_first_record() -> None:
    blob = "\n".join(
        [
            '{"id": "a", "name": "first"}',
            '{"id": "b", "name": "only"}',
            '{"id": "a", "name": "second"}',
        ]
    )

    result = dedupe_jsonl(blob, dedupe_key="id")
    rows = [json.loads(line) for line in result.splitlines()]

    assert rows == [
        {"id": "a", "name": "first"},
        {"id": "b", "name": "only"},
    ]
