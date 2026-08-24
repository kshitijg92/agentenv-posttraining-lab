# Week 12 Closure Audit

## Sources

This audit checks the current repository against:

- `references/agentic_evaluation_12_week_execution_manual.md`;
- `AGENTS.md` and `references/LOCAL_CONTEXT.txt`;
- `notes/weekly/week_12/plan.md`;
- `notes/weekly/week_12/implementation_notes.md`;
- `experiments/reports/week12_spike_report.md`;
- the task manifest, split lock, heldout freeze, and task-hash report;
- the retained Week 8-11 control, reward-hack, training, comparison, and
  reproduction authorities cited by the final report;
- the current README and repository-wide verification commands.

## Verdict

Week 12 is closed with one truthful final synthesis and one selected next
technical bet.

The strongest supported post-training result is:

```text
Within the frozen, limited development comparisons and under the pinned
harness, hidden scorer, model/serving protocol, deterministic greedy decoding,
and one rollout per policy-task cell, neither positive-SFT treatment nor the
exploratory DPO continuation improved observed nested task success.
```

Base, raw SFT, and efficiency-filtered SFT each succeeded on 0/8 frozen
development tasks. On the corrected DPO-lineage-disjoint comparison, base,
filtered SFT, and DPO each succeeded on 0/6. Both decisions abstained. This is
a negative observed result under the recorded experiment, not evidence of
policy equivalence or general SFT/DPO ineffectiveness.

Heldout-private natural-model outcomes remained unopened. Week 12 did not
retrain a policy, change the frozen comparisons, rescue the zero floor with a
post-hoc metric, or execute the next experiment.

## Final Evidence And Claim Boundaries

| surface | final result | claim boundary |
| --- | --- | --- |
| task pack | 26 tasks: practice 1, dev 19, heldout-private 6 | narrow local Python repo-patch distribution |
| SFT comparison | base 0/8, raw SFT 0/8, filtered SFT 0/8; abstain | eight dev tasks, one greedy rollout per cell, zero floor |
| corrected DPO comparison | base 0/6, filtered SFT 0/6, DPO 0/6; abstain | six lineage-disjoint dev tasks; exploratory parent |
| DPO behavior | 6/6 max-turn failures with prompt-example copying | severe regression in this run, not a general DPO claim |
| heldout-private | zero opened natural-model outcomes | isolation evidence only; no performance claim |
| reproduction | local Level 1 11/11; tracked Level 2 26/26 | no clean-clone/relocatable Level 1, live inference, or training rerun |

Every final claim is paired with its run/config identity, statistical support,
counterevidence, limitation, and decision in the report's claim/evidence table.
The contaminated first DPO matrix remains visible as diagnostic history and is
not used for the canonical 0/6 claim.

## Measurement-Trust And Control Audit

| control boundary | result | final use |
| --- | --- | --- |
| aggregate harness audit | PASS; agent 21/21 and scorer 12/12 | authored harness-behavior evidence |
| full-pack scorer controls | 234/234 expected | oracle and known-bad scorer calibration |
| full-pack agent controls | 234/234 expected | scripted happy, malformed, and recovery behavior |
| flake detection | 468/468 records; 156 stable groups; zero drift | deterministic control stability |
| public-check idempotency | 26/26 tasks | authored public-command stability |
| heldout pre-freeze gate | 36/36 controls; six replay groups; 6/6 idempotent | heldout isolation and calibration before freeze |
| reward-hack audit | 16/16; zero exposures; zero exploit traces training-allowed | authored v1 catalogue only |
| fresh core reproduction | 37/37 required checks | local stored-evidence and tracked deterministic paths |
| failure injection | focused typed fail-closed tests | separate from the core reproduction command |

The report indexes all 24 retained standalone `control_report.md` and
`harness_audit.md` files, plus reward-hack aggregate, CLI-smoke, derived child
audits, deterministic replay views, sandbox/isolation evidence, and failure-
injection evidence. It preserves both retained failures:

- the expanded-task diagnostic that caught four patch-application errors and
  two agent-control expectation failures before correction;
- the intentional flake-render fixture whose two drifted groups correctly make
  the report fail.

Passing controls reduce concern about known scorer, orchestration, replay, and
flake failures. They do not show that task or protocol difficulty was well
calibrated for the 3B base.

## Artifact-Economy Audit

The final interpretation has one owner:

```text
experiments/reports/week12_spike_report.md
```

The report cites existing typed authorities rather than copying their ownership
of hashes, task membership, run identity, or outcomes. A narrow `.gitignore`
exception tracks only this report; the generated experiment graph remains
ignored.

