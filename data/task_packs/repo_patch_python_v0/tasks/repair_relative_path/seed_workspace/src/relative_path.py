import posixpath


def normalize_relative_path(path: str) -> str:
    """Normalize a path for storage as a relative POSIX path."""
    return posixpath.normpath(path).lstrip("/")
