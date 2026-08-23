# Week 12 Plan

Status: ready to start. Week 11 is closed with a split reproducibility claim,
and Week 12 will synthesize the existing evidence without reopening model
selection, heldout evaluation, or post-training.

## Theme

Week 12 is about claim discipline, evidence synthesis, and choosing the next
technical bet from the observed bottleneck.

The manual's goal is:

```text
finish with one truthful technical report whose claims are no broader than the
authoritative evidence, place counterevidence and limitations beside the main
results, and choose one next experiment with a predeclared stop rule
```

The learning objectives are:

```text
claim boundaries as part of experimental design
evidence versus interpretation versus decision authority
statistical support for negative and abstaining results
counterevidence beside headline claims
artifact economy in final reporting
next-experiment selection from an observed bottleneck rather than novelty
```

This is not another model-tuning week. It must not inspect heldout-private
model outcomes, change prompts or decoding to rescue Week 10, retrain an
adapter, or reinterpret a zero-success comparison as evidence of improvement.

## Starting Evidence

Weeks 1-11 are closed. Week 12 starts from these settled facts.

### Measurement And Task Boundary

- The repository implements a local Python repo-patch eval/post-training loop
  with task manifests, isolated agent workspaces, public checks, hidden
  scorers, typed attempts, traces, replay, controls, and reports.
- The task pack contains 26 tasks: one practice, 19 development, and six
  heldout-private tasks.
- Task success is exactly nested `AttemptStatus.PASS`. Public-check success and
  prompt-loop completion are diagnostic only.
- Oracle, known-bad, scorer-audit, agent-audit, leakage, reward-hack, replay,
  split, and provenance checks exist to bound measurement trust.
- The six heldout-private tasks remain unopened by natural-model evaluation.

### Post-Training Result

- The raw and efficiency-filtered SFT arms used the same pinned base,
  model-input protocol, serving path, and 98-step exposure schedule.
- On the frozen eight-task development comparison, base, raw SFT, and filtered
  SFT each achieved 0/8 task successes. The selection decision was `abstain`.
- The DPO continuation was exploratory because no SFT policy won selection.
- The initial DPO comparison was contaminated by preference-source task reuse
  and was correctly demoted rather than rationalized.
- On the corrected six-task lineage-disjoint comparison, base, filtered SFT,
  and DPO each achieved 0/6 task successes. The decision again abstained.
- DPO exhausted every turn budget while copying the prompt's illustrative tool
  calls. It did not help in this experiment and was behaviorally worse than its
  parent, but this is not a general claim about DPO.

### Reliability And Reproduction Result

- The tracked Level 2 workflow executes deterministic controls, hidden
  scoring, replay, artifacts, and report regeneration offline in a clean tree.
- The retained Level 1 Week 10 graph passes local integrity and reconstruction
  checks at the original checkout and artifact location.
- Level 1 is not available in a clean clone and is not relocatable: seven
  designated top-level evidence files are absent from Git, and the top-level
  manifests contain 30 repository-owned absolute path references.
- Live model inference and training reproduction remain explicit skips.
- Resume and retry authority, terminal model failures, missing or corrupt
  evidence, duplicate identities, timeouts, missing validators, and semantic
  drift have typed fail-closed behavior.

These facts provide evidence about an auditable narrow lab and a negative
development experiment. They do not establish model improvement, heldout
generalization, broad coding-agent capability, stochastic reproducibility, or
production sandbox security.

## Artifact Economy Decision

Week 12 begins with synthesis, not a new reporting subsystem.

The default new final surface is:

```text
experiments/reports/week12_spike_report.md
```

It is a human-readable derived report. It must cite authoritative manifests,
typed records, canonical reports, closure audits, and reproduction evidence;
it must not become a second authority for run identity, hashes, task
membership, training lineage, or selection decisions.

Normal weekly notes may also be created as work proceeds:

```text
notes/weekly/week_12/implementation_notes.md
notes/weekly/week_12/learnings.md
notes/weekly/week_12/closure_audit.md
```

