from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Application settings returned by config_loader.load_settings."""

    host: str = "localhost"
    port: int = 8080
    debug: bool = False


DEFAULT_SETTINGS = Settings()
CONFIG_KEYS = {"host", "port", "debug"}
ENV_TO_FIELD = {
    "APP_PORT": "port",
}
