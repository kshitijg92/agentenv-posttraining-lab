# Week 12 Implementation Notes

## 2026-08-23 Claim And Evidence Inventory

### Scope

This checkpoint maps the Week 12 report to existing authorities before any
final narrative is written. It does not create a new manifest, schema, report
builder, or source of run identity.

The settled headline result is:

```text
Within the frozen, limited development comparisons and under the pinned
harness, hidden scorer, model/serving protocol, deterministic greedy decoding,
and one rollout per policy-task cell, neither positive-SFT treatment nor the
exploratory DPO continuation improved observed nested task success.
```

The exact observations are 0/8 successes for base, raw SFT, and
efficiency-filtered SFT, followed by 0/6 successes for base,
efficiency-filtered SFT, and DPO on the corrected lineage-disjoint comparison.
This supports two abstentions and no observed improvement. It does not support
policy equivalence, a population effect estimate, or a general claim about SFT
or DPO.

### Artifact Economy Decision

The final synthesis has one unique owner:

```text
experiments/reports/week12_spike_report.md
```

It owns the final human interpretation and next-bet decision. It does not own
task identity, hashes, training lineage, model artifacts, attempt outcomes,
control results, or reproduction status. Those facts remain with existing
typed artifacts.

No `report bundle` CLI or claim manifest is justified. Existing loaders and
the core reproduction command already validate and regenerate the machine-
owned evidence. A new bundle would duplicate authority without improving the
meaning of the final claim.

Because `experiments/` is ignored as a whole, the final report will need one
narrow `.gitignore` exception if it is to be available in a clean checkout.
That exception should cover only the final Week 12 report, not the local
experiment graph.

## Authority Order

When two human-readable files disagree, use this precedence:

1. typed manifests, records, split locks, configs, and attempt artifacts;
2. canonical reports regenerated from those artifacts;
3. closure audits that interpret the canonical evidence;
4. historical plans, implementation notes, and earlier reports.

`docs/construct_validity_v0.md` correctly defines the narrow measured
construct, but its embedded three-task development inventory is historical.
Current counts and membership must come from `splits.lock.json` and the current
task-hash report.

The Week 10 generated eval reports also say that a separate hidden-validator
version/hash was not captured. The final scorer-identity field must therefore
use:

```text
scoring_contract_v0
+ selected task hash set, which includes hidden-test bytes
+ eval config hash
+ harness runtime/source hashes
```

The absence of a separate scorer-version field remains an explicit limitation.

## Claim/Evidence Map

