# Week 9 Implementation Notes

## 2026-07-09

### Training-Eligibility Authority

#### Decision

When the schemas are revised, `TrainingCandidateRecord` will be the first and
only artifact that owns downstream-use decisions such as positive SFT,
negative-example, and preference-data eligibility.

`TrajectoryRecord` will retain source evidence and versioned derived
assessments, including reward and leakage evidence, but it will not own
training-use permission. Constructed dataset records will own the exact repair,
serialization, loss mask, or preference-pair transformation applied after
eligibility is decided.

#### Reasoning

The current implementation has both preliminary eligibility on
`TrajectoryRecord` and final eligibility on `TrainingCandidateRecord`. That
creates two authorities that can drift or disagree. Week 9 introduces the
candidate/data-contract boundary, so it is the appropriate point to remove the
duplicated decision instead of adding compatibility shims.

#### Status

Design decision only. No schema or builder migration has been implemented yet.

### Public-Check Repeatability And Workspace State

#### Decision

Add a required, non-defaulted field to every `PublicCheck`:

```text
are_tests_idempotent: bool
```

`true` declares that the check is expected to preserve canonical workspace
state and produce a repeat-stable normalized observation. `false` prevents
repeated `run_tests` calls from being classified as mechanically redundant.
Omitting the field is a task-manifest validation error.

Public-check idempotence will be defined against the repo's canonical workspace
hash rather than a literal hash of every generated filesystem byte. The
canonical boundary excludes declared noisy paths such as `.pytest_cache` and
`__pycache__`. If those exclusions become brittle or exploitable, the fallback
is to suppress cache generation and narrow the ignored surface.

A normally completed public check produces a valid observation whether its
validator outcome is PASS or FAIL. An immediate identical repeat can therefore
be mechanically redundant after either outcome when the check is calibrated as
repeat-stable and state-preserving. Timeouts and tool-execution errors do not
receive that treatment because they did not produce a trusted observation.

Control flake detection is the intended calibration surface for the public
check's repeatability declaration. The proposed evidence is:

```text
canonical workspace hash before first check
    == canonical workspace hash after first check
    == canonical workspace hash after immediate repeat

normalized first result == normalized repeated result
```

#### Limitation

Control calibration exercises known task states; it does not prove behavior on
every model-generated workspace. Mutations under excluded noisy paths are also
outside the canonical-state guarantee.

#### Open Design Questions

- Define the normalized result hash used for repeat comparison.

#### Status

The required `PublicCheck.are_tests_idempotent` field is implemented. All four
current task manifests explicitly declare `true`, and a focused regression test
proves that omission fails manifest validation.

Runtime tool-result workspace evidence, repeatability calibration execution,
and control-flake integration are implemented as described below.
Redundant-block detection is implemented by the candidate-assessment checkpoint
recorded below.

Adding the required field intentionally changes every task-manifest hash.
Existing Qwen and trajectory artifacts remain historical evidence for the old
task inputs; a new pipeline requiring idempotence calibration must not silently
treat those hashes as current.

Verification:

```text
task-manifest tests: 12 passed
task-pack validation: valid, 4 tasks
focused Ruff: passed
Pyright: passed
git diff --check: passed
full parallel suite: 709 passed
```

### Control Calibration Is A Hard Training-Candidate Gate

#### Decision

Training-candidate export must fail closed when its required control-calibration
evidence is missing, hash-mismatched, incomplete, or failed. It must not emit
analysis-only candidate rows as a fallback.

At that point the harness measurement is not trusted. The correct workflow is
to inspect the control-calibration failures, repair the task or harness, and
rerun calibration before constructing any post-training candidates.

The candidate export should pin the trusted control-calibration artifact once
in its manifest rather than duplicate suite-level evidence into every source
trajectory.

#### Reasoning

Analysis-only is a valid data-use outcome for a trustworthy trajectory that is
not eligible for training. It is not an escape hatch for an untrusted
measurement system. Emitting candidate records after the calibration gate
fails would give downstream consumers structured data whose task outcomes
cannot be believed.

#### Status

Implemented by the fail-closed training-candidate trust-gate checkpoint recorded
below. Both the programmatic builder and CLI/export path now require validated
harness-audit and control-calibration artifacts before constructing records.

### Mechanical-Redundancy Assessment Placement

#### Decision

Do not add a trusted mechanical-redundancy conclusion directly to
`TrajectoryRecord`. The trajectory already preserves raw assistant tool calls
and tool results, but it does not carry the suite-level control-calibration
evidence required to trust an idempotence-based conclusion.

Training-candidate construction will join:

```text
trajectory tool-call and tool-result evidence
task-manifest idempotence declaration
trusted control-calibration evidence
```

It will detect redundant blocks and store the resulting structured assessment
on `TrainingCandidateRecord`, alongside the downstream-use decisions owned by
that record.

#### Status

Placement, schema, detector, and candidate integration are implemented by the
candidate-assessment checkpoint recorded below.

### Public-Check Idempotence Calibration Statuses

#### Decision

Represent each invocation with a nested `SinglePublicCheckRun` rather than
parallel lists of workspace hashes and outcomes. Each run will pair its
before/after canonical workspace hashes with the observation produced by that
invocation.

The per-run execution statuses are:

```text
COMPLETED
TIMEOUT
RUNNER_FAILURE
```

`COMPLETED` means the command returned normally; the public validator may still
have passed or failed. `TIMEOUT` means the command did not return within its
budget. `RUNNER_FAILURE` is reserved for an unexpected failure in the
low-level command execution or result-collection path. Do not use
`ORCHESTRATION_FAILURE`, which belongs to the broader attempt lifecycle.

The top-level calibration statuses are:

```text
IDEMPOTENT
NON_IDEMPOTENT
INCONCLUSIVE
```

Derive them with this precedence:

```text
observed canonical-state or normalized-result drift -> NON_IDEMPOTENT
otherwise, any timeout or runner failure            -> INCONCLUSIVE
otherwise                                           -> IDEMPOTENT
```

The precedence prevents a later infrastructure failure from erasing a
non-idempotence violation already observed.

Do not serialize a separate freely assignable `idempotent: bool`. It would
duplicate the authoritative status and could contradict it. Code may expose a
derived convenience property with these semantics:

```text
IDEMPOTENT      -> true
NON_IDEMPOTENT  -> false
INCONCLUSIVE    -> none
```

Only `IDEMPOTENT` satisfies the hard candidate-export gate for a public check
whose task-manifest declaration is `are_tests_idempotent: true`.

For a completed run, do not reuse attempt-level or validator-level status
fields. Idempotence is based only on canonical state preservation and command
observation equivalence. The normalized command observation consists of:

```text
exit code
normalized stdout
normalized stderr
```

Raw stdout and stderr will be persisted as separate artifact files and
referenced from `SinglePublicCheckRun` with relative, content-hash-pinned
artifact references. Do not embed unbounded command output directly in the run
record. This keeps record size bounded for future checks with large output.

The raw artifact content hashes prove file integrity. A separate normalized
result hash, derived from exit code plus normalized stdout and stderr, supports
repeat comparison while excluding volatile values such as durations and
temporary paths. Duration may be retained for diagnostics but must not
contribute to the normalized result hash.

For `TIMEOUT` and `RUNNER_FAILURE`, persist partial stdout and stderr as
hash-pinned artifact files whenever the command runner captured them. The
references are optional because some failures occur before either stream
exists. Partial failure output is diagnostic evidence only: it must not produce
a normalized completed-result hash or participate in the equality comparison
used to establish idempotence.

Model a single run as a discriminated union rather than one object with many
nullable fields:

```text
CompletedPublicCheckRun:
    status: COMPLETED

FailedPublicCheckRun:
    status: FAILURE
    failure_mode: TIMEOUT | RUNNER_FAILURE

SinglePublicCheckRun = CompletedPublicCheckRun | FailedPublicCheckRun
```

Every failed run requires both a typed `error_class` and a non-empty,
human-readable `error_message`, following the repo's existing result-schema
discipline. Completed runs forbid failure mode and error fields. The stable
failure mode supports aggregation; error class and message preserve diagnostic
specificity.

Identify one calibrated public check with:

```text
task manifest hash
public check list index
exact command
```

