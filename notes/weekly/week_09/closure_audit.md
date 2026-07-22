# Week 9 Closure Audit

## Sources

This audit checks the current repository against:

- `references/agentic_evaluation_12_week_execution_manual.md`;
- `notes/weekly/week_09/plan.md`;
- `docs/post_training_data_contract.md`;
- `src/agentenv/training/README.md`;
- the canonical SFT, DPO, LoRA, harness-audit, and control-calibration
  artifacts named below.

## Verdict

Week 9 is closed.

The repository now has auditable source selection, review, repair,
preference-adjudication, target-model serialization, trainer-shaped SFT/DPO
materialization, explicit training authorization, and an operational LoRA
smoke. Invalid sources and invalid pair constructions fail in code. The final
persisted datasets reconstruct exactly from their pinned evidence chains.

The correct Week 9 claim is:

```text
reviewed trajectory evidence can be transformed into reconstructible SFT and
preference-training inputs with explicit loss ownership and authorization, and
those SFT inputs can drive a mechanically valid adapter-only LoRA smoke
```

This is not a claim that the adapter improved model quality.

## Final Trust Evidence

Fresh aggregate harness audit:

```text
artifact: experiments/harness_audit/week_09_closeout
overall status: PASS
agent audit: PASS
scorer audit: PASS
harness runtime hash: xxh64:95dc2d8fd2e7d812
harness source hash: xxh64:463eef405ab6619e
```

Fresh control calibration:

```text
artifact: experiments/runs/week_09_closeout_control_calibration
task count: 26
repeats: 3
records: 468
matching records: 468
flake status: stable
flake groups: 156
drifted groups: 0
public-check idempotency: 26/26 IDEMPOTENT
idempotency repeat count: 2
selected task hash set: xxh64:7455451b7893b71d
```

The audit and calibration runtime provenance objects are exactly equal. The
task inventory is:

```text
practice: 1
dev: 19
heldout_private: 6
public_calibration: 0
```

The six heldout task IDs and bytes remain protected by the existing freeze.
The six progressive tasks were added only to `dev`; they did not modify or
refreeze heldout content.

## Training-Data Artifacts

Canonical acquisition roots:

```text
experiments/runs/natural_model_anchor_contrast_acquisition
experiments/runs/natural_model_dev_coverage_acquisition
```

Final trainer-shaped inventory after exact source reconstruction:

```text
positive-SFT manifests: 8
positive-SFT records: 18 completed, 0 failed
DPO manifests: 8
DPO records: 29 completed, 0 failed
sequence-length exclusions: 0
materialization errors: 0
```

All 16 manifests record:

```text
training_authorization: authorized
override mode: explicit_user_override
authorized_by: kshitij
```

The override accepts a known source-runtime mismatch for a non-production
learning exercise. Upstream candidate, positive-SFT export, comparison,
adjudication, and preference-pair artifacts remain construction evidence rather
than independently authorized training releases.

Closeout reconstruction found that copied historical materializations carried
an earlier whole-source materializer hash. The affected derivatives were
rematerialized from the existing reviewed sources with the same recorded
override. No rollout, trajectory review, prefix approval, or preference label
was changed. All eight SFT and eight DPO artifact loaders then rebuilt records
exactly from their pinned source graphs under the current materializer hash:

```text
xxh64:463eef405ab6619e
```

## Loss And Preference Boundaries

Positive SFT uses one complete approved message prefix per source example.
System, user, and tool-observation tokens are context only. Loss is assigned
only to approved assistant-produced tokens, including assistant-produced
turn termination where required by the pinned model protocol. Overlength
examples fail whole rather than being silently truncated or windowed.

Preference discovery uses identical message history through a shared context
and distinct next assistant actions. Discovery does not infer direction from
task success. Adjudication is a separate authority with reviewer provenance and
a required reason. Only `preferred` decisions materialize; ties, ambiguity, and
invalid comparisons remain abstentions. DPO materialization creates one shared
masked prompt plus chosen and rejected response branches. Reference-policy
selection belongs to the later DPO training run, which was not performed in
Week 9.

