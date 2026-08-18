# Week 11 Plan

Status: in progress. Week 10 closes with a reproducible negative
post-training result and a prompt-copying DPO failure. Week 11 is preserving
that evidence while making the lab's ordinary validation and report path
repeatable after interruption. It is not a model-tuning week.

## Theme

Week 11 is about reliability, reproduction, and typed failure handling.

The manual's goal is:

```text
make the Week 10 result reproducible without depending on hidden local state,
and prove how the runner behaves when work is interrupted or artifacts are
missing, corrupt, duplicated, timed out, or incompatible
```

The learning objectives are:

```text
reproduction as a scoped claim rather than a single vague command
archived-artifact verification versus expensive experiment reruns
resume versus retry semantics
typed operational failures rather than ambiguous partial success
deterministic report regeneration
failure injection as evidence about recovery behavior
```

## Starting Evidence

Weeks 1-10 are closed. Week 10 leaves three important facts:

1. The raw and efficiency-filtered SFT training artifacts are mechanically
   valid and reconstructible from pinned source records.
2. The frozen SFT comparison abstained at 0/8 successes for every policy.
3. The exploratory DPO adapter was mechanically valid but exhausted all six
   clean evaluation tasks while copying prompt examples.

The Week 10 closeout evidence lives in:

```text
notes/weekly/week_10/closure_audit.md
experiments/models/week_10_positive_sft_raw_lora
experiments/models/week_10_positive_sft_efficiency_filtered_lora
experiments/models/week_10_dpo_lora_exploratory_full_pass
experiments/runs/week_10_positive_sft_policy_selection
experiments/runs/week_10_dpo_exploratory_policy_evaluation_disjoint_v0
experiments/reports/week_10_policy_selection.md
experiments/reports/week_10_dpo_exploratory_policy_evaluation_disjoint.md
```

Week 11 must not reinterpret the zero-success result, reopen heldout-private,
or tune the DPO adapter. The prompt-copying behavior is a preserved failure
case that motivates reliable reporting; it is not a target for post-hoc
selection or prompt changes.

## Primary Claim Target

The strongest acceptable Week 11 claim is:

```text
From a clean checkout with the declared Python environment, one documented
CPU-only command can validate the task pack and archived Week 10 artifact
graph, run deterministic fake-policy checks, regenerate designated reports,
and produce an explicit pass/fail reproduction summary. Interrupted work is
either resumed from validated completed units or rejected with a typed reason,
and injected failure cases demonstrate those boundaries.
```

An acceptable partial result is:

```text
The repository can reproduce deterministic validation and reporting, while a
specific resume or portability boundary remains blocked and is reported with
the exact missing authority or external dependency.
```

This week does not need to rerun GPU training or live Ollama inference to prove
the default claim.

## Reproduction Levels

Week 11 will use explicit levels so that "reproduce Week 10" cannot quietly
mean different things in different contexts.

### Level 1: Archived Evidence Verification

Recompute and validate from repository artifacts:

- schemas and manifest references;
- file, record, config, task-set, and source hashes;
- training/source lineage and split-disjointness invariants;
- attempt counts and typed outcomes;
- policy-comparison decisions;
- deterministic Markdown reports.

This is the required default. It must use CPU only and require no network,
model download, GPU, paid API, or running Ollama server.

### Level 2: Deterministic Local Smoke

Run the smallest executable lab loop with fake or scripted policies:

- task-pack validation;
- public and hidden scoring checks;
- control-policy or fake-model evaluation;
- report generation;
- filtering/accounting summary where supported by existing consumers.

This is also part of the default path if it remains fast and deterministic.

### Level 3: Live Model Evaluation

Optionally rerun base or adapter inference when the exact local Ollama model
compositions are available. This is a heavyweight environment check, not a
requirement for the default reproducibility claim.

### Level 4: Training Reproduction

