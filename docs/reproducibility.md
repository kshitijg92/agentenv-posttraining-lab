# Reproducibility

## Deterministic Core Smoke

Run the model-free reproduction smoke from the repository root with a new
output directory:

```bash
scripts/reproduce_core_smoke.sh experiments/reproduction/core_smoke
```

The command:

1. validates the task pack;
2. validates the split lock;
3. runs the deterministic scorer and scripted-agent control matrix;
4. runs the configured control replays;
5. writes the eval report;
6. regenerates the same report from persisted artifacts; and
7. requires the original and regenerated reports to be byte-identical.

The output path must not already exist. This preserves the repository's
fail-closed artifact-directory behavior and prevents stale files from being
mistaken for current evidence.

The smoke uses `uv run --frozen`, so it refuses to update dependency resolution
while reproducing the run. Eval manifests record the harness source,
`pyproject.toml`, `uv.lock`, Python implementation and version, platform, and
machine hashes through the existing runtime-provenance contract. Task and
config content are also hash-pinned by the eval artifacts.

## What This Reproduces

The smoke exercises the complete deterministic path from task loading through
public checks, hidden scoring, scripted agent actions, replay, artifact
persistence, manifest validation, and report regeneration. It requires neither
network access nor a local model server.

It supports the narrow claim that the checked-out deterministic harness and
control inputs can regenerate their declared outcomes and report under the
recorded runtime.

## What This Does Not Reproduce

The smoke does not rerun:

- stochastic local-model inference;
- provider availability or scheduling;
- GPU kernels or model-server state;
- human trajectory, reward-hack, repair, or positive-SFT reviews;
- filtering, preference construction, or training, whose contracts are still
  under design; or
- historical artifacts created under a different harness runtime.

Saved model trajectories can be rescored or analyzed only within the guarantees
of their pinned artifacts. Deterministic scorer replay is not evidence that a
stochastic model would emit the same transcript again.

## Continuous Integration

`.github/workflows/core-repro-smoke.yml` installs the locked development
environment, runs Ruff, Pyright, and the full test suite, then runs the same
model-free reproduction smoke in a fresh runner directory. A passing local
smoke is useful evidence but is not a substitute for a successful clean CI run.
