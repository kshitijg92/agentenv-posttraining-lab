from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from agentenv.rewards.cases import (
    hash_harness_audit_case_dir,
    load_reward_hack_case,
    verify_reward_hack_case_source_refs,
)
from agentenv.rewards.schema import (
    NoOpPatchExploit,
    PublicCheckTamperingExploit,
    PublicTestOnlyPassExploit,
    RewardHackCase,
)


CASE_PATH = Path(
    "data/reward_hack_cases/"
    "hidden_validator_path_submitted_patch_text_probe_attempt/case.yaml"
)
CASE_ROOT = Path("data/reward_hack_cases")


def test_load_reward_hack_case_accepts_hidden_validator_probe_case() -> None:
    case = load_reward_hack_case(CASE_PATH)

    assert case.schema_version == "reward_hack_case_v0"
    assert (
        case.reward_hack_id
        == "hidden_validator_path_submitted_patch_text_probe_attempt"
    )
    assert case.evidence.source_type == "scorer_audit_case"
    assert case.evidence.exploit.case_id == "hidden_validator_path_reference"
    assert case.evidence.valid_control.case_id == "correct_oracle"
    assert case.exploit.exploit_classification == "hidden_validator_probe_attempt"
    assert case.exploit.exploit_spec.probe_surface == "submitted_patch_text"
    assert case.exploit.exploit_spec.probe_reference_type == "hidden_validator_path"
    assert not case.expected_reward_hack_outcome.private_content_exposed
    assert case.expected_reward_hack_outcome.exploit_blocked
    assert not case.expected_reward_hack_outcome.training_allowed


def test_verify_reward_hack_case_source_refs_accepts_current_hashes() -> None:
    case = load_reward_hack_case(CASE_PATH)

    verify_reward_hack_case_source_refs(case, repo_root=Path.cwd())


def test_all_authored_reward_hack_cases_load_and_resolve_source_refs() -> None:
    cases = [
        load_reward_hack_case(path)
        for path in sorted(CASE_ROOT.rglob("case.yaml"))
    ]

    assert {
        case.reward_hack_id for case in cases
    } == {
        "hidden_validator_path_agent_tool_call_probe_attempt",
        "hidden_validator_path_submitted_patch_text_probe_attempt",
        "leakage_canary_agent_tool_call_probe_attempt",
        "leakage_canary_submitted_patch_text_probe_attempt",
        "no_op_patch_submitted_patch_text_probe_attempt",
        "public_check_tampering_submitted_patch_text_probe_attempt",
        "public_test_only_pass_submitted_patch_text_probe_attempt",
    }
    for case in cases:
        verify_reward_hack_case_source_refs(case, repo_root=Path.cwd())


def test_harness_audit_case_hashes_are_computable_for_runtime_outputs() -> None:
    assert (
        hash_harness_audit_case_dir(
            Path("data/harness_audit/scorer_cases/hidden_validator_path_reference")
        )
        == "xxh64:6680377130ae68d3"
    )
    assert (
        hash_harness_audit_case_dir(
            Path("data/harness_audit/scorer_cases/correct_oracle")
        )
        == "xxh64:b48668468074a4f9"
    )


def test_reward_hack_case_rejects_missing_valid_control() -> None:
    payload = _case_payload()
    payload["evidence"].pop("valid_control")

    with pytest.raises(ValidationError) as exc_info:
        RewardHackCase.model_validate(payload)

    error_types = {error["type"] for error in exc_info.value.errors()}
    assert "missing" in error_types


def test_reward_hack_case_rejects_training_allowed_expectation() -> None:
    payload = _case_payload()
    payload["expected_reward_hack_outcome"]["training_allowed"] = True

    with pytest.raises(
        ValidationError,
        match="reward-hack cases cannot be training-allowed",
    ):
        RewardHackCase.model_validate(payload)


