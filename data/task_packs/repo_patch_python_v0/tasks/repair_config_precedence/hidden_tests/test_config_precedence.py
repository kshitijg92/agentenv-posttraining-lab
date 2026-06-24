import json
from pathlib import Path

import pytest

from config_loader import load_settings
from settings import Settings


def test_environment_overrides_all_config_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps({"host": "file.local", "port": 9000, "debug": False})
    )

    settings = load_settings(
        config_path,
        environ={
            "APP_HOST": "env.local",
            "APP_PORT": "7001",
            "APP_DEBUG": "true",
        },
    )

    assert settings == Settings(host="env.local", port=7001, debug=True)


def test_defaults_config_and_partial_environment_are_merged(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"host": "file.local"}))

    settings = load_settings(config_path, environ={"APP_DEBUG": "true"})

    assert settings == Settings(host="file.local", port=8080, debug=True)


def test_debug_accepts_only_true_and_false_strings(tmp_path: Path) -> None:
    true_config = tmp_path / "true.json"
    true_config.write_text(json.dumps({"debug": "true"}))
    false_config = tmp_path / "false.json"
    false_config.write_text(json.dumps({"debug": "false"}))
    invalid_config = tmp_path / "invalid.json"
    invalid_config.write_text(json.dumps({"debug": "1"}))

    assert load_settings(true_config, environ={}).debug is True
    assert load_settings(false_config, environ={}).debug is False
    with pytest.raises(ValueError):
        load_settings(invalid_config, environ={})


def test_unknown_config_key_raises_value_error(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"host": "api.local", "timeout": 30}))

    with pytest.raises(ValueError):
        load_settings(config_path, environ={})


def test_boolean_port_is_invalid(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"port": True}))

    with pytest.raises(ValueError):
        load_settings(config_path, environ={})


def test_repeated_calls_do_not_leak_state(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"host": "first.local", "debug": True}))

    first = load_settings(config_path, environ={"APP_PORT": "7001"})
    second = load_settings(None, environ={})

    assert first == Settings(host="first.local", port=7001, debug=True)
    assert second == Settings()


def test_missing_explicit_config_file_raises_file_not_found_error(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError):
        load_settings(missing_path, environ={})
