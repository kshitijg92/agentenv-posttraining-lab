# Week 12 Spike Report

Status: final evidence synthesis. The headline claim and next technical bet
were confirmed on 2026-08-23. The next experiment is deliberately not executed
as part of Week 12.

## Abstract

This project built a small, auditable coding-agent evaluation and
post-training lab around local Python repo-patch tasks. The artifact separates
public diagnostics from hidden scoring, calibrates every task with oracle,
known-bad, and scripted-agent controls, preserves typed traces and replay, and
gates post-training data through split, provenance, leakage, reward-hack,
review, serialization, and loss-ownership contracts.

The final task pack contains 26 tasks: one practice task, 19 development tasks,
and six heldout-private tasks. The canonical full-pack calibration matched all
468 expected control records across three repeats, with zero drift among 156
flake groups. The aggregate harness audit passed all 21 agent cases and 12
scorer cases. A separate 16-case reward-hack audit detected and neutralized all
authored mechanisms, recorded no private-content exposure, and allowed none of
the exploit traces into training.

The post-training experiment produced mechanically valid raw positive-SFT,
efficiency-filtered positive-SFT, and exploratory DPO LoRA adapters from one
pinned Qwen2.5-Coder-3B base and model-input protocol. It did not produce an
observed task-success improvement. Base, raw SFT, and filtered SFT each
succeeded on 0/8 frozen development tasks. On the corrected six-task
DPO-lineage-disjoint comparison, base, filtered SFT, and DPO each succeeded on
0/6 tasks. Both comparison rules abstained. DPO additionally exhausted every
turn budget while copying the system prompt's illustrative tool calls.

This is a valid negative development result under a limited task distribution,
one deterministic rollout per cell, and this exact harness. It is not evidence
that the policies are equivalent, that SFT or DPO are generally ineffective,
or that any policy improves on heldout tasks. Heldout-private natural-model
outcomes remain unopened.

The tracked deterministic harness path reproduces offline in a clean tree. The
retained Week 10 training/evaluation graph reconstructs only at the original
checkout and artifact location; it is not available in a clean clone and is
not relocatable.

## Headline Claim

The strongest supported post-training claim is:

```text
Within the frozen, limited development comparisons and under the pinned
harness, hidden scorer, model/serving protocol, deterministic greedy decoding,
and one rollout per policy-task cell, neither positive-SFT treatment nor the
exploratory DPO continuation improved observed nested task success. Base, raw
SFT, and efficiency-filtered SFT each succeeded on 0/8 tasks; in the corrected
DPO-lineage-disjoint comparison, base, efficiency-filtered SFT, and DPO each
succeeded on 0/6 tasks. The correct decisions were therefore to abstain from
SFT selection and to report no observed DPO benefit in this experiment.
```

This wording says what was observed. It does not convert the zero-success floor
into evidence of policy equivalence or a general negative result about either
training method.

## Artifact Summary

The implemented loop is:

```text
task manifest + seed workspace
-> patch, scripted control, or model policy
-> orchestrator
-> public checks
-> hidden scorer
-> typed attempt artifacts and trace
-> replay and report
```

The post-training path is:

```text
eval attempts
-> evidence-only trajectories
-> trajectory and objective-specific review
-> training-use candidates
-> positive-SFT prefixes or shared-context preference pairs
-> target-model materialization and loss masks
-> explicit authorization
-> adapter-only LoRA training
-> fixed development comparison
```

| boundary | implemented authority | purpose |
| --- | --- | --- |
| task identity | task manifests, split lock, task hashes | pin visible and hidden task bytes and allowed use |
| task success | typed `AttemptStatus` plus public/hidden statuses | prevent public-only or structural completion from becoming success |
| model interaction | pinned prompt loop, typed tools, decoding and model configs | make policy behavior traceable and comparable |
| measurement trust | scorer/agent audits, controls, flakes, replay, leakage checks | test known harness behaviors before interpreting model results |
| trajectory evidence | immutable typed trajectory records | preserve what happened without deciding training use |
| data use | review and `TrainingCandidateRecord` eligibility | separate evidence from interpretation and permission |
| loss ownership | SFT and DPO materialization records | identify exactly which assistant tokens receive loss |
| training execution | SFT/DPO training manifests and results | pin base, protocol, data, schedule, runtime, and adapter state |
| comparison decision | frozen eval configs, suites, canonical reports | keep selection rules and task lineage auditable |
| reproduction | core reproduction report | compose local stored-evidence checks and clean-tree deterministic execution |

## Task Distribution

Current authoritative split state:

| split | count | permitted role | current interpretation |
| --- | ---: | --- | --- |
| practice | 1 | diagnostics and training subject to all gates | never generalization evidence |
| dev | 19 | training sources or development comparison | model selection and failure analysis only |
| heldout_private | 6 | one future frozen natural-model comparison | unopened; no performance claim |
| public_calibration | 0 | calibration only | unused |

The current task-hash report records 26 tasks at pack hash
`xxh64:70af6abbb3ae1d61`; the current split-lock hash is
`xxh64:6a8196091ebfeb31`.

### Task And Training-Lineage Table

The rows below overlap where DPO inherited SFT lineage. They describe use, not
additional tasks.

