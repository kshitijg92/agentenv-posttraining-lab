from copy import deepcopy

import pytest

from alias_registry import build_alias_index, normalize_name, resolve_names


LEAKAGE_CANARY = "CANARY_REPAIR_ALIAS_CHAIN_PRIVATE"


def test_normalization_trims_ascii_space_and_tab_and_lowercases() -> None:
    assert normalize_name(" \tPrimary-API\t ") == "primary-api"


@pytest.mark.parametrize(
    "value",
    [None, 3, "", " \t", "1name", "two words", "na.me", "éclair", "a\n"],
)
def test_normalization_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        normalize_name(value)


def test_transitive_aliases_resolve_to_the_final_canonical() -> None:
    assert build_alias_index(
        (name for name in ["Primary", "Backup"]),
        {"main": "service", "service": "PRIMARY", "spare": "backup"},
    ) == {
        "primary": "primary",
        "backup": "backup",
        "main": "primary",
        "service": "primary",
        "spare": "backup",
    }


def test_normalized_collisions_are_invalid() -> None:
    with pytest.raises(ValueError):
        build_alias_index(["Primary", " primary "], {})
    with pytest.raises(ValueError):
        build_alias_index(["primary"], {" PRIMARY ": "primary"})
    with pytest.raises(ValueError):
        build_alias_index(["primary"], {"Main": "primary", " main ": "primary"})


def test_missing_targets_and_cycles_are_invalid() -> None:
    with pytest.raises(ValueError):
        build_alias_index(["primary"], {"main": "missing"})
    with pytest.raises(ValueError):
        build_alias_index(["primary"], {"a": "b", "b": "a"})
    with pytest.raises(ValueError):
        build_alias_index(["primary"], {"a": "a"})


@pytest.mark.parametrize(
    ("canonical_names", "aliases"),
    [
        ("primary", {}),
        (None, {}),
        (["primary"], []),
        (["primary"], {1: "primary"}),
        (["primary"], {"main": 1}),
    ],
)
def test_malformed_registry_inputs_raise_value_error(
    canonical_names: object,
    aliases: object,
) -> None:
    with pytest.raises(ValueError):
        build_alias_index(canonical_names, aliases)  # type: ignore[arg-type]


def test_resolution_normalizes_requests_and_preserves_order() -> None:
    assert resolve_names(
        ["Primary", "Backup"],
        {"MAIN": "Primary", "service": "main"},
        (name for name in [" Service ", "BACKUP", "main", "main"]),
    ) == ["primary", "backup", "primary", "primary"]


@pytest.mark.parametrize("requested", ["main", None, ["missing"], [1]])
def test_invalid_requested_names_raise_value_error(requested: object) -> None:
    with pytest.raises(ValueError):
        resolve_names(["primary"], {"main": "primary"}, requested)  # type: ignore[arg-type]


def test_inputs_are_not_mutated() -> None:
    canonicals = ["Primary"]
    aliases = {"main": "PRIMARY"}
    requests = ["Main"]
    before = deepcopy((canonicals, aliases, requests))

    assert resolve_names(canonicals, aliases, requests) == ["primary"]
    assert (canonicals, aliases, requests) == before
