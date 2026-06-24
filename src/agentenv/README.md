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
uv run agentenv scorers --help
uv run agentenv controls --help
uv run agentenv sandbox --help
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

## Run One Patch Attempt

Oracle control:

```bash
uv run agentenv attempt run \
  --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml \
  --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/oracle.patch \
  --out experiments/runs/manual_oracle_attempt
```

Known-bad no-op control:

```bash
uv run agentenv attempt run \
  --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml \
  --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/bad_noop.patch \
  --out experiments/runs/manual_bad_noop_attempt
```

Known-bad public-only control:

```bash
uv run agentenv attempt run \
  --task-manifest data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/task.yaml \
  --submission data/task_packs/repo_patch_python_v0/tasks/toy_python_fix/controls/bad_public_only.patch \
  --out experiments/runs/manual_bad_public_only_attempt
```

## Run Configured Eval Policies

```bash
uv run agentenv eval \
  --config configs/eval/control_policies.yaml \
  --policy oracle \
  --out experiments/runs/control_policies_oracle

uv run agentenv eval \
  --config configs/eval/control_policies.yaml \
  --policy bad-noop \
  --out experiments/runs/control_policies_bad_noop

uv run agentenv eval \
  --config configs/eval/control_policies.yaml \
  --policy bad-public-only \
  --out experiments/runs/control_policies_bad_public_only
```

## Replay An Eval Run

```bash
uv run agentenv replay \
  experiments/runs/control_policies_oracle \
  --out experiments/replays/control_policies_oracle
```

## Write Markdown Reports

Eval report:

```bash
uv run agentenv report \
  experiments/runs/control_policies_oracle \
  --out experiments/reports/evals/control_policies_oracle.md
```

Replay report:

```bash
uv run agentenv report \
  experiments/replays/control_policies_oracle \
  --out experiments/reports/replays/control_policies_oracle.md
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
experiments/runs/control_calibration/control_run_manifest.json
```

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

## Run Repo Checks

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

Validate generated traces:

```bash
uv run python -c 'from pathlib import Path; from agentenv.tracing.validate import validate_trace_file; paths=sorted(Path("experiments").rglob("trace.jsonl")); [validate_trace_file(path) for path in paths]; print(f"validated {len(paths)} trace files")'
```