| claim id | proposed claim | authoritative evidence | statistical support | required counterevidence or limitation | decision |
| --- | --- | --- | --- | --- | --- |
| C1 | A narrow local Python repo-patch eval/post-training loop exists with hidden scoring, controls, traces, replay, data filtering, and training artifacts. | task pack and split lock; `docs/scoring_contract.md`; Week 9 closeout; Week 11 core reproduction | Deterministic construction and validation evidence, not a population sample | Python-only localized tasks; strict JSON-action interface; local runner is not a hostile-code sandbox | Support, narrowly |
| C2 | The final 26-task harness/control state behaved as declared. | Week 9 aggregate harness audit and full-pack control calibration | Census of all 26 task/control combinations over three repeats: 468/468 matched; 156/156 groups stable | Scripted controls encode expected behavior and are not model-capability trials; earlier failed diagnostics must remain visible | Support for known authored cases |
| C3 | The reward-hack layer detected and neutralized all authored v1 cases without exposing private content. | canonical Week 8 reward-hack report and source artifacts | 16/16 authored cases, with 16/16 valid controls | Hand-authored deterministic cases; two valid controls reused eight times each; no heldout reward-hack pack | Support only for the authored catalogue |
| C4 | Reviewed trajectory evidence was transformed into mechanically valid SFT and DPO inputs and adapters. | Week 9/10 source records; three Week 10 training manifests/results | Exact reconstruction: 98 SFT examples; 94 filtered examples; 29 DPO pairs; completed optimizer schedules | Explicit learning-lab authorization override for a source-runtime mismatch; AI-proxy review; mechanical validity is not efficacy | Support for plumbing and execution only |
| C5 | Neither positive-SFT treatment improved observed nested task success on the frozen selection comparison. | `configs/eval/positive_sft_policy_selection.yaml`; suite manifest; canonical report; Week 10 closure | Eight paired development tasks, one deterministic rollout per policy-task cell; every arm 0/8 | Zero-success floor; no stochastic or training-seed variance; two raw-SFT cells unscored; no heldout evidence | Abstain; no observed improvement |
| C6 | Exploratory DPO provided no observed task-success benefit and showed prompt-copying collapse on the corrected comparison. | DPO training manifest; corrected disjoint eval config, suite, report; Week 10 closure | Six paired lineage-disjoint development tasks, one deterministic rollout per cell; every arm 0/6 | DPO parent was designated after SFT abstention; first eight-task matrix was contaminated; one 29-pair pass; no hyperparameter search | Abstain; no observed benefit in this experiment |
| C7 | Stored Week 10 evidence reconstructs locally, and the tracked deterministic harness path reproduces offline in a clean tree. | reproduction plan; core reproduction report; Week 11 closure | 11/11 Level 1 and 26/26 Level 2 required checks; 24/24 control/replay expectations | Seven top-level evidence files absent from Git; 30 absolute repository references; live inference and training skipped | Support split Level 1/Level 2 claim only |
| C8 | Heldout-private natural-model outcomes did not influence training, filtering, prompt/decoder choices, or model selection. | split lock; heldout freeze record; heldout protocol; Week 10/11 closure audits | Six hash-frozen tasks; zero natural-model attempts at freeze; outcomes remain unopened | Authorship and scripted pre-freeze calibration are allowed; this is process evidence, not a heldout performance result | Support isolation claim; no generalization claim |

## Task And Lineage Map

Authoritative current split counts:

| split | count | role |
| --- | ---: | --- |
| practice | 1 | harness/model diagnostic only |
| dev | 19 | training-source or development-comparison tasks |
| heldout_private | 6 | frozen and unopened by natural-model evaluation |
| public_calibration | 0 | unused |

The eleven positive-SFT training tasks are the development tasks not selected
for the frozen eight-task SFT comparison:

```text
repair_jsonl_deduper
preserve_cli_error_codes
repair_config_precedence
repair_header_merge
repair_duration_parser
repair_record_chunking
repair_query_encoding
repair_semver_precedence
repair_csv_projection
repair_relative_path
repair_template_expansion
```

The frozen SFT selection tasks are:

```text
repair_retry_schedule
repair_interval_coalescing
repair_alias_chain
repair_inventory_transaction
repair_access_policy
repair_config_inheritance
repair_event_rollup
repair_job_dispatch
```

DPO preference data added `repair_retry_schedule` and
`repair_interval_coalescing` to the inherited eleven-task SFT lineage. The
corrected DPO comparison therefore used the remaining six tasks:

```text
repair_alias_chain
repair_inventory_transaction
repair_access_policy
repair_config_inheritance
repair_event_rollup
repair_job_dispatch
```

The heldout-private tasks are:

```text
repair_stable_toposort
repair_json_pointer_lookup
repair_utf8_batching
repair_env_assignment_parser
repair_decimal_rounding
repair_latest_record_selection
```

Current task-hash authority:

```text
report: experiments/reports/hashes/repo_patch_python_v0_task_hashes.json
task count: 26
pack record hash: xxh64:70af6abbb3ae1d61
manifest hash: xxh64:cff57ad8b0eabd03
current split-lock hash: xxh64:6a8196091ebfeb31
```

The heldout freeze records the historical pack/split state at freeze. Its
historical split-lock hash differs from the current split-lock hash because
later development tasks were permitted to be added; the six heldout task IDs
and hashes remain fixed.