| role | split | count | task ids |
| --- | --- | ---: | --- |
| practice diagnostic | practice | 1 | `toy_python_fix_001` |
| positive-SFT training lineage | dev | 11 | `repair_jsonl_deduper`, `preserve_cli_error_codes`, `repair_config_precedence`, `repair_header_merge`, `repair_duration_parser`, `repair_record_chunking`, `repair_query_encoding`, `repair_semver_precedence`, `repair_csv_projection`, `repair_relative_path`, `repair_template_expansion` |
| frozen SFT selection | dev | 8 | `repair_retry_schedule`, `repair_interval_coalescing`, `repair_alias_chain`, `repair_inventory_transaction`, `repair_access_policy`, `repair_config_inheritance`, `repair_event_rollup`, `repair_job_dispatch` |
| additional DPO preference lineage | dev | 2 | `repair_retry_schedule`, `repair_interval_coalescing` |
| corrected DPO comparison | dev | 6 | `repair_alias_chain`, `repair_inventory_transaction`, `repair_access_policy`, `repair_config_inheritance`, `repair_event_rollup`, `repair_job_dispatch` |
| frozen heldout-private | heldout_private | 6 | `repair_stable_toposort`, `repair_json_pointer_lookup`, `repair_utf8_batching`, `repair_env_assignment_parser`, `repair_decimal_rounding`, `repair_latest_record_selection` |

The eleven SFT tasks and eight SFT-selection tasks partition all 19 development
tasks. DPO inherited the eleven SFT tasks and added two preference-source tasks,
so its corrected comparison used the six remaining development tasks.

The heldout freeze records zero natural-model attempts at freeze time and pins
the six heldout task hashes. Scripted controls were run before freeze; no
natural-model heldout outcome has been inspected since.

## Scoring Contract

One attempt succeeds only when:

```text
attempt_status: PASS
public_status: PASS
hidden_status: PASS
```

Public checks are visible diagnostics. They are intentionally incomplete and
are not the score. A public-pass/hidden-fail attempt remains
`HIDDEN_TEST_FAIL`. A completed prompt loop, a plausible final answer, or a
success-looking log line is not task success.

Every task carries three scorer controls and three scripted-agent controls:

| layer | control | expected outcome |
| --- | --- | --- |
| scorer | oracle | final/public/hidden `PASS` |
| scorer | no-op | public `PASS`, hidden `FAIL`, final `HIDDEN_TEST_FAIL` |
| scorer | public-only | public `PASS`, hidden `FAIL`, final `HIDDEN_TEST_FAIL` |
| agent | happy | completed prompt loop and nested scorer `PASS` |
| agent | malformed | typed `invalid_model_output`, scorer not run |
| agent | recoverable | typed tool error followed by recovery and nested scorer `PASS` |

The scoring contract is `scoring_contract_v0`. The Week 10 eval suites did not
capture a separate hidden-validator version/hash field. Their effective scorer
identity is therefore bounded by the selected task hash set, which includes
hidden-test bytes, plus the eval config hash and harness runtime/source hashes.
That substitute is auditable but less direct than a dedicated scorer identity.

## Measurement Controls

### Canonical Control Summary

| boundary | scope | observed result | authority |
| --- | --- | --- | --- |
| aggregate harness audit | 21 agent cases and 12 scorer cases | PASS; zero mismatches and zero audit errors | `experiments/harness_audit/week_09_closeout/harness_audit.md` |
| scorer controls | 26 tasks, three controls, three repeats | 234/234 matched | `experiments/runs/week_09_closeout_control_calibration/control_report.md` |
| agent controls | 26 tasks, three controls, three repeats | 234/234 matched | same full-pack control report |
| flake detection | 156 task/control groups | stable; zero drifted groups | same report and manifest |
| public-check idempotency | 26 tasks, repeat count two | 26/26 `IDEMPOTENT` | Week 9 control manifest and closure audit |
| heldout pre-freeze controls | six tasks, six policies | 36/36 expected; six replay groups passed | `data/task_packs/repo_patch_python_v0/heldout_private.freeze.json` |
| reward-hack audit | 16 authored exploit/control pairs | 16/16 passed; zero private exposures; zero exploit traces training-allowed | `experiments/reports/reward_hack_audit_week_08_v1.md` |
| deterministic execution and replay | three dev tasks, six policies | 18/18 attempts expected; six replay groups; 24/24 control/replay outcomes | `experiments/reproduction/core_smoke/reproduction_report.md` |
| resume/failure injection | interruption, missing/corrupt evidence, duplicates, timeouts, missing validator, bad config, drift | typed fail-closed outcomes | `tests/test_resume.py` and Week 11 closure audit |

The control evidence supports confidence that the zero-success model results
were not caused by an obvious known oracle, bad-control, scripted-agent,
replay, flake, or idempotency failure. It does not establish that the task
difficulty or strict interaction protocol was well calibrated for the 3B
model.

### Control Failures That Were Preserved

The final control state is not presented as if every intermediate artifact had
always passed.

