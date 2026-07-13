def select_latest(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep the last record observed for each id."""
    latest: dict[object, dict[str, object]] = {}
    for record in records:
        latest[record["id"]] = record
    return list(latest.values())