## Canonical Measurement-Trust Evidence

| control boundary | canonical evidence | observed result | interpretation limit |
| --- | --- | --- | --- |
| aggregate harness audit | `experiments/harness_audit/week_09_closeout/harness_audit.md` | PASS; agent 21/21, scorer 12/12, zero mismatches/errors | Authored cases only |
| scorer controls | `experiments/runs/week_09_closeout_control_calibration/control_report.md` | 234/234 expected results across oracle, no-op, and public-only controls | Repeats are stability evidence, not independent tasks |
| agent controls | same full-pack report | 234/234 expected results across happy, malformed, and recoverable scripts | Scripted behavior is not model capability |
| flake detection | same report and manifest | 468/468 records matched; 156 groups; zero drifted | Normalized deterministic artifacts only |
| public-check idempotency | Week 9 control manifest and closure | 26/26 idempotent at two repeats | Authored public commands only |
| heldout pre-freeze gate | `heldout_private.freeze.json` | 36/36 expected control attempts; six replay groups; 6/6 public checks idempotent | Scripted calibration did not consume natural-model measurement |
| reward-hack audit | `experiments/reports/reward_hack_audit_week_08_v1.md` | 16/16 cases passed; 16/16 detected and neutralized; 0 exposures; 0 training-allowed | Hand-authored deterministic catalogue; controls heavily reused |
| fresh deterministic execution/replay | `experiments/reproduction/core_smoke/reproduction_report.md` | Level 2 PASS 26/26; 18 attempts; six replays; 24/24 expected outcomes | No live model or training rerun |
| workspace and leakage boundaries | `docs/sandbox_invariants_v0.md` plus focused tests | hidden validators, controls, manifest contents, and canaries excluded from agent workspace/artifacts; workspace reset enforced | Local layout isolation, not hostile-code security |
| resume and failure injection | Week 11 closure and `tests/test_resume.py` | interruption, missing/corrupt evidence, duplicates, timeouts, missing validator, bad config, and drift fail closed as designed | Focused tests; not rerun by core reproduction |

## Exhaustive Standalone Control-Report Index

This inventory covers every retained top-level `control_report.md` and
`harness_audit.md` outside per-case reward-hack subdirectories. Per-case audit
reports are derived children of the canonical reward-hack report and are not
separate aggregate authorities.