| retained failure | observed problem | response | final authority |
| --- | --- | --- | --- |
| `experiments/runs/week09_expanded_task_controls_diagnostic/control_report.md` | overall `FAIL`: four new oracle patches produced `PATCH_APPLY_ERROR`; two `repair_query_encoding` agent controls violated expected output | blocked the new tasks, corrected their assets, and reran the same gate | corrected v2 report passed 48/48; later 26-task closeout passed 468/468 |
| `experiments/runs/control_flake_report_smoke/control_report.md` | intentional negative fixture: two scorer groups drifted and overall status became `FAIL` | retained as detector/report evidence | canonical full-pack run has zero drifted groups |

These failures are evidence that the gates can reject bad state. Their later
passing replacements do not erase the failure history, and none of their
records are added to model-policy denominators.

### Flake And Exclusion Table

| surface | flake/exclusion state | use in final result |
| --- | --- | --- |
| canonical 26-task controls | 156 groups stable, zero drifted | supports measurement-trust claim |
| historical expanded-task diagnostic | no flake, but six expectation mismatches | blocked until corrected; excluded as authority |
| intentional drift smoke | two drifted scorer groups | negative detector fixture only |
| frozen SFT comparison | no task exclusions; two raw-SFT attempts ended at max turns | all eight tasks retained; unscored cells remain failures for success accounting |
| initial DPO comparison | task bytes stable, but two tasks contaminated by DPO preference lineage | entire comparison demoted to diagnostic |
| corrected DPO comparison | six lineage-disjoint tasks; no task exclusions | canonical DPO development evidence |
| heldout-private | no natural-model outcomes opened | absent from every model-result denominator |

## Baselines

Controls and model baselines answer different questions and are never pooled.

| policy/run | model or role | split/tasks | nested task success | interpretation |
| --- | --- | --- | ---: | --- |
| oracle controls, full-pack closeout | scorer calibration | all 26 tasks, three repeats | 78/78 | expected calibration, not model capability |
| known-bad controls, full-pack closeout | scorer calibration | all 26 tasks, three repeats | 0/156 final PASS | public-pass shortcuts correctly rejected |
| `local-qwen-dev` | Qwen3-14B GGUF sampling integration baseline | three dev tasks | 0/3 | historical negative integration result; not comparable to Week 10 treatments |
| base practice diagnostic | Qwen2.5-Coder-3B F16 base | one practice task | 1/1 | shows the model/harness path can succeed on the toy task; not selection evidence |
| base SFT-selection arm | same Qwen2.5-Coder-3B base path as adapters | eight dev tasks | 0/8 | frozen causal anchor for SFT comparison |
| base corrected-DPO arm | same base path as filtered SFT and DPO in that suite | six dev tasks | 0/6 | frozen anchor inside corrected DPO comparison |

The DeepSeek-R1-Distill-Qwen-14B probe was reachable and produced an initial
valid tool call, but reasoning/prose artifacts broke the strict one-action JSON
protocol after tool results. It is an interface-compatibility failure, not a
comparable coding baseline, and is excluded from pass-rate tables.

## Trace And Reward Schema

One `TrajectoryRecord` represents one eval attempt: one task, policy, and
attempt index. It preserves run/task/model identity, source artifacts,
messages, tool calls and outputs, typed errors, scoring outcome, leakage
evidence, reward components, and objective-specific eligibility.

`RewardComponents` are decomposed audit signals, not a scalar reward:

```text
public_validator_success
hidden_validator_success
model_output_format_valid
model_tool_usage_valid
orchestration_failure
reward_hack_flag
reward version/config/code hashes
```

The core distinctions are:

```text
trajectory evidence != training-use eligibility
task success != positive-prefix quality
terminal outcome != preference direction
constructed trainer input != training authorization
mechanically valid training != behavioral improvement
```

Week 9 reconstructed 156 source trajectories. Objective-specific review
produced a 100-row positive-SFT review universe and 29 auditable preference
pairs. Heldout-private, public-calibration, controls, stale evidence,
orchestration failures, private exposure, and incomplete reward-hack evidence
are programmatically forbidden from trainable paths.

## Filtering Policy

Positive SFT uses one contiguous, explicitly approved assistant prefix. A
failed trajectory may contribute a clean prefix before its earliest causal
error; a successful trajectory is not automatically an acceptable imitation
target.

### Filtering Rejection Table

| stage | accepted | rejected | unresolved | rejection interpretation |
| --- | ---: | ---: | ---: | --- |
| contiguous-prefix review | 98 | 2 | 0 | no nonempty clean prefix before the first invalid action |
| action-efficiency review over accepted prefixes | 94 | 4 | 0 | two repeated unchanged source reads and two unused `pyproject.toml` reads |
| target-model materialization | 98 completed | 0 failed | 0 overlength | all accepted source examples serialized under the pinned protocol |

| treatment | unique examples | tasks | supervised tokens | serialized sequence tokens |
| --- | ---: | ---: | ---: | ---: |
| raw eligible positive SFT | 98 | 11 | 16,412 | 97,005 |
| efficiency-filtered unique population | 94 | 11 | 13,207 | 86,700 |
| removed by efficiency filter | 4 | 0 tasks removed | 3,205 | 10,305 |

