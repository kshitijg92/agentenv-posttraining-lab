def parse_duration(value: str) -> float:
    """Parse a compact duration and return seconds."""
    if not value.endswith("s"):
        raise ValueError("duration must use seconds")
    return float(value[:-1])