| retained report | observed status | authority classification | final-report use |
| --- | --- | --- | --- |
| `experiments/harness_audit/week_09_closeout/harness_audit.md` | PASS | canonical final harness audit | headline control table |
| `experiments/harness_audit/week_09_harness_audit_v0/harness_audit.md` | PASS | historical Week 9 audit | evidence index only |
| `experiments/harness_audit/week_09_harness_audit_v1/harness_audit.md` | PASS | historical later Week 9 audit | evidence index only |
| `experiments/harness_audit/week_09_redundancy_harness_audit_v0/harness_audit.md` | PASS | historical redundancy checkpoint | evidence index only |
| `experiments/runs/control_agent_flake_detection_smoke/control_report.md` | PASS | test/smoke artifact | detector implementation evidence, not experiment evidence |
| `experiments/runs/control_flake_detection_groups_schema_smoke/control_report.md` | PASS | test/smoke artifact | schema smoke only |
| `experiments/runs/control_flake_detection_smoke/control_report.md` | PASS | historical/test smoke | evidence index only |
| `experiments/runs/control_flake_report_smoke/control_report.md` | FAIL | intentional negative drift-render smoke | show that two drifted scorer groups make the report fail |
| `experiments/runs/control_flake_report_stable_smoke/control_report.md` | PASS | paired stable render smoke | detector/report smoke only |
| `experiments/runs/eval_quality_controls_repo_patch_python_v0/control_report.md` | PASS | canonical at Week 6, historical now | Week 6 gate history |
| `experiments/runs/natural_model_anchor_contrast_acquisition/control_calibration/control_report.md` | PASS | historical acquisition trust artifact with foundation-worktree paths | source-provenance history; not current headline count |
| `experiments/runs/natural_model_anchor_contrast_acquisition/harness_audit/harness_audit.md` | PASS | historical acquisition trust artifact | source-provenance history |
| `experiments/runs/week06_controls/control_report.md` | PASS | historical Week 6 duplicate view | evidence index only |
| `experiments/runs/week09_dpo_control_calibration_v2/control_report.md` | PASS | historical DPO-data checkpoint | evidence index only |
| `experiments/runs/week09_dpo_control_calibration_v3/control_report.md` | PASS | final trust artifact for that DPO-data subphase, later superseded by closeout | evidence index only |
| `experiments/runs/week09_dpo_harness_audit/harness_audit.md` | PASS | historical early DPO-data audit | evidence index only |
| `experiments/runs/week09_dpo_harness_audit_v2/harness_audit.md` | PASS | historical DPO-data audit | evidence index only |
| `experiments/runs/week09_dpo_harness_audit_v3/harness_audit.md` | PASS | historical DPO-data audit | evidence index only |
| `experiments/runs/week09_dpo_harness_audit_v4/harness_audit.md` | PASS | final audit for that DPO-data subphase, later superseded by closeout | evidence index only |
| `experiments/runs/week09_expanded_task_controls_diagnostic/control_report.md` | FAIL | historical diagnostic that correctly blocked new tasks | report the failure and repair path |
| `experiments/runs/week09_expanded_task_controls_diagnostic_v2/control_report.md` | PASS | corrected rerun of the preceding diagnostic | report the recovery, not as an extra trial |
| `experiments/runs/week_09_closeout_control_calibration/control_report.md` | PASS | canonical final 26-task calibration | headline control table |
| `experiments/runs/week_09_control_calibration_v0/control_report.md` | PASS | historical early Week 9 calibration | evidence index only |
| `experiments/runs/week_09_redundancy_control_calibration_v0/control_report.md` | PASS | historical redundancy checkpoint | evidence index only |

The historical failed expanded-task diagnostic recorded four oracle patch-
application errors plus two failed agent-control expectations on
`repair_query_encoding`. The corrected v2 run passed 48/48 records before the
tasks entered later evidence. The intentional flake-render smoke records two
drifted scorer groups and an overall `FAIL`; it is a negative detector fixture,
not instability in the canonical task pack.

## Additional Aggregate Control Views

| evidence | status or role | authority classification |
| --- | --- | --- |
| `experiments/reports/week06_eval_quality.md` | PASS on the then-current four-task pack | historical gate report |
| `experiments/reports/eval_matrices/eval_quality_gate_repo_patch_python_v0.md` | controls and replay on three development tasks | historical/canonical deterministic config view |
| `experiments/reports/eval_matrices/week06_scorer_control_replay.md` | scorer replay view | historical derived view |
| `experiments/reports/eval_matrices/week06_agent_control_replay.md` | agent replay view | historical derived view |
| `experiments/reports/eval_matrices/qwen_model_eval_suite_sampling_4096.md` | controls on track beside a 0/3 Qwen model result | historical model-baseline view |
| `experiments/reports/reward_hack_audit_cli_smoke.md` | PASS 2/2 | historical CLI smoke; not a headline authority |
| `experiments/reports/reward_hack_audit_cli_smoke_via_report_cmd.md` | PASS 1/1 | historical report-command smoke; not a headline authority |
| `experiments/reports/reward_hack_audit_week_08_v1.md` | PASS 16/16 | canonical reward-hack aggregate |
| `data/task_packs/repo_patch_python_v0/heldout_private.freeze.json` | frozen control-gate counts and hashes | canonical heldout-isolation authority |
| `experiments/reproduction/core_smoke/eval_report.md` | fresh Level 2 control/replay report | canonical stored invocation, machine-local |
| `experiments/reproduction/core_smoke/eval_report_regenerated.md` | byte-identical to same-run report | canonical regeneration check, machine-local |
| `experiments/reproduction/core_smoke/reproduction_report.md` | PASS 37/37 combined checks | canonical local reproduction report |
| `docs/sandbox_invariants_v0.md` and focused tests | enforced local isolation invariants | documentation plus executable evidence |
| Week 11 failure-injection tests and closure audit | typed fail-closed recovery matrix | focused executable evidence, intentionally absent from core command |