The following manual-suggested surfaces are conditional rather than automatic:

- `docs/claim_boundaries.md`, `docs/claim_evidence_table.md`, and
  `docs/non_claims.md` are unnecessary if the final report owns the final
  synthesis without becoming unwieldy.
- `docs/next_phase_plan.md` is unnecessary if the report and Week 12 closure
  note can state the selected bet and stop rule without ambiguity.
- `docs/final_readiness_review.md` is unnecessary if the closure audit checks
  the same criteria.
- A `report bundle` CLI is unjustified unless existing loaders and reporting
  commands cannot regenerate the required evidence without unsafe manual
  interpretation.
- `README.md` should receive only the minimum updates needed to expose current
  quickstart commands, claim boundaries, limitations, and the final report.

Before adding any of these, answer the repository's artifact-economy questions:

1. What unique fact or decision would the surface own?
2. Which producer writes it and which concrete consumer needs it?
3. Why can the invariant not be derived from existing authoritative records?
4. What safety, reproducibility, or measurement property disappears without
   it?

If those answers are not concrete, do not add the surface.

## Design Checkpoint 1: Freeze The Headline Claim

This is the first collaborative design checkpoint. Before drafting the final
report, ask the user:

```text
What is the strongest claim the final lab artifact should make, and which
counterevidence must appear beside it so that the claim remains truthful?
```

Do not silently choose the final wording. Record the user's first-pass claim,
then pressure-test it against:

- the exact narrow task distribution;
- hidden-scorer and control evidence;
- zero successes in both Week 10 canonical comparisons;
- SFT selection abstention;
- the contaminated initial DPO comparison and corrected replacement;
- prompt-copying DPO collapse;
- one deterministic rollout per policy-task cell;
- the absence of training-seed and sampling variance estimates;
- the local-only Level 1 evidence graph;
- Level 3 and Level 4 reproduction skips;
- unopened heldout-private model outcomes.

The final claim should become narrower after this pressure test. If a clause
cannot be tied to authoritative evidence and its counterevidence, remove or
qualify it.

## Checkpoint 2: Build A Read-Only Claim/Evidence Map

Before creating the final report, map every required section and table to the
artifact that already owns its facts.

At minimum, inventory these relationships:

| report content | expected authority | main risk to check |
| --- | --- | --- |
| task distribution and split counts | task-pack manifest, split lock, task hashes | stale copied counts or heldout ambiguity |
| scoring contract | typed attempt status and scoring documentation | public success mislabeled as task success |
| controls, audits, and flakes | control, scorer-audit, agent-audit, replay artifacts | mixing expected controls with model capability |
| traces and reward evidence | trajectory records, review records, reward-hack audit | treating observability as reward validity |
| SFT population and filtering | positive-SFT records, embedded review, training manifests | duplicate filtering authority or stale totals |
| SFT comparison | canonical eval suite and comparison decision | efficiency tie-break over an empty success set |
| DPO comparison | corrected lineage-disjoint suite and comparison decision | citing the contaminated matrix as primary evidence |
| reproduction | core reproduction report and Week 11 closure audit | local integrity described as clean-clone portability |
| limitations and non-claims | Week 10/11 closure audits and governing docs | separating caveats from the claims they constrain |

Write the detailed inventory to `implementation_notes.md`, not to a new
machine-readable manifest. The inventory is working analysis; upstream typed
records remain authoritative.

Done when every proposed numerical statement, result, and claim in the final
report has one named source of authority and any conflicting or limiting
evidence is identified.

## Checkpoint 3: Freeze The Report Contract

After the headline claim is settled, freeze the final report outline and its
claim/evidence rows before writing narrative prose.

The expected report sections are:

```text
Abstract
Artifact summary and narrow task distribution
Scoring contract and measurement controls
Trace, reward, review, and training-data boundaries
SFT filtering and training treatment
Frozen base-versus-SFT result
Exploratory DPO result and contamination correction
Reward-hack evidence
Reliability and reproduction levels
Main evidence and failed hypotheses
Limitations and non-claims
Next technical bet and stop rule
Exact commands and artifact paths
```

