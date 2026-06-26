import json
from pathlib import Path

import pytest

from config_loader import load_settings
from settings import Settings


def test_defaults_when_no_config_or_environment() -> None:
    assert load_settings(None, environ={}) == Settings()


def test_json_config_overrides_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"host": "api.local", "port": 9000}))

    settings = load_settings(config_path, environ={})

    assert settings == Settings(host="api.local", port=9000, debug=False)


def test_environment_port_overrides_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"host": "api.local", "port": 9000}))

    settings = load_settings(config_path, environ={"APP_PORT": "7001"})

    assert settings == Settings(host="api.local", port=7001, debug=False)


def test_out_of_range_port_raises_value_error(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.json"
    config_path.write_text(json.dumps({"port": 70000}))

    with pytest.raises(ValueError):
        load_settings(config_path, environ={})
