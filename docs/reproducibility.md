# Reproducibility

## Core Command

Run the CPU-only core reproduction from the repository root with a fresh output
directory:

```bash
uv run --offline --frozen agentenv reproduce core \
  --out experiments/reproduction/core_smoke
```

The shell wrapper is an equivalent convenience entrypoint:

```bash
scripts/reproduce_core_smoke.sh experiments/reproduction/core_smoke
```

The output path must be empty or absent. The command writes:

```text
stored_evidence/stored_evidence_verification.md
stored_evidence/reports/*.md
eval/
eval_report.md
eval_report_regenerated.md
reproduction_report.md
```

`reproduction_report.md` is the final human-facing evidence for that invocation.
It records the exact resolved command, current source/dependency/runtime hashes,
Git state, required check counts, canonical top-level artifact identities,
reproduction levels, portability blockers, supported claim, and non-claims. It
does not replace any upstream manifest as an authority.

## Reproduction Levels

The core command distinguishes four different claims:

| level | operation | default status |
| --- | --- | --- |
| 1 | Validate designated stored Week 10 training/eval graphs and regenerate their reports | required |
| 2 | Execute fresh deterministic controls, hidden scoring, replay, and report regeneration | required |
| 3 | Rerun live model inference | skipped |
| 4 | Rerun optimization | skipped |

Level 1 validates the task pack and split lock, loads the three designated
training graphs, reconstructs both stored policy-selection decisions, checks
the pinned suite/report hashes, and requires both canonical reports to
regenerate byte-for-byte.

Level 2 executes 18 scorer/scripted-agent control attempts across three tasks,
checks their declared outcomes, validates six fresh replays, and requires the
two same-run eval reports to be byte-identical. It requires no GPU, paid API,
network access, model download, or local model server. The core workflow
enforces `UV_OFFLINE=1` while task checks run; the locked dependencies must
therefore already be available from environment setup.

Passing Levels 1 and 2 does not imply that Level 3 or Level 4 ran.

## Metadata Ownership

Metadata remains with the execution it describes:

- training manifests and results own the base repository/revision, adapter
  hash, input protocol, exact training config and seed, source materialization
  hashes, trainer-code hash, framework/runtime versions, Git state, and
  accelerator identity;
- eval suite and attempt artifacts own config/task hashes, harness source and
  lock hashes, Python/platform identity, model/provider digest, decoding
  strategy, input protocol, scorer behavior, and replay evidence;
- the final core report owns only the status and environment of the composed
  reproduction invocation and cites the existing artifact identities.

There is deliberately no global provenance manifest that recopies all of those
facts.

## Current Portability Boundary

Here, "stored" or "archived" evidence means retained, immutable, hash-pinned
local evidence. It does not currently mean a portable artifact bundle.

The designated Week 10 artifacts and reports live under the Git-ignored
`experiments/` tree. Historical manifests also contain absolute references to
repository-owned configs and upstream artifacts. Consequently:

- the present workstation can run Level 1 at the original checkout location;
- a clean clone does not contain the complete Level 1 inputs;
- copying only the three top-level training directories and two eval suites to
  another path is insufficient because their internal graph references remain
  location-bound.

The core report detects and states these blockers. Until a portable bundle and
repository-relative graph contract exist, do not claim clean-checkout Level 1
reproduction. Content hashes establish artifact identity; they do not by
themselves establish artifact availability or relocatability.

## Failure Injection

The core command does not rerun failure injection and therefore does not report
those cases as passing. Run the focused recovery matrix separately:

```bash
uv run --frozen pytest -q tests/test_resume.py
```

It covers interruption, missing or corrupt terminal evidence, duplicate task
and eval-attempt ids, model/scorer timeout, missing hidden validators, bad
config paths, and config/task/harness drift. Those tests establish recovery and
fail-closed semantics; they do not reproduce Week 10 model outputs.

## Deterministic Level 2 In A Clean Clone

Level 2 uses tracked configs, tasks, controls, and source. After installing the
locked environment, it can be exercised without the local Week 10 evidence:

```bash
uv run --offline --frozen agentenv eval \
  --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml \
  --all-policies \
  --out /tmp/agentenv-deterministic-eval \
  --report-out /tmp/agentenv-deterministic-eval.md

uv run --offline --frozen agentenv report \
  /tmp/agentenv-deterministic-eval \
  --out /tmp/agentenv-deterministic-eval-regenerated.md

cmp \
  /tmp/agentenv-deterministic-eval.md \
  /tmp/agentenv-deterministic-eval-regenerated.md
```

The eval command exits nonzero when control outcomes or configured replays do
not match their declared expectations.

## Continuous Integration

`.github/workflows/core-repro-smoke.yml` installs the locked environment, runs
Ruff, Pyright, and the test suite, then executes the tracked deterministic Level
2 path above. Tests whose subject is the local ignored evidence graph are
explicitly skipped only when those inputs are absent.

CI does not run or claim Level 1. Adding the local artifact path to a CI command
would not make the artifacts available; Level 1 belongs in CI only after the
complete graph has a real publication and relocation contract.

## Supported Claim And Non-Claims

A passing local core report supports only this claim:

```text
At the recorded checkout and artifact location, the designated stored
post-training evidence reconstructs under its pinned manifests, and the
current locked harness executes the deterministic control, hidden-scorer,
replay, artifact, and report path with all required checks passing.
```

It does not reproduce stochastic model samples, provider scheduling, GPU
kernels, optimization, or human review. It does not inspect heldout-private
outcomes and does not establish model improvement or broad coding-agent
capability.
