from access_policy import is_allowed


def _rule(effect: str, subjects: list[str], actions: list[str], resources: list[str]):
    return {
        "effect": effect,
        "subjects": subjects,
        "actions": actions,
        "resources": resources,
    }


def test_exact_allow() -> None:
    rules = [_rule("allow", ["alice"], ["invoice:read"], ["account:one"])]
    assert is_allowed(rules, "alice", "invoice:read", "account:one") is True


def test_no_matching_rule_denies() -> None:
    rules = [_rule("allow", ["alice"], ["invoice:read"], ["account:one"])]
    assert is_allowed(rules, "bob", "invoice:read", "account:one") is False


def test_global_wildcard_allow() -> None:
    rules = [_rule("allow", ["*"], ["*"], ["*"])]
    assert is_allowed(rules, "alice", "invoice:read", "account:one") is True


def test_non_overlapping_deny() -> None:
    rules = [
        _rule("deny", ["bob"], ["invoice:read"], ["account:one"]),
        _rule("allow", ["alice"], ["invoice:read"], ["account:one"]),
    ]
    assert is_allowed(rules, "alice", "invoice:read", "account:one") is True
