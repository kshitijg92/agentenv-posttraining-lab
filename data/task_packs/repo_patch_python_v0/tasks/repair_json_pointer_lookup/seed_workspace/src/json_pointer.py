def resolve_pointer(document: object, pointer: str) -> object:
    """Resolve a slash-separated path in a JSON-like value."""
    if pointer == "":
        return document
    current = document
    for part in pointer.strip("/").split("/"):
        current = current[part]  # type: ignore[index]
    return current