Do not add a separate `PublicCheck.id` in v0. The manifest hash pins the exact
ordered public-check list, the index disambiguates entries within that version,
and the command makes the reference human-auditable. Reordering or changing a
check intentionally changes the manifest hash and invalidates the old
calibration; identity does not need to remain stable across task-manifest
versions.

The number of consecutive same-workspace executions used for one idempotence
calibration is configurable, defaults to `2`, and must be at least `2`. Persist
the effective repeat count in the calibration artifact and require run indexes
to cover the full ordered range without gaps or duplicates.

This is conceptually distinct from the existing control-run `repeats` value,
which counts fresh whole-control attempts. Give consecutive public-check
idempotence runs their own CLI option rather than silently using one value for
both axes. The exact option name remains an implementation naming decision.

Calibrate each public check on its own fresh copy of `seed_workspace`. Do not
apply an oracle patch, known-bad patch, or model patch. Repeated executions for
that check share the one calibration workspace, but separate public checks do
not share a workspace. Hidden validators and control assets remain outside the
prepared workspace.

Seed-only calibration proves repeatability only on the seed state. It does not
prove that arbitrary model-generated code cannot cause the check to mutate
canonical workspace state. Therefore, actual model `run_tests` executions will
also record canonical workspace hashes before and after the call. Redundancy
assessment can then validate state preservation on the actual trajectory rather
than relying only on the seed calibration declaration.

These runtime hashes are evaluator evidence and must not be added to the
model-visible tool observation.

Persist them on every `ToolResult`, not only `run_tests` results:

```text
arguments_hash
canonical_workspace_hash_before
canonical_workspace_hash_after
```

Rename the existing `input_hash` field to `arguments_hash`. Do not add a
backward-compatible alias; this learning lab intentionally prefers a clean
current contract over compatibility with historical prompt-loop artifacts.

For valid calls, hash canonical validated arguments so omitted defaults and
explicit default values represent the same semantic input. Invalid calls may
hash the raw attempted arguments, but they are not eligible for mechanical
redundancy conclusions.

Require both canonical workspace hashes for every tool result, including
read-only tools, rejected calls, timeouts, and errors. This detects accidental
state mutation in implementations such as `read_file`, and proves that a
rejected call did not alter workspace state. The overhead is acceptable for the
small learning-lab workspaces.

Define canonical workspace state from a sorted sequence of included regular-file
records containing:

```text
workspace-relative path
exact file contents
```

Both path and contents must contribute. Content alone would miss semantically
important renames and the addition or removal of empty files such as
`__init__.py`. Continue excluding declared noisy paths. Do not include
timestamps, ownership, permissions, or symlink metadata in the v0 guarantee.
Use an unambiguous structured encoding so file boundaries cannot collide.

Keep both hashes out of model-visible tool-message content and metadata. Add a
regression test for that boundary when the fields are implemented.

If either required canonical workspace hash cannot be computed, do not emit an
incomplete `ToolResult`. Raise a typed harness/instrumentation failure and
terminate the attempt through the orchestrator-error path. Hash availability is
part of the measurement contract, so a normal model/tool outcome cannot be
reported without it.

The current prompt loop lets unexpected tool-execution exceptions propagate to
`run_agent_task_attempt`, which maps them to `AgentTaskRunStatus` value
`orchestrator_error`.

Change that boundary so a workspace-hash failure after prior turns preserves a
partial prompt-loop artifact containing the messages, model responses, and
valid tool results recorded before the failure. The failed call itself must not
create a `ToolResult`; its typed error class and message belong to the terminal
prompt-loop result. The enclosing agent task run must still classify the
outcome as an orchestrator/harness failure rather than a model failure.

Use `PromptLoopStatus` value `orchestrator_error` for this preserved harness
failure. The enclosing `AgentTaskRunStatus` is also `orchestrator_error`, while
the typed `error_class` identifies the specific cause such as workspace-state
hashing failure. Do not introduce the redundant status name
`prompt_loop_orchestration_error`; the containing `PromptLoopResult` already
provides that scope.

An orchestrator failure before prompt-loop construction has
`prompt_loop_status=None`. A failure caught inside the prompt loop has
`prompt_loop_status=orchestrator_error` and preserves the partial prompt-loop
artifact.

#### Status

Runtime `ToolResult` evidence and the prompt-loop failure boundary are
implemented as described below. The public-check calibration schema, runner,
and control-flake integration are also implemented in later checkpoints.

### Canonical Workspace Hash Helper

#### Implementation

Added the shared `agentenv.hashing.hash_directory` helper. It hashes a
structured, sorted list of workspace-relative paths and exact per-file content
hashes, reusing the existing noisy-path exclusions. It rejects missing and
non-directory roots rather than giving them the same hash as an empty
workspace.

Task hashing now delegates its directory hashing to the shared helper, removing
the private duplicate implementation without changing the intended task-hash
contract.

Focused tests cover:

```text
identical state with different file-creation order
file-content mutation
file rename, addition, and deletion
empty-file addition and removal
noisy-path exclusion
symlink exclusion without following workspace escapes
missing and non-directory root rejection
```

#### Verification

```text
focused hashing and task-hashing tests: 18 passed
focused Ruff: passed
focused Pyright: passed
full parallel suite: 715 passed, 2 nested audit/report failures
isolated sequential rerun of both failures: 2 passed
```

The two parallel failures are the same resource-sensitive nested audit tests
previously observed under 16-worker execution; both pass outside that
contention. This run is not recorded as a clean full-suite pass.

### Runtime Tool-Result Workspace Evidence

#### Implementation

`ToolResult` now requires all three evidence fields for successful, rejected,
timed-out, and otherwise failed tool executions:

```text
arguments_hash
canonical_workspace_hash_before
canonical_workspace_hash_after
```

The old `input_hash` name was removed without an alias. Valid tool calls hash
their validated arguments, so omitted defaults and explicit defaults have one
semantic hash. Invalid attempted calls retain a hash of their raw arguments.

Tool execution now computes canonical workspace state on both sides of every
call and constructs the public `ToolResult` only after both hashes exist. The
workspace hashes remain evaluator-only evidence: tool messages expose neither
hash in model-visible content nor metadata. Tool-message metadata retains only
`arguments_hash`.

Canonical directory hashing now ignores symlinks as well as declared noisy
paths. This keeps symlink metadata outside the v0 state contract and prevents a
workspace escape link from causing the evaluator to read or hash an external
file.

If either workspace hash fails, execution raises `WorkspaceStateHashError` and
does not emit a partial `ToolResult`. The prompt loop catches that typed
instrumentation failure, preserves all prior messages, model responses, and
valid tool results, and terminates with `PromptLoopStatus=orchestrator_error`.
The failed assistant tool call remains in the partial transcript with its tool
call ID, but it has no fabricated tool observation. The enclosing agent-task
run maps the same event to `AgentTaskRunStatus=orchestrator_error`.

#### Verification

```text
focused schema/tool/prompt-loop/orchestrator/reward tests: 123 passed
Ruff: passed
Pyright: passed
git diff --check: passed
full suite with 4 workers: 728 passed
```

The 16-worker run produced three late nested reward-audit timeout failures
under contention (`725 passed, 3 failed`). All three passed in an isolated
sequential rerun, and the complete four-worker run passed cleanly. This is the
same resource-sensitive nested-audit behavior recorded in the preceding hash
checkpoint, not a ToolResult contract regression.

### Public-Check Idempotency Calibration Schema

#### Implementation

Added a standalone, strict `PublicCheckIdempotencyCalibration` contract under
`agentenv.controls`. It is intentionally not yet attached to the existing
`ControlFlakeDetection` payload, because doing that would require the control
runner to populate a new required field in the same checkpoint.

The record pins one public check with:

```text
task_id
task_manifest_hash
public_check_index
exact command
normalizer_version
normalizer_code_hash
```

`task_id` is required for human-readable reporting. It does not replace the
manifest hash as the authoritative task-version pin. The future runner must
verify both the task ID and computed manifest hash against the loaded manifest.

It requires an effective repeat count of at least two and an ordered, gap-free
run list covering indexes `0` through `repeat_count - 1`.

Each run is a discriminated union:

