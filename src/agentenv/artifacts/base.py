import json
import shutil
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any


MANIFEST_FILENAME = "manifest.json"
JsonObject = dict[str, Any]


class ArtifactType(StrEnum):
    SCORER_ATTEMPT = "scorer_attempt"
    AGENT_ATTEMPT = "agent_attempt"
    EVAL_RUN = "eval_run"
    EVAL_SUITE = "eval_suite"
    CONTROL_CALIBRATION = "control_calibration"
    REPLAY_RUN = "replay_run"
    TRAJECTORY_EXPORT = "trajectory_export"
    TRAJECTORY_REVIEW = "trajectory_review"
    TRAINING_CANDIDATE_EXPORT = "training_candidate_export"
    TRAINING_CANDIDATE_REPAIR_EXPORT = "training_candidate_repair_export"
    POSITIVE_SFT_EXPORT = "positive_sft_export"
    SCORER_AUDIT = "scorer_audit"
    AGENT_TASK_AUDIT = "agent_task_audit"
    HARNESS_AUDIT = "harness_audit"
    REWARD_HACK_AUDIT = "reward_hack_audit"


class ArtifactDirectoryError(ValueError):
    pass


def prepare_artifact_output_dir(out_dir: Path, *, overwrite: bool = False) -> Path:
    out_dir = out_dir.resolve()
    if out_dir.exists() and not out_dir.is_dir():
        raise ArtifactDirectoryError(
            f"Output path exists and is not a directory: {out_dir}"
        )

    if out_dir.exists() and any(out_dir.iterdir()):
        if not overwrite:
            raise ArtifactDirectoryError(
                f"Output directory is not empty: {out_dir}. "
                "Choose a new --out directory or pass --overwrite."
            )
        _assert_safe_overwrite_target(out_dir)
        shutil.rmtree(out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _assert_safe_overwrite_target(out_dir: Path) -> None:
    protected_paths = {
        Path("/").resolve(),
        Path.home().resolve(),
        Path.cwd().resolve(),
    }
    if out_dir in protected_paths:
        raise ArtifactDirectoryError(f"Refusing to overwrite protected path: {out_dir}")


def load_json_object(path: Path) -> JsonObject:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def load_jsonl_objects(path: Path) -> list[JsonObject]:
    records: list[JsonObject] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        records.append(payload)
    return records


def validate_relative_artifact_ref(
    value: str, *, allow_current_dir: bool = False
) -> str:
    if value == "." and allow_current_dir:
        return value
    if "\\" in value or (len(value) >= 2 and value[0].isalpha() and value[1] == ":"):
        raise ValueError(f"artifact ref must be a POSIX-style relative path: {value}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError(f"artifact ref must be relative: {value}")
    if not path.parts or path.parts == (".",) or ".." in path.parts:
        raise ValueError(
            f"artifact ref cannot be empty or contain parent traversal: {value}"
        )
    if str(path) != value:
        raise ValueError(f"artifact ref must be canonical: {value}")
    return value


def resolve_relative_artifact_ref(
    root: Path,
    artifact_ref: str,
    *,
    allow_current_dir: bool = False,
) -> Path:
    validate_relative_artifact_ref(
        artifact_ref,
        allow_current_dir=allow_current_dir,
    )
    resolved_root = root.resolve()
    resolved = (resolved_root / artifact_ref).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"artifact ref escapes artifact root: {artifact_ref}")
    return resolved
