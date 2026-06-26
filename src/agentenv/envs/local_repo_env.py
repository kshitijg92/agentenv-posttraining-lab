import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agentenv.tasks.schema import TaskManifest
from agentenv.tasks.validate import validate_task_manifest_paths


@dataclass(frozen=True)
class LocalRepoWorkspace:
    path: Path
    task_dir: Path


def prepare_agent_workspace(
    manifest: TaskManifest,
    manifest_path: Path,
    workspace_parent: Path | None = None,
) -> LocalRepoWorkspace:
    validate_task_manifest_paths(manifest, manifest_path)

    task_dir = manifest_path.parent.resolve()
    seed_workspace = (task_dir / manifest.seed_workspace).resolve()
    workspace_root = _workspace_root(workspace_parent, manifest.id)
    workspace_path = workspace_root / "workspace"

    shutil.copytree(seed_workspace, workspace_path)
    _assert_hidden_validators_absent(manifest, workspace_path)

    return LocalRepoWorkspace(path=workspace_path, task_dir=task_dir)


def _workspace_root(workspace_parent: Path | None, task_id: str) -> Path:
    if workspace_parent is None:
        return Path(tempfile.mkdtemp(prefix=f"agentenv-{task_id}-")).resolve()

    workspace_parent.mkdir(parents=True, exist_ok=True)
    return workspace_parent.resolve()


def _assert_hidden_validators_absent(
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
