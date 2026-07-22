from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    event_id: str
    user: str
    kind: str
    amount_cents: int
    timestamp: datetime


@dataclass(frozen=True)
class UserRollup:
    user: str
    net_amount: str
    event_count: int


@dataclass(frozen=True)
class Rollup:
    event_count: int
    users: tuple[UserRollup, ...]