## Operational LoRA Smoke

Canonical artifact:

```text
experiments/models/week_09_positive_sft_lora_smoke_qwen2_5_coder_3b
```

Observed:

```text
status: completed
base: Qwen/Qwen2.5-Coder-3B-Instruct
revision: 89fe5444e8baf5736e70f528f1edcc79e6616ef6
selected examples: 1
real optimizer steps: 3
qualification steps: 2, discarded before real training
adapter hash: xxh64:ccd2828a4bc5fbe1
```

The qualification audit established that all intended LoRA adapters received
finite nonzero gradient evidence and changed, while the optimizer owned only
adapter parameters. Real training restarted from a matching fresh step-zero
state. Frozen base tensors remained bitwise unchanged, and the saved adapter
reloaded with identical adapter state, base state, and probe logits.

Loss values and the existence of a changed adapter are execution evidence, not
efficacy evidence.

## Manual Criteria And Adaptations

The manual required a data contract, programmatic rejection of bad examples,
valid SFT JSONL, auditable preference pairs or a documented insufficiency,
tool-call serialization/loss-mask tests, and a preserved smoke result.

The implementation intentionally uses repo-native typed packages and CLI
commands instead of the manual's proposed standalone scripts and flat schema
files. It also went beyond the manual by separating:

```text
trajectory evidence
training-use eligibility
repair and repair review
positive-SFT prefix review
preference discovery and adjudication
source-level examples/pairs
target-model materialization
training authorization
training execution
```

There are 29 auditable materialized preference pairs, so an
`insufficient-pairs` DPO deferral artifact would be false. DPO optimization is
still deferred because Week 9's learning objective was the data and
materialization contract; reference-policy and comparative-training semantics
belong to the later training experiment.

## Final Verification

```text
uv run pytest -n auto
  1200 passed in 319.65 seconds

uv run ruff check .
  passed

uv run pyright
  0 errors, 0 warnings

git diff --check
  passed
```

The canonical artifacts were also loaded outside the fixture suite:

```text
8/8 SFT materialization manifests reconstructed
18/18 SFT records reconstructed
8/8 DPO materialization manifests reconstructed
29/29 DPO records reconstructed
LoRA artifact loaded with status completed and 3 training-step records
```

## Remaining Limitations

These are explicit non-claims, not Week 9 blockers:

- The LoRA smoke used one example and three optimizer steps.
- No base-versus-adapter task evaluation has been run.
- No DPO optimizer run has been performed.
- The authorized trainer artifacts rely on an explicit learning-lab override,
  not a normal source-runtime-matched release.
- Copied historical acquisition manifests retain absolute provenance references
  to the foundation worktree. The refreshed trainer derivatives point to local
  source exports and reconstruct in the current environment, but deleting the
  original worktree would break deeper historical references. Do not rewrite
  those pins by hand; reacquire under the final runtime or design an explicit
  artifact-relocation protocol before claiming portability.
- AI-proxy review provenance does not equal independent expert human review.
- The six progressive dev tasks have structural ordering but no natural-model
  difficulty evidence yet.
- The heldout-private slice has not been inspected through model outcomes and
  must remain untouched until the Week 10 policy-selection procedure is frozen.
- The local runner is not a production hostile-code sandbox.

## Week 10 Handoff

Start Week 10 with a fixed baseline-controlled comparison, not another plumbing
expansion:

```text
B0         = exact pinned base policy
S_raw      = policy trained from the broad authorized SFT materialization
S_filtered = policy trained from the frozen filtering treatment
```

Freeze train/dev roles, selection criteria, model-input protocol, serving path,
decoding settings, seeds, budgets, and comparison metrics before examining the
heldout-private slice. Evaluate B0 and adapters through the same runtime path.
Use dev evidence for iteration; reserve heldout for the final paired comparison.
DPO may follow only from the exact selected SFT policy with an explicitly pinned
reference policy.
