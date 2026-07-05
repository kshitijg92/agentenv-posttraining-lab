# Agentenv CLI Examples

Run these from the repo root:

```bash
cd /home/kshitij/agentenv-posttraining-lab
```

## Help

```bash
uv run agentenv --help
uv run agentenv tasks --help
uv run agentenv attempt --help
uv run agentenv agents --help
uv run agentenv eval --help
uv run agentenv trajectories --help
uv run agentenv training --help
uv run agentenv replay --help
uv run agentenv report --help
uv run agentenv scorers --help
uv run agentenv controls --help
uv run agentenv sandbox --help
uv run agentenv local-model --help
```

## Validate A Task Pack Or Task

Task pack:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0
```

Single task:

```bash
uv run agentenv tasks validate data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml
```

## Check Task Splits

Verify that `splits.lock.json` matches the task manifests:

```bash
uv run agentenv tasks check-splits data/task_packs/repo_patch_python_v0/splits.lock.json
```

Expected current output:

```text
valid repo_patch_python_v0 tasks=4 practice=1 dev=3 heldout_private=0 public_calibration=0
```

This checks that:

- every task manifest is assigned in `splits.lock.json`;
- no task appears in more than one split;
- task manifest `split` fields match the split lock;
- the split lock does not reference missing task IDs;
- task IDs are unique across discovered task manifests.

## Hash A Task Pack

Write a task-pack hash report:

```bash
uv run agentenv tasks hash data/task_packs/repo_patch_python_v0 \
  --out experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
```

The report includes:

- pack-level hashes for `manifest.yaml` and `splits.lock.json`;
- one record per task;
- exact hashes for `task.yaml` and every `required_task_files` entry from the
  pack manifest;
- directory hashes for entries such as `seed_workspace` and `hidden_tests`;
- normalized text hashes for task instructions and visible tests;
- `extra_task_files`, which flags task-local files outside the declared
  required-file contract.

## Run One Patch Attempt

Oracle control:

```bash
uv run agentenv attempt run \
  --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml \
  --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/oracle.patch \
  --out experiments/runs/manual_oracle_attempt
```

Known-bad no-op control:

```bash
uv run agentenv attempt run \
  --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml \
  --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/bad_noop.patch \
  --out experiments/runs/manual_bad_noop_attempt
```

Known-bad public-only control:

```bash
uv run agentenv attempt run \
  --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml \
  --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/scorer_control_patches/bad_public_only.patch \
  --out experiments/runs/manual_bad_public_only_attempt
```

## Run Configured Eval Policies

Single scorer-control policy:

```bash
uv run agentenv eval \
  --config configs/eval/scorer_control_policies.yaml \
  --policy oracle \
  --out experiments/runs/scorer_control_policies_oracle \
  --report-out experiments/reports/evals/scorer_control_policies_oracle.md

uv run agentenv eval \
  --config configs/eval/scorer_control_policies.yaml \
  --policy bad-noop \
  --out experiments/runs/scorer_control_policies_bad_noop

uv run agentenv eval \
  --config configs/eval/scorer_control_policies.yaml \
  --policy bad-public-only \
  --out experiments/runs/scorer_control_policies_bad_public_only
```

Single agent-control policy:

```bash
uv run agentenv eval \
  --config configs/eval/agent_control_policies.yaml \
  --policy agent-happy \
  --out experiments/runs/agent_control_policies_agent_happy \
  --report-out experiments/reports/evals/agent_control_policies_agent_happy.md
```

All policies from one config:

```bash
uv run agentenv eval \
  --config configs/eval/dev_baseline.yaml \
  --all-policies \
  --out experiments/runs/dev_baseline \
  --report-out experiments/reports/eval_suites/dev_baseline.md
```

`--all-policies` writes an eval suite. Replay is policy-owned through each
policy's `replay.repeats`; for `dev_baseline`, scorer and agent control
policies each request one replay run.

Eval artifact directories must be new or empty. To intentionally rerun into an
existing directory, pass `--overwrite`; this deletes and recreates `--out`
before the eval starts.

Main eval suite outputs:

```text
experiments/runs/dev_baseline/manifest.json
experiments/runs/dev_baseline/policies/
experiments/runs/dev_baseline/replays/
```

Eval manifests include a `task_hashes` block with the selected task hash set
and one hash record per task selected by the eval config. This block is scoped
to evaluated tasks only; it does not include a task-pack-level hash. Each
selected task record includes both `required_task_files` and
`required_task_files_hash`, plus `full_task_dir_hash`.

Compare selected-task hashes across eval artifacts:

```bash
uv run agentenv eval compare-task-hashes \
  --reference experiments/runs/task_hash_provenance_smoke \
  --candidate experiments/runs/task_hash_provenance_smoke

