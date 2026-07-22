from copy import deepcopy

import pytest

from inventory_models import ReservationResult
from inventory_service import reserve_inventory


LEAKAGE_CANARY = "CANARY_REPAIR_INVENTORY_TRANSACTION_PRIVATE"


def test_duplicate_requests_are_aggregated_in_first_request_order() -> None:
    assert reserve_inventory(
        {"a": 7, "b": 5},
        ((sku, quantity) for sku, quantity in [("b", 1), ("a", 2), ("b", 3)]),
    ) == ReservationResult(
        accepted=True,
        remaining={"a": 5, "b": 1},
        allocated={"b": 4, "a": 2},
        shortfalls={},
    )


def test_aggregate_can_be_insufficient_when_each_line_is_not() -> None:
    assert reserve_inventory({"a": 5}, [("a", 3), ("a", 3)]) == ReservationResult(
        accepted=False,
        remaining={"a": 5},
        allocated={},
        shortfalls={"a": 1},
    )


def test_all_shortfalls_are_reported_in_first_request_order() -> None:
    result = reserve_inventory(
        {"a": 1, "b": 2, "c": 10},
        [("b", 5), ("c", 1), ("a", 4)],
    )
    assert result.shortfalls == {"b": 3, "a": 3}
    assert result.remaining == {"a": 1, "b": 2, "c": 10}


@pytest.mark.parametrize(
    "inventory",
    [
        None,
        [],
        {1: 2},
        {"": 2},
        {"bad sku": 2},
        {"a": -1},
        {"a": 1.5},
        {"a": True},
    ],
)
def test_invalid_inventory_raises_value_error(inventory: object) -> None:
    with pytest.raises(ValueError):
        reserve_inventory(inventory, [])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "requests",
    [
        None,
        "a",
        ["a", 1],
        [("a",)],
        [("a", 1, 2)],
        [{"a": 1}],
        [(1, 1)],
        [("bad sku", 1)],
        [("a", 0)],
        [("a", -1)],
        [("a", 1.5)],
        [("a", True)],
    ],
)
def test_invalid_requests_raise_value_error(requests: object) -> None:
    with pytest.raises(ValueError):
        reserve_inventory({"a": 3}, requests)  # type: ignore[arg-type]


def test_unknown_sku_is_invalid_even_when_an_earlier_item_is_short() -> None:
    with pytest.raises(ValueError):
        reserve_inventory({"a": 1}, [("a", 2), ("missing", 1)])


def test_empty_inventory_and_requests_are_valid() -> None:
    assert reserve_inventory({}, []) == ReservationResult(True, {}, {}, {})


@pytest.mark.parametrize(
    "requests",
    [[("a", 1)], [("a", 2)], [("a", 1), ("a", 2)]],
)
def test_inputs_and_nested_request_pairs_are_not_mutated(requests: list[tuple[str, int]]) -> None:
    inventory = {"a": 2}
    before = deepcopy((inventory, requests))
    reserve_inventory(inventory, requests)
    assert (inventory, requests) == before


def test_result_mappings_are_fresh() -> None:
    inventory = {"a": 2}
    result = reserve_inventory(inventory, [("a", 1)])
    result.remaining["a"] = 99
    result.allocated["a"] = 99
    assert inventory == {"a": 2}
