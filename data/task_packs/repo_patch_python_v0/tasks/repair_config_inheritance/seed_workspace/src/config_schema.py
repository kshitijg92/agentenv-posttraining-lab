from collections.abc import Mapping

from config_types import ConfigFragment, ParsedDocument


def validate_document(raw: object) -> ParsedDocument:
    if not isinstance(raw, Mapping):
        raise ValueError("configuration document must be an object")
    includes = tuple(raw.get("includes", ()))
    service = dict(raw.get("service", {}))
    limits = dict(raw.get("limits", {}))
    labels = dict(raw.get("labels", {}))
    return ParsedDocument(
        includes=includes,
        fragment=ConfigFragment(service=service, limits=limits, labels=labels),
    )
