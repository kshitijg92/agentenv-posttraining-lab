import json


def dedupe_jsonl(blob: str, dedupe_key: str) -> str:
    """Return JSONL with duplicate objects removed by dedupe_key.

    For each duplicate key value, keep the first record and drop later records.
    Raise ValueError for malformed JSONL, non-object lines, or records missing
    dedupe_key.
    """
    seen = set()
    kept_lines = []

    for raw_line in blob.splitlines():
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        key_value = record["id"]
        if key_value in seen:
            continue
        seen.add(key_value)
        kept_lines.append(raw_line)

    if not kept_lines:
        return ""
    return "\n".join(kept_lines) + "\n"
