from typing import TypeVar


T = TypeVar("T")


def chunk_records(records: list[T], size: int) -> list[list[T]]:
    """Split records into ordered chunks."""
    return [records[index : index + size] for index in range(0, len(records), size)]