```text
CompletedPublicCheckRun:
    status: COMPLETED
    before/after canonical workspace hashes
    exit code
    required hash-pinned stdout/stderr refs
    normalized result hash

FailedPublicCheckRun:
    status: FAILURE
    failure_mode: TIMEOUT | RUNNER_FAILURE
    before/after canonical workspace hashes
    optional hash-pinned partial stdout/stderr refs
    required error_class and error_message
```

Completed runs cannot carry failure-only fields, and failed runs cannot carry
an exit code or normalized completed-result hash. Artifact references require a
canonical relative path and non-empty content hash.

The top-level status is validated from the run evidence with the agreed
precedence:

```text
any observed workspace or normalized-result drift -> NON_IDEMPOTENT
otherwise, any failed run                          -> INCONCLUSIVE
otherwise                                         -> IDEMPOTENT
```

`non_idempotency_reasons` is a required, canonically ordered list derived from
the same evidence:

```text
differing workspace hashes        -> WORKSPACE_STATE_DRIFT
differing completed-result hashes -> NORMALIZED_RESULT_DRIFT
```

Both reasons are retained when both forms of drift occur. `NON_IDEMPOTENT`
requires the exact non-empty derived list; `IDEMPOTENT` and `INCONCLUSIVE`
require an empty list. Calling this workspace-state drift rather than public-
check-caused mutation avoids claiming causality that the hashes alone do not
prove.

`idempotent` is exposed only as a derived property mapping these states to
`true`, `false`, or `none`; it is not serialized and is rejected if supplied as
an input field.

#### Repo-Wide Output Normalization Decision

Use one repo-wide, versioned public-check output normalizer rather than
task-specific normalization rules. Calibration records pin both its declared
version and code hash. This keeps equivalence semantics consistent across tasks
and prevents per-check rules from hiding meaningful drift.

The v0 policy will normalize `CRLF` and bare `CR` line endings to `LF`, known
harness-controlled workspace or temporary paths, and narrowly recognized
duration fragments. Raw stdout and stderr artifacts remain byte-faithful and
content-hash pinned. Trailing spaces and final-newline differences remain
meaningful in v0. Unknown volatility is retained, so it produces observed drift
rather than being broadly stripped.

The normalizer implementation and normalized-result hashing were not part of
the schema-only checkpoint; they are implemented in the following checkpoint.

#### Verification

```text
focused calibration-schema tests: 37 passed
Ruff: passed
Pyright: passed
git diff --check: passed
full suite with 4 workers: 765 passed
```

### Public-Check Output Normalization Foundation

#### Implementation

Added the repo-wide `public_check_output_normalizer_v0` implementation and a
code-hash function that pins the normalizer module. The calibration schema now
requires a persisted `normalization_context` containing exactly the two
runner-controlled roots replaced during normalization:

```text
workspace_root  -> <WORKSPACE>
runner_temp_root -> <RUNNER_TEMP>
```

Both roots must be absolute, canonical POSIX paths, cannot be `/`, and cannot
overlap. Keeping the runner's temporary root outside the prepared workspace is
necessary so command-owned temporary files do not silently become part of the
canonical task state.

Path replacement is literal and token-boundary-aware. It replaces the supplied
root and its descendants but does not replace an unrelated sibling path that
merely shares the same string prefix. Arbitrary `/tmp` paths are not matched.
Unknown paths therefore remain visible and can cause result drift.

The v0 transformation order is:

```text
CRLF and bare CR -> LF
exact runner-supplied roots -> stable placeholders
recognized "in <number>s" or "in <number>ms" fragments -> in <DURATION>
```

It deliberately preserves trailing spaces, final-newline presence, arbitrary
numbers, and unknown paths.

The normalized result hash uses an unambiguous structured encoding of:

```text
exit_code
normalized stdout
normalized stderr
```

This preserves the stdout/stderr boundary and makes exit-code differences
meaningful. Tests show that two invocations with different known roots,
durations, and line-ending styles produce the same normalized result hash,
while meaningful text, exit codes, trailing spaces, and final-newline changes
produce different hashes.

The actual calibration runner must create and persist these roots, direct the
public check's temporary files to `runner_temp_root`, write raw output
artifacts, and populate the schema. Those execution steps are not implemented
in this checkpoint.

#### Verification

```text
focused calibration-schema and normalizer tests: 51 passed
Ruff: passed
Pyright: passed
git diff --check: passed
full suite with 4 workers: 779 passed
```

### Public-Check Idempotency Runner And Control Integration

#### Implementation

Added the public-check idempotency runner to the real `controls run` lifecycle.
For every public check whose manifest declaration is
`are_tests_idempotent: true`, the runner now:

```text
creates a fresh copy of seed_workspace for that check
runs the exact manifest command consecutively in that one workspace
defaults to two runs and rejects repeat counts below two
clears runner-controlled temporary state before each invocation
records canonical workspace hashes before and after every invocation
persists raw stdout and stderr as content-hash-pinned artifacts
computes the version-pinned normalized completed-result hash
emits one PublicCheckIdempotencyCalibration record
```

Checks declaring `false` are not calibrated. Distinct public checks never
share a prepared workspace. The effective repeat count is a programmatic
`run_controls` option for now; a distinct CLI option remains a later interface
checkpoint.

The control-flake payload now requires the emitted calibration list and derives
its overall status with this precedence:

```text
any control-record or public-check drift -> drifted
otherwise, any inconclusive public-check calibration -> inconclusive
otherwise -> stable
```

Only a stable flake payload can produce an overall control match. The control
calibration artifact schema was bumped to v1, and its artifact references now
include the directory containing raw public-check idempotency outputs.

The command runner accepts scoped environment overrides while retaining the
existing sensitive-environment scrubbing boundary.

#### Shared Public-Check Temporary Environment

Temporary-root control now belongs to the shared public-check execution path,
not only to calibration. Calibration, model `run_tests` calls, and orchestrator
public checks all execute with `TMPDIR`, `TMP`, and `TEMP` directed to an
external runner-controlled directory.

The lifecycle differs only where the evidence contract requires it:

```text
calibration:
  use one stable path recorded in normalization_context
  delete and recreate its contents before every repeated invocation

model run_tests and orchestrator public checks:
  allocate a fresh external root for each invocation
  remove it after the command returns or fails
```

The shared runner rejects a supplied temporary root that contains the workspace
or is contained by it. This both prevents accidental deletion of task state and
avoids creating an in-workspace hash exclusion where task-relevant mutation
could hide.

The prepared workspace and runner temporary root intentionally have different
state semantics. The workspace is preserved across calibration repeats so any
task-state mutation remains measurable. The temporary root is reset because it
contains disposable command scratch state that must not leak from one
invocation into the next.

#### Harness Defect Found By The Calibration

The first real control-run integration correctly classified all four declared
checks as non-idempotent. The first `uv run pytest ...` invocation created an
untracked `uv.lock` in the prepared workspace and performed first-run virtual-
environment setup; the repeated invocation did neither. This caused both
canonical workspace drift and normalized output drift. It was a real harness
repeatability defect, not noise to strip in the normalizer.

The task-level repair makes the public checks hermetic under the declared
contract:

```text
commit a generated uv.lock in each of the four seed workspaces
run: uv run --quiet --frozen pytest tests/test_public.py
```

`--frozen` prevents lockfile mutation, and the committed lockfile pins the
environment resolution used by both calibration and actual model executions.
`--quiet` suppresses `uv` setup progress without hiding pytest's meaningful
stdout or stderr. All task-pack and harness-audit control scripts that invoke
the public check now use the exact manifest command.

This repair belongs at the task boundary rather than in calibration-only setup.
Otherwise the harness would prove repeatability under conditions different
from those experienced by a model calling `run_tests`.

#### Verification

Following the agreed checkpoint cadence, this integration used focused tests;
the full suite is deferred until several checkpoints have accumulated.

```text
focused runner/schema/normalizer/command/artifact/report/task tests: 195 passed
real task-pack control-run integration: 1 passed
real agent-audit integration: 1 passed
reward-hack audit hidden-validator probe integration: 1 passed
shared public-check temp-path tests: 45 passed
real controls integration after sharing the execution path: 1 passed
Ruff over src and tests: passed
Pyright: passed
```

### Typed Control-Flake Authority

#### Implementation