No report-bundle CLI, duplicate claim schema, standalone non-claims document,
or redundant readiness report was added. The README contains only the current
result boundary, report link, and executable core/toy/small operator paths.
Detailed evidence remains in the report and existing authorities.

## Selected Next Technical Bet

The user approved the task/eval-quality direction on 2026-08-23.

```text
task budget: exactly 6 new development tasks
complexity bands: 3, with exactly 2 tasks per band
natural-model budget: exactly 6 unchanged-base attempts
decoding: one deterministic greedy rollout per task
task revision after model outcomes: none
target non-degenerate result: 2-4 nested PASS outcomes out of 6
```

Before natural-model use, every task requires human solve notes, oracle and
known-bad scorer controls, scripted-agent controls, hidden validators, hashes,
and three-repeat flake calibration. Task bytes, prompt, model/serving path,
decoding, budgets, scorer, and reporting rule then freeze.

The redirect rule is predeclared:

- 2-4/6 PASS: retain the slice as development data and next improve training-
  example quality for a controlled comparison;
- 0-1/6 PASS: do not train; diagnose interaction-protocol or base-capability
  limitations;
- 5-6/6 PASS: do not train against the slice; calibrate a harder construct.

The calibration slice can never be relabeled as heldout. This decision selects
future work; it did not authorize execution during Week 12.

## Closeout Verification

The final verification was:

```text
fresh core reproduction
  -> PASS 37/37 required checks
  -> Level 1 PASS 11/11
  -> Level 2 PASS 26/26
  -> Levels 3 and 4 SKIP

README one-task deterministic control eval
  -> PASS 6/6 operational checks

README three-task deterministic small eval
  -> PASS 24/24 operational checks
  -> regenerated report byte-identical

uv run --offline --frozen pytest -n auto
  -> 1,291 passed in 286.01s

uv run --offline --frozen ruff check .
  -> all checks passed

uv run --offline --frozen pyright
  -> 0 errors, 0 warnings

git diff --check
  -> passed
```

The final static audit also found:

- all literal report artifact paths resolve;
- all 24 standalone control/audit paths are present in the control index;
- the report has balanced fenced-code delimiters;
- no forbidden LaTeX delimiters occur in the Week 12 artifacts.

## Done-Criteria Audit

| Week 12 criterion | result | evidence or limitation |
| --- | --- | --- |
| User-supplied headline claim pressure-tested | Met | narrowed to observed development result with zero-floor limits |
| Claims map to exact evidence and counterevidence | Met | implementation notes and final claim/evidence table |
| One report includes all required evidence views | Met | final spike report and exhaustive control index |
| Exact commands and paths are present | Met | report and README |
| Negative SFT/DPO results are primary evidence | Met | abstract, headline claim, main evidence, failed hypotheses |
| DPO contamination and collapse are preserved | Met | corrected comparison owns final claim; first matrix diagnostic only |
| Reproduction levels remain distinct | Met | Level 1-4 table and portability blockers |
| Heldout-private remains unopened | Met | freeze/process evidence; no outcome claim |
| Artifact economy gate applied | Met | one tracked report; no bundle CLI or duplicate final docs |
| README operator path is current | Met | core, toy, small, regeneration, limits, report link |
| One next bet has budget and redirect rule | Met | approved six-task calibration ladder |
| Full closeout verification passes | Met | 1,291 tests, Ruff, Pyright, core and README smoke checks |
| Closure audit and learnings exist | Met | this file and `learnings.md` |

## Limitations And Non-Claims

- The primary comparisons contain eight and six development tasks, with one
  deterministic greedy rollout per cell and no seed or sampling variance.
- All policies are at a zero-success floor, so equivalence and useful effect
  size are not established.
- The task family and interaction protocol are narrow and synthetic.
- The Week 10 suites lack a dedicated hidden-scorer version field; task hashes,
  config hashes, and harness provenance are the auditable substitute.
- Authored controls and reward-hack cases do not establish broad robustness or
  model capability.
- Stored Level 1 evidence is machine-local, incomplete in Git, and bound by
  absolute paths. Levels 3 and 4 remain skipped.
- No heldout, generalization, benchmark, production-security, large-scale RLHF,
  validated-human-preference, or proprietary-knowledge claim is made.

## Handoff

The next phase begins with authored development tasks and pre-model calibration,
not another optimizer run. The predeclared six-attempt base result decides
whether later work addresses training examples, protocol/base capability, or
task difficulty. Until that gate runs, the Week 12 negative result and both
abstentions remain the final model-comparison decisions.
