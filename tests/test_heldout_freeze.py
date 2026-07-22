import json
from pathlib import Path
from typing import Any

from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.hashing import hash_file
from agentenv.tasks.hashing import build_task_hash_report


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
FREEZE_PATH = TASK_PACK / "heldout_private.freeze.json"
CONTROL_CONFIG = Path("configs/eval/heldout_private_control_gate.yaml")
HASH_FIELDS = (
    "task_yaml_hash",
    "instruction_normalized_hash",
    "visible_tests_normalized_hash",
    "required_task_files_hash",
    "full_task_dir_hash",
    "task_record_hash",
)


def test_heldout_freeze_matches_current_task_bytes_and_split() -> None:
    freeze = _load_json(FREEZE_PATH)
    report = build_task_hash_report(TASK_PACK).payload.model_dump(mode="json")

    assert freeze["artifact_type"] == "heldout_private_freeze"
    assert freeze["freeze_version"] == "heldout_private_freeze_v0"
    assert freeze["natural_model_attempt_count_at_freeze"] == 0
    assert freeze["manifest_yaml_hash"] == report["manifest_yaml_hash"]
    assert freeze["splits_lock_hash"] == report["splits_lock_hash"]
    assert freeze["pack_record_hash_at_freeze"] == report["pack_record_hash"]

    heldout_records = {
        record["task_id"]: record
        for record in report["tasks"]
        if record["split"] == "heldout_private"
    }
    frozen_records = {record["task_id"]: record for record in freeze["tasks"]}
    assert frozen_records.keys() == heldout_records.keys()
    assert len(frozen_records) == 6
    for task_id, frozen_record in frozen_records.items():
        current_record = heldout_records[task_id]
        for field in HASH_FIELDS:
            assert frozen_record[field] == current_record[field]


def test_heldout_control_gate_contains_only_deterministic_controls() -> None:
    freeze = _load_json(FREEZE_PATH)
    config = load_eval_config(CONTROL_CONFIG)
    validate_eval_config_paths(config, CONTROL_CONFIG)

    assert config.split == "heldout_private"
    assert set(config.tasks) == {record["task_id"] for record in freeze["tasks"]}
    assert {policy.type for policy in config.policies.values()} == {
        "scorer_control_patch",
        "agent_control_script",
    }
    assert freeze["control_gate"]["config_path"] == CONTROL_CONFIG.as_posix()
    assert freeze["control_gate"]["config_file_hash"] == hash_file(CONTROL_CONFIG)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    assert isinstance(payload, dict)
    return payload
