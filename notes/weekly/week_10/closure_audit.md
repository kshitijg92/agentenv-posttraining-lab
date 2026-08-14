# Week 10 Closure Audit

## Sources

This audit checks the current repository against:

- `references/agentic_evaluation_12_week_execution_manual.md`;
- `notes/weekly/week_10/plan.md`;
- `notes/weekly/week_10/implementation_notes.md`;
- `notes/weekly/week_10/learnings.md`;
- the positive-SFT review, materialization, training, serving, evaluation, and
  policy-comparison artifacts named below;
- the DPO materialization, training, serving, and disjoint evaluation artifacts
  named below.

## Verdict

Week 10 is closed.

The repository completed a controlled base-versus-SFT comparison and an
explicitly exploratory DPO continuation. The SFT experiment used the existing
reviewed `PositiveSFTExampleRecord` population directly: 98 prefix-accepted
examples formed the raw arm, and the embedded efficiency judgment retained 94
of them for the filtered arm. Both adapters trained for 98 optimizer steps over
the same pinned base and model-input protocol, then ran through the same
immutable Ollama base-plus-adapter serving path.

The frozen eight-task development selection matrix produced zero task successes
for all three SFT policies. The predeclared rule therefore abstained: token and
action counts were reported, but an empty successful-task set could not support
an efficiency tie-break. No SFT policy was established as better than the base.

DPO was consequently run only as an exploratory continuation from the exact
filtered-SFT checkpoint, not as a continuation from a selected winner. Its
mechanics were valid, but its first evaluation reused two preference-source
tasks and was demoted to a contaminated diagnostic. A replacement six-task
comparison excluded the complete DPO training-task lineage. All three policies
again achieved zero successes, and DPO exhausted every turn budget while
copying the prompt's illustrative tool calls. There is no evidence of DPO
benefit in Week 10.

The correct Week 10 claim is:

```text
The lab reproducibly filtered already-authorized positive-SFT units, trained
matched-exposure raw and efficiency-filtered LoRA treatments, compared them
with the pinned base on a task-disjoint development set, and correctly
abstained when all policies scored zero. An exploratory DPO continuation was
mechanically valid but showed prompt-copying collapse on a corrected disjoint
evaluation.
```

This is not a claim of model improvement, broad coding capability, or heldout
generalization.

## Positive-SFT Population And Filtering

The semantic training unit remained the existing source-level
`PositiveSFTExampleRecord`. Efficiency was reviewed on its already-approved
assistant prefix inside `PositiveSFTReviewRecord`; no second review artifact or
copied filtered dataset was introduced.

Final accounting:

```text
combined review universe: 100
prefix accepted: 98
prefix rejected: 2
efficiency accepted: 94
efficiency rejected: 4
unresolved or abstained efficiency judgments: 0

raw examples: 98
raw supervised tokens: 16,412
raw serialized sequence tokens: 97,005

filtered unique examples: 94
filtered unique supervised tokens: 13,207
filtered unique serialized sequence tokens: 86,700
```

The raw arm used all 98 prefix-accepted records. The filtered arm selected the
94 records whose embedded efficiency judgment was accepted, then repeated four
complete examples deterministically to reach the same 98 optimizer steps. Its
executed exposure was 16,071 supervised tokens and 94,440 serialized context
tokens, a 341-supervised-token shortfall within the frozen 907-token
complete-example tolerance.

All eight source exports and materializations were regenerated after review:

```text
completed materializations: 98
failed materializations: 0
sequence-length exclusions: 0
materialization errors: 0
training task ids: 11
```

No practice, selection-dev, heldout-private, or public-calibration task entered
either SFT treatment. Exact source records, embedded review decisions, and
training manifests own the authoritative accounting; this audit summarizes
that evidence rather than adding a duplicate filtering artifact.

## SFT Training And Serving Integrity

Both SFT runs used:

```text
base: Qwen/Qwen2.5-Coder-3B-Instruct
revision: 89fe5444e8baf5736e70f528f1edcc79e6616ef6
model-input protocol: qwen2_5_coder_3b_agentenv_json
protocol hash: xxh64:9b9eba719de618f1
optimizer steps per arm: 98
```

Raw treatment:

```text
artifact: experiments/models/week_10_positive_sft_raw_lora
run id: positive_sft_lora_run_75026bd7b64e4b229450ced024f23221
config hash: xxh64:112f566a2d9d56e8
manifest hash: xxh64:3828900162386f5c
adapter hash: xxh64:628c8c9a46b0bd1e
selected examples: 98
completed steps: 98/98
```

Efficiency-filtered treatment:

