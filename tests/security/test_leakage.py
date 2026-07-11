import json
from pathlib import Path
from typing import Any, cast

import pytest

from agentenv.models.schema import Message
from agentenv.security.leakage import (
    LEAKAGE_CHECK_VERSION,
    LeakageScanText,
    assert_hidden_validator_files_absent,
    build_private_task_metadata_markers,
    contains_hidden_validator_asset_reference,
    find_hidden_validator_reference_types,
    hash_canary,
    list_agent_visible_artifact_files,
    patch_modifies_public_tests,
    scan_agent_visible_artifacts,
    scan_directory_for_leakage,
    scan_files_for_leakage,
    scan_messages_for_leakage,
    scan_texts_for_leakage,
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


def test_find_hidden_validator_reference_types_distinguishes_path_and_canary() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    assert find_hidden_validator_reference_types(
        "hidden_tests/test_behavior.py",
        manifest,
    ) == {"hidden_validator_path"}
    assert find_hidden_validator_reference_types(
        manifest.leakage_canary,
        manifest,
    ) == {"leakage_canary"}
    assert find_hidden_validator_reference_types(
        f"hidden_tests {manifest.leakage_canary}",
        manifest,
    ) == {"hidden_validator_path", "leakage_canary"}


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


def test_scan_texts_for_leakage_reports_canary_and_private_markers() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    result = scan_texts_for_leakage(
        (
            LeakageScanText("task_input", "clean public text"),
            LeakageScanText(
                f"message:{manifest.leakage_canary}",
                f"assistant repeated {manifest.leakage_canary}",
            ),
            LeakageScanText("message:hidden", '"controls": {}'),
        ),
        manifest,
    )

    assert result.canary_leaked
    assert result.hidden_validators_visible_to_model
    assert result.canary_matches == ("message:[REDACTED_CANARY]",)
    assert result.private_marker_matches == ("message:hidden",)
    assert result.scanned_files == (
        "task_input",
        "message:[REDACTED_CANARY]",
        "message:hidden",
    )
    assert manifest.leakage_canary not in repr(result)


def test_scan_texts_for_leakage_rejects_empty_refs() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)

    with pytest.raises(ValueError, match="refs must be non-empty"):
        scan_texts_for_leakage((LeakageScanText("", "clean"),), manifest)


def test_scan_messages_for_leakage_accepts_model_visible_messages() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    messages = (
        Message(role="system", name="agentenv", content="Use JSON actions only."),
        Message(role="user", name="task_view", content="Fix src/mathlib.py."),
        Message(
            role="assistant",
            content='{"action": "tool_call", "tool_name": "run_tests"}',
        ),
        Message(
            role="tool",
            name="run_tests",
            tool_call_id="tool_call_0001",
            content='{"status": "failed", "output": "public test failed"}',
        ),
    )

    result = scan_messages_for_leakage(messages, manifest)

    assert not result.canary_leaked
    assert not result.hidden_validators_visible_to_model
    assert result.scanned_files == (
        "message:0:system",
        "message:1:user",
        "message:2:assistant",
        "message:3:tool",
    )


def test_scan_messages_for_leakage_scans_content_and_metadata() -> None:
    manifest = load_task_manifest(TOY_TASK_MANIFEST)
    messages = (
        Message(
            role="assistant",
            content=f"I saw {manifest.leakage_canary}",
        ),
        Message(
            role="tool",
            name="run_tests",
            tool_call_id="tool_call_0001",
            content="public output",
            metadata={"controls": "private field key leaked"},
        ),
        Message(
            role="tool",
            name="read_file",
            tool_call_id="tool_call_0002",
            content="hidden_tests/test_behavior.py",
        ),
    )

    result = scan_messages_for_leakage(messages, manifest)

    assert result.canary_matches == ("message:0:assistant",)
    assert result.private_marker_matches == (
        "message:1:tool",
        "message:2:tool",
    )


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
    (artifact_dir / "decoding_config.json").write_text("clean")
    (artifact_dir / "agent_task_view.json").write_text("clean")
    (artifact_dir / "error.txt").write_text("clean")
    (artifact_dir / "prompt_loop_result.json").write_text("clean")
    (artifact_dir / "candidate.patch").write_text("clean")
    (nested_attempt_dir / "trace.jsonl").write_text("hidden_tests")
    (artifact_dir / "manifest.json").write_text(
        json.dumps(
            _agent_attempt_manifest(
                artifacts={
                    "agent_task_run": "agent_task_run.json",
                    "decoding_config": "decoding_config.json",
                    "agent_task_view": "agent_task_view.json",
                    "error": "error.txt",
                    "prompt_loop_result": "prompt_loop_result.json",
                    "candidate_patch": "candidate.patch",
                    "attempt": "attempt",
                }
            )
        )
        + "\n"
    )

    files = list_agent_visible_artifact_files(artifact_dir)
    result = scan_agent_visible_artifacts(artifact_dir, manifest)

    assert tuple(path.relative_to(artifact_dir).as_posix() for path in files) == (
        "agent_task_run.json",
        "agent_task_view.json",
        "candidate.patch",
        "decoding_config.json",
        "error.txt",
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
            _agent_attempt_manifest(
                artifacts={
                    "agent_task_run": "agent_task_run.json",
                    "decoding_config": "decoding_config.json",
                    "agent_task_view": "agent_task_view.json",
                    "error": "error.txt",
                    "prompt_loop_result": "prompt_loop_result.json",
                }
                | {"agent_task_run": "../agent_task_run.json"}
            )
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="parent traversal"):
        list_agent_visible_artifact_files(artifact_dir)


def _agent_attempt_manifest(*, artifacts: dict[str, str]) -> dict[str, object]:
    return {
        "artifact_type": "agent_attempt",
        "artifact_schema_version": "agent_attempt_artifact_v0",
        "orchestrator_version": "agent_task_run_orchestrator_v0",
        "agent_attempt_id": "agent_attempt_test",
        "task_id": "toy_python_fix_001",
        "task_manifest_path": str(TOY_TASK_MANIFEST),
        "status": "agent_loop_failed",
        "prompt_loop_status": "model_error",
        "attempt_status": None,
        "artifacts": artifacts,
    }
