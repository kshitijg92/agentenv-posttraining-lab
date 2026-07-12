import pytest

from chunking import chunk_records


def test_accepts_one_shot_iterable_and_materializes_once() -> None:
    consumed = 0

    def values():
        nonlocal consumed
        for value in range(5):
            consumed += 1
            yield value

    assert chunk_records(values(), 3) == [[0, 1, 2], [3, 4]]
    assert consumed == 5


def test_empty_input_returns_empty_list() -> None:
    assert chunk_records(iter(()), 2) == []


def test_chunks_are_fresh_lists() -> None:
    source = [1, 2, 3]
    chunks = chunk_records(source, 2)
    chunks[0].append(99)

    assert source == [1, 2, 3]
    assert chunks[1] == [3]


@pytest.mark.parametrize("size", [0, -1, True, False, 1.5, "2"])
def test_invalid_sizes_raise_value_error(size: object) -> None:
    with pytest.raises(ValueError):
        chunk_records([1, 2], size)  # type: ignore[arg-type]


def test_non_iterable_records_raise_value_error() -> None:
    with pytest.raises(ValueError):
        chunk_records(None, 2)  # type: ignore[arg-type]
