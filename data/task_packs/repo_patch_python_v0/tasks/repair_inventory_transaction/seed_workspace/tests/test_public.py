import pytest

from inventory_models import ReservationResult
from inventory_service import reserve_inventory


def test_successful_reservation() -> None:
    assert reserve_inventory(
        {"widget": 5, "gizmo": 2},
        [("widget", 3), ("gizmo", 1)],
    ) == ReservationResult(
        accepted=True,
        remaining={"widget": 2, "gizmo": 1},
        allocated={"widget": 3, "gizmo": 1},
        shortfalls={},
    )


def test_insufficient_reservation_is_rejected() -> None:
    assert reserve_inventory({"widget": 2}, [("widget", 3)]) == ReservationResult(
        accepted=False,
        remaining={"widget": 2},
        allocated={},
        shortfalls={"widget": 1},
    )


def test_invalid_quantity_raises_value_error() -> None:
    with pytest.raises(ValueError):
        reserve_inventory({"widget": 2}, [("widget", 0)])


def test_inputs_are_not_mutated() -> None:
    inventory = {"widget": 2}
    requests = [("widget", 1)]
    reserve_inventory(inventory, requests)
    assert inventory == {"widget": 2}
    assert requests == [("widget", 1)]