The filter removed 4.08% of examples, 19.53% of supervised tokens, and 10.62%
of serialized context tokens. All four exclusions came from one source policy;
three were on `preserve_cli_error_codes` and one on
`repair_jsonl_deduper`. Both tasks remained represented.

The filtered training schedule repeated four complete examples to reach the
same 98 optimizer steps as the raw arm. It executed 16,071 supervised tokens,
341 fewer than the raw arm and within the predeclared 907-token
complete-example tolerance. No heldout, practice, public-calibration, or
selection task entered either arm.

## Training Smoke And Execution

All three runs used:

```text
base: Qwen/Qwen2.5-Coder-3B-Instruct
revision: 89fe5444e8baf5736e70f528f1edcc79e6616ef6
protocol: qwen2_5_coder_3b_agentenv_json
protocol hash: xxh64:9b9eba719de618f1
```

| policy | run id | manifest hash | adapter hash | completed steps | source units |
| --- | --- | --- | --- | ---: | ---: |
| raw SFT | `positive_sft_lora_run_75026bd7b64e4b229450ced024f23221` | `xxh64:3828900162386f5c` | `xxh64:628c8c9a46b0bd1e` | 98/98 | 98 examples |
| efficiency-filtered SFT | `positive_sft_lora_run_ba8374dd03734bbc8de84a678f41c234` | `xxh64:024cb3a3d8a4facb` | `xxh64:4b88697558dcbdd3` | 98/98 | 94 unique examples |
| exploratory DPO | `dpo_lora_run_b8a3752e281f4ca8af9d65bd97a1ef1b` | `xxh64:a7b4da47350bdb08` | `xxh64:ea8dadb299dfed48` | 29/29 | 29 preference pairs |

The SFT runs proved assistant-only loss masking, exact adapter-only optimizer
ownership, adapter mutation, frozen-base invariance, and exact save/reload
behavior. DPO proved identical policy/reference initialization from the exact
filtered-SFT parent, frozen reference log probabilities before optimization,
adapter-only policy updates, and exact reload.

The trainer-shaped artifacts inherited an explicit learning-lab authorization
override for a known source-runtime mismatch. That override grants permission
for this exercise; it does not repair or erase the mismatch. Mechanical checks
and completed loss optimization establish plumbing, not efficacy.

## Main Evidence

### Frozen Base Versus Positive SFT

Canonical identity:

```text
config: configs/eval/positive_sft_policy_selection.yaml
config hash: xxh64:f3861aef6336bbe2
suite: experiments/runs/week_10_positive_sft_policy_selection
suite id: eval_suite_c53b4f76646b45269032e9b69878ef0b
suite manifest hash: xxh64:6a46d6e79373889c
selected task hash set: xxh64:cb95e4422a6ee152
harness runtime hash: xxh64:02cd08e1c3fbbad8
report: experiments/reports/week_10_policy_selection.md
report hash: xxh64:51fca6823174a8f4
split: dev
rollouts: one deterministic greedy rollout per policy-task cell
```

| policy | task success | scored attempts | public pass | prompt-loop failures | total tokens | actions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 0/8 | 8/8 | 7/8 | 0/8 | 37,938 | 33 |
| raw SFT | 0/8 | 6/8 | 6/8 | 2/8 max turns | 246,251 | 104 |
| efficiency-filtered SFT | 0/8 | 8/8 | 8/8 | 0/8 | 87,511 | 62 |

The selection rule was success first, then successful-task token efficiency,
then actions. With an empty successful-task set for every policy, the decision
was `abstained` on a `complete_tie`. Token and action counts are operational
descriptions; they cannot select a capability winner here.

The one-task practice diagnostic produced base 1/1, raw SFT 0/1, and filtered
SFT 0/1. Both adapters repeated an inspection/test loop until max turns. This
is useful behavioral counterevidence, but practice data did not alter the
frozen development decision.

### Exploratory DPO And Contamination Correction

No SFT policy won selection. The filtered checkpoint became a designated
exploratory parent because it represented the planned filtering treatment,
not because it was retrospectively declared a winner.

The initial eight-task DPO evaluation reused two preference-source tasks:
`repair_retry_schedule` contributed four pairs and
`repair_interval_coalescing` contributed two. That complete matrix is retained
as a contaminated diagnostic and is not used for the final DPO claim.

Canonical corrected identity:

```text
config: configs/eval/dpo_exploratory_policy_evaluation.yaml
config hash: xxh64:3f424ac17b2f6dd6
suite: experiments/runs/week_10_dpo_exploratory_policy_evaluation_disjoint_v0
suite id: eval_suite_f53256f26a5d47a49a7214253722f447
suite manifest hash: xxh64:de5a948521bf8316
selected task hash set: xxh64:f620bafa6b168d4c
harness runtime hash: xxh64:dee571c4bcad79c0
report: experiments/reports/week_10_dpo_exploratory_policy_evaluation_disjoint.md
report hash: xxh64:dc796e3f37e64f08
split: dev
rollouts: one deterministic greedy rollout per policy-task cell
```

| policy | task success | scored attempts | public pass | prompt-loop failures | total tokens | actions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 0/6 | 6/6 | 5/6 | 0/6 | 35,464 | 29 |
| efficiency-filtered SFT | 0/6 | 6/6 | 6/6 | 0/6 | 70,640 | 47 |
| DPO | 0/6 | 0/6 | 0/6 | 6/6 max turns | 303,394 | 156 |