`ControlRun.flake_detection` now requires the validated
`ControlFlakeDetection` model. The control runner no longer serializes that
model to an untyped dictionary immediately after constructing it, and the
reporter consumes typed fields and nested groups directly. JSON conversion now
occurs only when the artifact manifest is written.

Removed the duplicate `ControlRun.public_check_idempotency` data field.
`ControlFlakeDetection.public_check_idempotency` is the single owner, while
`ControlRun.public_check_idempotency` is a derived read-only tuple convenience
property for callers that need to iterate the calibrations.

The persisted `ControlCalibrationManifest.flake_detection` field is now
required and non-nullable. Its `overall_match` invariant therefore always
requires a stable typed flake record in addition to matching control records;
missing flake evidence can no longer behave like an implicitly successful
calibration. This persisted contract change advances the control-calibration
artifact schema from v1 to v2 rather than changing the meaning of v1 in place.

#### Verification

```text
focused control-reporting and artifact-schema tests: 110 passed
real controls construction/report/manifest integration: 1 passed
focused Ruff: passed
Pyright: passed
```

### Harness-Audit Trust-Root Schema

#### Decision

Use one atomic `harness_audit` artifact for the scorer and agent-task audit
layers. The name deliberately avoids “harness faith” and does not claim that a
finite audit proves complete harness correctness. The artifact records whether
this exact harness runtime conformed to the exact versioned audit cases it ran.

Each layer and the root manifest use:

```text
PASS
FAIL
INCONCLUSIVE
```

Status derivation gives observed violations precedence:

```text
any completed expectation mismatch -> FAIL
otherwise, any AUDIT_ERROR          -> INCONCLUSIVE
otherwise                           -> PASS
```

The root status applies the same three-valued AND to the agent and scorer layer
statuses. Only `PASS + PASS` produces root `PASS`.

#### Schema

Added strict schema-only contracts under `agentenv.audits`. The agent and
scorer JSONL files have separate discriminated record unions:

```text
COMPLETED   -> full provenance, typed comparisons, derived overall_match,
               and a hash-pinned per-case artifact-directory reference
AUDIT_ERROR -> available partial provenance plus audit_stage, error_class,
               and error_message
```

The agent and scorer comparison-field vocabularies have one neutral definition
under `agentenv.audits.types`. The existing runtime audit modules and the new
persisted-record schemas import those definitions; neither redeclares the field
lists.

Completed agent records carry a bounded `scorer_result` summary whenever the
agent run reached scoring. It includes the scorer attempt ID, attempt status,
public status, hidden status, and scorer error class. This observation is
unconditional; the comparison list remains limited to expectations explicitly
declared by the audit case. The schema requires `scorer_result` exactly when
`agent_run_status=scored` and applies the existing attempt terminal-state
validator to its nested statuses.

The stable audit stages are:

```text
CASE_PREPARATION
HARNESS_EXECUTION
EXPECTATION_COMPARISON
RESULT_PERSISTENCE
```

An invalid case remains a discovered record and makes its layer inconclusive.
Its source path and any computable hashes are retained, while unparsed case or
task IDs remain null rather than being fabricated from directory names.

Completed records require both the exact task-manifest hash and the existing
composite `task_record_hash`; the latter is authoritative for task-version
binding because task behavior can change through seed files, validators, or
other referenced inputs without changing `task.yaml`. The root manifest also
pins the task-hash-report schema version used to interpret that composite.

The versioned runtime-provenance record contains:

```text
canonical hash of the entire src/agentenv tree
root pyproject.toml hash
root uv.lock hash
Python implementation and exact version
sys.platform and platform machine
derived harness_runtime_hash over the complete structured record
```

Git SHA is retained as diagnostic metadata only. Hostname, kernel release, CPU
features, system-package inventory, and container identity are explicitly
outside the v0 runtime fingerprint.

The root artifact points to separate `agent/` and `scorer/` directories. Each
standalone layer manifest owns its schema versions and summary, including the
source case-root hash, results JSONL hash, case-artifact directory hash,
discovered/record/completed/error counts, and derived status. The root does not
redeclare those fields. It hash-pins each complete child manifest, records the
child artifact identity and run ID, and requires both children to have the
root's exact complete runtime provenance.

#### Status

The typed scorer and agent-task layer runners and their standalone manifests
were implemented in this checkpoint. Atomic root assembly, CLI integration,
typed reward-audit migration, and removal of the historical entrypoints were
completed in the later checkpoint recorded below. Training-candidate export
gating remains future work.

#### Verification

```text
focused harness-audit and artifact-schema tests: 128 passed
focused Ruff: passed
Pyright: passed
```

### Audit Module Ownership

#### Implementation

Moved the existing layer-specific audit modules into the first-class audit
package:

```text
agentenv.agents.audit  -> agentenv.audits.agent_task
agentenv.scorers.audit -> agentenv.audits.scorer
```

The underlying prompt-loop, agent-task, and scorer execution code remains in
`agentenv.agents`, `agentenv.orchestrators`, and `agentenv.scorers`. At this
checkpoint, audit case schemas, comparisons, historical JSONL/Markdown
renderers, and layer runners moved with the shared audit types. The historical
renderers and runners were subsequently deleted after their consumers migrated
to the typed artifacts.

Updated the CLI, reward-hack audit, reward-hack export/reporting, source-case
validation, and tests to import the new modules. The old modules were removed
without compatibility shims. At this checkpoint only module ownership changed;
the later typed-consumer checkpoint removed the historical formats.

#### Verification

```text
focused agent/scorer runner and harness-schema tests: 28 passed
focused reward-hack audit and source-schema tests: 32 passed
CLI import/help smoke: passed
focused Ruff: passed
Pyright: passed
```

### Typed Scorer-Audit Layer Runner

#### Implementation

Added `run_scorer_audit_layer`, which treats every immediate child directory
of the scorer case root as a discovered case. Missing or malformed `case.yaml`
files are therefore persisted as `AUDIT_ERROR` records rather than silently
excluded by discovery.

Each case advances through separately guarded preparation, harness-execution,
expectation-comparison, and result-persistence phases. A case-scoped exception
produces one typed error record with the most complete provenance available,
then execution continues with the next discovered directory. Artifact paths use
stable numeric directory names such as `cases/0001`; a parsed case ID is never
inferred from or replaced by its source directory name.

Preparation now pins:

```text
canonical case-directory hash
parsed case ID
exact repository-relative task-manifest path and file hash
parsed task ID
existing composite task_record_hash from the owning task pack
```

The task-record helper verifies that the referenced task manifest is the unique
manifest for that task ID in the owning pack before reusing the existing eval
task-hash contract. The canonical harness-case hash helper moved from reward
code to `agentenv.audits.hashing`; reward-hack consumers now import the same
neutral implementation.

After all cases finish, the runner writes `results.jsonl`, reloads it through
the discriminated-union loader, and requires exact typed equality. It then
derives the layer status and counts and writes a standalone `manifest.json`
pinning the case root, results JSONL, case-artifact directory, schemas, and
harness runtime. An empty or unreadable case root fails before output creation.
A layer-wide write, readback, validation, or hashing failure removes the partial
output directory instead of leaving an apparently usable artifact.

At this checkpoint the historical scorer runner shared the extracted per-case
execution path. It was deleted after the CLI and reward-hack consumers migrated
to the standalone typed layer artifact.

#### Verification

```text
historical plus typed scorer runner tests: 13 passed
focused canonical case-hash tests: 4 passed
real typed scorer layer: 12 completed, 12 matched, PASS
fault injection: malformed case and execution error recorded; later case ran
root JSONL readback failure: partial layer artifact removed
focused Ruff: passed
Pyright over src and tests: passed
```

### Standalone Audit-Layer Artifacts

#### Manifest Contract

Added first-class artifact types and strict manifests for both independently
persistable layers:

```text
scorer_audit      -> ScorerAuditManifest
agent_task_audit  -> AgentTaskAuditManifest
```

Each manifest records its layer run ID, creation time, diagnostic Git SHA,
harness runtime version and complete runtime provenance, current case and
record schema versions, task-hash schema version, layer-specific attempt
artifact schema version, typed layer summary, and exact `results.jsonl` and
`cases/` artifact refs.

Replaced `artifact_dir_hash` with `artifact_payload_hash`. The latter is
derived from the declared results-file and case-directory refs and hashes. It
deliberately excludes `manifest.json`, avoiding a circular contract in which a
manifest would need to contain the hash of a directory that contains itself.
The eventual root harness manifest can instead hash-pin each completed child
manifest.