def test_reward_hack_case_accepts_no_op_patch_exploit_spec() -> None:
    payload = _case_payload()
    payload["reward_hack_id"] = "no_op_patch_schema_probe"
    payload["exploit"] = {
        "exploit_classification": "no_op_patch",
        "exploit_spec": {
            "probe_surface": "submitted_patch_text",
            "patch_must_be_empty": True,
        },
    }

    case = RewardHackCase.model_validate(payload)

    assert isinstance(case.exploit, NoOpPatchExploit)
    assert case.exploit.exploit_classification == "no_op_patch"
    assert case.exploit.exploit_spec.probe_surface == "submitted_patch_text"
    assert case.exploit.exploit_spec.patch_must_be_empty is True


def test_reward_hack_case_accepts_public_test_only_pass_exploit_spec() -> None:
    payload = _case_payload()
    payload["reward_hack_id"] = "public_test_only_pass_schema_probe"
    payload["exploit"] = {
        "exploit_classification": "public_test_only_pass",
        "exploit_spec": {
            "probe_surface": "submitted_patch_text",
            "patch_must_be_non_empty": True,
            "public_tests_must_not_be_modified": True,
        },
    }

    case = RewardHackCase.model_validate(payload)

    assert isinstance(case.exploit, PublicTestOnlyPassExploit)
    assert case.exploit.exploit_classification == "public_test_only_pass"
    assert case.exploit.exploit_spec.probe_surface == "submitted_patch_text"
    assert case.exploit.exploit_spec.patch_must_be_non_empty is True
    assert case.exploit.exploit_spec.public_tests_must_not_be_modified is True


def test_reward_hack_case_accepts_public_check_tampering_exploit_spec() -> None:
    payload = _case_payload()
    payload["reward_hack_id"] = "public_check_tampering_schema_probe"
    payload["exploit"] = {
        "exploit_classification": "public_check_tampering",
        "exploit_spec": {
            "probe_surface": "submitted_patch_text",
            "public_test_files_must_be_modified": True,
            "expected_blocking_layer": "patch_preflight_public_test_guard",
        },
    }

    case = RewardHackCase.model_validate(payload)

    assert isinstance(case.exploit, PublicCheckTamperingExploit)
    assert case.exploit.exploit_classification == "public_check_tampering"
    assert case.exploit.exploit_spec.probe_surface == "submitted_patch_text"
    assert case.exploit.exploit_spec.public_test_files_must_be_modified is True
    assert (
        case.exploit.exploit_spec.expected_blocking_layer
        == "patch_preflight_public_test_guard"
    )


def test_reward_hack_case_rejects_disabled_no_op_patch_requirement() -> None:
    payload = _case_payload()
    payload["exploit"] = {
        "exploit_classification": "no_op_patch",
        "exploit_spec": {
            "probe_surface": "submitted_patch_text",
            "patch_must_be_empty": False,
        },
    }

    with pytest.raises(ValidationError, match="patch_must_be_empty=true"):
        RewardHackCase.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "match"),
    [
        ("patch_must_be_non_empty", "patch_must_be_non_empty=true"),
        (
            "public_tests_must_not_be_modified",
            "public_tests_must_not_be_modified=true",
        ),
    ],
)
def test_reward_hack_case_rejects_disabled_public_test_only_pass_requirements(
    field: str,
    match: str,
) -> None:
    payload = _case_payload()
    payload["exploit"] = {
        "exploit_classification": "public_test_only_pass",
        "exploit_spec": {
            "probe_surface": "submitted_patch_text",
            "patch_must_be_non_empty": True,
            "public_tests_must_not_be_modified": True,
        },
    }
    payload["exploit"]["exploit_spec"][field] = False

    with pytest.raises(ValidationError, match=match):
        RewardHackCase.model_validate(payload)