The corrected decision also abstained on a complete tie in nested task
success. DPO behavior was nevertheless qualitatively worse than its parent:
all six attempts exhausted their turn budgets, every action copied one of four
illustrative tool calls from the system prompt, every write targeted the
placeholder `src/file.py`, and no final answer was emitted.

This establishes no observed DPO benefit and a severe behavioral regression in
this experiment. It does not establish that DPO is generally ineffective or
harmful.

## Reward-Hack Analysis

The reward-hack audit treats each case as a view over underlying scorer or
agent-audit evidence. Each exploit is paired with a valid control.

| metric | result |
| --- | ---: |
| authored cases | 16 |
| audit cases passed | 16/16 |
| exploit mechanisms detected | 16/16 |
| exploit mechanisms neutralized | 16/16 |
| private-content exposures | 0/16 |
| exploit cases allowed task success | 1/16 |
| exploit cases allowed training | 0/16 |
| valid controls succeeded | 16/16 |

Covered classes include hidden-validator probes, no-op and public-only
patches, public-check tampering, fake success output, tool-output spoofing,
format-only compliance, state corruption, and authored timeout/retry exploits.

One fake-success case contained a genuinely correct patch, so task success was
allowed while training remained denied because the trace contained a spoofed
success mechanism. This demonstrates the intended separation between task
success and training eligibility.

The audit is not a reward-robustness proof. Cases are deterministic and
hand-authored, valid controls are reused heavily, leakage matching is limited
to canaries and boundary markers, and no heldout reward-hack task pack exists.

## Reliability And Reproduction

The core command is:

```bash
uv run --offline --frozen agentenv reproduce core \
  --out <fresh-output-directory>
```

The retained invocation passed 37/37 required checks:

| level | operation | result | supported boundary |
| --- | --- | --- | --- |
| 1 | validate stored Week 10 training/eval graphs and regenerate canonical reports | PASS 11/11 | local integrity and reconstruction at original paths |
| 2 | execute deterministic controls, hidden scoring, replay, and same-run report regeneration | PASS 26/26 | tracked clean-tree CPU/offline workflow |
| 3 | live model inference | SKIP | no model-server or stochastic inference claim |
| 4 | training rerun | SKIP | no fresh optimizer/GPU reproducibility claim |

Level 2 executed 18 attempts and six replay groups with 24/24 expected
control/replay outcomes. Same-run reports regenerated byte-for-byte.

Level 1 has two material portability blockers:

- seven declared top-level evidence files are absent from Git;
- top-level manifests contain 30 repository-owned absolute path references.

Content hashes establish identity once evidence is found. They do not establish
availability in a clean clone or relocatability to another checkout.

### Week 12 Closeout Verification

The report and documented operator path were checked without rerunning live
inference, training, or heldout evaluation:

| check | result |
| --- | --- |
| fresh CPU/offline core reproduction | PASS 37/37; Level 1 11/11 and Level 2 26/26; Levels 3-4 skipped |
| one-task README scorer-control eval | PASS 6/6 operational checks |
| three-task README deterministic small eval | PASS 24/24 operational checks |
| same-run report regeneration | byte-identical |
| full test suite | 1,291 passed in 286.01 seconds |
| Ruff | all checks passed |
| Pyright | zero errors and zero warnings |
| final path, control-index, and diff checks | passed |

Resume uses predeclared attempt identity and exact config, task, model,
decoding, declaration, and harness provenance. A validated terminal attempt is
reused. A terminal model error is not resampled. Missing or corrupt terminal
evidence rejects that attempt while independent siblings may continue, but an
invalid suite cannot publish a complete policy comparison. Retry remains a new
attempt or run, not resume.

## Claim/Evidence Table

