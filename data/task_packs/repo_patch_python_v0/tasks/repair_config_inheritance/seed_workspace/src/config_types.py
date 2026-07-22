from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigFragment:
    service: dict[str, object]
    limits: dict[str, object]
    labels: dict[str, str]


@dataclass(frozen=True)
class ParsedDocument:
    includes: tuple[str, ...]
    fragment: ConfigFragment


@dataclass(frozen=True)
class ServiceConfig:
    host: str
    port: int
    timeout_seconds: float
    retries: int
    labels: dict[str, str]
