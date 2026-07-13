#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 OUTPUT_DIRECTORY" >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_root="$1"

if [[ -e "$out_root" ]]; then
  echo "output path already exists: $out_root" >&2
  exit 2
fi

mkdir -p "$out_root"
cd "$repo_root"

uv run --frozen agentenv tasks validate \
  data/task_packs/repo_patch_python_v0
uv run --frozen agentenv tasks check-splits \
  data/task_packs/repo_patch_python_v0/splits.lock.json

uv run --frozen agentenv eval \
  --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml \
  --all-policies \
  --out "$out_root/eval" \
  --report-out "$out_root/eval_report.md"

uv run --frozen agentenv report \
  "$out_root/eval" \
  --out "$out_root/eval_report_regenerated.md"

cmp "$out_root/eval_report.md" "$out_root/eval_report_regenerated.md"

echo "core reproduction smoke passed: $out_root"