The canonical reward-hack aggregate owns 16 derived child audits: eight
`scorer_audit.md` reports and eight `agent_task_audit.md` reports below
`experiments/runs/reward_hack_audit_week_08_v1/case_runs/`. All 16 source
audits passed their declared cases. The retained CLI-smoke run has two further
scorer-audit children. The one-case `via_report_cmd` view points to a historical
child run that is no longer retained locally. These children and smoke views
are indexed here for completeness but are not independent trials and are not
added to the canonical 16-case denominator.

## Post-Training Accounting

### Review And Filtering

| stage | accepted | rejected | unresolved | interpretation |
| --- | ---: | ---: | ---: | --- |
| contiguous positive-prefix review | 98 | 2 | 0 | two sources had no nonempty clean prefix before the first invalid action |
| embedded action-efficiency review over accepted prefixes | 94 | 4 | 0 | two duplicate unchanged reads and two unused `pyproject.toml` inspections |
| target-model SFT materialization | 98 completed | 0 failed | 0 overlength | mechanical serialization result |

Raw versus filtered source accounting:

| treatment | unique examples | tasks | supervised tokens | serialized sequence tokens |
| --- | ---: | ---: | ---: | ---: |
| raw positive SFT | 98 | 11 | 16,412 | 97,005 |
| efficiency-filtered unique population | 94 | 11 | 13,207 | 86,700 |
| removed | 4 | 0 tasks removed | 3,205 | 10,305 |

The filtered executed schedule repeated four complete examples to match 98
optimizer steps. It carried 16,071 supervised tokens, a 341-token shortfall
within the frozen 907-token complete-example tolerance.

### Training Artifacts

| policy | run id | config hash | manifest hash | adapter hash | steps | source units |
| --- | --- | --- | --- | --- | ---: | ---: |
| raw SFT | `positive_sft_lora_run_75026bd7b64e4b229450ced024f23221` | `xxh64:112f566a2d9d56e8` | `xxh64:3828900162386f5c` | `xxh64:628c8c9a46b0bd1e` | 98/98 | 98 examples |
| efficiency-filtered SFT | `positive_sft_lora_run_ba8374dd03734bbc8de84a678f41c234` | `xxh64:4fe146e3e33500c7` | `xxh64:024cb3a3d8a4facb` | `xxh64:4b88697558dcbdd3` | 98/98 | 94 unique examples |
| exploratory DPO | `dpo_lora_run_b8a3752e281f4ca8af9d65bd97a1ef1b` | `xxh64:2938bcf1227fddd8` | `xxh64:a7b4da47350bdb08` | `xxh64:ea8dadb299dfed48` | 29/29 | 29 pairs |

All three use `Qwen/Qwen2.5-Coder-3B-Instruct` revision
`89fe5444e8baf5736e70f528f1edcc79e6616ef6` and protocol
`qwen2_5_coder_3b_agentenv_json` at hash `xxh64:9b9eba719de618f1`.

## Canonical Policy Comparisons

### SFT Selection

```text
config: configs/eval/positive_sft_policy_selection.yaml
config hash: xxh64:f3861aef6336bbe2
suite id: eval_suite_c53b4f76646b45269032e9b69878ef0b
suite manifest hash: xxh64:6a46d6e79373889c
selected task hash set: xxh64:cb95e4422a6ee152
harness runtime hash: xxh64:02cd08e1c3fbbad8
report hash: xxh64:51fca6823174a8f4
```

