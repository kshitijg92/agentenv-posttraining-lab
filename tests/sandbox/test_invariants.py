from pathlib import Path

from agentenv.controls.controls_run import ControlRecord, run_controls
from agentenv.envs.local_repo_env import prepare_agent_workspace
from agentenv.orchestrators.attempt_runner import run_and_persist_patch_attempt_to_dir
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)
TOY_ORACLE_PATCH = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/oracle.patch"
)
TOY_TASK_PACK = Path("data/task_packs/repo_patch_python_v0")


def test_hidden_validators_are_not_present_in_prepared_agent_workspace(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    task_dir = TOY_TASK_MANIFEST.parent

    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path,
    )

    for hidden_validator in manifest.hidden_validators:
        assert (task_dir / hidden_validator.path).exists()
        assert not (workspace.path / hidden_validator.path).exists()


def test_scorer_control_patches_are_not_present_in_prepared_agent_workspace(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    task_dir = TOY_TASK_MANIFEST.parent

    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path,
    )

    control_paths = [
        manifest.controls.scorer_control_patches.oracle,
        manifest.controls.scorer_control_patches.bad.noop,
        manifest.controls.scorer_control_patches.bad.public_only,
    ]
    for control_path in control_paths:
        assert (task_dir / control_path).is_file()
        assert not (workspace.path / control_path).exists()


def test_mutating_one_prepared_workspace_does_not_mutate_seed_or_later_workspace(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    task_dir = TOY_TASK_MANIFEST.parent
    seed_source = task_dir / manifest.seed_workspace / "src/mathlib.py"
    original_source = seed_source.read_text()

    first_workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path / "first",
    )
    (first_workspace.path / "src/mathlib.py").write_text("# mutated\n")
    (first_workspace.path / "attempt_only.txt").write_text("attempt-local file\n")

    second_workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path / "second",
    )

    assert seed_source.read_text() == original_source
    assert (second_workspace.path / "src/mathlib.py").read_text() == original_source
    assert not (second_workspace.path / "attempt_only.txt").exists()


def test_leakage_canary_is_absent_from_workspace_and_attempt_artifacts(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path / "workspace",
    )
    attempt_dir = tmp_path / "attempt"
    run_and_persist_patch_attempt_to_dir(
        TOY_TASK_MANIFEST,
        TOY_ORACLE_PATCH,
        attempt_dir,
    )

    workspace_files = _files_under(workspace.path)
    artifact_files = _files_under(attempt_dir)

    assert _files_containing(manifest.leakage_canary, workspace_files) == []
    assert _files_containing(manifest.leakage_canary, artifact_files) == []


def test_task_manifest_contents_are_absent_from_workspace_and_attempt_artifacts(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    workspace = prepare_agent_workspace(
        manifest,
        TOY_TASK_MANIFEST,
        workspace_parent=tmp_path / "workspace",
    )
    attempt_dir = tmp_path / "attempt"
    run_and_persist_patch_attempt_to_dir(
        TOY_TASK_MANIFEST,
        TOY_ORACLE_PATCH,
        attempt_dir,
    )

    workspace_files = _files_under(workspace.path)
    artifact_files = _files_under(attempt_dir)
    manifest_content_markers = [
        "hidden_validators:",
        "controls:",
        "leakage_canary:",
    ]

    assert not (workspace.path / TOY_TASK_MANIFEST.name).exists()
    for marker in manifest_content_markers:
        assert _files_containing(marker, workspace_files) == []
        assert _files_containing(marker, artifact_files) == []


def test_repeated_control_runs_produce_stable_statuses_and_final_diff_hashes(
    tmp_path: Path,
) -> None:
    control_run = run_controls(
        TOY_TASK_PACK,
        repeats=2,
        out_dir=tmp_path / "controls",
    )

    scorer_records = [
        record for record in control_run.records if record.control_layer == "scorer"
    ]
    records_by_task_control: dict[tuple[str, str], list[ControlRecord]] = {}
    for record in scorer_records:
        records_by_task_control.setdefault(
            (record.task_id, record.control_name),
            [],
        ).append(record)

    assert records_by_task_control
    for records in records_by_task_control.values():
        assert len(records) == 2
        observed_results = {
            (
                record.actual["attempt_status"],
                record.actual["public_status"],
                record.actual["hidden_status"],
                record.actual["final_diff_hash"],
            )
            for record in records
        }
        assert len(observed_results) == 1


def _files_under(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def _files_containing(needle: str, paths: list[Path]) -> list[Path]:
    needle_bytes = needle.encode()
    return [path for path in paths if needle_bytes in path.read_bytes()]
