import json
from pathlib import Path
import unicodedata

import xxhash


NOISY_HASH_PATH_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def hash_normalized_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = " ".join(normalized.split())
    return hash_bytes(normalized.encode())


def hash_json(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hash_bytes(payload.encode())


def hash_bytes(payload: bytes) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(payload)}"


def hash_directory(root: Path) -> str:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Expected directory for hashing: {root}")

    entries = [
        {
            "path": relative_path(file_path, root),
            "hash": hash_file(file_path),
        }
        for file_path in iter_hashable_files(root)
    ]
    return hash_json(entries)


def iter_hashable_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root.resolve()]

    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if is_noisy_hash_path(path):
            continue
        if path.is_file():
            files.append(path.resolve())
    return files


def is_noisy_hash_path(path: Path) -> bool:
    return any(part in NOISY_HASH_PATH_NAMES for part in path.parts)


def relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
