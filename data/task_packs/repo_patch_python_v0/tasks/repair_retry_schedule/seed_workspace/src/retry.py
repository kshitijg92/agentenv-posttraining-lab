def retry_delays(
    base_delay: float,
    multiplier: float,
    attempts: int,
    cap: float,
) -> list[float]:
    """Build a capped exponential retry schedule."""
    return [min(base_delay * multiplier**index, cap) for index in range(attempts)]
