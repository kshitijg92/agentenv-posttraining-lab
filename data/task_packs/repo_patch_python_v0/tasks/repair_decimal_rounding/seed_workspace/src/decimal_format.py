def round_decimal(value: str, places: int) -> str:
    """Round decimal text for display."""
    return f"{float(value):.{places}f}"