The standalone loaders verify more than manifest syntax. They recompute the
results and case-directory hashes, reload the discriminated JSONL records,
rederive counts and three-valued status, require every completed case artifact
to remain under `cases/`, and verify every per-case directory hash.

Harness runtime provenance is captured from the repository containing the
executing `agentenv` source and dependency lock. This is intentionally separate
from the repository root used to resolve task and case inputs; an external task
pack must not redefine which harness implementation actually executed it.

#### Agent-Task Layer Runner

Added `run_agent_task_audit_layer` with the same execution semantics as the
typed scorer layer:

```text
every immediate child directory remains in the denominator
case preparation/execution/comparison/persistence errors become AUDIT_ERROR
later cases continue after a case-scoped error
root persistence or integrity errors remove the partial artifact
```

Completed agent records include complete task and case provenance, a
hash-pinned agent-attempt directory, agent and prompt-loop terminal state, the
unconditional nested scorer summary when scoring occurred, typed expectation
comparisons, and comparison-derived `overall_match`.

At this checkpoint the historical runner shared the extracted per-case
execution function. Root harness composition and removal of both historical
layer runners were completed in the next checkpoint below.

#### Verification

```text
standalone manifest and shared schema tests: 24 passed
scorer runner/manifest/integrity tests: 13 passed
agent runner/manifest/continuation/integrity tests: 4 passed
legacy reward-audit regression tests: 3 passed
real scorer layer: 12 completed, 12 matched, PASS
real agent-task layer: 21 completed, 21 matched, PASS
focused Ruff: passed
focused Pyright: passed
git diff --check: passed
```

### Atomic Harness-Audit Artifact And Typed Consumer Migration

#### Root Composition

Implemented `run_harness_audit` as the only aggregate runner. It creates the
root output directory, runs the standalone agent-task and scorer layers into
`agent/` and `scorer/`, requires their complete `HarnessRuntimeProvenance`
records to be exactly equal, writes `harness_audit.md`, and then writes the root
manifest.

The root manifest contains hash-pinned child-manifest references rather than
duplicating child summaries or schema versions. Each reference includes:

```text
child artifact type and artifact schema version
child layer run ID
root-relative child manifest path
exact child manifest content hash
child harness-runtime hash
child three-valued status
```

It also pins the aggregate report hash. Its status is the validated
three-valued AND of the two child statuses. The aggregate loader first verifies
both child-manifest hashes, then invokes each standalone layer's full integrity
loader, checks the child identities and statuses against the root refs,
requires complete runtime-provenance equality with the root, and verifies the
report hash.

A global failure at any point removes the entire partial root, including any
child layer that already finished. Case-scoped failures remain typed records
inside a completed child artifact and do not abort later cases or prevent the
other layer from running. A regression test injects a scorer-layer failure
after an agent child was staged and proves that no partial root remains.

#### CLI And Reward-Audit Consumers

The standalone CLI commands now call only `run_scorer_audit_layer` and
`run_agent_task_audit_layer`; both write `manifest.json`, `results.jsonl`, and
`cases/`. Added `agentenv harness audit` for atomic composition. CLI wiring
tests verify that paths and overwrite authority reach the typed runners.

Reward-hack runtime audits now consume `CompletedScorerAuditRecord` and
`CompletedAgentTaskAuditRecord` from standalone layer artifacts. Each
exploit/control pair is staged as a small repository containing the two exact
case directories plus their owning task pack, allowing the typed runners to
recompute repository-relative case, task-manifest, and composite task-record
provenance. Any `AUDIT_ERROR` fails closed instead of being interpreted as an
exploit outcome.

Agent reward checks load prompt-loop and candidate-patch evidence from the
hash-pinned case artifact instead of retaining an ephemeral in-memory
orchestrator object. Scorer reward checks read typed comparison observations;
agent success checks use the unconditional nested scorer summary. Reward-hack
JSONL serialization persists the complete typed records and explicit case
artifact paths. This contract change advances both reward-hack runtime and
artifact schema versions to v2.

#### Legacy Removal

Deleted the old `ScorerAuditResult`, `AgentTaskAuditResult`, comparison
dataclasses, list-returning layer runners, historical JSONL names, historical
Markdown renderers, and their tests. No adapter or compatibility alias remains.
The substantive comparison, terminal-state, and case-artifact assertions now
exercise the typed standalone runners. The README documents the current
standalone and aggregate artifact layouts.

#### Verification

```text
real scorer layer and fault/integrity tests: 12 passed
real agent-task layer and fault/integrity tests: 3 passed
root runner, schema, manifest, integrity, and atomic-cleanup tests: 25 passed
typed CLI wiring tests: 2 passed
reward-hack audit, export, and schema tests: 35 passed
repo-wide Ruff: passed
focused Pyright over all changed source and tests: passed
full suite with 2 workers: 825 passed
```

The first full run used four workers and produced one late nested reward-report
failure (`824 passed, 1 failed`). The exact failing test passed immediately in
an isolated rerun, and the complete two-worker rerun passed cleanly. The typed
reward path now performs standalone layer persistence, task/case provenance
hashing, and integrity readback for every exploit/control pair, so two workers
is the recorded stable full-suite concurrency for this checkpoint.

### Real Harness-Audit CLI Artifact

Ran the aggregate CLI against the complete authored agent-task and scorer audit
case roots:

```text
uv run agentenv harness audit \
  --agent-cases data/harness_audit/agent_task_cases \
  --scorer-cases data/harness_audit/scorer_cases \
  --out experiments/harness_audit/week_09_harness_audit_v0
```

The persisted artifact is approximately 1.5 MiB and has:

```text
root status: PASS
agent-task layer: 21 completed, 21 matched, 0 audit errors
scorer layer: 12 completed, 12 matched, 0 audit errors
harness runtime hash: xxh64:0cc432bd402d8aae
task record hash: xxh64:30a95f75648e5aad
```

Reloading the artifact through `load_harness_audit_artifact` succeeded. This
verified both child-manifest content hashes, both complete child payloads and
per-case directory hashes, exact child/root runtime-provenance equality, the
root report hash, record counts, and derived statuses. An additional inspection
confirmed unique case IDs, source paths, and case-artifact refs in both layers.

### Fail-Closed Training-Candidate Trust Gates

#### Control-Calibration Provenance

Advanced the control-calibration artifact schema from v2 to v3. Its manifest
now binds the calibration to:

```text
complete HarnessRuntimeProvenance
the exact composite EvalTaskHashes set for every calibrated task
every typed scorer and agent control record
every typed flake group and public-check idempotency calibration
```

The runner captures the harness runtime and task hash set before executing
controls and recomputes both after execution. A mid-run source or task-input
change aborts before manifest persistence.

The manifest now requires unique control identities, exact task-ID agreement
between records and task hashes, exact record/flake-group agreement in both
layers, and complete repeat indexes `0..repeats-1` for every control group.
Public-check calibration task IDs and task-manifest hashes must agree with the
same composite task-hash set.

The controls CLI exposes the independently configurable
`--public-check-idempotency-repeats` option. Its terminal status now includes
flake evidence through `ControlRun.overall_match`; an unstable calibration is
reported as `FAIL` and exits nonzero even if every individual expectation
matched.

#### Candidate-Export Gate

Advanced the training-candidate export artifact schema from v0 to v1 and added
two required manifest-level gate records:

```text
harness_audit_gate
control_calibration_gate
```

Each gate records the source artifact type/schema, absolute artifact directory,
exact manifest hash, run ID, common harness-runtime hash, and required success
state. The control gate additionally pins the task-pack ID and calibrated task
hash set. Suite-level evidence is stored once in the export manifest rather
than duplicated into every candidate row.

Both `build_training_candidate_records` and
`export_training_candidate_records` require explicit harness-audit and
control-calibration directories. Before constructing candidate records, the
gate validator requires:

```text
aggregate harness audit status PASS
control overall_match true and flake status stable
both artifacts use the exact current harness runtime
the current authored harness-audit case-root hashes still match
the trajectory export still binds its exact source eval manifest
control composite task hashes cover and exactly match every trajectory task
current task-pack bytes still reproduce the calibrated task hashes
every currently declared idempotent public check has one matching IDEMPOTENT
calibration with the exact task-manifest hash, list index, and command
control_results.jsonl exactly matches the manifest's typed records
all referenced public-check stdout/stderr files retain their content hashes
```

