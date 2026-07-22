from collections.abc import Iterable, Mapping

from inventory_models import ReservationResult
from inventory_validation import normalize_requests, validate_inventory


def reserve_inventory(
    inventory: Mapping[object, object],
    requests: Iterable[object],
) -> ReservationResult:
    stock = validate_inventory(inventory)
    requested = normalize_requests(requests)
    unknown = [sku for sku in requested if sku not in stock]
    if unknown:
        raise ValueError(f"unknown SKU: {unknown[0]}")

    shortfalls: dict[str, int] = {}
    for sku, quantity in requested.items():
        if quantity > stock[sku]:
            shortfalls[sku] = quantity - stock[sku]
            break
    if shortfalls:
        return ReservationResult(
            accepted=False,
            remaining=dict(stock),
            allocated={},
            shortfalls=shortfalls,
        )

    remaining = dict(stock)
    for sku, quantity in requested.items():
        remaining[sku] -= quantity
    return ReservationResult(
        accepted=True,
        remaining=remaining,
        allocated=dict(requested),
        shortfalls={},
    )