Optionally rerun SFT or DPO optimization with the pinned base revision and
hardware-capable environment. Bitwise equality is not assumed across hardware
or library changes unless the experiment proves it. This level is outside the
default Week 11 path.

The reproduction report must say which levels ran. Passing Level 1 and Level 2
must never be worded as if Level 3 or Level 4 also ran.

## Core Constraints

The default reproduction path must:

- run without a GPU, paid API, network access, model download, or Ollama;
- avoid inspecting heldout-private model outcomes;
- fail nonzero when required evidence is missing or invalid;
- distinguish a skipped optional heavyweight check from a passed check;
- use pinned manifests and records rather than mutable directory discovery;
- produce deterministic output from the same inputs;
- avoid overwriting authoritative Week 10 evidence;
- work from repository-relative inputs where current artifact contracts permit;
- report historical absolute-reference limitations honestly where they do not;
- remain small enough for local use and a lightweight CI job.

## Artifact Economy Decisions

Week 11 begins with an inventory, not new schemas.

Reuse these existing authorities where possible:

```text
task manifests and split locks          -> task identity and split ownership
training manifests                      -> training inputs, schedules, and model lineage
eval-suite manifests                    -> selected tasks, policies, attempts, and runtime
typed attempt records                   -> completion and failure evidence
comparison records                      -> selection decision authority
reporting commands                      -> human-readable derived output
existing artifact loaders               -> integrity validation
```

Potential manual-suggested surfaces are conditional:

- A human-facing `docs/reproducibility.md` has unique value if it is the single
  operator procedure and claim boundary.
- A machine-readable reproduction plan is justified only if it freezes an
  ordered set of checks that no existing config owns and one command consumes.
- A wrapper script is justified only as a thin stable entrypoint after the
  underlying commands are known; it must not duplicate validation logic.
- A reproduction report is justified as final run evidence, not as another
  source of truth for facts already present in manifests.
- A CI workflow is added only after the CPU/no-network command is stable.
- Resume records or schemas are added only after the resume authority and
  statuses are conceptually resolved with the user.

Do not create all filenames suggested by the manual merely because they are
listed there. Each new persisted surface must pass the repository's artifact
economy gate.

## Checkpoint 1: Inventory Existing Reproduction Surfaces

Perform a read-only audit of:

- CLI entrypoints for task validation, eval, artifact validation, and report
  generation;
- existing run-directory and attempt-directory ownership;
- manifest and comparison loaders that already reconstruct artifacts;
- current behavior when an output directory already exists;
- current test fixtures for interruption, timeouts, missing files, corrupt
  JSON, duplicate ids, and config-path failures;
- environment and lock metadata already captured by run manifests;
- repository-relative versus absolute provenance references.

Deliverable: one concise table in `implementation_notes.md` mapping each desired
Week 11 check to an existing producer/consumer or a concrete missing boundary.

Done when we can identify the smallest composition of current commands and the
few gaps that genuinely require implementation.

## Checkpoint 2: Freeze The Default Reproduction Claim

Before writing an orchestrator, specify:

```text
required inputs
checks that execute
outputs regenerated
optional checks skipped
exit-code meaning
expected runtime class
environment assumptions
```

The plan must answer separately:

- Does the command prove stored evidence is internally valid?
- Does it execute a fresh agent/scorer path?
- Does it reproduce a report byte-for-byte or only semantically?
- Which outputs may contain timestamps or machine-specific paths?
- What constitutes drift rather than ordinary environment variation?

The preferred initial scope is Level 1 plus a small Level 2 smoke. If an
existing CLI composition already provides this, document and test it before
introducing a new plan schema.

## Checkpoint 3: Build The Minimal CPU Reproduction Path

Implement the narrowest command sequence that satisfies Checkpoint 2.

Expected operations, subject to the inventory:

1. validate the task pack and split lock;
2. load and reconstruct the canonical Week 10 SFT and DPO training artifacts;
3. load both canonical eval suites and validate task hashes, policy topology,
   attempt counts, and typed outcomes;
