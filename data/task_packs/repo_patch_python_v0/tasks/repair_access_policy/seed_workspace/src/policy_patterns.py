import re


_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def validate_subject(value: object) -> str:
    if not isinstance(value, str) or _SEGMENT_RE.fullmatch(value) is None:
        raise ValueError("invalid subject")
    return value


def validate_exact_name(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid {label}")
    parts = value.split(":")
    if not parts or any(_SEGMENT_RE.fullmatch(part) is None for part in parts):
        raise ValueError(f"invalid {label}")
    return value


def validate_pattern(value: object, *, subject: bool = False) -> str:
    if value == "*":
        return "*"
    if subject:
        return validate_subject(value)
    if not isinstance(value, str):
        raise ValueError("invalid pattern")
    if value.endswith(":*"):
        validate_exact_name(value[:-2], label="pattern")
        return value
    validate_exact_name(value, label="pattern")
    return value


def matches_pattern(pattern: str, value: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith(":*"):
        return value.startswith(pattern[:-2])
    return pattern == value
