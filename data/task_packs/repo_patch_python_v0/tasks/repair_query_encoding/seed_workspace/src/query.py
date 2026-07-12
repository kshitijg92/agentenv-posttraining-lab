def encode_query(params: dict[str, str]) -> str:
    """Encode query parameters into a deterministic query string."""
    return "&".join(f"{key}={value}" for key, value in params.items())
