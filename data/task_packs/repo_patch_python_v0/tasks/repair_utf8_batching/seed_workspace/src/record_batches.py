def batch_records(
    records: list[str],
    max_items: int,
    max_bytes: int,
) -> list[list[str]]:
    """Greedily batch strings by count and character length."""
    batches: list[list[str]] = []
    current: list[str] = []
    current_size = 0
    for record in records:
        if current and (
            len(current) >= max_items
            or current_size + len(record) > max_bytes
        ):
            batches.append(current)
            current = []
            current_size = 0
        current.append(record)
        current_size += len(record)
    if current:
        batches.append(current)
    return batches