Required tables should be included only once and should cover:

```text
task and split inventory
control, replay, and flake evidence
reward-hack outcomes
SFT filtering and treatment accounting
base versus raw SFT versus filtered SFT
filtered SFT versus DPO on the corrected disjoint suite
reproduction levels and portability boundaries
claim, evidence, run/config identity, split, scorer identity, statistical
support, counterevidence, limitation, and decision
```

The claim/evidence table is a reporting view, not a new schema. Its rows should
be few enough that each represents a meaningful final claim rather than one
row per implementation feature.

Freeze these interpretation rules before drafting:

- nested hidden-scorer `PASS` is the only task-success authority;
- development evidence cannot become heldout evidence by relabeling;
- task lineage, not attempt identity, determines training/evaluation
  contamination;
- an abstention remains an experimental decision, not missing analysis;
- token and action efficiency cannot choose a winner with no successful cells;
- mechanical training validity is separate from behavioral improvement;
- deterministic report reproduction is separate from stochastic inference or
  optimization reproduction;
- limitations must appear in the same section or row as the claims they bound.

## Checkpoint 4: Draft The Final Spike Report

Create `experiments/reports/week12_spike_report.md` from the frozen evidence
map.

Draft in this order:

1. Populate tables directly from authoritative artifacts.
2. Add claim/evidence rows with counterevidence and limitations.
3. Write the negative-results and reproduction-boundary sections.
4. Write the abstract and headline synthesis last.
5. Add exact commands and paths only after verifying they are current.

The report must preserve at least these failed hypotheses:

```text
matched raw or efficiency-filtered SFT would produce a selectable development
policy

exploratory DPO from the filtered-SFT parent would improve behavior on a
lineage-disjoint development comparison

content-hashed retained evidence would be sufficient for clean-clone,
relocatable Level 1 reproduction
```

Do not copy entire closure audits into the report. Summarize the evidence,
identify its authority, and link to the detailed records.

## Checkpoint 5: Select One Next Technical Bet

Choose the next bet only after the evidence map makes the dominant uncertainty
explicit.

The starting hypothesis to test is:

```text
measurement, provenance, and deterministic reliability are currently stronger
than the observed model behavior, while the all-zero development outcomes do
not distinguish task difficulty, interaction-protocol difficulty, base-model
capability, and post-training-data quality well enough to justify another
optimization run
```

The selected bet must state:

```text
observed bottleneck
hypothesis
smallest experiment that can falsify it
frozen development inputs
primary metric and diagnostic metrics
budget
success criterion
stop rule
what result would redirect the next phase
explicit non-claims
```

Do not choose based on novelty. Do not use heldout-private outcomes to choose
the bet. Do not begin executing the bet during Week 12.

The likely decision boundary to resolve is whether the next phase should first
improve task/eval calibration or improve post-training examples. That choice
must follow from the failure evidence; it is not settled by this plan.

## Checkpoint 6: Align The README And Operator Path

Inspect `README.md` only after the report is stable. Make the smallest update
needed so a new reader can find:

- what the artifact is and is not;
- the narrow task and scoring contract;
- the CPU-only fake/scripted small-eval or reproduction command;
- report regeneration behavior;
- the main limitations and non-claims;
- the final Week 12 report.

Do not turn the README into a second final report. Detailed evidence belongs in
the spike report and authoritative run artifacts.

## Checkpoint 7: Verification And Closure

Run read-only validation and regeneration before claiming completion. Use a
fresh caller-selected output directory for the core reproduction command and
do not overwrite retained Week 10 or Week 11 evidence.

Expected verification:

```bash
week12_repro_root="$(mktemp -d)"
uv run --offline --frozen agentenv reproduce core \
  --out "$week12_repro_root/core"

uv run --offline --frozen pytest -n auto
uv run --offline --frozen ruff check .
uv run --offline --frozen pyright
git diff --check
```

