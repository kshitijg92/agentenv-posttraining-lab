import json
from pathlib import Path

from agentenv.evals.validate import load_eval_config, validate_eval_config_paths
from agentenv.tasks.splits import check_splits_lock
from agentenv.tasks.validate import validate_task_pack


TASK_PACK = Path("data/task_packs/repo_patch_python_v0")
TASK_IDS = (
    "repair_alias_chain",
    "repair_inventory_transaction",
    "repair_access_policy",
    "repair_config_inheritance",
    "repair_event_rollup",
    "repair_job_dispatch",
)
EXPECTED_SOURCE_FILE_COUNTS = (1, 3, 4, 5, 6, 7)
EVAL_CONFIGS = (
    Path("configs/eval/progressive_dev_controls.yaml"),
    Path("configs/eval/progressive_dev_acquisition.yaml"),
    Path("configs/eval/progressive_dev_budget_matrix.yaml"),
)


def test_progressive_tasks_belong_to_the_main_development_pack() -> None:
    result = validate_task_pack(TASK_PACK)
    splits = check_splits_lock(TASK_PACK / "splits.lock.json")

    assert result.task_pack_id == "repo_patch_python_v0"
    assert result.task_count == 26
    assert splits.split_counts == {
        "practice": 1,
        "dev": 19,
        "heldout_private": 6,
        "public_calibration": 0,
    }
    split_lock = json.loads((TASK_PACK / "splits.lock.json").read_text())
    assert set(TASK_IDS).issubset(split_lock["dev"])


def test_documented_structural_progression_matches_source_layout() -> None:
    observed = tuple(
        len(list((TASK_PACK / "tasks" / task_id / "seed_workspace/src").glob("*.py")))
        for task_id in TASK_IDS
    )

    assert observed == EXPECTED_SOURCE_FILE_COUNTS


def test_progressive_eval_configs_resolve_the_complete_suite() -> None:
    for config_path in EVAL_CONFIGS:
        config = load_eval_config(config_path)
        validate_eval_config_paths(config, config_path)
        assert config.task_pack == TASK_PACK.as_posix()
        assert tuple(config.tasks) == TASK_IDS
        assert config.split == "dev"


def test_each_task_has_discriminating_scorer_controls() -> None:
    for task_id in TASK_IDS:
        control_dir = TASK_PACK / "tasks" / task_id / "controls/scorer_control_patches"
        assert (control_dir / "oracle.patch").stat().st_size > 0
        assert (control_dir / "bad_noop.patch").read_bytes() == b""
        assert (control_dir / "bad_public_only.patch").stat().st_size > 0
