def parse_env_assignments(text: str) -> dict[str, str]:
    """Parse simple KEY=VALUE lines."""
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"')
    return result
