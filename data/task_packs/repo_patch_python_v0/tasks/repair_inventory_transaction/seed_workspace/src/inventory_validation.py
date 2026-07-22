import re
from collections.abc import Iterable, Mapping


_SKU_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def validate_inventory(inventory: object) -> dict[str, int]:
    if not isinstance(inventory, Mapping):
        raise ValueError("inventory must be a mapping")
    validated: dict[str, int] = {}
    for sku, quantity in inventory.items():
        if not isinstance(sku, str) or _SKU_RE.fullmatch(sku) is None:
            raise ValueError("invalid inventory SKU")
        if not isinstance(quantity, int) or quantity < 0:
            raise ValueError("invalid inventory quantity")
        validated[sku] = quantity
    return validated


def normalize_requests(requests: Iterable[object]) -> dict[str, int]:
    if isinstance(requests, (str, bytes)):
        raise ValueError("requests must be a non-string iterable")
    try:
        materialized = list(requests)
    except TypeError as exc:
        raise ValueError("requests must be iterable") from exc

    normalized: dict[str, int] = {}
    for request in materialized:
        if not isinstance(request, (list, tuple)) or len(request) != 2:
            raise ValueError("invalid request")
        sku, quantity = request
        if not isinstance(sku, str) or _SKU_RE.fullmatch(sku) is None:
            raise ValueError("invalid request SKU")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("invalid request quantity")
        normalized[sku] = quantity
    return normalized
