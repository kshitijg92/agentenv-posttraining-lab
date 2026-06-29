# Eval Report

## Run Details

- Artifact directory: experiments/runs/agent_model_smoke_missing_env
- Eval manifest: run_manifest.json
- Eval run id: eval_b557b0647d474820bd043822e3c25ac2
- Config name: agent_model_smoke
- Config path: configs/eval/agent_model_smoke.yaml
- Config hash: xxh64:beaadbe71f3caee5
- Policy: real-agent-smoke
- Policy type: agent_model
- Policy family: agent
- Control layer: 
- Control name: 
- Split: practice
- Task pack: data/task_packs/repo_patch_python_v0
- Attempts per task: 1
- Attempt count: 1
- Replay repeats: 0

## Layer Counts

| layer | status | count |
| --- | --- | ---: |
| agent_status | agent_loop_failed | 1 |
| prompt_loop_status | model_error | 1 |

## Attempts

| task_id | attempt_index | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | agent_scorer_status | agent_scorer_public_status | agent_scorer_hidden_status | error_class | final_diff_hash | artifact_dir |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| toy_python_fix_001 | 0 | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | model_error |  |  |  | MissingModelBaseUrlEnvVar |  | attempts/toy_python_fix_001__attempt_001 |
