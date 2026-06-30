# Eval Report

## Run Details

- Artifact directory: experiments/runs/cli_smoke_eval_report
- Eval manifest: run_manifest.json
- Eval run id: eval_2358beec0d1b4bb78c8bcb198e580d2d
- Config name: scorer_control_policies
- Config path: configs/eval/scorer_control_policies.yaml
- Config hash: xxh64:be1a25b6a52abf58
- Policy: oracle
- Policy type: scorer_control_patch
- Policy family: control
- Control layer: scorer
- Control name: oracle
- Split: practice
- Task pack: data/task_packs/repo_patch_python_v0
- Attempts per task: 1
- Attempt count: 1
- Replay repeats: 1

## Layer Counts

| layer | status | count |
| --- | --- | ---: |
| scorer_hidden_status | PASS | 1 |
| scorer_public_status | PASS | 1 |
| scorer_status | PASS | 1 |

## Attempts

| task_id | attempt_index | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | agent_scorer_status | agent_scorer_public_status | agent_scorer_hidden_status | error_class | final_diff_hash | artifact_dir |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| toy_python_fix_001 | 0 | run_artifacts_v0 | PASS | PASS | PASS |  |  |  |  |  |  | xxh64:e3fc746d6fe0786c | attempts/toy_python_fix_001__attempt_001 |
