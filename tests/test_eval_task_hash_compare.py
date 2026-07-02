import json
from pathlib import Path

import pytest

from agentenv.evals.task_hash_compare import (
    compare_eval_task_hashes,
    load_eval_task_hash_source,
    render_eval_task_hash_comparison_summary,
)


def test_compare_eval_task_hashes_matches_run_and_matrix_manifests(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    matrix_dir = tmp_path / "matrix"
    _write_manifest(
        run_dir / "run_manifest.json",
        artifact_version="eval_run_v0",
        selected_task_hash_set="xxh64:same-set",
        selected_tasks=[_selected_task("task_a")],
    )
    _write_manifest(
        matrix_dir / "eval_matrix_manifest.json",
        artifact_version="eval_matrix_v0",
        selected_task_hash_set="xxh64:same-set",
        selected_tasks=[_selected_task("task_a")],
    )

    comparison = compare_eval_task_hashes(run_dir, matrix_dir)

    assert comparison.status == "matched"
    assert comparison.reference.artifact_version == "eval_run_v0"
    assert comparison.candidate.artifact_version == "eval_matrix_v0"
    assert comparison.task_pack_id_match is True
    assert comparison.selected_task_hash_set_match is True
    assert comparison.added_task_ids == ()
    assert comparison.removed_task_ids == ()
    assert comparison.changed_tasks == ()
    assert comparison.to_dict()["status"] == "matched"
    assert render_eval_task_hash_comparison_summary(comparison) == [
        "task input provenance matched",
        "reference=eval_run_v0 task_pack=repo_patch_python_v0 selected_tasks=1",
        "candidate=eval_matrix_v0 task_pack=repo_patch_python_v0 selected_tasks=1",
    ]


def test_compare_eval_task_hashes_detects_selected_task_drift(
    tmp_path: Path,
) -> None:
    reference_dir = tmp_path / "reference"
    candidate_dir = tmp_path / "candidate"
    _write_manifest(
        reference_dir / "run_manifest.json",
        artifact_version="eval_run_v0",
        selected_task_hash_set="xxh64:reference-set",
        selected_tasks=[
            _selected_task(
                "task_a",
                task_record_hash="xxh64:task-a-record-before",
                task_yaml_hash="xxh64:task-a-yaml-before",
                required_task_files_hash="xxh64:task-a-required-before",
                full_task_dir_hash="xxh64:task-a-full-before",
                required_task_files=[
                    _required_task_file("task.yaml", "file", "xxh64:task-yaml-before"),
                    _required_task_file(
                        "seed_workspace",
                        "directory",
                        "xxh64:seed-before",
                    ),
                ],
            ),
            _selected_task("task_b"),
        ],
    )
    _write_manifest(
        candidate_dir / "eval_matrix_manifest.json",
        artifact_version="eval_matrix_v0",
        selected_task_hash_set="xxh64:candidate-set",
        selected_tasks=[
            _selected_task(
                "task_a",
                task_record_hash="xxh64:task-a-record-after",
                task_yaml_hash="xxh64:task-a-yaml-after",
                required_task_files_hash="xxh64:task-a-required-after",
                full_task_dir_hash="xxh64:task-a-full-after",
                required_task_files=[
                    _required_task_file("task.yaml", "file", "xxh64:task-yaml-after"),
                    _required_task_file(
                        "hidden_tests",
                        "directory",
                        "xxh64:hidden-after",
                    ),
                ],
            ),
            _selected_task("task_c"),
        ],
    )

    comparison = compare_eval_task_hashes(reference_dir, candidate_dir)

    assert comparison.status == "drifted"
    assert comparison.task_pack_id_match is True
    assert comparison.selected_task_hash_set_match is False
    assert comparison.added_task_ids == ("task_c",)
    assert comparison.removed_task_ids == ("task_b",)
    assert len(comparison.changed_tasks) == 1
    changed_task = comparison.changed_tasks[0]
    assert changed_task.task_id == "task_a"
    assert changed_task.changed_fields == (
        "task_record_hash",
        "task_yaml_hash",
        "required_task_files_hash",
        "full_task_dir_hash",
    )
    assert [
        (drift.path, drift.status)
        for drift in changed_task.required_task_file_drifts
    ] == [
        ("seed_workspace", "removed"),
        ("hidden_tests", "added"),
        ("task.yaml", "changed"),
    ]
    assert render_eval_task_hash_comparison_summary(comparison) == [
        "task input provenance drifted",
        "reference=eval_run_v0 task_pack=repo_patch_python_v0 selected_tasks=2",
        "candidate=eval_matrix_v0 task_pack=repo_patch_python_v0 selected_tasks=2",
        (
            "drift task_pack_id_match=true "
            "selected_task_hash_set_match=false "
            "added_tasks=1 removed_tasks=1 changed_tasks=1"
        ),
        "added_task_ids=task_c",
        "removed_task_ids=task_b",
        (
            "changed_task=task_a "
            "fields=task_record_hash,task_yaml_hash,"
            "required_task_files_hash,full_task_dir_hash "
            "required_file_drifts=3"
        ),
    ]


def test_load_eval_task_hash_source_accepts_manifest_file_path(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "run_manifest.json"
    _write_manifest(
        manifest_path,
        artifact_version="eval_run_v0",
        selected_task_hash_set="xxh64:selected-set",
        selected_tasks=[_selected_task("task_a")],
    )

    source = load_eval_task_hash_source(manifest_path)

    assert source.manifest_path == manifest_path
    assert source.selected_task_hash_set == "xxh64:selected-set"
    assert [task.task_id for task in source.selected_tasks] == ["task_a"]


def test_load_eval_task_hash_source_rejects_unsupported_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(
        json.dumps({"artifact_version": "attempt_run_v0"}) + "\n"
    )

    with pytest.raises(ValueError, match="Expected eval_run_v0 or eval_matrix_v0"):
        load_eval_task_hash_source(manifest_path)


def _write_manifest(
    path: Path,
    *,
    artifact_version: str,
    selected_task_hash_set: str,
    selected_tasks: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "artifact_version": artifact_version,
                "task_hashes": {
                    "schema_version": "eval_task_hashes_v0",
                    "task_pack_id": "repo_patch_python_v0",
                    "selected_task_hash_set": selected_task_hash_set,
                    "selected_tasks": selected_tasks,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _selected_task(
    task_id: str,
    *,
    task_record_hash: str = "xxh64:task-record",
    task_yaml_hash: str = "xxh64:task-yaml",
    required_task_files_hash: str = "xxh64:required-files",
    full_task_dir_hash: str = "xxh64:full-task-dir",
    required_task_files: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "split": "practice",
        "task_record_hash": task_record_hash,
        "task_yaml_hash": task_yaml_hash,
        "required_task_files_hash": required_task_files_hash,
        "full_task_dir_hash": full_task_dir_hash,
        "required_task_files": required_task_files
        if required_task_files is not None
        else [
            _required_task_file("task.yaml", "file", "xxh64:task-yaml"),
            _required_task_file("seed_workspace", "directory", "xxh64:seed"),
        ],
    }


def _required_task_file(path: str, kind: str, hash_value: str) -> dict[str, str]:
    return {
        "path": path,
        "kind": kind,
        "hash": hash_value,
    }