uv run agentenv eval compare-task-hashes \
  --reference experiments/runs/task_hash_provenance_smoke \
  --candidate experiments/runs/task_hash_provenance_smoke \
  --out experiments/reports/hash_comparisons/task_hash_provenance_smoke.json
```

The command accepts `eval_run` and `eval_suite` artifact directories, or direct
manifest JSON paths. It exits `0` when task input provenance matches and
non-zero when drift is detected.

## Export Private Trajectory Records

Export trajectory records from a single eval run:

```bash
uv run agentenv trajectories export \
  --source experiments/runs/scorer_control_policies_oracle \
  --out experiments/runs/scorer_control_policies_oracle_trajectory_export
```

Export trajectory records from an eval suite:

```bash
uv run agentenv trajectories export \
  --source experiments/runs/dev_baseline \
  --out experiments/runs/dev_baseline_trajectory_export
```

Main outputs:

```text
experiments/runs/dev_baseline_trajectory_export/manifest.json
experiments/runs/dev_baseline_trajectory_export/trajectories.jsonl
```

The export manifest records the source eval artifact type/id, source manifest
hash, trajectory record schema version, JSONL hash, and record count. This is a
private eval artifact for analysis and later training-data conversion; it does
not run replay, harness-audit, or training-eligibility gates.

## Initialize A Trajectory Review Workspace

Create pending review rows and a human-readable review queue from a trajectory
export:

```bash
uv run agentenv trajectories review-init \
  --source experiments/runs/dev_baseline_trajectory_export \
  --out experiments/runs/dev_baseline_trajectory_review
```

Main outputs:

```text
experiments/runs/dev_baseline_trajectory_review/manifest.json
experiments/runs/dev_baseline_trajectory_review/reviews.jsonl
experiments/runs/dev_baseline_trajectory_review/review_queue.md
```

`review-init` creates one `not_reviewed` row per trajectory and does not make
human decisions. Review rows are keyed by `trajectory_id`; the source
trajectory export remains unchanged.

Validate a review workspace after editing `reviews.jsonl`:

```bash
uv run agentenv trajectories review-validate \
  --source experiments/runs/dev_baseline_trajectory_export \
  --reviews experiments/runs/dev_baseline_trajectory_review
```

This checks that the review artifact still points to the same trajectory export
and that `reviews.jsonl` has exactly one row per trajectory with matching
identity fields.

## Export Training Candidates

Create a training-candidate artifact from a trajectory export and validated
review artifact:

```bash
uv run agentenv training candidates export \
  --trajectories experiments/runs/dev_baseline_trajectory_export \
  --reviews experiments/runs/dev_baseline_trajectory_review \
  --out experiments/runs/dev_baseline_training_candidates
```

Main outputs:

```text
experiments/runs/dev_baseline_training_candidates/manifest.json
experiments/runs/dev_baseline_training_candidates/training_candidates.jsonl
```

This export validates the trajectory/review join, builds candidate records in
memory, and persists the resulting eligibility surface. It is not an SFT dataset
or a preference dataset.

## Replay An Artifact Directory

Replay a scorer eval run:

```bash
uv run agentenv replay \
  experiments/runs/scorer_control_policies_oracle \
  --out experiments/replays/scorer_control_policies_oracle
```

Replay an agent eval run:

```bash
uv run agentenv replay \
  experiments/runs/dev_baseline/policies/agent-happy \
  --out experiments/replays/dev_baseline_agent_happy
```

Replay accepts source artifact directories such as `eval_run` policy runs and
direct `agent_attempt` artifacts.
Replay artifact directories follow the same rule: use a new/empty `--out`, or
pass `--overwrite` to recreate it.

## Write Markdown Reports

Eval commands can write reports directly with `--report-out`. To regenerate a
report from an existing artifact directory, use `agentenv report`.

Eval report:

```bash
uv run agentenv report \
  experiments/runs/scorer_control_policies_oracle \
  --out experiments/reports/evals/scorer_control_policies_oracle.md
