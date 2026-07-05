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
        run_dir / "manifest.json",
        artifact_type="eval_run",
        artifact_schema_version="eval_run_artifact_v0",
        selected_task_hash_set="xxh64:same-set",
        selected_tasks=[_selected_task("task_a")],
    )
    _write_manifest(
        matrix_dir / "manifest.json",
        artifact_type="eval_suite",
        artifact_schema_version="eval_suite_artifact_v0",
        selected_task_hash_set="xxh64:same-set",
        selected_tasks=[_selected_task("task_a")],
    )

    comparison = compare_eval_task_hashes(run_dir, matrix_dir)

    assert comparison.status == "matched"
    assert comparison.reference.artifact_type == "eval_run"
    assert comparison.reference.artifact_schema_version == "eval_run_artifact_v0"
    assert comparison.candidate.artifact_type == "eval_suite"
    assert comparison.candidate.artifact_schema_version == "eval_suite_artifact_v0"
    assert comparison.task_pack_id_match is True
    assert comparison.selected_task_hash_set_match is True
    assert comparison.added_task_ids == ()
    assert comparison.removed_task_ids == ()
    assert comparison.changed_tasks == ()
    assert comparison.to_dict()["status"] == "matched"
    assert render_eval_task_hash_comparison_summary(comparison) == [
        "task input provenance matched",
        (
            "reference=eval_run/eval_run_artifact_v0 "
            "task_pack=repo_patch_python_v0 selected_tasks=1"
        ),
        (
            "candidate=eval_suite/eval_suite_artifact_v0 "
            "task_pack=repo_patch_python_v0 selected_tasks=1"
        ),
    ]


def test_compare_eval_task_hashes_detects_selected_task_drift(
    tmp_path: Path,
) -> None:
    reference_dir = tmp_path / "reference"
    candidate_dir = tmp_path / "candidate"
    _write_manifest(
        reference_dir / "manifest.json",
        artifact_type="eval_run",
        artifact_schema_version="eval_run_artifact_v0",
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
        candidate_dir / "manifest.json",
        artifact_type="eval_suite",
        artifact_schema_version="eval_suite_artifact_v0",
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
        (drift.path, drift.status) for drift in changed_task.required_task_file_drifts
    ] == [
        ("seed_workspace", "removed"),
        ("hidden_tests", "added"),
        ("task.yaml", "changed"),
    ]
    assert render_eval_task_hash_comparison_summary(comparison) == [
        "task input provenance drifted",
        (
            "reference=eval_run/eval_run_artifact_v0 "
            "task_pack=repo_patch_python_v0 selected_tasks=2"
        ),
        (
            "candidate=eval_suite/eval_suite_artifact_v0 "
            "task_pack=repo_patch_python_v0 selected_tasks=2"
        ),
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
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        artifact_type="eval_run",
        artifact_schema_version="eval_run_artifact_v0",
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
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact_type": "scorer_attempt",
                "artifact_schema_version": "scorer_attempt_artifact_v0",
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="Expected eval run or eval suite"):
        load_eval_task_hash_source(manifest_path)


@pytest.mark.parametrize(
    ("artifact_type", "artifact_schema_version", "expected_message"),
    [
        (
            "eval_run",
            "eval_run_artifact_v999",
            "artifact_schema_version must be",
        ),
        (
            "eval_suite",
            "eval_suite_artifact_v999",
            "artifact_schema_version must be",
        ),
    ],
)
def test_load_eval_task_hash_source_rejects_bad_artifact_schema_version(
    tmp_path: Path,
    artifact_type: str,
    artifact_schema_version: str,
    expected_message: str,
) -> None:
    _write_manifest(
        tmp_path / "manifest.json",
        artifact_type=artifact_type,
        artifact_schema_version=artifact_schema_version,
        selected_task_hash_set="xxh64:selected-set",
        selected_tasks=[_selected_task("task_a")],
    )

    with pytest.raises(ValueError, match=expected_message):
        load_eval_task_hash_source(tmp_path)