Also verify manually that:

- all report paths exist or are explicitly labeled unavailable;
- all reported run, config, suite, scorer, and hash identities match their
  authoritative sources;
- both canonical Week 10 abstentions remain unchanged;
- the contaminated DPO comparison is not presented as primary evidence;
- heldout-private model outcomes remain unopened;
- Level 1, Level 2, Level 3, and Level 4 claims remain distinct;
- every headline statement has nearby counterevidence and a limitation;
- the chosen next bet has a concrete stop rule.

At closeout, write:

```text
notes/weekly/week_12/closure_audit.md
notes/weekly/week_12/learnings.md
```

Use `closure_audit.md` for evidence, commands, outcomes, unmet criteria, and
the final next-bet decision. Use `learnings.md` only for durable lessons about
claim scope, negative evidence, counterevidence, artifact economy, and
experiment selection.

## Self-Deception Traps

- A large final report is not stronger evidence than the manifests and typed
  records it summarizes.
- Repeating a number across several documents does not independently verify
  it.
- A mechanically valid LoRA or DPO run is not evidence of improved behavior.
- Zero successes do not show that two policies are equivalent; they show that
  this comparison could not distinguish them on its primary metric.
- Lower token or action use with no successful tasks is not a capability win.
- The corrected DPO comparison does not erase the contaminated first matrix;
  both belong in the failure history with different authority.
- Six unopened heldout tasks do not support a heldout claim.
- Local hash validation does not imply artifact availability or relocatability.
- A clean deterministic control run does not reproduce live model sampling or
  training.
- Choosing another training run because the first failed is not an
  evidence-based next bet unless the failure analysis identifies what the run
  would discriminate.
- A stop rule written after seeing results is not a stop rule.

## Cut Plan

If scope grows, cut in this order:

1. report styling and diagrams;
2. duplicated standalone claim/non-claim documents;
3. a new report-bundle CLI;
4. broad README prose;
5. optional historical narrative;
6. rerunning already-closed trust artifacts that no relevant code change
   invalidated.

Do not cut:

- the collaborative headline-claim decision;
- the read-only claim/evidence inventory;
- exact authority for every main result;
- counterevidence beside headline claims;
- both Week 10 abstentions and the DPO collapse;
- contamination and heldout-isolation statements;
- the split Level 1/Level 2 reproducibility boundary;
- one failed hypothesis;
- one evidence-based next bet with a predeclared stop rule;
- final verification and written non-claims.

## Week 12 Done Criteria

Week 12 is complete when:

- the user has supplied and pressure-tested the first-pass headline claim;
- every final claim maps to authoritative evidence, exact run/config identity,
  support, counterevidence, limitation, and decision;
- one final spike report contains the required task, control, reward-hack,
  filtering, policy-comparison, reproduction, and claim/evidence views;
- the report states exact commands and artifact paths;
- the zero-success SFT result, selection abstention, DPO contamination
  correction, and prompt-copying collapse are presented as primary negative
  evidence rather than buried caveats;
- the reproduction claim distinguishes local stored-evidence integrity from
  clean-tree deterministic execution, availability, relocatability, live
  inference, and training reruns;
- heldout-private model outcomes remain unopened;
- no redundant first-class artifact or CLI is added without passing the
  artifact-economy gate;
- README quickstart and report links are current without duplicating the final
  report;
- one next technical bet is selected from the observed bottleneck and includes
  a budget, success criterion, stop rule, redirect condition, and non-claims;
- the CPU-only core reproduction and full closeout checks pass, or any blocker
  is preserved precisely;
- `closure_audit.md` and `learnings.md` record the final evidence and durable
  conceptual lessons.

## First Next Step

Resolve Design Checkpoint 1 with the user before drafting the evidence map or
the final report:

```text
What is the strongest claim the final lab artifact should make, and which
counterevidence must appear beside it so that the claim remains truthful?
```
