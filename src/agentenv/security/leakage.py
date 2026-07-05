from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import xxhash

from agentenv.artifacts import MANIFEST_FILENAME
from agentenv.artifacts.base import resolve_relative_artifact_ref
from agentenv.tasks.schema import (
    TaskManifest,
    agent_private_task_manifest_field_names,
)
from agentenv.models.schema import Message


LEAKAGE_CHECK_VERSION = "leakage_check_v0"


@dataclass(frozen=True)
class LeakageScanResult:
    leakage_check_version: str
    canary_hash: str | None
    canary_matches: tuple[str, ...]
    private_marker_matches: tuple[str, ...]
    scanned_files: tuple[str, ...]

    @property
    def canary_leaked(self) -> bool:
        return bool(self.canary_matches)

    @property
    def hidden_validators_visible_to_model(self) -> bool:
        return bool(self.private_marker_matches)


@dataclass(frozen=True)
class LeakageScanText:
    ref: str
    text: str


def hash_canary(canary: str | None) -> str | None:
    if canary is None:
        return None
    return f"xxh64:{xxhash.xxh64_hexdigest(canary.encode())}"


def contains_hidden_validator_asset_reference(
    text: str,
    manifest: TaskManifest,
) -> bool:
    markers = [
        manifest.leakage_canary,
        *build_hidden_validator_asset_markers(manifest),
    ]
    return any(marker in text for marker in markers if marker)


def build_hidden_validator_asset_markers(manifest: TaskManifest) -> tuple[str, ...]:
    markers: list[str] = []
    for hidden_validator in manifest.hidden_validators:
        hidden_path = Path(hidden_validator.path)
        markers.append(hidden_validator.path)
        markers.extend(
            str(parent) for parent in hidden_path.parents if str(parent) != "."
        )
    return tuple(dict.fromkeys(marker for marker in markers if marker))


def build_private_task_leak_markers(manifest: TaskManifest) -> tuple[str, ...]:
    markers = [
        *build_hidden_validator_asset_markers(manifest),
        *build_private_task_metadata_markers(),
    ]
    return tuple(dict.fromkeys(marker for marker in markers if marker))


def build_private_task_metadata_markers() -> tuple[str, ...]:
    markers: list[str] = []
    for field_name in agent_private_task_manifest_field_names():
        markers.extend(_build_structured_field_markers(field_name))
    return tuple(dict.fromkeys(markers))


def patch_modifies_public_tests(patch_text: str) -> bool:
    for line in patch_text.splitlines():
        if not line.startswith(("--- ", "+++ ")):
            continue
        path = line[4:]
        if path == "/dev/null":
            continue
        if path.startswith(("a/", "b/")):
            path = path[2:]
        if Path(path).parts[:1] == ("tests",):
            return True
    return False


def assert_hidden_validator_files_absent(
    manifest: TaskManifest,
    workspace_path: Path,
) -> None:
    for hidden_validator in manifest.hidden_validators:
        hidden_path = (workspace_path / hidden_validator.path).resolve()
        if hidden_path.exists():
            raise ValueError(
                f"Hidden validator {hidden_validator.id} is present in "
                f"agent workspace: {hidden_path}"
            )


def list_files_under(root: Path) -> tuple[Path, ...]:
    return tuple(sorted(path for path in root.rglob("*") if path.is_file()))


def scan_directory_for_leakage(
    root: Path,
    manifest: TaskManifest,
) -> LeakageScanResult:
    return scan_files_for_leakage(list_files_under(root), manifest, root=root)


def scan_agent_visible_artifacts(
    artifact_dir: Path,
    manifest: TaskManifest,
) -> LeakageScanResult:
    return scan_files_for_leakage(
        list_agent_visible_artifact_files(artifact_dir),
        manifest,
        root=artifact_dir,
    )


def list_agent_visible_artifact_files(artifact_dir: Path) -> tuple[Path, ...]:
    from agentenv.artifacts.manifests import load_agent_attempt_manifest

    artifact_root = artifact_dir.resolve()
    manifest_path = artifact_root / MANIFEST_FILENAME
    artifact_manifest = load_agent_attempt_manifest(manifest_path)

    paths = {manifest_path}
    for artifact_name, artifact_ref in artifact_manifest.artifacts.items():
        if artifact_name == "attempt":
            continue
        artifact_path = resolve_relative_artifact_ref(artifact_root, artifact_ref)
        if artifact_path.is_file():
            paths.add(artifact_path)
    return tuple(sorted(paths))


def scan_messages_for_leakage(
    messages: Iterable[Message],
    manifest: TaskManifest,
) -> LeakageScanResult:
    return scan_texts_for_leakage(
        (
            LeakageScanText(
                ref=f"message:{index}:{message.role}",
                text=message.model_dump_json(),
            )
            for index, message in enumerate(messages)
        ),
        manifest,
    )


def scan_texts_for_leakage(
    texts: Iterable[LeakageScanText],
    manifest: TaskManifest,
) -> LeakageScanResult:
    return _scan_named_contents_for_leakage(
        ((text.ref, text.text.encode()) for text in texts),
        manifest,
    )


def scan_files_for_leakage(
    paths: Iterable[Path],
    manifest: TaskManifest,
    *,
    root: Path | None = None,
) -> LeakageScanResult:
    return _scan_named_contents_for_leakage(
        _read_file_contents_for_leakage(paths, root=root),
        manifest,
    )


def _read_file_contents_for_leakage(
    paths: Iterable[Path],
    *,
    root: Path | None = None,
) -> Iterable[tuple[str, bytes]]:
    for path in sorted({candidate.resolve() for candidate in paths}):
        if not path.is_file():
            raise ValueError(f"Expected file to scan: {path}")
        yield _format_path_ref(path, root), path.read_bytes()


def _scan_named_contents_for_leakage(
    named_contents: Iterable[tuple[str, bytes]],
    manifest: TaskManifest,
) -> LeakageScanResult:
    canary = manifest.leakage_canary.encode()
    hidden_markers = tuple(
        marker.encode() for marker in build_private_task_leak_markers(manifest)
    )
    canary_matches: list[str] = []
    private_marker_matches: list[str] = []
    scanned_files: list[str] = []

    for ref, contents in named_contents:
        if not ref:
            raise ValueError("Leakage scan refs must be non-empty")
        redacted_ref = _redact_canary(ref, manifest.leakage_canary)
        scanned_files.append(redacted_ref)
        if canary and canary in contents:
            canary_matches.append(redacted_ref)
        if any(marker in contents for marker in hidden_markers if marker):
            private_marker_matches.append(redacted_ref)

    return LeakageScanResult(
        leakage_check_version=LEAKAGE_CHECK_VERSION,
        canary_hash=hash_canary(manifest.leakage_canary),
        canary_matches=tuple(canary_matches),
        private_marker_matches=tuple(private_marker_matches),
        scanned_files=tuple(scanned_files),
    )


def _build_structured_field_markers(field_name: str) -> tuple[str, ...]:
    return (
        f"{field_name}:",
        f'"{field_name}"',
        f"'{field_name}'",
    )


def _format_path_ref(path: Path, root: Path | None) -> str:
    if root is None:
        return path.as_posix()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _redact_canary(text: str, canary: str) -> str:
    return text.replace(canary, "[REDACTED_CANARY]")
