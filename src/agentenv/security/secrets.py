import os
import re
from collections.abc import Mapping
from typing import Any


REDACTED_SECRET = "[REDACTED_SECRET]"

_SENSITIVE_ENV_NAMES = {
    "AGENTENV_MODEL_API_KEY",
    "ALL_PROXY",
    "ANTHROPIC_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "HF_TOKEN",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "HUGGINGFACE_HUB_TOKEN",
    "OPENAI_API_KEY",
    "PIP_EXTRA_INDEX_URL",
    "PIP_INDEX_URL",
    "UV_EXTRA_INDEX_URL",
    "UV_INDEX_URL",
}

_SENSITIVE_ENV_TERMS = {
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "CREDENTIALS",
    "KEY",
    "PASSWORD",
    "SECRET",
    "SESSION",
    "TOKEN",
}

_TOKEN_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{12,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{12,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
)


def is_sensitive_env_name(name: str) -> bool:
    upper_name = name.upper()
    if upper_name in _SENSITIVE_ENV_NAMES:
        return True

    parts = [part for part in re.split(r"[^A-Z0-9]+", upper_name) if part]
    return any(part in _SENSITIVE_ENV_TERMS for part in parts)


def scrubbed_subprocess_env(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source_env = os.environ if env is None else env
    return {
        name: value
        for name, value in source_env.items()
        if not is_sensitive_env_name(name)
    }


def redact_secrets(
    text: str,
    env: Mapping[str, str] | None = None,
) -> str:
    redacted = text
    for secret_value in _secret_env_values(env):
        redacted = redacted.replace(secret_value, REDACTED_SECRET)
    for pattern in _TOKEN_PATTERNS:
        redacted = pattern.sub(REDACTED_SECRET, redacted)
    return redacted


def redact_jsonable(
    value: Any,
    env: Mapping[str, str] | None = None,
) -> Any:
    if isinstance(value, str):
        return redact_secrets(value, env=env)
    if isinstance(value, list):
        return [redact_jsonable(item, env=env) for item in value]
    if isinstance(value, tuple):
        return [redact_jsonable(item, env=env) for item in value]
    if isinstance(value, dict):
        return {
            (redact_secrets(key, env=env) if isinstance(key, str) else key): (
                redact_jsonable(item, env=env)
            )
            for key, item in value.items()
        }
    return value


def _secret_env_values(env: Mapping[str, str] | None = None) -> list[str]:
    source_env = os.environ if env is None else env
    values = [
        value
        for name, value in source_env.items()
        if is_sensitive_env_name(name) and len(value) >= 8
    ]
    return sorted(set(values), key=len, reverse=True)