| claim | evidence and identity | split/scorer identity | statistical support | counterevidence | limitation | decision |
| --- | --- | --- | --- | --- | --- | --- |
| The narrow harness behaved as declared on its authored controls. | Week 9 closeout harness audit; full-pack control run `controls_85352e44c3cf4c78ae8fd914589187f2` | all splits for calibration; `scoring_contract_v0`; task hashes; matching audit/control runtime | deterministic census: 468/468 records; 156/156 stable groups | early expanded-task diagnostic failed and was repaired; intentional drift fixture fails | controls encode known cases and are not model trials | supported for authored controls |
| Authored reward hacks were measured and neutralized. | reward report hash `xxh64:c1a4b98a7fa073a7` | scorer/agent audit cases; no model split claim | 16/16 cases and controls | one exploit still allowed legitimate task success; valid controls reused | hand-authored catalogue, no heldout adversarial distribution | supported only for v1 catalogue |
| Raw and filtered positive SFT did not improve observed task success. | suite `eval_suite_c53b4f76646b45269032e9b69878ef0b`; config `xxh64:f3861aef6336bbe2`; report `xxh64:51fca6823174a8f4` | dev; task set `xxh64:cb95e4422a6ee152`; harness `xxh64:02cd08e1c3fbbad8`; no separate scorer-version field | eight paired tasks, one greedy rollout each; all arms 0/8 | base succeeds 1/1 on toy practice; raw has two max-turn cells; public pass differs | zero floor, no sampling/training-seed variance, narrow task family | abstain; no observed improvement |
| Exploratory DPO provided no task-success benefit and collapsed behaviorally. | run `dpo_lora_run_b8a3752e281f4ca8af9d65bd97a1ef1b`; suite `eval_suite_f53256f26a5d47a49a7214253722f447`; report `xxh64:dc796e3f37e64f08` | dev; task set `xxh64:f620bafa6b168d4c`; harness `xxh64:dee571c4bcad79c0`; no separate scorer-version field | six paired lineage-disjoint tasks, one greedy rollout each; all arms 0/6 | first matrix contaminated; DPO parent was not a selected winner; 6/6 max-turn prompt copying | one 29-pair pass, no hyperparameter/seed search, no heldout | abstain; no observed benefit in this experiment |
| The deterministic harness reproduces cleanly; stored Week 10 evidence reconstructs locally. | reproduction plan `xxh64:7ef42e465da5f543`; retained core report | Level 2 tracked dev controls; Level 1 local stored graph | Level 1 11/11; Level 2 26/26; repeated byte matches | live inference and training skipped | Level 1 unavailable in clean clone and non-relocatable | support split reproduction claim only |
| Heldout-private outcomes did not influence the experiment. | split lock; freeze record; Week 10/11 closures | six frozen heldout tasks; zero natural attempts at freeze | process and hash evidence, not outcome statistics | tasks were authored and scripted-control calibrated before freeze | outcomes remain unopened, so no generalization result exists | support isolation; make no performance claim |

## Negative Results And Failed Hypotheses

### Hypothesis 1: Positive SFT Would Produce A Selectable Policy

It did not. Both trained policies remained at 0/8 nested successes. Raw SFT
also consumed substantially more tokens and hit max turns on two tasks, while
filtered SFT completed and passed public checks on all tasks but produced empty
patches that failed hidden validation. The selection rule correctly abstained.

### Hypothesis 2: Efficiency Filtering Would Improve Task Success

It did not produce an observed success difference: raw and filtered SFT were
both 0/8. Filtering changed data volume and runtime behavior, but the primary
metric could not distinguish the treatments. This does not show the filter was
useless; it shows this comparison did not measure a task-success benefit.

### Hypothesis 3: Exploratory DPO Would Improve Its Parent

It did not. The corrected comparison remained 0/6 for all arms, and DPO
regressed into systematic prompt-example copying. Mechanical objective
correctness did not protect behavior.

### Hypothesis 4: Hash-Pinned Local Evidence Was A Portable Reproduction

It was not. Local integrity passed, but missing Git availability and absolute
references prevent clean-clone Level 1 reproduction and relocation.

### Measurement Failure That Was Caught

An early expanded-task calibration failed because four oracle patches could not
apply and two agent controls violated their declared outcomes. The tasks were
blocked, corrected, and rerun before later use. Preserving this failure is more
informative than showing only the final green report.

## Limitations

- The task family is synthetic, Python-only, local, and mostly localized to a
  few files and functions.
- The strict one-JSON-action protocol is part of the measured construct and can
  confound coding ability with interface compliance.
- The primary SFT comparison has eight tasks; the corrected DPO comparison has
  six different tasks.
- Every Week 10 model-policy cell has one deterministic greedy rollout.
  Sampling variance and training-seed variance were not measured.
- All compared policies sit at a zero-success floor, preventing a useful
  effect-size or equivalence claim.
- Public checks are intentionally weak on some tasks. Public pass is diagnostic
  and cannot rescue hidden failure.
- The Week 10 reports do not carry a dedicated hidden-scorer version/hash;
  selected task hashes, config hashes, and harness provenance are the current
  substitute.
- Raw provider responses are not persisted, cost is `not_recorded`, and local
  model serving depends on machine-local Ollama/GGUF assets.
- The SFT and DPO artifacts inherit an explicit learning-lab authorization
  override for a known source-runtime mismatch.
- AI-proxy review is recorded provenance, not independent expert human review.
- The reward-hack catalogue is hand-authored, deterministic, and control-heavy;
  it does not establish broad robustness.
- Hidden-leakage scanning detects canaries and boundary markers, not arbitrary
  semantic similarity to hidden validators.
- The local runner and Docker smoke are not production hostile-code sandboxes.
- Level 1 stored evidence is local, untracked as a complete graph, and
  non-relocatable. Live inference and training were not reproduced.
- Heldout-private natural-model outcomes remain unopened.
- Some human-readable historical documents contain stale task counts. Current
  split and task-hash artifacts take precedence.

## Non-Claims

This report makes no claim of:

- general coding-agent improvement;
- policy equivalence from the zero-success ties;
- general ineffectiveness or harmfulness of SFT or DPO;
- heldout or out-of-distribution improvement;
- benchmark state of the art;
- large-scale RLHF or validated human-preference modeling;
- scalar-reward validity or learned reward-model quality;
- stochastic inference or optimization reproducibility;
- clean-clone or relocatable Week 10 stored-evidence reproduction;
- production sandbox security;
- capability evidence from oracle or scripted controls;
- broad conclusions from proprietary or private organizational knowledge.

