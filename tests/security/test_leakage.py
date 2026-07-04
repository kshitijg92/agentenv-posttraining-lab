import json
from pathlib import Path
from typing import Any, cast

import pytest

from agentenv.security.leakage import (
    LEAKAGE_CHECK_VERSION,
    assert_hidden_validator_files_absent,
    build_private_task_metadata_markers,
    contains_hidden_validator_asset_reference,
    hash_canary,
    list_agent_visible_artifact_files,
    patch_modifies_public_tests,
    scan_agent_visible_artifacts,
    scan_directory_for_leakage,
    scan_files_for_leakage,
)
from agentenv.tasks.schema import agent_private_task_manifest_field_names
from agentenv.tasks.validate import load_task_manifest


TOY_TASK_MANIFEST = Path(
    "data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml"
)


def test_hash_canary_redacts_raw_canary() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    canary_hash = hash_canary(manifest.leakage_canary)

    assert canary_hash is not None
    assert canary_hash.startswith("xxh64:")
    assert manifest.leakage_canary not in canary_hash


def test_leakage_scan_result_derives_status_booleans() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    clean_result = scan_files_for_leakage([], manifest)

    assert not clean_result.canary_leaked
    assert not clean_result.hidden_validators_visible_to_model


def test_leakage_scan_result_rejects_independent_status_booleans() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    clean_result = scan_files_for_leakage([], manifest)
    constructor = cast(Any, type(clean_result))

    with pytest.raises(TypeError, match="canary_leaked"):
        constructor(
            leakage_check_version=LEAKAGE_CHECK_VERSION,
            canary_hash=None,
            canary_leaked=True,
            canary_matches=(),
            private_marker_matches=(),
            scanned_files=(),
        )


def test_contains_hidden_validator_asset_reference_detects_private_markers() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    texts = (
        "diff mentions hidden_tests/test_behavior.py",
        "diff mentions hidden_tests",
        f"diff mentions {manifest.leakage_canary}",
    )
    for text in texts:
        assert contains_hidden_validator_asset_reference(text, manifest)


def test_contains_hidden_validator_asset_reference_ignores_public_text() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    assert not contains_hidden_validator_asset_reference("src/mathlib.py", manifest)


def test_patch_modifies_public_tests_detects_tests_path() -> None:
    assert patch_modifies_public_tests(
        """diff --git a/tests/test_public.py b/tests/test_public.py
--- a/tests/test_public.py
+++ b/tests/test_public.py
@@ -1 +1 @@
-old
+new
"""
    )