```

Eval suite report:

```bash
uv run agentenv report \
  experiments/runs/dev_baseline \
  --out experiments/reports/eval_suites/dev_baseline.md
```

Replay report:

```bash
uv run agentenv report \
  experiments/replays/scorer_control_policies_oracle \
  --out experiments/reports/replays/scorer_control_policies_oracle.md
```

## Run The Scorer Audit

```bash
uv run agentenv scorers audit \
  --cases data/harness_audit/scorer_cases \
  --out experiments/harness_audit/scorer_audit
```

Main outputs:

```text
experiments/harness_audit/scorer_audit/scorer_audit.md
experiments/harness_audit/scorer_audit/scorer_audit_results.jsonl
experiments/harness_audit/scorer_audit/attempts/
```

## Run The Agent Task Audit

```bash
uv run agentenv agents audit \
  --cases data/harness_audit/agent_task_cases \
  --out experiments/harness_audit/agent_task_audit
```

Main outputs:

```text
experiments/harness_audit/agent_task_audit/agent_task_audit.md
experiments/harness_audit/agent_task_audit/agent_task_audit_results.jsonl
experiments/harness_audit/agent_task_audit/agent_task_runs/
```

## Run Repeated Control Calibration

```bash
uv run agentenv controls run \
  --task-pack data/task_packs/repo_patch_python_v0 \
  --repeats 3 \
  --out experiments/runs/control_calibration
```

Main outputs:

```text
experiments/runs/control_calibration/control_report.md
experiments/runs/control_calibration/control_results.jsonl
experiments/runs/control_calibration/manifest.json
```

`manifest.json` includes `flake_detection` for scorer-control
repeat artifact drift. `overall_match` is true only when expected control
outcomes match and checked repeat artifacts are stable.

## Run Docker Smoke

```bash
uv run agentenv sandbox smoke \
  --config configs/sandbox/docker_none.yaml \
  --out experiments/sandbox/docker_smoke
```

Main outputs:

```text
experiments/sandbox/docker_smoke/docker_smoke.md
experiments/sandbox/docker_smoke/docker_smoke_result.json
```

The result JSON records `image_digest` when Docker exposes a repo digest for the
configured image.

This is only a smoke check for Docker startup and `--network none`; it is not a
production sandbox guarantee.

## Set Up A Local Ollama Model

Print the recommended local model setup plan:

```bash
uv run agentenv local-model ollama plan --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
```

Download the model and smoke test the OpenAI-compatible local API:

```bash
uv run agentenv local-model ollama setup --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
```

The setup script is also runnable directly:

```bash
uv run python -m agentenv.local_model_setup.setup_ollama_model \
  --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
```

Lower-level probe, pull, and smoke commands are available for debugging:

```bash
uv run agentenv local-model ollama probe
uv run agentenv local-model ollama pull --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
uv run agentenv local-model ollama smoke --model-id hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M
```

To pre-download DeepSeek R1 Distill Qwen 14B for Week 6:

```bash
uv run agentenv local-model ollama setup \
  --model-id hf.co/unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF:Q4_K_M \
  --system-suffix ""
```

The matching configs are:

```text
configs/models/ollama_deepseek_r1_distill_qwen_14b_q4_k_m.yaml
configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml
configs/eval/agent_model_dev_ollama_deepseek_r1_distill_qwen_14b.yaml
```

Once Ollama is running, point the eval adapter at its OpenAI-compatible
endpoint:

```bash
export AGENTENV_MODEL_BASE_URL=http://localhost:11434/v1
```

Then run the local Qwen agent-model smoke:

```bash
uv run agentenv eval \
  --config configs/eval/agent_model_smoke_ollama_qwen3_14b.yaml \
  --policy local-qwen-smoke \
  --out experiments/runs/agent_model_smoke_ollama_qwen3_14b
```

Run the DeepSeek R1 Distill Qwen smoke with:

```bash
uv run agentenv eval \
  --config configs/eval/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b.yaml \
  --policy local-deepseek-r1-distill-qwen-smoke \
  --out experiments/runs/agent_model_smoke_ollama_deepseek_r1_distill_qwen_14b
```

## Run Repo Checks

```bash
uv run pytest -n auto
uv run ruff check .
uv run pyright
```

Validate generated traces:

```bash
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```
