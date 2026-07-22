import json
from pathlib import Path

from config_merge import empty_fragment, finalize_config, merge_fragments
from config_schema import validate_document
from config_types import ConfigFragment, ServiceConfig


def _read_document(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read configuration: {path}") from exc


def _load_direct(path: Path) -> ConfigFragment:
    parsed = validate_document(_read_document(path))
    merged = empty_fragment()
    for include in parsed.includes:
        include_path = path.parent / include
        included = validate_document(_read_document(include_path))
        merged = merge_fragments(merged, included.fragment)
    return merge_fragments(merged, parsed.fragment)


def load_config(entry_path: str | Path) -> ServiceConfig:
    fragment = _load_direct(Path(entry_path))
    return finalize_config(fragment)
