from pathlib import Path

import pytest

from agentenv.hashing import hash_directory


def test_hash_directory_matches_for_identical_workspace_state(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write(first / "src/module.py", "value = 1\n")
    _write(first / "tests/test_module.py", "def test_value(): pass\n")
    _write(second / "tests/test_module.py", "def test_value(): pass\n")
    _write(second / "src/module.py", "value = 1\n")

    assert hash_directory(first) == hash_directory(second)


def test_hash_directory_changes_when_file_content_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src/module.py"
    _write(source, "value = 1\n")
    before = hash_directory(workspace)

    source.write_text("value = 2\n")

    assert hash_directory(workspace) != before


@pytest.mark.parametrize("mutation", ["rename", "add", "delete"])
def test_hash_directory_changes_when_relative_file_paths_change(
    tmp_path: Path,
    mutation: str,
) -> None:
    workspace = tmp_path / "workspace"
    source = workspace / "src/module.py"
    _write(source, "value = 1\n")
    before = hash_directory(workspace)

    if mutation == "rename":
        source.rename(workspace / "src/renamed.py")
    elif mutation == "add":
        _write(workspace / "src/added.py", "value = 1\n")
    else:
        source.unlink()

    assert hash_directory(workspace) != before


def test_hash_directory_detects_empty_file_addition_and_removal(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write(workspace / "src/module.py", "value = 1\n")
    before = hash_directory(workspace)

    package_marker = workspace / "src/__init__.py"
    package_marker.touch()
    with_empty_file = hash_directory(workspace)

    assert with_empty_file != before

    package_marker.unlink()

    assert hash_directory(workspace) == before


def test_hash_directory_ignores_declared_noisy_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write(workspace / "src/module.py", "value = 1\n")
    before = hash_directory(workspace)

    _write(workspace / ".pytest_cache/state", "cache state\n")
    _write(workspace / "src/__pycache__/module.pyc", "bytecode\n")

    assert hash_directory(workspace) == before


def test_hash_directory_rejects_non_directory_root(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("content\n")

    with pytest.raises(ValueError, match="Expected directory for hashing"):
        hash_directory(file_path)

    with pytest.raises(ValueError, match="Expected directory for hashing"):
        hash_directory(tmp_path / "missing")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