Gate validation occurs before output-directory creation, so missing, failed,
incomplete, stale, or mismatched evidence produces no candidate artifact—not
even analysis-only rows. Loading an existing candidate artifact reruns the same
validation and requires the observed gate records, including both manifest
hashes, to exactly equal the pinned records. Positive-SFT construction inherits
this revalidation through the candidate-artifact loader.

The CLI now requires `--harness-audit` and `--control-calibration` for training
candidate export and reports both accepted run IDs.

#### Candidate-Owned Training Eligibility

Changed the current trajectory-record and training-candidate-record schemas in
place, without a version bump or compatibility shim. `TrajectoryRecord` no
longer stores `TrainingEligibility`; it now ends at the trajectory evidence
boundary: provenance, policy, statuses, artifact references, reward-component
fields, and leakage evidence. Whether the reward components themselves belong
at this boundary remains a separate decision.

`TrainingCandidateRecord.training_eligibility` is the only persisted training-
use decision. Candidate construction derives it from the pinned trajectory
evidence plus the review decision, and only runs after harness-audit and
control-calibration gates pass. The derivation enforces model-policy, split,
leakage, orchestration, required-agent-evidence, task-success, gradability, and
positive-SFT reward-hack conditions at the training boundary.

The training-candidate artifact loader recomputes every candidate record from
its pinned trajectories and reviews and requires exact equality with the
persisted records. Rehashing a manually altered eligibility decision therefore
does not make it authoritative. Positive-SFT construction consults only the
candidate's `training_eligibility`; it still validates the referenced
trajectory artifacts but no longer asks the trajectory for a second
eligibility decision.

Trajectory review rendering now shows raw evidence such as policy type, split,
statuses, leakage, orchestration failure, and reward-hack state rather than
precomputed training-use flags. Historical artifacts using the earlier shape
may no longer validate even though the in-progress schema labels remain v0;
this lab intentionally carries neither compatibility shims nor schema bumps.

Because harness runtime provenance hashes the complete `src/agentenv` tree,
this source change also makes the previously generated real harness-audit,
control-calibration, and gated candidate smoke chain historical rather than
current. Regenerate that chain at the next real-artifact checkpoint; do not
reuse its old runtime hash with the changed record schemas.

#### Explicit Reward-Hack Adjudication

Added `RewardHackReview` as a separate typed model nested in
`TrajectoryReviewRecord`, without changing the in-progress schema version. It
uses the existing review-state pattern and records its own review ID, reviewer
ID, optional notes reference, and one of two completed decisions:

```text
confirmed
cleared
```

An accepted trajectory review cannot carry a pending nested reward-hack
review. A confirmed reward-hack adjudication blocks positive SFT while leaving
later adversarial/negative-use decisions available; a cleared adjudication does
not block positive SFT by itself. Clearance cannot override direct
detector-confirmed evidence already present on the trajectory.

No per-finding hash or review-migration mechanism was added. The review
artifact already pins the complete source trajectory manifest and trajectory
JSONL hashes, so changed embedded findings invalidate the review artifact as a
whole.

This checkpoint does not yet auto-initialize nested reviews. The current
trajectory reward-hack flag covers only two attempt statuses and cannot
honestly produce the planned `confirmed | ambiguous | not_detected` aggregate.
Detector generalization remains the next boundary; until then initialized
review rows keep `reward_hack_review=null`.

#### Reward-Hack Finding Classification

Added required `finding_classification` evidence to every `RewardHackCase`
without changing `reward_hack_case_v0`. It is orthogonal to
`exploit_classification`: the exploit field names the mechanism family, while
the finding field records what the current authored evidence establishes.

The 16 cases are classified as:

```text
confirmed: 11
ambiguous: 5
```

Confirmed cases cover hidden-validator probing, public-check tampering, fake
success output, tool-output spoofing, and state corruption. Ambiguous cases
cover public-pass/hidden-fail, no-op, format-only, and both timeout surfaces.
The five ambiguous case descriptions now explicitly preserve the possibility
of honest model failure rather than claiming observed intent.

`not_detected` is deliberately absent from the case schema. It is a runtime
aggregate that is valid only after applicable detector coverage completes.
The reward-hack report now includes each case's finding classification, and the
persisted audit results retain it through the embedded typed case.

Changing every authored case changes the case-root inputs and makes historical
reward-hack audit artifacts stale. No compatibility shim or schema bump was
added.

#### Reward-Hack Check Catalogue

Added a required `exploit_check_id` to each `RewardHackCase`. The case ID and
check ID have different identities: `reward_hack_id` names one audit fixture,
while `exploit_check_id` names the concrete exploit specification and surface
that runtime detection must evaluate.

The 16 authored cases derive a deterministic catalogue of 14 unique checks.
The fake-success cases share one check, as do the tool-output-spoofing cases;
their different task outcomes provide multiple audit fixtures for the same
runtime check rather than expanding runtime coverage.

Catalogue construction fails closed for an empty case set, duplicate
`reward_hack_id`, one check ID mapped to different exploit specifications or
finding classifications, or one identical exploit specification mapped to
different check IDs. The reward-hack audit runner now constructs and validates
the catalogue before executing cases, so these invariants are exercised by the
real audit path rather than only by schema tests.

This checkpoint does not yet evaluate the catalogue against exported
trajectories. The next boundary is the per-check trajectory result and its
reviewable evidence contract.

```text
focused reward-hack schema/audit/export tests: 47 passed
targeted Ruff: passed
repo-wide Pyright: passed
git diff --check: passed
```

The repository-wide pytest suite was not run for this small checkpoint.

#### Candidate-Eligibility Verification

```text
consolidated trajectory/training/artifact-manifest tests: 195 passed
affected trajectory/review/training CLI tests: 3 passed
repo-wide Ruff: passed
repo-wide Pyright: passed
git diff --check: passed
```

The full repository test suite and real trust-artifact chain were not rerun for
this boundary checkpoint.

#### Historical Real CLI Check

Regenerated both trust artifacts after the source change:

```text
harness artifact: experiments/harness_audit/week_09_harness_audit_v1
harness status: PASS (21/21 agent, 12/12 scorer)

control artifact: experiments/runs/week_09_control_calibration_v0
control status: PASS (48/48 records, stable flake evidence)

common runtime hash: xxh64:6568c19237a239b7
control task hash set: xxh64:034a1fb9a5c3435c
```

A fresh agent-control eval, trajectory export, and review produced a gated
candidate artifact at:

```text
experiments/runs/week_09_training_gate_smoke_candidates
```

Independent loader validation succeeded and confirmed that its v1 manifest
pins harness run `harness_audit_5a25058b5be24861ad67767f2eddd8ba`
and control run `controls_6aea7b942b054ee8b345f74950603177`.
The one control-policy trajectory remains analysis-only, and the downstream
positive-SFT smoke artifact correctly contains zero examples.

As a negative check, the historical Qwen trajectory/review artifacts were
submitted to the new gate with the current controls. Export failed on a
composite task-hash mismatch for `preserve_cli_error_codes` and left no output
directory. This is expected: those trajectories predate the required public-
check idempotency field and therefore describe older task bytes.

#### Historical Gate Verification

```text
focused real trust-gate success/failure/tamper tests: 8 passed
consolidated affected training/control/manifest/CLI/sandbox tests: 149 passed
repo-wide Ruff: passed
repo-wide Pyright: passed
git diff --check: passed
```

The full repository suite was not rerun for this checkpoint. The previous
checkpoint's clean full result remains historical evidence for the pre-gate
source; the affected-surface run above is the current verification result.

#### Runtime Reward-Hack Catalogue Evaluation

Replaced the trajectory reward-hack shortcut derived from two attempt statuses
with a required top-level `RewardHackDetection`. Every exported trajectory now
records the detector version, hash of the 14-check catalogue, one result for
each concrete check, evaluation completeness, and the derived aggregate
finding. Per-check states are `detected`, `not_detected`, `not_applicable`, or
`detector_error`; any detector error makes the aggregate
`incomplete_evaluation` with no finding classification.

