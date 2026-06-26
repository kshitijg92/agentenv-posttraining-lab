import json
import sys
from pathlib import Path


SUCCESS = 0
USAGE_ERROR = 2
MISSING_FILE = 3
INVALID_INPUT = 4


def load_jsonl(path: Path) -> list[dict[str, str]]:
    """Load JSONL records.

    Each line must be a JSON object with string id and string status.
    Duplicate ids are invalid.
    Raise FileNotFoundError when the input path does not exist.
    Raise ValueError for malformed JSONL, invalid record schema, or duplicate ids.
    """
    records = []
    for raw_line in path.read_text().splitlines():
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        records.append(record)
    return records


def summarize_records(records: list[dict[str, str]]) -> dict[str, int]:
    """Return counts by status."""
    counts: dict[str, int] = {}
    for record in records:
        status = record["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Usage errors return 2, missing input files return 3, invalid input returns 4,
    and success returns 0. Expected user/input errors should not print tracebacks.
    """
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m validate_records INPUT.jsonl", file=sys.stderr)
        return 1

    try:
        records = load_jsonl(Path(args[0]))
        print(json.dumps(summarize_records(records)))
        return SUCCESS
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