def test_scan_files_for_leakage_reports_canary_and_hidden_markers(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    canary_file = tmp_path / "candidate.patch"
    hidden_file = tmp_path / "prompt_loop_result.json"
    clean_file = tmp_path / "agent_task_run.json"
    canary_file.write_text(f"patch text {manifest.leakage_canary}")
    hidden_file.write_text('"hidden_validators": []')
    clean_file.write_text("clean public artifact")

    result = scan_files_for_leakage(
        [clean_file, hidden_file, canary_file],
        manifest,
        root=tmp_path,
    )

    assert result.leakage_check_version == LEAKAGE_CHECK_VERSION
    assert result.canary_hash == hash_canary(manifest.leakage_canary)
    assert result.canary_leaked
    assert result.hidden_validators_visible_to_model
    assert result.canary_matches == ("candidate.patch",)
    assert result.private_marker_matches == ("prompt_loop_result.json",)
    assert result.scanned_files == (
        "agent_task_run.json",
        "candidate.patch",
        "prompt_loop_result.json",
    )
    assert manifest.leakage_canary not in repr(result)


def test_private_task_metadata_markers_come_from_schema_annotations() -> None:
    assert agent_private_task_manifest_field_names() == (
        "split",
        "hidden_validators",
        "scoring",
        "controls",
        "replay",
        "leakage_canary",
    )
    assert "controls" not in build_private_task_metadata_markers()
    assert "controls:" in build_private_task_metadata_markers()
    assert '"controls"' in build_private_task_metadata_markers()
    assert "domain" not in agent_private_task_manifest_field_names()
    assert '"domain"' not in build_private_task_metadata_markers()


def test_scan_files_for_leakage_does_not_match_bare_private_field_words(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    clean_file = tmp_path / "notes.txt"
    clean_file.write_text("experiment controls are stable")

    result = scan_files_for_leakage([clean_file], manifest, root=tmp_path)

    assert not result.hidden_validators_visible_to_model


def test_scan_files_for_leakage_does_not_match_public_domain_field(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    public_file = tmp_path / "agent_task_view.json"
    public_file.write_text('"domain": "repo_patch_python"')

    result = scan_files_for_leakage([public_file], manifest, root=tmp_path)

    assert not result.hidden_validators_visible_to_model


def test_scan_files_for_leakage_matches_structured_private_field_keys(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    private_file = tmp_path / "prompt_loop_result.json"
    private_file.write_text('"controls": {}')

    result = scan_files_for_leakage([private_file], manifest, root=tmp_path)

    assert result.hidden_validators_visible_to_model
    assert result.private_marker_matches == ("prompt_loop_result.json",)


def test_scan_directory_for_leakage_scans_agent_workspace(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src.py").write_text("clean")
    (workspace / "notes.txt").write_text("hidden_tests")

    result = scan_directory_for_leakage(workspace, manifest)

    assert result.hidden_validators_visible_to_model
    assert result.private_marker_matches == ("notes.txt",)


def test_scan_files_for_leakage_redacts_canary_from_path_refs(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    leaky_path = tmp_path / f"{manifest.leakage_canary}.txt"
    leaky_path.write_text("clean contents")

    result = scan_files_for_leakage([leaky_path], manifest, root=tmp_path)

    assert result.scanned_files == ("[REDACTED_CANARY].txt",)
    assert manifest.leakage_canary not in repr(result)


def test_assert_hidden_validator_files_absent_rejects_copied_hidden_asset(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    hidden_path = tmp_path / manifest.hidden_validators[0].path
    hidden_path.parent.mkdir(parents=True, exist_ok=True)
    hidden_path.write_text("private test")

    with pytest.raises(ValueError, match="Hidden validator .* is present"):
        assert_hidden_validator_files_absent(manifest, tmp_path)


def test_scan_agent_visible_artifacts_skips_nested_scorer_attempt(
    tmp_path: Path,
) -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    artifact_dir = tmp_path / "agent_attempt"
    nested_attempt_dir = artifact_dir / "attempt"
    nested_attempt_dir.mkdir(parents=True)
    (artifact_dir / "agent_task_run.json").write_text("clean")
    (artifact_dir / "prompt_loop_result.json").write_text("clean")
    (artifact_dir / "candidate.patch").write_text("clean")
    (nested_attempt_dir / "trace.jsonl").write_text("hidden_tests")
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "agent_attempt",
                "artifacts": {
                    "agent_task_run": "agent_task_run.json",
                    "prompt_loop_result": "prompt_loop_result.json",
                    "candidate_patch": "candidate.patch",
                    "attempt": "attempt/",
                },
            }
        )
        + "\n"
    )

    files = list_agent_visible_artifact_files(artifact_dir)
    result = scan_agent_visible_artifacts(artifact_dir, manifest)

    assert tuple(path.relative_to(artifact_dir).as_posix() for path in files) == (
        "agent_task_run.json",
        "candidate.patch",
        "manifest.json",
        "prompt_loop_result.json",
    )
    assert not result.canary_leaked
    assert not result.hidden_validators_visible_to_model


def test_list_agent_visible_artifact_files_rejects_path_traversal(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "agent_attempt"
    artifact_dir.mkdir()
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "agent_attempt",
                "artifacts": {"agent_task_run": "../agent_task_run.json"},
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="must stay inside artifact directory"):
        list_agent_visible_artifact_files(artifact_dir)
