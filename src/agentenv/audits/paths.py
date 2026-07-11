"""Strict path handling shared by typed harness-audit layer runners."""

from pathlib import Path

from agentenv.artifacts.base import validate_relative_artifact_ref


def discover_case_dirs(case_root: Path, *, layer_name: str) -> list[Path]:
    case_root = case_root.resolve()
    if not case_root.is_dir():
        raise ValueError(f"Expected {layer_name} case root directory: {case_root}")
    return sorted(
        path.resolve()
        for path in case_root.iterdir()
        if path.is_dir() and not path.is_symlink()
    )


def resolve_repo_relative_path(
    path_text: str,
    *,
    repo_root: Path,
    layer_name: str,
) -> Path:
    validate_relative_artifact_ref(path_text)
    root = repo_root.resolve()
    path = (root / path_text).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{layer_name} path escapes repository root: {path_text}")
    return path


def resolve_case_relative_file(
    case_dir: Path,
    path_text: str,
    *,
    layer_name: str,
    file_label: str,
) -> Path:
    validate_relative_artifact_ref(path_text)
    case_dir = case_dir.resolve()
    path = (case_dir / path_text).resolve()
    if not path.is_relative_to(case_dir):
        raise ValueError(f"{layer_name} path escapes case directory: {path_text}")
    if not path.is_file():
        raise ValueError(f"Missing {file_label}: {path}")
    return path


def repo_relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Harness audit source path must be inside repository root: {path}"
        ) from exc