4. regenerate comparison decisions and Markdown reports into a disposable
   output directory;
5. run a deterministic fake/scripted policy evaluation and scorer check;
6. compare regenerated outputs with their declared canonical expectations;
7. write one concise reproduction summary and exit nonzero on a required
   failure.

The path must write generated test output to an explicit temporary or requested
directory. It must not silently mutate the Week 10 archive.

Focused tests should cover a successful clean run, a missing required input,
and a mismatch between regenerated and canonical evidence before broadening the
matrix.

## Checkpoint 4: Define Resume Semantics Before Code

This is the main conceptual design checkpoint. Before adding `resume.py`, a
resume schema, or new statuses, ask the user:

```text
What should a resumed evaluation trust and reuse: only fully validated task
attempts, or any completed phase inside an attempt?
```

Do not propose the final field list before the user has made a first-pass
choice. Pressure-test the answer against these distinctions:

```text
resume   = continue the same declared run from validated existing work
retry    = create another attempt for a unit that failed or was incomplete
replay   = rerun a recorded action trace to test determinism
rerun    = start a new run under the same or changed config
repair   = modify invalid stored state
```

The design must identify:

- the authority that says a unit is complete;
- the hashes that make existing work reusable;
- whether a partial attempt can ever be trusted;
- how duplicate task/attempt identities are handled;
- how a config or code/runtime change invalidates reuse;
- whether retry history is append-only within a run or belongs to a new run;
- how skipped, failed, timed-out, and corrupt states affect the final suite
  outcome.

Only then implement the smallest runner change. Prefer deriving resumability
from existing manifests and typed attempts. Add persisted resume state only if
an invariant cannot be recovered safely from them.

## Checkpoint 5: Failure-Injection Matrix

Exercise the resolved contract with deterministic, inexpensive failures:

| injected condition | property to prove |
| --- | --- |
| interruption between task attempts | validated complete units are neither lost nor duplicated |
| missing partial result | incomplete work is not treated as success |
| corrupt attempt JSON | corruption is typed and blocks unsafe reuse |
| duplicate attempt or task id | ambiguity is rejected rather than resolved by file order |
| model or scorer timeout | timeout remains distinct from task failure and infrastructure failure |
| missing hidden validator | the attempt cannot become PASS |
| bad config path | failure occurs before work is attributed to a run |
| changed config/task hash | stale completed work is not reused under a different declaration |

For each case, record:

```text
injection point
expected typed outcome
whether resume is permitted
whether retry is permitted
suite-level effect
exit code
artifact evidence retained
```

Tests should assert semantics, not incidental exception strings or directory
ordering.

## Checkpoint 6: Reproduction Metadata And Report

Audit whether current manifests already capture:

```text
git SHA and dirty-state hash
dependency or lock hash
Python and platform
model repository and revision
adapter and deployed-composition hashes
data, task, scorer, protocol, and runtime hashes
seed and decoding strategy
hardware where relevant
```

Fill only material gaps at the manifest that naturally owns the fact. Do not
create a global provenance object that recopies every existing manifest.

The final reproduction report should contain:

- exact command and environment summary;
- reproduction levels attempted;
- required pass/fail/skip counts;
- canonical artifact identities checked;
- report regeneration result;
- failure-injection summary;
- portability blockers and optional-dependency skips;
- the exact claim supported and explicit non-claims.

## Checkpoint 7: Lightweight CI

After the local default path is stable, add a CI smoke only if it remains
CPU-only, network-independent after environment setup, and reasonably fast.

CI should cover:

- focused schema/loader/report tests;
- the deterministic fake/scripted reproduction path;
- representative failure injections;
- lint and static typing if their runtime is acceptable.

CI must not download the 3B base model, train adapters, launch Ollama, call paid
APIs, or evaluate heldout-private model outcomes.

## Verification Strategy

Use focused checks while implementing:

