import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from settings import CONFIG_KEYS, DEFAULT_SETTINGS, ENV_TO_FIELD, Settings


def load_settings(
    config_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load application settings.

    Settings are resolved in precedence order: environment variables override
    JSON config values, which override defaults. The supported JSON config keys
    are host, port, and debug. Unknown JSON config keys are invalid.

    Environment overrides use APP_HOST, APP_PORT, and APP_DEBUG.

    host must be a string. port must be an int or numeric string in the range
    1..65535; booleans are not valid ports. debug must be a bool or one of the
    exact strings "true" or "false"; strings such as "1", "0", "yes", and
    "no" are invalid.

    Passing None for config_path means no config file is read. Passing an
    explicit path that does not exist should raise FileNotFoundError. Invalid
    config contents or invalid values should raise ValueError. Each call should
    return a fresh Settings object and must not mutate shared defaults.
    """
    raw_settings: dict[str, Any] = {
        "host": DEFAULT_SETTINGS.host,
        "port": DEFAULT_SETTINGS.port,
        "debug": DEFAULT_SETTINGS.debug,
    }

    if config_path is not None:
        loaded = json.loads(Path(config_path).read_text())
        if not isinstance(loaded, dict):
            raise ValueError("config must be a JSON object")
        for key, value in loaded.items():
            if key in CONFIG_KEYS:
                raw_settings[key] = value

    env = os.environ if environ is None else environ
    for env_name, field_name in ENV_TO_FIELD.items():
        if env_name in env:
            raw_settings[field_name] = env[env_name]

    return Settings(
        host=_parse_host(raw_settings["host"]),
        port=_parse_port(raw_settings["port"]),
        debug=_parse_debug(raw_settings["debug"]),
    )


def _parse_host(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("host must be a string")
    return value


def _parse_port(value: Any) -> int:
    if isinstance(value, int):
        port = value
    elif isinstance(value, str) and value.isdigit():
        port = int(value)
    else:
        raise ValueError("port must be an int or numeric string")

    if not 1 <= port <= 65535:
        raise ValueError("port must be in the range 1..65535")
    return port


def _parse_debug(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("debug must be a boolean or true/false string")
    return value
