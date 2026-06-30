import shutil
from pathlib import Path

from agentenv.runners.diff_runner import hash_diff, render_directory_diff
from agentenv.runners.patch_runner import apply_patch_file


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


def test_render_directory_diff_applies_when_after_file_lacks_final_newline(
    tmp_path: Path,
) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    workspace = tmp_path / "workspace"
    before.mkdir()
    after.mkdir()
    (before / "example.py").write_text("value = 1\n")
    (after / "example.py").write_text("value = 2")

    diff = render_directory_diff(before, after)
    patch_path = tmp_path / "candidate.patch"
    patch_path.write_text(diff)
    shutil.copytree(before, workspace)

    result = apply_patch_file(workspace, patch_path, timeout_seconds=10)

    assert "\\ No newline at end of file\n" in diff
    assert result.returncode == 0, result.stderr
    assert (workspace / "example.py").read_bytes() == (after / "example.py").read_bytes()


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


def test_render_directory_diff_ignores_generated_virtualenv(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after_venv = after / ".venv/lib"
    after_venv.mkdir(parents=True)
    (after_venv / "binary.so").write_bytes(b"\xa7\r\r\n")

    assert render_directory_diff(before, after) == ""


def test_render_directory_diff_ignores_after_only_uv_lock(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (after / "uv.lock").write_text("generated lock\n")

    assert render_directory_diff(before, after) == ""


def test_render_directory_diff_keeps_seeded_uv_lock_changes(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "uv.lock").write_text("old lock\n")
    (after / "uv.lock").write_text("new lock\n")

    diff = render_directory_diff(before, after)

    assert "--- a/uv.lock" in diff
    assert "+++ b/uv.lock" in diff
    assert "-old lock" in diff
    assert "+new lock" in diff
