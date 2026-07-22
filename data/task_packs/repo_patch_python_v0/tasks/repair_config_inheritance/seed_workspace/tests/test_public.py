import json

from service_config import ServiceConfig, load_config


def write_json(path, payload: object) -> None:
    path.write_text(json.dumps(payload))


def test_empty_document_uses_defaults(tmp_path) -> None:
    entry = tmp_path / "config.json"
    write_json(entry, {})
    assert load_config(entry) == ServiceConfig(
        host="localhost",
        port=8080,
        timeout_seconds=30.0,
        retries=3,
        labels={},
    )


def test_local_values_are_loaded(tmp_path) -> None:
    entry = tmp_path / "config.json"
    write_json(
        entry,
        {
            "service": {"host": "api.internal", "port": 9000},
            "limits": {"timeout_seconds": 2.5, "retries": 1},
            "labels": {"env": "dev"},
        },
    )
    assert load_config(entry) == ServiceConfig(
        host="api.internal",
        port=9000,
        timeout_seconds=2.5,
        retries=1,
        labels={"env": "dev"},
    )


def test_one_direct_include_with_non_overlapping_sections(tmp_path) -> None:
    base = tmp_path / "base.json"
    entry = tmp_path / "config.json"
    write_json(base, {"service": {"host": "base", "port": 7000}})
    write_json(
        entry,
        {
            "includes": ["base.json"],
            "limits": {"timeout_seconds": 8, "retries": 2},
        },
    )
    config = load_config(entry)
    assert (config.host, config.port) == ("base", 7000)
    assert (config.timeout_seconds, config.retries) == (8.0, 2)