| policy | nested task success | scored | public pass | prompt loop | total tokens | actions |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| base | 0/8 | 8/8 | 7/8 | completed 8/8 | 37,938 | 33 |
| raw SFT | 0/8 | 6/8 | 6/8 | completed 6/8; max turns 2/8 | 246,251 | 104 |
| efficiency-filtered SFT | 0/8 | 8/8 | 8/8 | completed 8/8 | 87,511 | 62 |

Decision: `abstained`, `complete_tie`, no selected policy. Token/action counts
cannot break a tie over an empty successful-task set.

### Corrected DPO Comparison

```text
config: configs/eval/dpo_exploratory_policy_evaluation.yaml
config hash: xxh64:3f424ac17b2f6dd6
suite id: eval_suite_f53256f26a5d47a49a7214253722f447
suite manifest hash: xxh64:de5a948521bf8316
selected task hash set: xxh64:f620bafa6b168d4c
harness runtime hash: xxh64:dee571c4bcad79c0
report hash: xxh64:dc796e3f37e64f08
```

| policy | nested task success | scored | public pass | prompt loop | total tokens | actions |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| base | 0/6 | 6/6 | 5/6 | completed 6/6 | 35,464 | 29 |
| efficiency-filtered SFT | 0/6 | 6/6 | 6/6 | completed 6/6 | 70,640 | 47 |
| DPO | 0/6 | 0/6 | 0/6 | max turns 6/6 | 303,394 | 156 |

Decision: `abstained`, `complete_tie`, no selected policy. All DPO actions
copied one of the four illustrative prompt tool calls; no final answer was
emitted.

The earlier eight-task DPO suite is retained only as a contaminated diagnostic
because six of the 29 preference pairs came from two evaluation tasks. Its
0/8 result does not enter the final efficacy claim.

## Reproduction Boundary

The retained core report passed 37/37 required checks:

```text
Level 1 stored evidence:       PASS 11/11
Level 2 deterministic runtime: PASS 26/26
Level 3 live inference:        SKIP
Level 4 training rerun:        SKIP
```

Level 1 is locally reconstructible but not available in a clean clone or
relocatable. Level 2 is tracked, clean-tree, CPU-only, and offline after locked
dependency installation. These are separate claims.

## Next-Bet Decision

The user approved the task/eval calibration spike on 2026-08-23. The frozen
proposal authors exactly six new development tasks, two in each of three
predeclared complexity bands; calibrates controls, hidden tests, hashes, human
solve notes, and three-repeat flakes before model use; and then spends exactly
six deterministic base-model attempts. A 2-4/6 nested-success result licenses
a later post-training comparison, 0-1/6 redirects to protocol/base-capability
diagnosis, and 5-6/6 redirects to harder construct calibration. The new slice
is permanently development data and can never become heldout evidence.

Approval selects the next phase. It does not authorize executing the spike,
opening heldout outcomes, or running more post-training during Week 12.

## 2026-08-23 Report-Draft Verification

- `experiments/reports/week12_spike_report.md` was created as the single final
  synthesis surface and given a narrow `.gitignore` exception.
- Its 24-path standalone `control_report.md`/`harness_audit.md` index matches
  the retained filesystem inventory exactly. Reward-hack aggregate, smoke,
  and derived child-audit surfaces are accounted for separately.
- Headline SFT and DPO counts, control totals, flake totals, training identities,
  and retained reproduction counts were checked against their canonical
  reports and manifests.
- A fresh disposable invocation of `uv run --offline --frozen agentenv
  reproduce core` passed 37/37 required checks: Level 1 passed 11/11, Level 2
  passed 26/26, and Levels 3-4 remained explicit skips.
- The README toy control eval passed 6/6 operational checks. Its deterministic
  three-task small eval passed 24/24, and the regenerated report matched the
  same-run report byte-for-byte.
- The full closeout suite passed: 1,291 tests in 286.01 seconds, Ruff clean,
  Pyright with zero errors and zero warnings, and `git diff --check` clean.
