# Eval Report

## Run Details

- Artifact directory: experiments/runs/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b
- Eval manifest: run_manifest.json
- Eval run id: eval_ae8450bc18034a6eafdcea4eea89696f
- Config name: agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b
- Config path: configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml
- Config hash: xxh64:ef560807652371b7
- Model config: configs/models/ollama_deepseek_r1_distill_qwen_14b_q4_k_m.yaml
- Decoding config: configs/decoding/greedy_1024.yaml
- Policy: local-deepseek-r1-distill-qwen-smoke
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
| prompt_loop_status | invalid_model_output | 1 |

## Attempts

| task_id | attempt_index | artifact_version | scorer_status | scorer_public_status | scorer_hidden_status | agent_status | prompt_loop_status | agent_scorer_status | agent_scorer_public_status | agent_scorer_hidden_status | error_class | final_diff_hash | artifact_dir |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| toy_python_fix_001 | 0 | agent_task_run_artifacts_v0 |  |  |  | agent_loop_failed | invalid_model_output |  |  |  | MalformedModelOutput |  | attempts/toy_python_fix_001__attempt_001 |
