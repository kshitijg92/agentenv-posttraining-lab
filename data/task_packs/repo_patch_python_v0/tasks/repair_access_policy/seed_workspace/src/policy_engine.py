from collections.abc import Iterable

from policy_models import parse_rules
from policy_patterns import matches_pattern, validate_exact_name, validate_subject


def is_allowed(
    rules: Iterable[object],
    subject: object,
    action: object,
    resource: object,
) -> bool:
    parsed_rules = parse_rules(rules)
    query_subject = validate_subject(subject)
    query_action = validate_exact_name(action, label="action")
    query_resource = validate_exact_name(resource, label="resource")

    for rule in parsed_rules:
        if (
            any(matches_pattern(pattern, query_subject) for pattern in rule.subjects)
            and any(matches_pattern(pattern, query_action) for pattern in rule.actions)
            and any(
                matches_pattern(pattern, query_resource) for pattern in rule.resources
            )
        ):
            return rule.effect == "allow"
    return False
