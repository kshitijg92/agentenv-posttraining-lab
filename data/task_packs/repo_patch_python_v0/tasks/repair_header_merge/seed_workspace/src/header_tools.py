def merge_headers(
    defaults: dict[str, str],
    overrides: dict[str, str],
) -> dict[str, str]:
    """Merge default and override HTTP-style headers."""
    result = dict(defaults)
    result.update(overrides)
    return result