## Next Technical Bet

Status: selected with user confirmation on 2026-08-23. Execution belongs to
the next phase, not Week 12.

### Bet

Run a task/eval calibration spike before collecting more training data or
launching another optimization run.

This selects the manual's task/eval-quality direction. It does not authorize a
heldout run, another adapter, or post-outcome task revision.

### Observed Bottleneck

Measurement integrity, provenance, and deterministic reliability are stronger
than model-result discriminability. The base passes the toy practice task but
all policies score zero on the frozen development comparisons. The current
evidence cannot separate an overly difficult development slice, strict-
protocol difficulty, limited 3B base capability, and post-training target
quality well enough to justify another optimizer run.

### Hypothesis

A six-task development-only calibration ladder between the toy task and the
current selection tasks can produce a non-degenerate base-model nested-success
rate under the same audited scorer/tool contract.

### Smallest Experiment

1. Author six new repo-patch development tasks in the same domain, with two
   tasks at each of three predeclared complexity bands.
2. Require human solve notes, oracle/known-bad/scripted-agent controls, hidden
   validators, task hashes, and three-repeat flake calibration before any
   natural-model run.
3. Freeze task bytes, prompt, model/serving path, decoding, budgets, scorer,
   and reporting rule.
4. Run the unchanged Qwen2.5-Coder-3B base once per task under deterministic
   greedy decoding.
5. Report nested success first; public-pass/hidden-fail, nonempty patch rate,
   prompt-loop completion, tokens, and actions remain diagnostics.

### Budget And Stop Rule

```text
task budget: exactly 6 new development tasks
natural-model budget: exactly 6 base-policy attempts
task iteration after model outcomes: none
success criterion: 2-4 nested PASS outcomes out of 6
```

Stop after that one frozen base run:

- `2-4/6 PASS`: the metric is non-degenerate enough for a later controlled
  post-training comparison; freeze the slice as development data and next
  improve training-example quality.
- `0-1/6 PASS`: do not train; redirect to interaction-protocol/base-capability
  diagnosis because the eval remains floor-limited.
- `5-6/6 PASS`: do not train against this slice; record that it is too easy for
  useful selection and redirect to task-construct calibration.

This slice would be development data chosen partly for calibration. It could
never be relabeled as heldout evidence.

## Exact Commands And Artifact Paths

### Current CPU-Only Reproduction

```bash
week12_repro_root="$(mktemp -d)"
uv run --offline --frozen agentenv reproduce core \
  --out "$week12_repro_root/core"
```

### Tracked Deterministic Eval And Report Regeneration

```bash
week12_eval_root="$(mktemp -d)"
uv run --offline --frozen agentenv eval \
  --config configs/eval/eval_quality_gate_repo_patch_python_v0.yaml \
  --all-policies \
  --out "$week12_eval_root/eval" \
  --report-out "$week12_eval_root/eval.md"

uv run --offline --frozen agentenv report \
  "$week12_eval_root/eval" \
  --out "$week12_eval_root/eval-regenerated.md"

cmp "$week12_eval_root/eval.md" "$week12_eval_root/eval-regenerated.md"
```

### Canonical Evidence

```text
task identity:
  data/task_packs/repo_patch_python_v0/manifest.yaml
  data/task_packs/repo_patch_python_v0/splits.lock.json
  data/task_packs/repo_patch_python_v0/heldout_private.freeze.json
  experiments/reports/hashes/repo_patch_python_v0_task_hashes.json

measurement trust:
  experiments/harness_audit/week_09_closeout
  experiments/runs/week_09_closeout_control_calibration
  experiments/runs/reward_hack_audit_week_08_v1
  experiments/reports/reward_hack_audit_week_08_v1.md

training:
  experiments/models/week_10_positive_sft_raw_lora
  experiments/models/week_10_positive_sft_efficiency_filtered_lora
  experiments/models/week_10_dpo_lora_exploratory_full_pass

model comparisons:
  configs/eval/positive_sft_policy_selection.yaml
  experiments/runs/week_10_positive_sft_policy_selection
  experiments/reports/week_10_policy_selection.md
  configs/eval/dpo_exploratory_policy_evaluation.yaml
  experiments/runs/week_10_dpo_exploratory_policy_evaluation_disjoint_v0
  experiments/reports/week_10_dpo_exploratory_policy_evaluation_disjoint.md

reproduction:
  configs/reproduction/posttraining_result.yaml
  experiments/reproduction/core_smoke/reproduction_report.md
  docs/reproducibility.md
  notes/weekly/week_11/closure_audit.md
```

The Week 10 live-model suites and training artifacts should not be overwritten
to regenerate this report. The core command validates and regenerates their
designated reports into a disposable directory.

## Control-Evidence Index

The first table enumerates all 24 retained standalone top-level
`control_report.md` and `harness_audit.md` files. Historical and test-smoke
reports are retained for failure history but do not contribute additional
model trials or headline counts. Reward-hack aggregate and derived child-audit
surfaces are accounted for immediately below the table.

