# Eval Report

## Run Details

- Artifact directory: experiments/runs/agent_model_smoke_ollama_qwen3_14b_contract_fix
- Eval manifest: run_manifest.json
- Eval run id: eval_a875076a518246238a90546ec934c3b6
- Config name: agent_model_smoke_ollama_qwen3_14b
- Config path: configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml
- Config hash: xxh64:c4186d7dbcb37777
- Model config: configs/models/ollama_qwen3_14b_q4_k_m.yaml
- Decoding config: configs/decoding/greedy_1024.yaml
- Policy: local-qwen-smoke
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
| agent_scorer_hidden_status | PASS | 1 |
| agent_scorer_public_status | PASS | 1 |
| agent_scorer_status | PASS | 1 |
| agent_status | scored | 1 |
| prompt_loop_status | completed | 1 |

## Attempts

| task_id | attempt_index | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | agent_scorer_status | agent_scorer_public_status | agent_scorer_hidden_status | error_class | final_diff_hash | artifact_dir |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| toy_python_fix_001 | 0 | agent_task_run_artifacts_v0 |  |  |  | scored | completed | PASS | PASS | PASS |  | xxh64:f7df83e4e593672d | attempts/toy_python_fix_001__attempt_001 |
