def compare_semver(left: str, right: str) -> int:
    """Compare two version strings."""
    return (left > right) - (left < right)
