import pytest

from alias_registry import build_alias_index, normalize_name, resolve_names


def test_normalize_already_canonical_name() -> None:
    assert normalize_name("primary_api") == "primary_api"


def test_builds_direct_alias_index() -> None:
    assert build_alias_index(
        ["primary", "backup"],
        {"main": "primary", "spare": "backup"},
    ) == {
        "primary": "primary",
        "backup": "backup",
        "main": "primary",
        "spare": "backup",
    }


def test_resolves_requests_in_order_and_preserves_duplicates() -> None:
    assert resolve_names(
        ["primary", "backup"],
        {"main": "primary"},
        ["main", "backup", "main"],
    ) == ["primary", "backup", "primary"]


def test_unknown_request_is_invalid() -> None:
    with pytest.raises(ValueError):
        resolve_names(["primary"], {}, ["missing"])