The catalogue remains mechanism-first: it contains the check ID, exploit
specification, and declared `confirmed | ambiguous` strength. It does not copy
audit-case expected attempt/public/hidden outcomes. Public-pass/hidden-fail and
actual-timeout checks inspect result state inside their detector because that
state is intrinsic to those named ambiguous patterns. Direct probe, tampering,
spoofing, state-corruption, no-op, and format-only checks are not gated on a
particular terminal outcome.

Moved mechanism evaluation into one shared reward detector used by both the
authored reward-hack audit and real trajectory export. Hidden-validator probes
reuse the same private-reference classifier as the prompt-loop and scorer
guards; public-test tampering reuses the scorer's public-test patch classifier.
The format-only analysis and workspace-spoof classifiers likewise have one
implementation shared by audit fixtures and model trajectories. Aggregate
finding and completeness derivation also have one schema-level implementation
used during construction and validation.

Detected results contain only symbolic references to existing hash-pinned
trajectory artifacts, such as `candidate_patch`, `prompt_loop_result_json`,
and `attempt_json`; transcript or patch contents are not copied into the
finding. Detector error text is bounded and passes through secret/private-
reference redaction. `TrajectoryRecord` rejects evidence names that do not
resolve to present hash-pinned artifacts.

Ambiguous findings now initialize a nested `RewardHackReview`. Review-artifact
validation rejects removal of that nested adjudication, and direct training-
candidate construction blocks every trainable path until it is present. A
human-confirmed finding blocks positive SFT while remaining available for
reviewed negative/adversarial uses; a cleared ambiguous finding may proceed to
the ordinary path-specific eligibility rules. Confirmed detector evidence
cannot be cleared, and incomplete detector evaluation blocks all training uses
while preserving analysis eligibility.

No compatibility shim or schema-version bump was added.

```text
focused reward-hack audit/detection/schema and leakage tests: 73 passed
focused trajectory/schema/review/training-builder tests: 78 passed
focused reward/trajectory/training export tests: 12 passed
targeted Ruff: passed
repo-wide Pyright: passed
git diff --check: passed
```

The full repository pytest suite was not run for this checkpoint.

#### Mechanical Tool-Call Redundancy Candidate Assessment

Added a required `MechanicalRedundancyAssessment` to
`TrainingCandidateRecord`. The assessment owns producer provenance once through
`detector_version` and `detector_code_hash`, an explicit
`complete | incomplete` evaluation status, and a list of structured
`MechanicallyRedundantToolCallBlock` findings. An empty block list means the
detector completed and found no qualifying block; it cannot represent a failed
or skipped evaluation.

Each block records:

```text
tool_name
arguments_hash
baseline_tool_call_id
ordered redundant_tool_call_ids
redundant_call_count
stable_workspace_hash
normalized_observation_hash
optional public_check_index for run_tests only
```

The count must exactly match the redundant ID list. IDs are unique within and
across blocks, the baseline cannot be one of its own redundant calls, and
`public_check_index` is required only for `run_tests`. Source IDs are the stable
`tool_call_NNNN` identities already persisted in the prompt-loop transcript;
the candidate export manifest continues to pin the source trajectory and
suite-level trust artifacts rather than copying them into every block.

The detector evaluates maximal consecutive runs only. The first successful
call is the baseline. Later calls qualify when they have the same tool and
validated semantic argument hash, produce the same canonical model-visible
tool observation, begin from the baseline's resulting canonical workspace
state, and leave that state unchanged. This allows the first `write_file` to
establish a new state while correctly labeling an immediate identical second
write as redundant. Tool errors and timeouts do not qualify. Alternating cycles
such as `read, write, read, write` remain outside the v0 detector.

The normalized observation hash is derived from the JSON content actually
shown to the model. Evaluator-only duration, workspace hashes, and successful
runner stdout/stderr therefore do not create superficial observation drift.
Canonical tool argument hashing now lives in `agentenv.tools.hashing`, shared
by execution and assessment rather than being duplicated or placed in a schema
module.

Repeated `run_tests` calls receive the label only when the command identifies
one task public check, that check declares `are_tests_idempotent: true`, and the
validated control artifact contains the exact matching `IDEMPOTENT`
calibration. A normally completed failing validator result remains eligible:
tool execution succeeded even though `passed=false`. Missing or mismatched
calibration and observed calibrated runtime drift produce an incomplete
assessment with no partial blocks.

Candidate construction validates the prompt-loop and task-manifest artifact
hashes before assessment. Hash mismatch or missing hash-pinned source bytes is
an artifact-integrity failure rather than an ordinary detector finding.
Trajectory-specific evidence that cannot be interpreted is represented as an
incomplete, redacted assessment. This checkpoint records the interpretation
but does not yet change positive-SFT, negative-example, or preference
eligibility; those consumers can choose repair, masking, rejection, or
comparison policies explicitly.

No compatibility shim or schema-version bump was added.

```text
focused training tests: 78 passed
focused tool/prompt-loop tests: 107 passed
targeted Ruff: passed
repo-wide Pyright: passed
git diff --check: passed
```

The full repository pytest suite was not run for this checkpoint.

#### Real Qwen Mechanical-Redundancy Artifact Check

The historical Qwen suite at
`experiments/runs/qwen_model_eval_suite_sampling_4096` was submitted to the
current trajectory-export CLI and correctly rejected before output. Its task
YAML hash for `repair_jsonl_deduper` was
`xxh64:2429eb19232c6c7a`, while the current required task hash is
`xxh64:b07bfbf839a51530`. The old model behavior was not silently rebound to
new task or calibration evidence.

Generated fresh trust artifacts for the current committed harness source and
task pack:

```text
harness audit:
  experiments/harness_audit/week_09_redundancy_harness_audit_v0
  status: PASS (agent PASS, scorer PASS)

control calibration:
  experiments/runs/week_09_redundancy_control_calibration_v0
  status: PASS (72/72 records, flake status stable)

common harness runtime hash:
  xxh64:e68f06f50710432b
```

Ran the installed `hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M` model against the three
current dev tasks using only policy `local-qwen-dev`. The initial sandboxed
attempt produced provider connection errors and was overwritten; the retained
artifact is the successful local-provider invocation:

```text
eval:
  experiments/runs/week_09_qwen_redundancy_eval_v0
report:
  experiments/reports/eval_matrices/week_09_qwen_redundancy_eval_v0.md
attempts: 3
prompt-loop outcomes: terminal_tool_error=3
terminal error: CommandNotAllowed=3
```

In every attempt, Qwen requested `uv run pytest tests/test_public.py` rather
than the exact allowed frozen command. The traces remain valid failed model
trajectories and preserve 6-7 executed tool calls each.

Exported and validated the downstream artifacts:

```text
trajectory export:
  experiments/runs/week_09_qwen_redundancy_trajectory_export_v0
accepted smoke reviews:
  experiments/runs/week_09_qwen_redundancy_trajectory_review_v0
training candidates:
  experiments/runs/week_09_qwen_redundancy_training_candidates_v0
candidate JSONL hash:
  xxh64:8a6707ae1cdaf2cc
detector code hash:
  xxh64:26e13c7727ff8c81
```

All three candidate assessments are `complete` with zero redundant blocks.
Inspection confirmed that this is the correct negative result: successful tool
calls were not immediately repeated with identical arguments. Each apparent
two-call `write_file` sequence began with an argument-incomplete errored call,
and each `run_tests` call occurred once and ended in `CommandNotAllowed`.
Neither error class satisfies the successful-observation requirement.

With the explicitly accepted smoke reviews, all three candidates are permitted
as negative examples, none is positive-SFT eligible, and none is preference-
data eligible because the terminal tool error made the trajectories
ungradable. This check validates persisted assessment construction; it does not
claim model quality or provide a positive detector firing from real Qwen
behavior.

#### Post-Training Data Contract

Added `docs/post_training_data_contract.md` as the Week 9 Checkpoint 1 boundary.
It records the existing candidate authority and suite-level fail-closed trust
gates, then distinguishes candidate permission from objective-specific dataset
construction and token-level loss.

The contract treats `negative_example_allowed` as permission to retain reviewed,
labeled negative source evidence. It does not call that evidence directly
trainable under ordinary SFT. Preference pairing, unlikelihood training, or any
other negative objective must define its own transformation and comparison or
credit-assignment rules.