def _write_manifest(
    path: Path,
    *,
    artifact_type: str,
    artifact_schema_version: str,
    selected_task_hash_set: str,
    selected_tasks: list[dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    task_hashes = {
        "schema_version": "eval_task_hashes_v0",
        "task_pack_id": "repo_patch_python_v0",
        "selected_task_hash_set": selected_task_hash_set,
        "selected_tasks": selected_tasks,
    }
    task_ids = [
        task["task_id"] for task in selected_tasks if isinstance(task["task_id"], str)
    ]
    if artifact_type == "eval_run":
        payload = _eval_run_manifest(
            artifact_schema_version=artifact_schema_version,
            task_hashes=task_hashes,
            task_ids=task_ids,
        )
    elif artifact_type == "eval_suite":
        payload = _eval_suite_manifest(
            artifact_schema_version=artifact_schema_version,
            task_hashes=task_hashes,
            task_ids=task_ids,
        )
    else:
        payload = {
            "artifact_type": artifact_type,
            "artifact_schema_version": artifact_schema_version,
            "task_hashes": task_hashes,
        }
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _eval_run_manifest(
    *,
    artifact_schema_version: str,
    task_hashes: dict[str, object],
    task_ids: list[str],
) -> dict[str, object]:
    attempts = _scorer_attempt_records(task_ids)
    return {
        "artifact_type": "eval_run",
        "artifact_schema_version": artifact_schema_version,
        "eval_run_id": "eval_run_test",
        "created_at": "2026-06-30T00:00:00Z",
        "config_path": "configs/eval/test.yaml",
        "config_hash": "xxh64:config",
        "config_name": "test",
        "task_pack": "data/task_packs/repo_patch_python_v0",
        "split": "practice",
        "task_hashes": task_hashes,
        "policy": "oracle",
        "policy_type": "scorer_control_patch",
        "policy_family": "control",
        "control_layer": "scorer",
        "control_name": "oracle",
        "attempts_per_task": 1,
        "replay_repeats": 0,
        "attempt_count": len(attempts),
        "layer_counts": _scorer_pass_layer_counts(len(attempts)),
        "artifacts": {"trace": "trace.jsonl", "attempts": "attempts"},
        "attempts": attempts,
    }


def _eval_suite_manifest(
    *,
    artifact_schema_version: str,
    task_hashes: dict[str, object],
    task_ids: list[str],
) -> dict[str, object]:
    layer_counts = _scorer_pass_layer_counts(len(task_ids))
    return {
        "artifact_type": "eval_suite",
        "artifact_schema_version": artifact_schema_version,
        "eval_suite_id": "eval_suite_test",
        "created_at": "2026-06-30T00:00:00Z",
        "config_path": "configs/eval/test.yaml",
        "config_hash": "xxh64:config",
        "config_name": "test",
        "task_pack": "data/task_packs/repo_patch_python_v0",
        "split": "practice",
        "task_hashes": task_hashes,
        "tasks": task_ids,
        "task_count": len(task_ids),
        "policy_count": 1,
        "attempt_count": len(task_ids),
        "layer_counts": layer_counts,
        "artifacts": {"policies": "policies"},
        "policy_runs": [
            {
                "policy": "oracle",
                "policy_type": "scorer_control_patch",
                "policy_family": "control",
                "control_layer": "scorer",
                "control_name": "oracle",
                "attempts_per_task": 1,
                "replay_repeats": 0,
                "eval_run_id": "eval_run_test",
                "artifact_dir": "policies/oracle",
                "manifest": "policies/oracle/manifest.json",
                "attempt_count": len(task_ids),
                "layer_counts": layer_counts,
            }
        ],
        "replay_run_count": 0,
        "replay_policy_count": 0,
        "replay_run_success_summary": "0/0",
        "replay_runs": [],
    }


def _scorer_attempt_records(task_ids: list[str]) -> list[dict[str, object]]:
    return [
        {
            "eval_attempt_id": f"eval_attempt_{index:03d}",
            "task_id": task_id,
            "attempt_index": 0,
            "artifact_dir": f"attempts/{task_id}__attempt_001",
            "artifact_type": "scorer_attempt",
            "artifact_schema_version": "scorer_attempt_artifact_v0",
            "scorer": {
                "scorer_attempt_id": f"scorer_attempt_{index:03d}",
                "status": "PASS",
                "public_status": "PASS",
                "hidden_status": "PASS",
                "error_class": None,
                "final_diff_hash": f"xxh64:final-diff-{index:03d}",
                "duration_ms": 0,
            },
            "agent": None,
        }
        for index, task_id in enumerate(task_ids, start=1)
    ]


def _scorer_pass_layer_counts(count: int) -> dict[str, dict[str, int]]:
    return {
        "scorer_status": {"PASS": count},
        "scorer_public_status": {"PASS": count},
        "scorer_hidden_status": {"PASS": count},
    }


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
