from copy import deepcopy

import pytest

from access_policy import is_allowed


LEAKAGE_CANARY = "CANARY_REPAIR_ACCESS_POLICY_PRIVATE"


def rule(effect: str, subjects: object, actions: object, resources: object):
    return {
        "effect": effect,
        "subjects": subjects,
        "actions": actions,
        "resources": resources,
    }


@pytest.mark.parametrize(
    "rules",
    [
        [
            rule("allow", ["alice"], ["billing:*"], ["account:*"]),
            rule("deny", ["alice"], ["billing:delete"], ["account:one"]),
        ],
        [
            rule("deny", ["alice"], ["billing:delete"], ["account:one"]),
            rule("allow", ["alice"], ["billing:*"], ["account:*"]),
        ],
    ],
)
def test_any_applicable_deny_wins_regardless_of_order(rules: object) -> None:
    assert is_allowed(rules, "alice", "billing:delete", "account:one") is False


def test_prefix_wildcard_requires_a_complete_colon_prefix() -> None:
    rules = [rule("allow", ["alice"], ["billing:*"], ["account:*"])]
    assert is_allowed(rules, "alice", "billing:read", "account:one") is True
    assert is_allowed(rules, "alice", "billinger:read", "account:one") is False
    assert is_allowed(rules, "alice", "billing-admin:read", "account:one") is False


def test_rules_may_be_a_generator_and_matching_is_case_sensitive() -> None:
    rules = (
        item
        for item in [rule("allow", ["Alice"], ["Invoice:read"], ["Account:one"])]
    )
    assert is_allowed(rules, "Alice", "Invoice:read", "Account:one") is True
    assert is_allowed(
        [rule("allow", ["Alice"], ["Invoice:read"], ["Account:one"])],
        "alice",
        "Invoice:read",
        "Account:one",
    ) is False


@pytest.mark.parametrize(
    "rules",
    [
        None,
        "rules",
        [None],
        [{"effect": "allow", "subjects": ["alice"], "actions": ["x"]}],
        [
            {
                "effect": "allow",
                "subjects": ["alice"],
                "actions": ["x"],
                "resources": ["y"],
                "extra": True,
            }
        ],
        [rule("permit", ["alice"], ["x"], ["y"])],
        [rule("allow", [], ["x"], ["y"])],
        [rule("allow", ["alice", "alice"], ["x"], ["y"])],
        [rule("allow", "alice", ["x"], ["y"])],
        [rule("allow", ["alice"], ["bad*"], ["y"])],
        [rule("allow", ["alice"], ["x:*:bad"], ["y"])],
        [rule("allow", ["alice"], [":*"], ["y"])],
    ],
)
def test_malformed_rules_raise_value_error(rules: object) -> None:
    with pytest.raises(ValueError):
        is_allowed(rules, "alice", "x", "y")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("subject", "action", "resource"),
    [
        ("*", "x", "y"),
        ("bad subject", "x", "y"),
        ("alice", "*", "y"),
        ("alice", "x:*", "y"),
        ("alice", "x", ""),
        (1, "x", "y"),
    ],
)
def test_malformed_query_values_raise_value_error(
    subject: object,
    action: object,
    resource: object,
) -> None:
    with pytest.raises(ValueError):
        is_allowed([], subject, action, resource)


def test_all_rules_are_validated_before_an_early_allow_can_return() -> None:
    rules = [
        rule("allow", ["*"], ["*"], ["*"]),
        rule("allow", [], ["x"], ["y"]),
    ]
    with pytest.raises(ValueError):
        is_allowed(rules, "alice", "x", "y")


def test_empty_rules_are_valid_and_deny() -> None:
    assert is_allowed([], "alice", "x", "y") is False


def test_inputs_are_not_mutated() -> None:
    rules = [rule("allow", ["alice"], ["x:*"], ["y:*"])]
    before = deepcopy(rules)
    assert is_allowed(rules, "alice", "x:read", "y:one") is True
    assert rules == before