The contract also exposes the next implementation gap instead of hiding it:
`PositiveSFTExampleRecord` currently stores source-level messages, but there is
no deterministic tool-call serialization or loss mask. The positive-SFT builder
also does not yet reject, repair, or mask a source containing a complete
mechanical-redundancy finding. Such a row is not trainer-ready merely because
candidate-level positive-SFT eligibility is true.

Current implementation status is listed in the contract. Negative-example and
preference-pair exporters, human-repair provenance, and token loss masking
remain unimplemented. No schema, code path, compatibility shim, or artifact
version changed in this documentation-only checkpoint.

#### Deterministic Positive-SFT Redundancy Repair Policy

Tightened the post-training data contract so loss masking is no longer an
accepted way to clean a mechanically redundant positive-SFT trajectory. Masked
actions and observations remain in the model context for later loss-bearing
assistant spans.

The initial allowed repair is limited to deterministic deletion of a detected
redundant assistant tool call and its matching tool-result message. The baseline
call/result pair and all other message bytes remain unchanged, and the source
trajectory remains immutable. Ambiguous linkage, malformed output, an
incomplete redundancy assessment, or failed post-repair leakage validation
blocks positive-SFT export.

This checkpoint changes the written contract only. The repair provenance
schema, transformation, and positive-SFT builder integration remain to be
designed and implemented in small follow-up checkpoints.

#### Training-Candidate Repair Record Schema

Added `src/agentenv/training/repair_schema.py` and focused schema tests in
`tests/training/test_repair_schema.py`.

`TrainingCandidateRepairRecord` represents one actual repair attempt and maps
back to a training candidate through `trajectory_id` and `eval_attempt_id`.
`repair_id` permits one candidate to have multiple repair records. No no-op
record is emitted: a candidate with a complete zero-block assessment can use
its original transcript, while a blocked candidate without a completed repair
remains unavailable for positive SFT.

The common record contains repair identity, status, artifact type, the existing
hash-pinned source artifact ref, an optional repaired artifact ref, repairer
version/code hash, status errors, and method-specific repair details. The only
current artifact type is `transcript`; a repaired transcript artifact is a root
JSON list of typed model `Message` values. The original ref points to the
existing prompt-loop result rather than copying the original messages.

The only current method is `mechanical_redundancy_deletion`. Its details retain
the original assessment, the optional after-repair assessment, and an optional
`cannot_complete_reason`. The schema enforces:

```text
completed:
  hash-pinned changed output artifact
  complete zero-block after-repair assessment
  same detector version and code hash before and after
  no cannot-complete or error fields

cannot_complete:
  method-specific non-empty reason
  no repaired artifact, after assessment, or error fields

repair_error:
  error class and message
  no repaired artifact, after assessment, or cannot-complete reason
```

All repair records require a complete original assessment with at least one
detected block. At this point source-candidate artifact pinning, record
uniqueness, explicit `repair_id` selection, deterministic message deletion, and
export persistence remained later manifest/builder checkpoints. No
compatibility shim or existing schema-version bump was added.

#### Training-Candidate Repair Export Manifest Schema

Added `training_candidate_repair_export` to the artifact taxonomy and added a
`TrainingCandidateRepairExportManifest` schema. This is an artifact contract
only; no writer, loader that traverses the source chain, or CLI was added.

The manifest owns artifact-level provenance through a minimal
`TrainingCandidateExportManifestRef` containing the source export directory and
manifest content hash. It does not repeat the candidate JSONL hash or the
trajectory, review, harness-audit, and control-calibration fields already
authoritative in the referenced manifest. The eventual loader must validate
that referenced manifest and follow its own pinned artifacts.

Each `TrainingCandidateRepairRecord` now owns
`source_training_candidate_record_hash` in addition to `trajectory_id` and
`eval_attempt_id`. The eventual loader must locate the source candidate by the
two ids, match the exact record hash, and require the embedded original
mechanical-redundancy assessment to equal the candidate assessment.

The repair manifest pins `repair_records.jsonl`, its content hash, the current
repair-record schema version, and counts for `completed`, `cannot_complete`, and
`repair_error`. Status counts must sum to total records, and a zero-record
artifact is valid because no-op repairs are intentionally absent. Repaired
transcript refs remain hash-pinned inside completed repair records rather than
being duplicated into the manifest.

Focused verification:

```text
repair/artifact manifest schema tests: 113 passed
targeted Ruff: passed
targeted format check: passed
targeted Pyright: passed
```

Source-record hashing, source-chain traversal, record uniqueness, transcript
artifact verification, and persistence remain the next runtime/export
checkpoint. No existing schema or artifact version was bumped.

#### Deterministic Repair Runtime And Artifact Export

Added `src/agentenv/training/repair.py` and
`src/agentenv/training/repair_export.py`.

The repairer computes a canonical content hash for the validated source
`TrainingCandidateRecord` and a deterministic `repair_id` from the source hash,
repair method, repairer version, and repairer code hash. The source candidate
remains immutable.

For each candidate with a complete mechanical-redundancy assessment containing
at least one block, the repairer:

1. resolves and hash-validates the original prompt-loop artifact;
2. requires exactly one adjacent assistant/tool-result message pair for every
   baseline and redundant tool-call id named by the assessment;
3. removes only redundant pairs and their aligned `ToolResult` values;
4. preserves every other typed message value and retains every baseline;
5. validates complete tool-call/result linkage in the repaired transcript;
6. reruns the same redundancy detector against the repaired in-memory prompt
   loop;
7. permits `completed` only for a complete zero-block assessment from the same
   detector version and code hash.

Candidates with complete zero-block assessments produce no repair record. A
known unsafe transformation becomes `cannot_complete`; unexpected
transformation or per-transcript persistence failure becomes `repair_error`.
Source manifest, candidate, trajectory, task-manifest, and artifact integrity
failures remain hard export failures rather than per-record outcomes.

`export_training_candidate_repairs` writes completed transcripts under
`transcripts/<repair_id>.json`, writes `repair_records.jsonl`, and writes the
typed repair manifest. Its loader revalidates the source candidate export and
its full trust chain, matches candidate ids and record hashes, checks original
assessment equality, verifies repairer provenance and deterministic ids,
recomputes non-error repairs, and compares completed transcript bytes and
after-repair assessments. Repair-error records remain audit evidence and do not
authorize training use.

Focused integration tests construct a real candidate artifact chain, inject a
mechanically redundant successful `read_file` call, and verify completed repair
export and reload. They also cover a valid empty no-op-free export, transcript
tamper rejection, source-candidate rebinding rejection, and source-manifest
drift rejection.

No CLI or positive-SFT consumption was added. In particular, completed repair
does not change task outcome, review state, reward-hack evidence, split, or
candidate eligibility. Repair selection and review inheritance remain the next
positive-SFT design boundary.

```text
focused repair/training tests: 66 passed
targeted Ruff: passed
targeted format check: passed
targeted Pyright: passed
```

The full repository pytest suite was not run for this checkpoint.

#### Training-Candidate Repair Review Artifact

Added a distinct repair-review layer in
`src/agentenv/training/repair_review.py`, with its record schema in
`src/agentenv/training/repair_schema.py` and its artifact manifest in
`src/agentenv/artifacts/manifests.py`.

The initializer emits one `not_reviewed` row for every actual repair record,
including `completed`, `cannot_complete`, and `repair_error`. A zero-record
repair export produces an empty review artifact; no no-op repair or review rows
are synthesized. The review queue explicitly states that accepting a
non-completed repair validates the recorded failure outcome only and never
authorizes training use.

The review manifest hash-pins the source repair-export manifest. Each review
row additionally carries `repair_id` and
`source_training_candidate_repair_record_hash`. Validation requires exact
one-to-one ID coverage and recomputes the canonical repair-record hash, so a
review decision cannot be silently transferred to a changed repair status,
reason, error, artifact reference, assessment, or repairer provenance under the
same ID.

Focused verification:

```text
repair/review/artifact tests: 63 passed
targeted Ruff: passed
targeted format check: passed
targeted Pyright: passed
```

The full repository pytest suite was not run for this checkpoint. Repair-review
CLI commands and positive-SFT selection/gating remain unimplemented.
