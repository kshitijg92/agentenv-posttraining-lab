import re
from collections.abc import Iterable, Mapping


_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def normalize_name(value: object) -> str:
    """Return the canonical spelling for one registry name."""
    if not isinstance(value, str) or _NAME_RE.fullmatch(value) is None:
        raise ValueError("invalid name")
    return value


def build_alias_index(
    canonical_names: Iterable[object],
    aliases: Mapping[object, object],
) -> dict[str, str]:
    """Map canonical names and aliases to canonical names."""
    if isinstance(canonical_names, (str, bytes)):
        raise ValueError("canonical_names must be a non-string iterable")
    try:
        canonicals = [normalize_name(name) for name in canonical_names]
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid canonical names") from exc
    if len(canonicals) != len(set(canonicals)):
        raise ValueError("duplicate canonical name")
    if not isinstance(aliases, Mapping):
        raise ValueError("aliases must be a mapping")

    index = {name: name for name in canonicals}
    for raw_alias, raw_target in aliases.items():
        alias = normalize_name(raw_alias)
        target = normalize_name(raw_target)
        if alias in index or target not in index:
            raise ValueError("invalid alias")
        index[alias] = target
    return index


def resolve_names(
    canonical_names: Iterable[object],
    aliases: Mapping[object, object],
    requested_names: Iterable[object],
) -> list[str]:
    """Resolve requested names through a freshly built alias index."""
    index = build_alias_index(canonical_names, aliases)
    if isinstance(requested_names, (str, bytes)):
        raise ValueError("requested_names must be a non-string iterable")
    try:
        requested = [normalize_name(name) for name in requested_names]
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid requested names") from exc
    try:
        return [index[name] for name in requested]
    except KeyError as exc:
        raise ValueError("unknown requested name") from exc