```bash
uv run pytest <changed focused test files>
uv run ruff check <changed Python files>
uv run pyright <changed Python files or package>
git diff --check
```

Run the full repository suite once at Week 11 closeout, not after every small
checkpoint:

```bash
uv run pytest -n auto
uv run ruff check .
uv run pyright
git diff --check
```

The reproduction command itself must be tested from a disposable output
directory and rerun once to show deterministic behavior or explain approved
nondeterministic fields.

## Self-Deception Traps

- A script that exits zero after skipping most checks is not reproduction.
- Revalidating stored JSON is not the same as rerunning model inference or
  training; name the level honestly.
- Reusing a file because its path exists is not resume; identity and completion
  must be validated.
- Retrying a failed task until it passes changes the evaluation procedure.
- Treating timeout, missing validator, or corrupt output as task failure hides
  infrastructure defects in the model-quality denominator.
- Regenerating a Markdown report without recomputing its comparison decision
  proves formatting, not result reconstruction.
- Byte differences from timestamps or absolute paths should not excuse semantic
  drift in tasks, policies, outcomes, or decisions.
- CI success on fake policies does not validate local model availability or
  accelerator reproducibility.
- Fixing Week 10 artifacts in place during reproduction destroys the evidence
  the procedure is supposed to validate.

## Cut Plan

Cut in this order if scope grows:

1. live Ollama reruns;
2. GPU training reruns;
3. broad concurrency experiments;
4. exhaustive failure combinations;
5. CI matrix expansion;
6. report polish.

Do not cut:

- an explicit reproduction claim boundary;
- CPU/no-network default behavior;
- manifest and hash validation;
- fresh deterministic fake/scripted execution;
- report decision regeneration;
- interruption, corruption, duplicate-id, timeout, missing-validator, and
  changed-config coverage;
- typed distinction between operational failure and task failure;
- heldout isolation;
- written limitations and non-claims.

## Week 11 Done Criteria

Week 11 is complete when:

- one documented default command runs without GPU, model server, paid API, or
  network access;
- its exact required inputs, outputs, checks, skips, and exit semantics are
  documented;
- canonical Week 10 SFT, DPO, eval, and report evidence reconstructs from
  pinned artifacts or any blocker is named precisely;
- at least one fresh deterministic task/scorer path executes;
- designated reports and comparison decisions regenerate into a disposable
  location;
- a second identical run has the expected deterministic result;
- resume and retry have distinct, tested meanings;
- validated completed units are reused only under matching declarations;
- corrupt, missing, duplicate, timed-out, missing-validator, bad-config, and
  drifted-input cases produce the intended typed outcomes;
- optional heavyweight checks are explicitly skipped rather than reported as
  passed;
- a lightweight CI smoke covers the stable default path if its dependency and
  runtime constraints are satisfied;
- the final report states which reproduction levels ran and preserves Week
  10's negative result without embellishment;
- the full closeout verification passes once.

## Notes Discipline

Use `implementation_notes.md` for command inventories, file changes, exact
failure-injection mechanics, test results, and blockers.

Use `learnings.md` only for durable conceptual lessons such as:

- what a reproducibility claim actually covers;
- why resume requires validated identity and completion authority;
- why infrastructure failure must remain distinct from task failure;
- when semantic equivalence is sufficient and when exact bytes matter;
- how optional checks can create false confidence if skips are hidden.

Do not put helper placement, script naming, exception wording, CI syntax, or
routine refactors in `learnings.md`.

## Next Small Step

Compose the Level 1 archived-evidence verifier from existing authoritative
loaders and the suite-backed policy-selection consumer. Keep report rendering
unchanged: regenerate each designated report in a disposable location and
require both the reconstructed decision and exact report bytes to match.

Do not add resume execution yet. The resume unit, terminal generation outcome,
predeclared attempt set, strict identity matching, and corrupt-attempt scope are
now decided; they should be implemented only after the required Level 1 path is
working.