```text
artifact: experiments/models/week_10_positive_sft_efficiency_filtered_lora
run id: positive_sft_lora_run_ba8374dd03734bbc8de84a678f41c234
config hash: xxh64:4fe146e3e33500c7
manifest hash: xxh64:024cb3a3d8a4facb
adapter hash: xxh64:4b88697558dcbdd3
unique selected examples: 94
completed steps: 98/98
```

Both runs recorded exact adapter-only optimizer ownership, changed adapter
state, bitwise-unchanged frozen base state, and exact save/reload probe logits.

Serving kept the base and each adapter separate rather than merging weights:

```text
shared F16 base GGUF blob:
  e38087533702eddfb4025e230c08e5b5a37912c6d1341200dc5e6a5a085b53c1

raw adapter GGUF:
  6ce692b6bb6947a907f7d4ae63409eabc5793db2a5ba28a924ac6eae79dea968
raw Ollama composition manifest:
  sha256:0d205a44cee00b3d9abb610d2c6414c83d6a69a572ad085b4b3c110d71d68234

filtered adapter GGUF:
  93bdd3d12ccda20f075dd8ffcf4c492e8091260b5bc64de243d070af6cce6311
filtered Ollama composition manifest:
  sha256:038a771b66ecea02b765e0f677e98d492a2116cea1039b23f98030c70893550f
```

Model configs pin the deployed composition digest and source training
manifest. Base and adapters used the same Ollama generation and constrained
tool-call decoding path.

## Frozen SFT Policy Selection

Canonical evidence:

```text
config: configs/eval/positive_sft_policy_selection.yaml
config hash: xxh64:f3861aef6336bbe2
suite: experiments/runs/week_10_positive_sft_policy_selection
suite id: eval_suite_c53b4f76646b45269032e9b69878ef0b
suite manifest hash: xxh64:6a46d6e79373889c
report: experiments/reports/week_10_policy_selection.md
report hash: xxh64:51fca6823174a8f4
selected task-set hash: xxh64:cb95e4422a6ee152
attempts: 3 policies x 8 tasks = 24
invalid comparison cells: 0
```

All arms used deterministic greedy decoding. Final outcomes were:

| policy | task success | scored attempts | total tokens | actions |
| --- | ---: | ---: | ---: | ---: |
| base | 0/8 | 8/8 | 37,938 | 33 |
| raw SFT | 0/8 | 6/8 | 246,251 | 104 |
| efficiency-filtered SFT | 0/8 | 8/8 | 87,511 | 62 |

The two unscored raw-SFT attempts exhausted their turn budgets. The comparison
branch was `complete_tie`, and the mechanical decision was `abstain`. Because
there were no successful cells, neither total tokens nor action counts could
select a capability winner.

A separate one-task practice diagnostic produced a base PASS while both SFT
adapters repeated the same inspection/test loop without writing a patch. That
is useful failure analysis, not selection evidence, and did not change the
frozen abstention.

## Exploratory DPO

No SFT arm won selection. The filtered-SFT checkpoint was therefore designated
explicitly as an exploratory parent because it implements the planned data
treatment; this designation must not be read as a retroactive selection result.

Canonical training evidence:

```text
config: configs/train/dpo_lora_exploratory_full_pass.yaml
config hash: xxh64:2938bcf1227fddd8
artifact: experiments/models/week_10_dpo_lora_exploratory_full_pass
run id: dpo_lora_run_b8a3752e281f4ca8af9d65bd97a1ef1b
manifest hash: xxh64:a7b4da47350bdb08
adapter hash: xxh64:ea8dadb299dfed48
parent SFT manifest hash: xxh64:024cb3a3d8a4facb
parent SFT adapter hash: xxh64:4b88697558dcbdd3
preference pairs: 29
completed steps: 29/29
logical input tokens: 64,863
loss-bearing response tokens: 12,587
```

Policy and reference were exactly equal before optimization. Only the policy
adapter was optimized; the shared base remained frozen; and the saved adapter
reloaded exactly. The separately served DPO adapter pins:

```text
adapter GGUF:
  236dab3552975903d43a396c13ea78dc2be620add67bdf0cc7ae2578cc2a63e0
Ollama composition manifest:
  sha256:e56bd7cf4582ec1b33b6d9a5e2759e732ac59720cd9462a9645ac7f2ac45d057
```

Six of the 29 preference pairs came from two tasks in the original eight-task
SFT selection set: four from `repair_retry_schedule` and two from
`repair_interval_coalescing`. The initial 24-cell DPO evaluation is therefore
retained only as a contaminated behavioral diagnostic:

```text
suite: experiments/runs/week_10_dpo_exploratory_policy_evaluation_v0
suite manifest hash: xxh64:9af876a601b8cb71
report hash: xxh64:50eeffd1876c39ff
```

The corrected evaluation derives the full 13-task DPO lineage: eleven inherited
SFT tasks plus the tasks represented by preference pairs. It excludes that
lineage and runs on the six remaining development tasks:

