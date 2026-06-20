from pathlib import Path

from agentenv.runners.diff_runner import hash_diff, render_directory_diff


def test_render_directory_diff_for_modified_file(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "example.py").write_text("value = 1\n")
    (after / "example.py").write_text("value = 2\n")

    diff = render_directory_diff(before, after)

    assert "--- a/example.py" in diff
    assert "+++ b/example.py" in diff
    assert "-value = 1" in diff
    assert "+value = 2" in diff


def test_hash_diff_is_stable() -> None:
    assert hash_diff("example diff\n") == hash_diff("example diff\n")
    assert hash_diff("example diff\n").startswith("xxh64:")


def test_render_directory_diff_ignores_pycache(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before_cache = before / "__pycache__"
    after_cache = after / "__pycache__"
    before_cache.mkdir(parents=True)
    after_cache.mkdir(parents=True)
    (before_cache / "module.pyc").write_bytes(b"\xa7\r\r\n")
    (after_cache / "module.pyc").write_bytes(b"\xa7\r\r\nchanged")

    assert render_directory_diff(before, after) == ""
