"""Runtime provenance captured by standalone and aggregate harness audits."""

import platform
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys

from agentenv.audits.schema import (
    HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
    HarnessRuntimeProvenance,
    derive_harness_runtime_hash,
)
from agentenv.hashing import hash_bytes, hash_directory, hash_file


def harness_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def capture_harness_runtime_provenance(repo_root: Path) -> HarnessRuntimeProvenance:
    repo_root = repo_root.resolve()
    harness_source_hash = hash_directory(repo_root / "src/agentenv")
    root_pyproject_hash = hash_file(repo_root / "pyproject.toml")
    root_uv_lock_hash = hash_file(repo_root / "uv.lock")
    python_implementation = platform.python_implementation().lower()
    python_version = platform.python_version()
    sys_platform = sys.platform
    platform_machine = platform.machine() or "unknown"
    return HarnessRuntimeProvenance(
        schema_version=HARNESS_RUNTIME_PROVENANCE_SCHEMA_VERSION,
        harness_source_root="src/agentenv",
        harness_source_hash=harness_source_hash,
        root_pyproject_path="pyproject.toml",
        root_pyproject_hash=root_pyproject_hash,
        root_uv_lock_path="uv.lock",
        root_uv_lock_hash=root_uv_lock_hash,
        python_implementation=python_implementation,
        python_version=python_version,
        sys_platform=sys_platform,
        platform_machine=platform_machine,
        harness_runtime_hash=derive_harness_runtime_hash(
            harness_source_hash=harness_source_hash,
            root_pyproject_hash=root_pyproject_hash,
            root_uv_lock_hash=root_uv_lock_hash,
            python_implementation=python_implementation,
            python_version=python_version,
            sys_platform=sys_platform,
            platform_machine=platform_machine,
        ),
    )


def git_sha_or_unknown(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root.resolve(),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    sha = result.stdout.strip()
    if result.returncode != 0 or not sha:
        return "unknown"
    return sha


def git_worktree_state(repo_root: Path) -> tuple[bool, str]:
    """Return whether tracked/untracked work exists and a hash of that state."""

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root.resolve(),
            check=False,
            capture_output=True,
            timeout=10,
        )
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--"],
            cwd=repo_root.resolve(),
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return True, hash_bytes(b"git-worktree-state-unavailable")
    if status.returncode != 0 or diff.returncode != 0:
        return True, hash_bytes(b"git-worktree-state-unavailable")
    payload = b"status\0" + status.stdout + b"\0diff\0" + diff.stdout
    return bool(status.stdout.strip()), hash_bytes(payload)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
