import json
import math
from pathlib import Path

import pytest

from service_config import ServiceConfig, load_config


LEAKAGE_CANARY = "CANARY_REPAIR_CONFIG_INHERITANCE_PRIVATE"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_recursive_includes_resolve_from_each_including_file(tmp_path: Path) -> None:
    write_json(
        tmp_path / "shared.json",
        {
            "service": {"host": "shared", "port": 7100},
            "limits": {"timeout_seconds": 12, "retries": 5},
            "labels": {"tier": "base", "region": "west"},
        },
    )
    write_json(
        tmp_path / "nested/middle.json",
        {
            "includes": ["../shared.json"],
            "service": {"port": 7200},
            "labels": {"tier": "middle"},
        },
    )
    write_json(
        tmp_path / "entry.json",
        {
            "includes": ["nested/middle.json"],
            "limits": {"retries": 1},
            "labels": {"env": "dev"},
        },
    )
    assert load_config(tmp_path / "entry.json") == ServiceConfig(
        host="shared",
        port=7200,
        timeout_seconds=12.0,
        retries=1,
        labels={"tier": "middle", "region": "west", "env": "dev"},
    )


def test_later_includes_then_local_values_take_precedence(tmp_path: Path) -> None:
    write_json(
        tmp_path / "first.json",
        {"service": {"host": "first", "port": 7001}, "labels": {"x": "1"}},
    )
    write_json(
        tmp_path / "second.json",
        {"service": {"port": 7002}, "labels": {"x": "2", "y": "2"}},
    )
    write_json(
        tmp_path / "entry.json",
        {
            "includes": ["first.json", "second.json"],
            "service": {"host": "local"},
            "labels": {"y": "local"},
        },
    )
    config = load_config(tmp_path / "entry.json")
    assert (config.host, config.port) == ("local", 7002)
    assert config.labels == {"x": "2", "y": "local"}


def test_repeated_non_active_include_is_valid(tmp_path: Path) -> None:
    write_json(tmp_path / "common.json", {"labels": {"common": "yes"}})
    write_json(tmp_path / "a.json", {"includes": ["common.json"]})
    write_json(tmp_path / "b.json", {"includes": ["common.json"]})
    write_json(tmp_path / "entry.json", {"includes": ["a.json", "b.json"]})
    assert load_config(tmp_path / "entry.json").labels == {"common": "yes"}


def test_active_include_cycle_is_invalid(tmp_path: Path) -> None:
    write_json(tmp_path / "a.json", {"includes": ["b.json"]})
    write_json(tmp_path / "b.json", {"includes": ["a.json"]})
    with pytest.raises(ValueError):
        load_config(tmp_path / "a.json")


def test_parent_escape_is_rejected_even_when_target_exists(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    write_json(tmp_path / "outside.json", {"service": {"host": "outside"}})
    write_json(root / "entry.json", {"includes": ["../outside.json"]})
    with pytest.raises(ValueError):
        load_config(root / "entry.json")


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    write_json(tmp_path / "outside.json", {})
    try:
        (root / "link.json").symlink_to(tmp_path / "outside.json")
    except OSError:
        pytest.skip("symlinks unavailable")
    write_json(root / "entry.json", {"includes": ["link.json"]})
    with pytest.raises(ValueError):
        load_config(root / "entry.json")


def test_symlink_resolution_loop_is_reported_as_value_error(tmp_path: Path) -> None:
    try:
        (tmp_path / "loop.json").symlink_to(tmp_path / "loop.json")
    except OSError:
        pytest.skip("symlinks unavailable")
    write_json(tmp_path / "entry.json", {"includes": ["loop.json"]})
    with pytest.raises(ValueError):
        load_config(tmp_path / "entry.json")


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"unknown": 1},
        {"includes": "base.json"},
        {"includes": [""]},
        {"includes": ["/absolute.json"]},
        {"includes": ["windows\\path.json"]},
        {"includes": ["bad\u0000path.json"]},
        {"service": {"unknown": 1}},
        {"service": {"host": ""}},
        {"service": {"port": True}},
        {"service": {"port": 65536}},
        {"limits": {"unknown": 1}},
        {"limits": {"timeout_seconds": False}},
        {"limits": {"timeout_seconds": 0}},
        {"limits": {"timeout_seconds": math.inf}},
        {"limits": {"retries": True}},
        {"limits": {"retries": -1}},
        {"labels": {"": "value"}},
        {"labels": {"env": 1}},
    ],
)
def test_malformed_documents_raise_value_error(tmp_path: Path, payload: object) -> None:
    entry = tmp_path / "entry.json"
    write_json(entry, payload)
    with pytest.raises(ValueError):
        load_config(entry)


def test_malformed_included_document_is_not_hidden_by_local_values(tmp_path: Path) -> None:
    write_json(tmp_path / "bad.json", {"service": {"port": True}})
    write_json(
        tmp_path / "entry.json",
        {"includes": ["bad.json"], "service": {"port": 9000}},
    )
    with pytest.raises(ValueError):
        load_config(tmp_path / "entry.json")


def test_missing_files_and_invalid_json_have_distinct_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.json")
    entry = tmp_path / "entry.json"
    entry.write_text("{not json")
    with pytest.raises(ValueError):
        load_config(entry)


def test_each_call_returns_a_fresh_labels_mapping(tmp_path: Path) -> None:
    entry = tmp_path / "entry.json"
    write_json(entry, {"labels": {"env": "dev"}})
    first = load_config(entry)
    second = load_config(entry)
    first.labels["env"] = "changed"
    assert second.labels == {"env": "dev"}
