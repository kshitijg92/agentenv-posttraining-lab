import shutil
from pathlib import Path


class ArtifactDirectoryError(ValueError):
    pass


def prepare_artifact_output_dir(out_dir: Path, *, overwrite: bool = False) -> Path:
    out_dir = out_dir.resolve()
    if out_dir.exists() and not out_dir.is_dir():
        raise ArtifactDirectoryError(f"Output path exists and is not a directory: {out_dir}")

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
