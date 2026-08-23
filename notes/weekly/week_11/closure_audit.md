# Week 11 Closure Audit

## Sources

This audit checks the current repository against:

- `references/agentic_evaluation_12_week_execution_manual.md`;
- `notes/weekly/week_11/plan.md`;
- `notes/weekly/week_11/implementation_notes.md`;
- `docs/reproducibility.md`;
- `configs/reproduction/posttraining_result.yaml`;
- `experiments/reproduction/core_smoke/reproduction_report.md`;
- the pre-execution suite declaration, terminal generation, resume, failure-
  injection, stored-evidence, and deterministic-suite tests;
- `.github/workflows/core-repro-smoke.yml`.

## Verdict

Week 11 is closed, with a deliberately split reproducibility claim.

The tracked Level 2 workflow is a clean-tree, CPU-only reproduction of the
current deterministic task, control, hidden-scorer, replay, artifact, and
report path. It runs offline after the locked environment is installed.

The Level 1 workflow is narrower. At the original checkout and retained
artifact location, it validates the integrity and lineage of the designated
Week 10 training and evaluation graph, reconstructs both policy-selection
decisions, and regenerates both canonical reports byte-for-byte. It is not a
clean-checkout reproduction: seven declared top-level evidence files are
absent from Git and the top-level manifests contain 30 repository-owned
absolute path references. The graph is locally auditable but is neither
available in a clean clone nor relocatable as currently recorded.

The exact supported claim is:

```text
The tracked, locked harness reproduces its deterministic control, hidden-
scorer, replay, artifact, and report behavior offline in a clean tree. At the
original checkout and artifact location, the designated Week 10 stored
post-training evidence also reconstructs under its pinned manifests. The Week
10 evidence graph itself is not a clean-checkout or relocatable reproduction.
```

This wording preserves the execution manual's rule that clean-environment
reproducibility must be demonstrated rather than inferred from local hashes.

## Reproduction Evidence

The documented local command is:

```bash
uv run --offline --frozen agentenv reproduce core \
  --out experiments/reproduction/core_smoke
```

Its retained report records:

| level | operation | observed result | claim boundary |
| --- | --- | --- | --- |
| 1 | Validate designated Week 10 SFT, DPO, eval, and report evidence | PASS, 11/11 checks | Local integrity and reconstruction only |
| 2 | Execute deterministic controls, hidden scoring, replay, and report regeneration | PASS, 26/26 checks | Tracked clean-tree offline workflow |
| 3 | Live model inference | SKIP | No Ollama server, model download, network, or model sampling ran |
| 4 | Training rerun | SKIP | No GPU, optimizer, or fresh adapter training ran |

The combined local report passed 37/37 required checks. Level 2 executed 18
fresh attempts, validated all 18 declared control outcomes and six configured
replays, and regenerated the same-run report byte-for-byte. Two independent
Level 1 invocations produced identical regenerated reports and verification
summaries. The local Level 2 run and an isolated clean tracked-tree run both
produced the expected 24/24 control-and-replay outcomes.

The command writes only to a fresh caller-selected output directory. It exits
nonzero when a required check fails, while still preserving a report for a
completed failed verification. Invalid input syntax and unsafe or non-empty
output locations are rejected before a reproduction run begins.

## Preserved Week 10 Result

Reconstruction did not reinterpret the negative model result:

| comparison | base | adapted policies | decision |
| --- | ---: | ---: | --- |
| frozen SFT development comparison | 0/8 | raw SFT 0/8; filtered SFT 0/8 | abstain, complete tie |
| corrected DPO-lineage-disjoint comparison | 0/6 | filtered SFT 0/6; DPO 0/6 | abstain, complete tie |

The exploratory DPO policy exhausted every turn budget while copying prompt
examples. This is evidence that DPO did not help in this experiment, not a
general claim about DPO. Heldout-private model outcomes remain unopened.

## Resume, Retry, And Completion Authority

All planned eval attempts are declared before execution. Each declaration pins
its policy, task id, attempt index, preassigned `eval_attempt_id`, config hash,
selected task hashes, model and decoding provenance where applicable, and
harness runtime. Resume requires exact identity; task, config, harness, or
other semantic hashes do not change inside one continued suite.

The settled behavior is:

```text
valid terminal attempt
  -> reuse the complete attempt byte-for-byte

valid successful terminal generation, but no terminal attempt
  -> reuse the policy result and rerun scoring plus remaining orchestration

valid terminal policy failure, but no terminal attempt
  -> preserve the policy failure and finish outer orchestration without a
     second policy sample

no terminal generation or attempt
  -> rerun that interrupted declared attempt

invalid terminal evidence
  -> reject only that attempt, continue independent work, and withhold the
     terminal policy/suite result needed for a valid comparison
```