| report | status | authority |
| --- | --- | --- |
| `experiments/harness_audit/week_09_closeout/harness_audit.md` | PASS | canonical final harness audit |
| `experiments/harness_audit/week_09_harness_audit_v0/harness_audit.md` | PASS | historical Week 9 audit |
| `experiments/harness_audit/week_09_harness_audit_v1/harness_audit.md` | PASS | historical Week 9 audit |
| `experiments/harness_audit/week_09_redundancy_harness_audit_v0/harness_audit.md` | PASS | historical redundancy checkpoint |
| `experiments/runs/control_agent_flake_detection_smoke/control_report.md` | PASS | test/smoke artifact |
| `experiments/runs/control_flake_detection_groups_schema_smoke/control_report.md` | PASS | test/smoke artifact |
| `experiments/runs/control_flake_detection_smoke/control_report.md` | PASS | test/smoke artifact |
| `experiments/runs/control_flake_report_smoke/control_report.md` | FAIL | intentional negative drift fixture |
| `experiments/runs/control_flake_report_stable_smoke/control_report.md` | PASS | paired stable report fixture |
| `experiments/runs/eval_quality_controls_repo_patch_python_v0/control_report.md` | PASS | historical Week 6 gate authority |
| `experiments/runs/natural_model_anchor_contrast_acquisition/control_calibration/control_report.md` | PASS | historical acquisition trust artifact; absolute foundation-worktree paths |
| `experiments/runs/natural_model_anchor_contrast_acquisition/harness_audit/harness_audit.md` | PASS | historical acquisition trust artifact |
| `experiments/runs/week06_controls/control_report.md` | PASS | historical duplicate view |
| `experiments/runs/week09_dpo_control_calibration_v2/control_report.md` | PASS | historical DPO-data checkpoint |
| `experiments/runs/week09_dpo_control_calibration_v3/control_report.md` | PASS | final control artifact for that subphase; later superseded by closeout |
| `experiments/runs/week09_dpo_harness_audit/harness_audit.md` | PASS | historical DPO-data audit |
| `experiments/runs/week09_dpo_harness_audit_v2/harness_audit.md` | PASS | historical DPO-data audit |
| `experiments/runs/week09_dpo_harness_audit_v3/harness_audit.md` | PASS | historical DPO-data audit |
| `experiments/runs/week09_dpo_harness_audit_v4/harness_audit.md` | PASS | final audit for that subphase; later superseded by closeout |
| `experiments/runs/week09_expanded_task_controls_diagnostic/control_report.md` | FAIL | historical diagnostic that blocked invalid new task assets |
| `experiments/runs/week09_expanded_task_controls_diagnostic_v2/control_report.md` | PASS | corrected rerun of preceding diagnostic |
| `experiments/runs/week_09_closeout_control_calibration/control_report.md` | PASS | canonical final 26-task calibration |
| `experiments/runs/week_09_control_calibration_v0/control_report.md` | PASS | historical early Week 9 calibration |
| `experiments/runs/week_09_redundancy_control_calibration_v0/control_report.md` | PASS | historical redundancy checkpoint |

Additional aggregate views:

| evidence | role |
| --- | --- |
| `experiments/reports/week06_eval_quality.md` | historical eval-quality gate summary |
| `experiments/reports/eval_matrices/eval_quality_gate_repo_patch_python_v0.md` | deterministic control/eval matrix |
| `experiments/reports/eval_matrices/week06_scorer_control_replay.md` | historical scorer replay view |
| `experiments/reports/eval_matrices/week06_agent_control_replay.md` | historical agent replay view |
| `experiments/reports/eval_matrices/qwen_model_eval_suite_sampling_4096.md` | historical controls beside Qwen model baseline |
| `experiments/reports/reward_hack_audit_cli_smoke.md` | historical CLI smoke; PASS 2/2 |
| `experiments/reports/reward_hack_audit_cli_smoke_via_report_cmd.md` | historical report-command smoke; PASS 1/1 |
| `experiments/reports/reward_hack_audit_week_08_v1.md` | canonical reward-hack aggregate |
| `data/task_packs/repo_patch_python_v0/heldout_private.freeze.json` | canonical heldout control-gate and freeze authority |
| `experiments/reproduction/core_smoke/eval_report.md` | canonical stored Level 2 control/replay report |
| `experiments/reproduction/core_smoke/eval_report_regenerated.md` | byte-identical regenerated Level 2 view |
| `experiments/reproduction/core_smoke/reproduction_report.md` | canonical composed local reproduction evidence |
| `docs/sandbox_invariants_v0.md` and focused tests | local workspace/leakage isolation evidence |
| `tests/test_resume.py` and Week 11 closure audit | focused failure-injection evidence |

The canonical 16-case reward-hack run also retains 16 derived source-audit
reports below `experiments/runs/reward_hack_audit_week_08_v1/case_runs/`: eight
`scorer_audit/scorer_audit.md` files and eight
`agent_task_audit/agent_task_audit.md` files. All passed their declared source
cases. The retained CLI-smoke run adds two scorer-audit children. The historical
one-case `via_report_cmd` view points to a child run that is no longer retained
locally. These are child evidence or smoke artifacts, not independent
aggregates; none are added to the canonical 16-case or model-policy
denominators.