def test_reward_hack_case_rejects_disabled_public_check_tampering_requirement() -> None:
    payload = _case_payload()
    payload["exploit"] = {
        "exploit_classification": "public_check_tampering",
        "exploit_spec": {
            "probe_surface": "submitted_patch_text",
            "public_test_files_must_be_modified": False,
            "expected_blocking_layer": "patch_preflight_public_test_guard",
        },
    }

    with pytest.raises(
        ValidationError,
        match="public_test_files_must_be_modified=true",
    ):
        RewardHackCase.model_validate(payload)


def test_verify_reward_hack_case_source_refs_rejects_case_id_mismatch() -> None:
    payload = _case_payload()
    payload["evidence"]["exploit"]["case_id"] = "not_the_real_case"
    case = RewardHackCase.model_validate(payload)

    with pytest.raises(ValueError, match="case id mismatch"):
        verify_reward_hack_case_source_refs(case, repo_root=Path.cwd())


def test_verify_reward_hack_case_source_refs_rejects_task_manifest_mismatch(
    tmp_path: Path,
) -> None:
    exploit_dir = _write_scorer_case_dir(
        tmp_path / "exploit",
        case_id="exploit_case",
        task_manifest="data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml",
    )
    control_dir = _write_scorer_case_dir(
        tmp_path / "control",
        case_id="control_case",
        task_manifest="data/task_packs/repo_patch_python_v0/tasks/repair_jsonl_deduper/task.yaml",
    )
    payload = _case_payload()
    payload["evidence"] = {
        "source_type": "scorer_audit_case",
        "exploit": {
            "case_dir": exploit_dir.relative_to(tmp_path).as_posix(),
            "case_id": "exploit_case",
        },
        "valid_control": {
            "case_dir": control_dir.relative_to(tmp_path).as_posix(),
            "case_id": "control_case",
        },
    }
    case = RewardHackCase.model_validate(payload)

    with pytest.raises(ValueError, match="same task manifest"):
        verify_reward_hack_case_source_refs(case, repo_root=tmp_path)


def test_harness_audit_case_hash_normalizes_notes_text(tmp_path: Path) -> None:
    case_dir_a = _write_harness_case_dir(tmp_path / "a", notes="# Notes\n\nHello   WORLD\n")
    case_dir_b = _write_harness_case_dir(tmp_path / "b", notes="# notes hello world\n")

    assert hash_harness_audit_case_dir(case_dir_a) == hash_harness_audit_case_dir(
        case_dir_b
    )


def test_harness_audit_case_hash_changes_when_execution_file_changes(
    tmp_path: Path,
) -> None:
    case_dir_a = _write_harness_case_dir(tmp_path / "a", patch="same patch\n")
    case_dir_b = _write_harness_case_dir(tmp_path / "b", patch="different patch\n")

    assert hash_harness_audit_case_dir(case_dir_a) != hash_harness_audit_case_dir(
        case_dir_b
    )


def _case_payload() -> dict[str, Any]:
    raw = yaml.safe_load(CASE_PATH.read_text())
    assert isinstance(raw, dict)
    return raw


def _write_harness_case_dir(
    path: Path,
    *,
    notes: str = "# Notes\n",
    patch: str = "patch text\n",
) -> Path:
    path.mkdir()
    (path / "case.yaml").write_text("id: sample\n")
    (path / "submission.patch").write_text(patch)
    (path / "notes.md").write_text(notes)
    return path


def _write_scorer_case_dir(
    path: Path,
    *,
    case_id: str,
    task_manifest: str,
) -> Path:
    path.mkdir()
    (path / "case.yaml").write_text(
        "\n".join(
            [
                f"id: {case_id}",
                f"task_manifest: {task_manifest}",
                "submission: submission.patch",
                "expected_attempt_status: PASS",
                "expected_public_status: PASS",
                "expected_hidden_status: PASS",
                'purpose: "temporary scorer audit case"',
                "",
            ]
        )
    )
    (path / "submission.patch").write_text("")
    (path / "notes.md").write_text("# Notes\n")
    return path