```text
config: configs/eval/dpo_exploratory_policy_evaluation.yaml
config hash: xxh64:3f424ac17b2f6dd6
suite: experiments/runs/week_10_dpo_exploratory_policy_evaluation_disjoint_v0
suite id: eval_suite_f53256f26a5d47a49a7214253722f447
suite manifest hash: xxh64:de5a948521bf8316
report: experiments/reports/week_10_dpo_exploratory_policy_evaluation_disjoint.md
report hash: xxh64:dc796e3f37e64f08
selected task-set hash: xxh64:f620bafa6b168d4c
attempts: 3 policies x 6 tasks = 18
invalid comparison cells: 0
```

| policy | task success | scored attempts | total tokens | actions |
| --- | ---: | ---: | ---: | ---: |
| base | 0/6 | 6/6 | 35,464 | 29 |
| efficiency-filtered SFT | 0/6 | 6/6 | 70,640 | 47 |
| DPO | 0/6 | 0/6 | 303,394 | 156 |

The rule again abstained on a `complete_tie`. Every DPO attempt exhausted its
turn budget. Across 156 actions, the policy emitted only the four illustrative
tool calls from the system prompt: 52 `list_files`, 35 `read_file`, 21
`write_file`, and 48 `run_tests` calls, with no `final_answer`. Every write used
the illustrative `src/file.py` path and placeholder contents, producing six
missing-file errors. This is evidence of prompt-example copying and completion
collapse, not partial task success.

The clean DPO suite has a different harness-runtime hash from the earlier SFT
suite because repository code changed between runs. Base, filtered SFT, and DPO
within the clean suite share one runtime, so the incremental DPO comparison is
internally controlled. Absolute numbers across the two suites are descriptive,
not a causal cross-run comparison.

## Manual Criteria And Adaptations

The manual called for reproducible filtering, LoRA training, base-controlled
evaluation, and a comparison report. Those criteria are met through repo-native
typed records, training manifests, model configs, eval-suite manifests, and
reports rather than the manual's illustrative standalone scripts and flat
artifact names.

The implementation intentionally did not create a task-partition artifact,
standalone efficiency-review artifact, copied filtered dataset, or standalone
training-schedule artifact. Each would have duplicated authority already owned
by source records, combined reviews, eval configs, or training manifests.

The manual's normal DPO path assumes a selected SFT parent. Since SFT selection
abstained, Week 10 preserved that negative result and labeled the DPO run
exploratory. Discovering task contamination in the first DPO matrix did not
trigger post-hoc deletion or reinterpretation; the original was demoted and a
strictly disjoint replacement was run.

Heldout-private outcomes remained unopened. Development evidence was sufficient
to establish that none of the trained policies warranted advancement.

## Final Verification

```text
uv run pytest -n auto
  1250 passed in 302.51 seconds

uv run ruff check .
  passed

uv run pyright
  0 errors, 0 warnings

git diff --check
  passed
```

## Remaining Limitations

These are explicit non-claims, not Week 10 blockers:

- Every primary and exploratory policy achieved zero nested task successes, so
  Week 10 estimates neither a positive SFT effect nor a filtering effect.
- Greedy decoding contributed one rollout per policy-task cell; stochastic
  variance and training-seed variance were not measured.
- The development tasks may be too difficult for the 3B model and current
  harness interaction protocol, but that possibility does not convert
  unsuccessful trajectories into task successes.
- Token and action counts describe operational behavior. They are not measures
  of capability when the successful-task set is empty.
- The DPO run used one pass over 29 pairs and showed a severe behavioral
  regression. No hyperparameter search or repair was attempted.
- Both SFT arms inherit the Week 9 explicit learning-lab authorization for a
  known source-runtime mismatch.
- Historical acquisition graphs retain some absolute references to the earlier
  foundation worktree. Current consumers validate pinned records, but the full
  archive is not yet portable across arbitrary paths.
- Ollama model compositions and converted GGUF blobs are machine-local. Their
  identities are pinned, but rebuilding or serving them requires the local
  model assets and suitable compute.
- AI-proxy efficiency review is not independent expert human review.
- The local runner is not a production hostile-code sandbox.

## Week 11 Handoff

Week 11 should make the existing result reproducible and interruption-tolerant,
not tune around Week 10's negative outcome. The default reproduction path must
run without a GPU, paid API, or local Ollama model by validating archived
artifacts and regenerating deterministic reports. Model training and live
inference remain optional heavyweight checks.

The first Week 11 design boundary is the meaning of resume: identify which
current attempt, suite, and report states can be trusted after interruption,
then add only the smallest typed state needed to distinguish reusable completed
work from missing, corrupt, duplicate, timed-out, or configuration-drifted
work.