Resume continues the same predeclared work. Retry is a new configured attempt
or new run and may obtain a new policy sample. Replay reruns deterministic
scoring/orchestration against persisted source evidence for comparison. A
rerun is a new execution; repair changes evidence and is not resume. In
particular, a recorded model timeout or model error is terminal and cannot be
silently replaced by another sample.

Structural completion also does not mean success. A suite can truthfully
finish with a terminal model failure or scorer timeout; downstream selection
and reproduction consumers must still interpret those outcomes and fail or
abstain as required.

## Failure-Injection Evidence

| injected condition | enforced outcome |
| --- | --- |
| interruption between attempts | reuse valid terminal children and run only incomplete declared work |
| missing terminal payload | reject that attempt; do not regenerate or resample it |
| corrupt terminal payload | retain and reject that attempt; allow independent siblings to continue |
| duplicate configured task id | reject config before declaring a suite |
| duplicate stored `eval_attempt_id` | reject declaration before selecting child work |
| terminal model timeout/error | reuse the failure and make no second policy call |
| terminal scorer timeout | reuse the timeout; do not relabel structural completion as PASS |
| missing hidden validator | fail validation before any attempt executes |
| bad config path | fail before output preparation |
| config, task, or harness drift | reject the whole continuation before reusing children |

These cases are established by focused tests, not by the core command. The
core report states that separation instead of presenting unexecuted failure
injection as a pass.

## Done-Criteria Audit

| Week 11 criterion | result | evidence or limitation |
| --- | --- | --- |
| One documented no-GPU/no-server/no-network default command | Met | `docs/reproducibility.md`; offline core command |
| Exact inputs, outputs, checks, skips, and exit semantics documented | Met | reproduction doc and retained report |
| Canonical Week 10 graphs reconstruct or blocker is precise | Met, scoped | local checks 11/11; seven unavailable files and 30 absolute refs recorded |
| Fresh deterministic task/scorer path executes | Met | 18 attempts across three tasks and six policies |
| Reports and decisions regenerate in disposable output | Met | two stored decisions; two stored reports and one same-run report byte-identical |
| Repeated execution has the expected deterministic result | Met | repeated Level 1 outputs identical; local and clean-tree Level 2 outcomes 24/24 |
| Resume and retry have distinct tested meanings | Met | predeclared suite and resume tests |
| Completed work is reused only under matching declarations | Met | exact config/task/model/decoding/harness binding |
| Required failure matrix has typed outcomes | Met | focused resume and lower-level timeout/config/task tests |
| Heavyweight checks are explicit skips | Met | Levels 3 and 4 are `SKIP`, not PASS |
| Lightweight CI covers the stable default path | Met, scoped | clean-tree Level 2 only; CI makes no Level 1 availability claim |
| Final report scopes levels and preserves the negative result | Met | `reproduction_report.md` and this audit |
| Full closeout verification passes once | Met | 1,291 tests, Ruff, Pyright, and diff check pass |

No task was excluded as flaky. The deterministic control calibration remained
stable; flake detection and split/training-lineage validation remain active in
tests and CI.

## Closeout Verification

The final repository-wide pass was:

```text
uv run --offline --frozen pytest -n auto
  -> 1,291 passed in 298.74s

uv run --offline --frozen ruff check .
  -> passed

uv run --offline --frozen pyright
  -> 0 errors, 0 warnings

git diff --check
  -> passed
```

The first full-suite attempt exposed two stale exception-message expectations
after readers were routed through the shared suite/generation validator. The
underlying fail-closed behavior was correct; the two focused assertions were
updated, passed in isolation, and the complete suite then passed.

## Limitations And Non-Claims

- Level 1 is not available from a clean clone and is not relocatable.
- Live model samples, provider scheduling, GPU optimization, and human review
  were not reproduced.
- Byte-identical deterministic reports do not establish stochastic model or
  training determinism.
- Failure injection covers filesystem-observable boundaries under a
  single-writer assumption; concurrent resume is unsupported.
- The agent-generation terminal manifest is published atomically, but the
  complete artifact graph is not a general transactional filesystem protocol.
- No heldout-private outcomes were inspected.
- Week 11 establishes no model improvement, broad coding-agent capability,
  benchmark result, or production sandbox-security claim.

## Week 12 Handoff

Week 12 should synthesize the existing authoritative evidence into one final
claim/evidence map, preserve counterevidence beside headline results, and pick
one next technical bet with a stop rule. The manual's suggested bundle command
and multiple documents are not automatically required: first apply the
artifact-economy gate and add only a surface that owns a real final claim or
decision rather than duplicating existing manifests and closure audits.

The strongest evidence-based starting hypothesis is that measurement and data
lineage are now substantially stronger than the model behavior. The final
report should pressure-test whether the next bet is better task/eval
calibration or better post-training examples, rather than treating another
optimization run as the default.
