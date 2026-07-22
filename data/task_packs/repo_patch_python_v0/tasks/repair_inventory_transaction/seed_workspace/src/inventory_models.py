from dataclasses import dataclass


@dataclass(frozen=True)
class ReservationResult:
    accepted: bool
    remaining: dict[str, int]
    allocated: dict[str, int]
    shortfalls: dict[str, int]
