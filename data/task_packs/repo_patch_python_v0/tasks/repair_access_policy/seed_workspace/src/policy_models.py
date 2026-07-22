from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    effect: str
    subjects: tuple[str, ...]
    actions: tuple[str, ...]
    resources: tuple[str, ...]


def parse_rules(raw_rules: Iterable[object]) -> list[Rule]:
    if isinstance(raw_rules, (str, bytes)):
        raise ValueError("rules must be a non-string iterable")
    try:
        materialized = list(raw_rules)
    except TypeError as exc:
        raise ValueError("rules must be iterable") from exc

    rules: list[Rule] = []
    for raw_rule in materialized:
        if not isinstance(raw_rule, Mapping):
            raise ValueError("rule must be a mapping")
        effect = raw_rule.get("effect")
        if effect not in {"allow", "deny"}:
            raise ValueError("invalid effect")
        rules.append(
            Rule(
                effect=effect,
                subjects=tuple(raw_rule.get("subjects", ())),
                actions=tuple(raw_rule.get("actions", ())),
                resources=tuple(raw_rule.get("resources", ())),
            )
        )
    return rules
