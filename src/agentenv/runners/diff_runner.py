import difflib
from collections.abc import Iterable
from pathlib import Path

import xxhash


IGNORED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv"}
IGNORED_AFTER_ONLY_FILE_NAMES = {"uv.lock"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def render_directory_diff(before_dir: Path, after_dir: Path) -> str:
    before_files = _relative_files(before_dir)
    after_files = _relative_files(after_dir)
    relative_files = sorted(
        before_files | _after_files_to_diff(before_files, after_files)
    )
    diff_chunks: list[str] = []

    for relative_file in relative_files:
        before_path = before_dir / relative_file
        after_path = after_dir / relative_file
        before_lines = _read_lines(before_path) if before_path.exists() else []
        after_lines = _read_lines(after_path) if after_path.exists() else []

        if before_lines == after_lines:
            continue

        diff_chunks.extend(
            _git_apply_compatible_lines(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"a/{relative_file.as_posix()}",
                    tofile=f"b/{relative_file.as_posix()}",
                )
            )
        )

    return "".join(diff_chunks)


def hash_diff(diff: str) -> str:
    return f"xxh64:{xxhash.xxh64_hexdigest(diff.encode())}"


def _relative_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and not _is_ignored_path(path.relative_to(root))
    }


def _after_files_to_diff(before_files: set[Path], after_files: set[Path]) -> set[Path]:
    return before_files | {
        path
        for path in after_files
        if path in before_files or path.name not in IGNORED_AFTER_ONLY_FILE_NAMES
    }


def _read_lines(path: Path) -> list[str]:
    return path.read_text().splitlines(keepends=True)


def _git_apply_compatible_lines(lines: Iterable[str]) -> list[str]:
    compatible_lines: list[str] = []
    for line in lines:
        if line.endswith("\n"):
            compatible_lines.append(line)
            continue

        compatible_lines.append(f"{line}\n")
        if _is_unified_diff_content_line(line):
            compatible_lines.append("\\ No newline at end of file\n")
    return compatible_lines


def _is_unified_diff_content_line(line: str) -> bool:
    if line.startswith(("--- ", "+++ ")):
        return False
    return line.startswith((" ", "-", "+"))


def _is_ignored_path(path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in path.parts) or (
        path.suffix in IGNORED_SUFFIXES
    )
