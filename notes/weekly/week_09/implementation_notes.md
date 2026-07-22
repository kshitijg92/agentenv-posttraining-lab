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

### Overall Action Preference Rubric

Added the reusable v0 rubric at:

```text
configs/training/preference_rubrics/overall_action_preference_v0.md
```

The rubric covers only assistant actions observed in original rollouts. It
orders task solvability before efficiency and requires every `preferred`
decision to include an action-level explanation grounded in the exact shared
context. Downstream outcomes may support that explanation but cannot supply the
label by themselves.

The strict v0 policy returns `ambiguous` when both actions are flawed, even if
one looks less harmful. `tie` is reserved for confidently equivalent acceptable
actions, while `invalid` remains a broken-comparison state. Repaired, edited,
and synthetic alternatives are explicitly deferred.

Added a focused fixture that loads the repository rubric, computes its content
hash, constructs `PreferenceRubricProvenance`, and checks the settled semantic
invariants remain present.

Focused verification:

```text
candidate/preference/rubric regression slice: 73 passed
Ruff: passed
Pyright: passed
git diff --check: passed
```

### Training Package Workflow Refactor

Split the former flat `training/` package into ownership-aligned subsystems:

```text
candidates/    trajectory-review and harness/control gates, candidate records
repairs/       redundancy detection, deletion repair, repair export and review
positive_sft/  exact source selection, prefix review, example build and export
```

Removed the old top-level modules instead of leaving compatibility imports.
Candidate-pinned trajectory and review validation now lives in
`candidates/source_integrity.py`; positive-SFT original/repaired source selection
lives in `positive_sft/source_selection.py`. This also removes the prior
dependency from repair export code onto the positive-SFT builder. The CLI
objective group is now `training positive-sft` rather than the ambiguous
`training sft`.

Added `training/README.md` and `trajectories/README.md` with Mermaid workflow
diagrams and the evidence, repair, review, and export invariants. Focused
candidate/repair/positive-SFT/CLI tests pass (`176 passed`), repository-wide
Ruff passes, targeted Pyright reports zero errors, and `git diff --check`
passes.

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

#### Positive-SFT Repair Consumption

Extended the positive-SFT schema and artifact path to consume explicitly
selected deterministic repairs.

`PositiveSFTExampleRecord` now has discriminated `original` and `repaired`
source provenance. Both forms carry the exact source candidate hash and
hash-pinned transcript reference. Repaired rows additionally carry the selected
`repair_id`, canonical repair-record hash, canonical repair-review-record hash,
accepted repair-review id, and the narrow task-outcome inheritance basis. The
example id is content-derived from the selected source rather than from
`trajectory_id`, so multiple derivatives of one trajectory cannot share an
ambiguous identity.

The positive-SFT manifest records original/repaired counts. When repaired rows
exist it pins the repair-export manifest, repair-review manifest, and editable
repair-review JSONL snapshot. Unused repair sources are forbidden. The loader
now traverses all pinned sources and deterministically rebuilds the expected
rows instead of trusting only the output JSONL hash.

The builder accepts an explicit set of repair ids. Its policy is:

```text
complete assessment + zero blocks -> original transcript
complete assessment + blocks + no selection -> no positive-SFT row
explicit completed + accepted selection -> repaired transcript
explicit invalid selection -> hard error
```

Unknown ids, duplicate ids, multiple selections for one candidate,
non-completed repairs, unaccepted repair reviews, ineligible source candidates,
and source-artifact mismatches fail closed. An accepted `cannot_complete`
record remains unusable because review acceptance validates that failure record
but cannot satisfy the independent `completed` gate.

Only `mechanical_redundancy_deletion` currently inherits the trusted source
task outcome. The row states that its basis is state-and-observation-preserving
deletion. No general inheritance rule was added for future repair producers or
methods.

Focused verification:

```text
positive-SFT/repair/review focused tests: 110 passed
full repository pytest: 946 passed, 1 stale reporting assertion failed
corrected reporting assertion rerun: 1 passed
repository Ruff check: passed
repository Pyright: passed
targeted format check: passed
git diff --check: passed
```

The full suite's only failure expected the pre-classification reward-hack report
column order. The report correctly contained the newer `confirmed | ambiguous`
field, so the stale expected rows were updated and the failing test passed on a
targeted rerun. The entire 14-minute suite was not repeated. Repository-wide
format checking still identifies 22 unchanged files outside this checkpoint;
they were not reformatted. Repair/review and repair-selection CLI commands
remain a later artifact-usability checkpoint.

## 2026-07-12

### Acquisition Prompt And Model-Action Contract

Corrected the agent prompt's `run_tests` example so it uses the exact public
check command rather than a generic placeholder. The prompt now also states
that an action must be the JSON tool-call envelope itself, without Markdown
fences or a second copy of the tool name inside the arguments.

Added `agent_action_format: prompt_only | json_schema` to model configuration.
The OpenAI-compatible client sends a strict action response schema when
configured, and the Qwen Ollama acquisition configs use that mode. This
substantially reduced malformed action envelopes. The Qwen `/no_think` suffix
was used where supported so hidden reasoning did not consume the local
generation budget.

These interface changes were used to improve the rate of harness-clean,
gradable model trajectories. How prompt or action-interface provenance should
constrain future pairing remains an open design question.

### Eval Runtime Provenance

`EvalRunManifest` and `EvalSuiteManifest` now require complete
`HarnessRuntimeProvenance`. Eval orchestration captures it at run start and
refuses to finalize a manifest if harness source, dependencies, or interpreter
provenance changes before completion.

Training gates require the source eval runtime to exactly match the runtime
pinned by the current passing harness-audit and control-calibration artifacts.
This invalidated an early acquisition pilot whose run predated the final source
changes; it was discarded rather than reinterpreted under the new audit.

### Task Pack And Acquisition Runs

Added four dev tasks with public/hidden tests, oracle and known-bad patches, and
agent controls:

```text
repair_header_merge
repair_duration_parser
repair_record_chunking
repair_query_encoding
```

The task pack now contains one practice and seven dev tasks. Control
calibration passed all 48 task/control combinations at one repeat, and public
check idempotency calibration remained stable.

Added local acquisition configs for Qwen2.5-Coder 14B, 7B, and 3B and Qwen3 8B,
plus greedy retry and high-diversity sampling configs. Qwen3 structured
generation was too slow and sometimes ended with empty/max-token responses, so
its partial runs were stopped and excluded.

Final trust artifacts:

```text
experiments/runs/week09_dpo_harness_audit_v4
experiments/runs/week09_dpo_control_calibration_v3
```

Both pass and pin the post-revert harness runtime
`xxh64:2e228ddac2b3c29f`.

Historical candidate exports retained for acquisition-yield analysis:

```text
experiments/runs/week09_dpo_qwen2-5-coder-14b_candidates_v2
experiments/runs/week09_dpo_qwen2-5-coder-7b_candidates_v2
experiments/runs/week09_dpo_qwen2-5-coder-3b_candidates_v2
experiments/runs/week09_dpo_qwen2_5_coder_14b_retries_candidates_v2
experiments/runs/week09_dpo_high_diversity_rejected_yield_candidates_v2
```

All accepted source reviews use reviewer id
`codex_provisional_under_user_authorization`. That records the user's temporary
authorization to mark reviews accepted for artifact construction; it is not a
claim that every long transcript received human review.

These model evals, trajectories, reviews, and candidates were produced under
pre-revert runtime `xxh64:9292345e1dff4cad`. Removing the prematurely designed
preference subsystem correctly changed the whole-tree runtime hash. The
historical artifacts were not relabeled. They remain useful evidence about
acquisition yield and failure modes, but they do not satisfy the current-runtime
training gate. Fresh model evals are required after preference design is
settled and before constructing current candidate or pair artifacts.

### Acquisition Diversity Observation

An earlier pilot had eight distinct eval attempt ids but only one behavior
transcript. It was stopped and excluded from the candidate pool. The result
shows that additional attempt ids do not necessarily provide additional
behavioral coverage. The definition and enforcement of behavior-level
deduplication remain for the later preference design discussion.

### Verification Notes

The first repository run used `pytest -n auto` and produced subprocess-heavy
harness/reward audit failures under CPU contention. The same harness and reward
tests passed serially (`6 passed`), showing that those failures were test-runner
resource contention rather than audit mismatches. Stale eval-manifest fixtures
were updated for required runtime provenance, and task-pack assertions were
updated from four to eight tasks. Final verification results are recorded after
the concluding test pass.

#### Timeout Audit Flake Correction And Artifact Rebuild

The first serial full suite exposed that the `hidden_check_timeout` scorer
audit case used a one-second task timeout for both public and hidden phases.
Under sustained suite load, ordinary public pytest startup occasionally
exceeded one second, so the case produced a public timeout instead of reaching
the intentional hidden hang. This was a case-design flake: it tested whichever
phase happened to consume the tiny budget first.

Raised that case's timeout override to five seconds. The public tests now have
startup headroom while the deliberately non-terminating hidden behavior still
guarantees a hidden-phase timeout. The separate `public_check_timeout` case
retains its one-second override.

Because audit-case and runtime bytes are provenance, old trust pins were not
reused. After removing the premature preference subsystem, generated:

```text
experiments/runs/week09_dpo_harness_audit_v4
experiments/runs/week09_dpo_control_calibration_v3
```

The regenerated audit is aggregate/agent/scorer `PASS` and retains harness
runtime `xxh64:2e228ddac2b3c29f`. Control calibration has 48 matching records,
stable flake detection, and complete idempotency evidence for the expanded task
pack.

Final verification:

```text
post-revert manifest/model/eval/CLI regression set: 168 passed
post-revert training package: 150 passed
current harness audit: PASS (agent PASS, scorer PASS)
current controls: 48/48 matching, flake stable
repository Ruff: passed
repository Pyright: passed
git diff --check: passed
```

The full repository suite was not repeated after the scoped rollback. The
focused sets cover every mixed file changed by the removal and the complete
retained training package.

### Cadence-Neutral Acquisition Configuration

Renamed the eight acquisition eval configs and their internal `name` values so
reusable configuration does not encode the weekly learning cadence. Names now
describe the model, split, and acquisition strategy, for example:

```text
agent_model_dev_multi_policy_acquisition.yaml
qwen2_5_coder_14b_dev_repeated_sampling.yaml
qwen3_8b_dev_targeted.yaml
```

Historical experiment manifests retain their original config paths as honest
records of what executed. Added a root `AGENTS.md` rule allowing week/date
labels only in notes, documentation, and generated `experiments/` paths, not in
source, APIs, schemas, task ids, or reusable config filenames and names.

### Qwen3 Token-Budget Diagnostic

The initial Qwen3 acquisitions used `max_new_tokens: 4096`. The Qwen3 8B
targeted attempt reached that limit on its first turn and the provider returned
empty content. A later controlled 8192-token diagnostic did not repeat the
ceiling: it stopped normally after 76 completion tokens with valid structured
output. It nevertheless returned a final answer without editing the workspace
and scored `HIDDEN_TEST_FAIL`. More output budget removed the truncation symptom
but did not make the policy act on the task.

Qwen3 14B showed a different problem: provider timeouts, max-turn cycling, and
repeated short behaviors. Its recorded responses did not exhaust the 4096-token
limit, so increasing the per-turn budget is not the primary intervention for
that model.

### Acquisition Foundation Worktree Checkpoint

Continued autonomous foundation work in the isolated worktree:

```text
/home/kshitij/agentenv-posttraining-foundation-wt
branch: codex/acquisition-foundation
```

No commit was created.

### Positive-SFT Prefix Review And Message Identity

Added required globally unique occurrence ids to persisted messages. Runtime
creation assigns ids to system, user, assistant, and tool messages; provider
payload serialization excludes them. Prompt-loop, repaired-transcript, and
positive-SFT schemas reject duplicate ids, and deletion repair preserves ids
for retained messages.

Renamed candidate-level `TrainingEligibility` to
`TrainingCandidateEligibility`. Its fields now describe downstream candidate
paths rather than claiming that rows are already trainable:

```text
analysis_eligible
positive_sft_review_eligible
negative_example_eligible
preference_pairing_eligible
```

Related manifest counts no longer use `trainable`. Positive-SFT review
eligibility no longer requires task success or a scored terminal result. It
retains the model-policy, split, leakage, orchestration, required-evidence, and
reward-hack gates. This permits trustworthy failed trajectories to enter
prefix review while keeping harness failures blocked.

Added a standalone positive-SFT review artifact. Each record pins the exact
candidate hash and original or accepted repaired transcript, then records the
usual review authority plus `last_approved_assistant_message_id`. Accepted
reviews require that boundary to exist exactly once and identify an assistant
message. Rejected, pending, and follow-up reviews cannot authorize a boundary.

Positive-SFT export now requires this review artifact. It exports only accepted
records, truncates each transcript immediately after the approved assistant
message, preserves message ids, and pins both the review artifact and exact
review-record hash. Example identity includes the review-record hash so two
approved boundaries over the same source cannot collide. The export manifest
points to the positive-SFT review artifact as its direct source; candidate and
repair provenance remain reachable through that artifact rather than being
duplicated.

Focused verification on the source branch:

```text
message identity checkpoint: 131 passed
positive-SFT/candidate/repair/CLI focused set: 102 passed
expanded training/model/agent/security/reward set: 333 passed, 1 stale fixture
corrected repaired-transcript schema file: 31 passed
Ruff on changed source and tests: passed
Pyright on changed source and tests: passed
git diff --check: passed
```

### Current-Runtime Rescore, Clustering, Taxonomy, And Privacy Checkpoint

This checkpoint supersedes the replay counts and review-packet state in the
historical acquisition sections below.

Completed two fresh scorer executions for every scored trajectory in the
55-record compatible cohort. The rescorer now fails unless the current full
task-input hash set equals the source eval task hashes, in addition to the
existing harness-runtime, trajectory-export, and candidate-patch hash checks.

```text
52 source scored trajectories
104 fresh scorer executions
104/104 exact outcome matches
rescorer code hash: xxh64:8e74f5afbec83ae5

experiments/runs/model_diversity_near_solution_acquisition_final_runtime_patch_rescore_r3
experiments/runs/model_decoding_task_gap_acquisition_final_runtime_patch_rescore_r2
experiments/runs/qwen3_coder_30b_interval_probe_final_runtime_patch_rescore_r2
experiments/runs/qwen3_coder_30b_task_gap_acquisition_final_runtime_patch_rescore_r2
```

Added analysis-only behavior clustering. The 55 trajectories form 46 exact
assistant-action clusters; five clusters contain duplicates and nine rows are
duplicates beyond the cluster representatives. Tool observations are excluded
from the behavior hash and remain individually linked in review artifacts.

Added an analysis-only public-contract taxonomy for the four acquisition tasks.
It verifies source task hashes, validates every probe against the corresponding
oracle, uses no hidden-validator evidence, and labels its output as
`review_hypothesis`. All four oracles passed all probes; all 46 clusters received
a hypothesis record.

Added a content-level privacy scanner over semantic messages, typed tool-result
strings, and candidate patches. It verifies source manifests, exact cohort
coverage, task-manifest hashes, and artifact content hashes before scanning. It
stores only finding classes and hashes of matched values.

```text
status: NORMALIZATION_REQUIRED
55 trajectories scanned
50 trajectories with findings
64 ephemeral harness-path occurrences
1 user-host-path occurrence
0 configured sensitive-pattern matches
```

The path findings occur only in environment/tool observations. The generated
artifact explicitly states that a zero sensitive-pattern count is not proof of
arbitrary private-content absence.

Generated compact review cards that join the evidence, 46 behavior clusters,
public-contract hypotheses, privacy audit, unreviewed review rows, and all
hash-pinned artifact locators:

```text
experiments/analysis/current_runtime_behavior_clusters.json
experiments/analysis/current_runtime_contract_failure_taxonomy.json
experiments/analysis/current_runtime_privacy_audit.json
experiments/analysis/current_runtime_compact_review_cards.md
```

No preference schema, pair label, accepted review, training candidate, or DPO
export was added.

Verification for this checkpoint:

```text
full-cohort patch replay: 104/104 matched
empty-runtime cluster/privacy requests: failed closed without artifacts
focused model/config/provider/eval tests: 54 passed
repository and analysis-helper Ruff: passed
repository and analysis-helper Pyright: passed
git diff --check: passed
Ollama processes: 0
orphan AgentEnv attempt/probe processes: 0
all 55 source reviews: not_reviewed
```

### Deterministic Rescore, Task-Gap Acquisition, And Review Packet

Continued only in the isolated acquisition-foundation worktree. No commit was
created and no preference schema, pair builder, decision, or training export
was added.

The repository replay CLI re-executes scripted agent controls and requires an
`agent_control_script`. Real model trajectories intentionally have no such
artifact. Added the analysis-only scorer replay helper:

```text
experiments/analysis/rescore_model_patches.py
```

It joins the eval suite to its hash-pinned trajectory export, requires exact
source-runtime equality, verifies each live candidate-patch content hash, and
re-scores every scored patch twice in fresh workspaces. The then-authoritative
run, now superseded by the full-cohort checkpoint above, was:

```text
experiments/runs/model_diversity_near_solution_acquisition_final_runtime_patch_rescore_r2
```

Result: 44/44 re-scores matched the 22 source trajectories on status,
public/hidden outcome, error class, and final-diff hash. The earlier `r1`
artifact used an earlier helper that did not join through the trajectory export
and is superseded for trust purposes.

Added equal-budget decoding and acquisition configs:

```text
configs/decoding/greedy_8192.yaml
configs/eval/model_decoding_task_gap_acquisition.yaml
```

The matrix fixed three tasks, two model families, greedy/sampling decoding, and
two attempts per cell before execution: 24 attempts total. Greedy and sampling
both used 8192 maximum tokens and a 300-second provider timeout so decoding was
not confounded with response budget.

Artifact:

```text
experiments/runs/model_decoding_task_gap_acquisition_final_runtime
```

Outcome:

```text
24 attempts
23 scored
17 HIDDEN_TEST_FAIL
6 PUBLIC_TEST_FAIL
1 model_error
0 PASS
```

Devstral greedy produced duplicate interval patches and repeated no-ops on
retry/SemVer. The matrix was retained in full; no outcome-dependent early stop
or filtering occurred.

Because fewer than two of the three target tasks gained a passing endpoint,
the predeclared additional-model probe triggered. Added:

```text
configs/models/ollama_qwen3_coder_30b.yaml
configs/eval/qwen3_coder_30b_interval_probe.yaml
configs/eval/qwen3_coder_30b_task_gap_acquisition.yaml
```

The exact provider identity is:

```text
qwen3-coder:30b-a3b-q4_K_M
sha256:06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca
Ollama 0.30.11
```

The official Ollama catalogue describes this as an Apache-2.0 30.5B MoE code
model with 3.3B active parameters. Its 18.5 GB local artifact partially
offloaded on the 16 GB GPU but remained practical for a bounded probe.

The one-task probe reached scoring with a substantive nonempty interval patch,
so the predeclared branch expanded to two sampling attempts on each of interval,
retry, and SemVer. Acquisition then stopped regardless of outcome.

```text
probe:     1 HIDDEN_TEST_FAIL
expansion: 6 HIDDEN_TEST_FAIL
public checks: 7/7 PASS
nonempty patches: 6/7
```

Exports and initialized unreviewed review artifacts:

```text
experiments/runs/model_decoding_task_gap_acquisition_final_runtime_trajectories
experiments/runs/model_decoding_task_gap_acquisition_final_runtime_reviews_unreviewed
experiments/runs/qwen3_coder_30b_interval_probe_final_runtime_trajectories
experiments/runs/qwen3_coder_30b_interval_probe_final_runtime_reviews_unreviewed
experiments/runs/qwen3_coder_30b_task_gap_acquisition_final_runtime_trajectories
experiments/runs/qwen3_coder_30b_task_gap_acquisition_final_runtime_reviews_unreviewed
```

Strengthened `acquisition_evidence_audit.py` during self-review:

- every live transcript, model-provenance, and patch file must match its
  trajectory content hash before analysis;
- source export, calibration, and generator hashes are recorded;
- duplicate trajectory ids are rejected;
- missing patch/status values are explicit;
- runtime cohorts remain separate;
- `PASS`-versus-non-`PASS` counts are separate from generic cross-status counts.

Final compatible cohort under runtime `xxh64:48587f8f45327ef3`:

```text
55 records
52 scored
2 PASS
40 HIDDEN_TEST_FAIL
10 PUBLIC_TEST_FAIL
3 unscored prompt-loop failures
46 exact task/action behaviors
37 exact task/patch combinations
123 scored cross-status pairs
8 PASS-versus-non-PASS pairs
```

All eight obvious success/failure comparisons are on `repair_relative_path`.
Interval, retry, and SemVer still have no current-runtime passing model
trajectory. The expanded failure pool is useful evidence but does not solve
positive-anchor coverage.

Added an analysis-only task-grouped review navigator:

```text
experiments/analysis/build_trajectory_review_packet.py
experiments/analysis/current_runtime_trajectory_review_packet.md
```

It validates each trajectory/review join and current runtime, rejects duplicate
trajectory ids, requires every review to remain `not_reviewed`, and lists
hash-pinned review, transcript, patch, agent-result, and model-provenance
locators without reproducing their content.

Final analysis artifacts:

```text
experiments/analysis/acquisition_foundation_evidence.json
experiments/analysis/acquisition_foundation_evidence.md
experiments/analysis/current_runtime_trajectory_review_packet.md
```

Verification:

```text
44/44 hash-pinned patch re-scores matched
27/27 eval configs and all model/decoding configs loaded and resolved
focused model/config/provider/eval regression tests: 54 passed
repository Ruff: passed
analysis-script Ruff: passed
repository Pyright: passed
analysis-script Pyright: passed
git diff --check: passed
Ollama stopped
orphan AgentEnv processes: 0
```

Only configs, generated experiments, analysis helpers, and notes changed in
this continuation, so the final harness runtime and passing r6/v3 trust
artifacts remain unchanged.

Addressed the main-session review findings:

- `repair_duration_parser` now rejects post-conversion non-finite values in the
  oracle and successful agent controls, with an explicit numeric-overflow
  hidden test;
- eval finalization has a direct negative test proving runtime mutation refuses
  the manifest;
- training export has a direct negative test proving source-eval runtime
  mismatch creates no candidate artifact;
- future reusable training/data config paths in the Week 9 plan are
  cadence-neutral.

Added optional `provider_runtime_probe: ollama` to model configs. All Ollama
acquisition configs require it. Before a model attempt, the runtime queries the
native Ollama version and tag catalogue, requires one exact model-id match, and
records a canonical `sha256:<digest>` plus server version in
`model_config.json`. Missing or ambiguous identity fails before acquisition.
The trajectory artifact layer already hashes this file, so later consumers can
pin the observed provider identity without a preference-specific schema.

Added six dev tasks with complete public/hidden/oracle/known-bad/agent-control
surfaces:

```text
repair_semver_precedence
repair_csv_projection
repair_relative_path
repair_retry_schedule
repair_interval_coalescing
repair_template_expansion
```

The task pack now contains one practice task and thirteen dev tasks. Every new
oracle passed its public and hidden tests in a fresh workspace. Pack validation,
split locking, and task hashing were updated to fourteen total tasks.

Added cadence-neutral acquisition configs:

```text
configs/decoding/sampling_8192.yaml
configs/eval/qwen2_5_coder_14b_dev_task_expansion.yaml
configs/eval/model_scale_dev_task_expansion.yaml
configs/eval/qwen3_8b_dev_long_output_diagnostic.yaml
```

The general multi-policy acquisition config now includes all thirteen dev
tasks. All 21 eval configs validate their referenced task, model, and decoding
paths.

Current trust artifacts:

```text
experiments/runs/acquisition_foundation_control_calibration_r4
experiments/runs/acquisition_foundation_harness_audit
```

The final calibration has 252/252 matching control records at three repeats,
stable flake detection, and 14/14 `IDEMPOTENT` public-check calibrations. The
harness audit is aggregate/agent/scorer `PASS`. Both pin runtime
`xxh64:5dc09c553267a93a`.

Fresh model evidence under that same runtime:

```text
experiments/runs/qwen3_8b_long_output_diagnostic
experiments/runs/qwen2_5_coder_14b_task_expansion
experiments/runs/model_scale_task_expansion
```

The Qwen3 8B 8192-token diagnostic ended normally after 76 completion tokens,
so it did not repeat the earlier 4096-token ceiling. It immediately returned a
final answer without modifying the workspace and scored `HIDDEN_TEST_FAIL`.

The repeated Qwen2.5-Coder 14B run produced 12/12 harness-clean scored
trajectories: five `HIDDEN_TEST_FAIL` and seven `PUBLIC_TEST_FAIL`. The scale
sweep produced 18/18 harness-clean scored trajectories: fourteen
`HIDDEN_TEST_FAIL` and four `PUBLIC_TEST_FAIL`. No model trajectory passed the
hidden contract. The runs are acquisition-yield evidence, not preference rows
and not evidence of model improvement.

All fresh evals, the final audit, final calibration, and the current harness
capture share runtime `xxh64:5dc09c553267a93a`. Observed model digests are
pinned per attempt for Qwen3 8B and Qwen2.5-Coder 14B/7B/3B.

Final verification:

```text
full serial pytest: 985 passed, 1 stale eight-task count assertion failed
corrected control integration test: 1 passed
repository Ruff: passed
repository Pyright: passed
git diff --check: passed
```

The failed test's control execution itself produced 168/168 matching records;
only its explicit eight-task `TASK_IDS` fixture was stale. After adding the six
new task ids, the same integration test passed. The sixteen-minute full suite
was not repeated solely for that fixture correction.

### Final Acquisition-Foundation And Timeout-Isolation Checkpoint

Exported the three earlier acquisition suites into canonical trajectory
artifacts and initialized review artifacts without accepting any records:

```text
experiments/runs/qwen3_8b_long_output_diagnostic_trajectories
experiments/runs/qwen2_5_coder_14b_task_expansion_trajectories
experiments/runs/model_scale_task_expansion_trajectories
```

Added `experiments/analysis/acquisition_evidence_audit.py`. It reports only
trajectory metadata, action patterns, statuses, and content hashes; it does
not reproduce transcript, tool-output, or patch content. Runtime cohorts are
separate, exact duplicates are scoped by runtime and task, missing patch hashes
are explicit, and scored cross-status counts exclude prompt-loop failures.

Tightened calibration semantics so `stable` requires at least two executions.
One matching repeat now derives `inconclusive`, and training export rejects a
control calibration with fewer than two repeats. Payload validation enforces
the same rule as the runner.

Added a pinned Ollama model config for:

```text
devstral-small-2:24b-instruct-2512-q4_K_M
sha256:24277f07f62db8f9cb68e9dfc679ea1818a7fbac47a50eff0a701d3f645b63c8
Ollama 0.30.11
```

The model was selected as a 24B agentic-coding diagnostic that fits the local
16 GB GPU at the explicit 15 GB Q4 tag. The 19 GB Qwen3-Coder alternative was
not pulled. Added cadence-neutral one-task and focused acquisition configs:

```text
configs/eval/devstral_small_2_near_solution_diagnostic.yaml
configs/eval/model_family_14b_near_solution_diagnostic.yaml
configs/eval/model_diversity_near_solution_acquisition.yaml
```

The focused acquisition uses four identical tasks, three model policies, and
two attempts per policy. This creates task-matched comparison structure without
adding a preference schema, pair builder, preference decisions, or DPO rows.

During final full-suite self-review, timeout audit cases left descendant pytest
processes running after their direct parents timed out. Some survived for more
than fifteen minutes and materially slowed later tests. The shared command
runner now starts each command in its own process group, kills the entire group
on timeout, reaps it, and then re-raises the existing `TimeoutExpired` outcome.
A real descendant-process regression test and timeout-heavy audit integration
prove that no `/tmp/agentenv-*` processes remain orphaned.

Because that runner correction changed harness bytes, the preceding
`e94a0d9d505c3281` acquisitions were retained as historical evidence rather
than relabeled. Final trust artifacts and acquisition were regenerated under:

```text
harness runtime: xxh64:48587f8f45327ef3
control calibration: experiments/runs/acquisition_foundation_control_calibration_r6
harness audit: experiments/runs/acquisition_foundation_harness_audit_v3
model acquisition: experiments/runs/model_diversity_near_solution_acquisition_final_runtime
trajectory export: experiments/runs/model_diversity_near_solution_acquisition_final_runtime_trajectories
review artifact: experiments/runs/model_diversity_near_solution_acquisition_final_runtime_reviews_unreviewed
```

Final control calibration is 252/252 matching at three repeats with stable
flake detection and 14/14 idempotent public checks. Harness audit is aggregate,
agent, and scorer `PASS`.

Final-runtime acquisition outcome:

```text
24 attempts
22 scored
2 PASS
16 HIDDEN_TEST_FAIL
4 PUBLIC_TEST_FAIL
1 invalid_model_output
1 terminal_tool_error
```

The machine-readable audit finds 21 scored cross-status comparison
opportunities: 11 relative-path, 6 retry-schedule, and 4 SemVer. Interval
coalescing has 15 behaviorally distinct unordered comparisons but all six
records are hidden failures. These are comparison opportunities only; reviews
remain unreviewed, ambiguous reward-hack findings remain uncleared, and no
record is called a valid preference pair or training example.

No canary leak, hidden-validator visibility, orchestration failure, confirmed
reward-hack finding, or mechanical-redundancy block was detected in the final
cohort. The evidence summaries are:

```text
experiments/analysis/acquisition_foundation_evidence.json
experiments/analysis/acquisition_foundation_final_runtime_evidence.json
experiments/analysis/acquisition_foundation_evidence.md
```

Verification:

```text
full serial pytest before timeout-runner correction: 987 passed in 17m45s
post-correction command-runner regression: 4 passed
post-correction scorer/harness timeout integration: 2 passed, 0 orphans
post-correction direct runner consumers: 63 passed
repository Ruff: passed
repository Pyright: passed
git diff --check: passed
```

No commit was created.

### Week9 Merge, Historical Matrix Inventory, And Tool-Path Sanitization

Merged the `week9` branch into the acquisition-foundation worktree. Conflict
resolution retained the 13-task pack, finite-duration overflow contract,
Ollama digest probing, and natural-model budget matrix while incorporating the
message-identity and positive-SFT prefix-review package from `week9`.

Fresh message ids initially made agent control repeats and replays appear to
drift. Added `message_id` to the volatile comparison fields for controls and
replay. Message count, order, role, content, tool-call identity, observations,
and all nonvolatile artifact fields remain compared. The merged tree passed:

```text
focused merge regressions: 532 passed after the comparison correction
full repository suite: 1005 passed
repository Ruff: passed
repository Pyright: passed
changed-file Ruff formatting: passed
```

The earlier 312-attempt natural-model matrix predates required persisted
message occurrence ids. It was not mutated or passed through a compatibility
shim. It remains analysis-only historical evidence. A raw, non-authorizing
inventory was written to:

```text
experiments/analysis/natural_model_full_dev_budget_matrix_evidence.json
experiments/analysis/natural_model_full_dev_budget_matrix_evidence.md
```

The inventory found 320 raw pass-versus-scored-failure comparison
opportunities, 267 after action-plus-patch behavioral clustering, and 14
same-model cross-decoding opportunities. All 312 mechanical-redundancy checks
completed; seven attempts contained redundant blocks. The current reward-hack
catalogue produced 235 ambiguous findings, three confirmed public-check
tampering findings, and 74 not-detected findings. These are review signals, not
preference decisions.

Configured transcript scanning found zero canary, private-marker, or secret-
pattern matches. It did find scratch/workspace paths in 23 transcripts, all
outside the 17 passing trajectories. The source was model-visible tool errors
and public-check output. Centralized model-visible tool-result sanitization now
replaces the active workspace root with `<WORKSPACE>` and external agentenv temp
paths with `<AGENTENV_TEMP>` in tool error messages, stdout, and stderr. File
contents and relative workspace paths remain unchanged. Tool, prompt-loop,
control, replay, and trajectory regressions passed 93 tests after this change.

Final harness audit and control calibration were intentionally deferred until
after current-runtime reacquisition is complete.

### Current-Runtime Anchor/Contrast Acquisition And Final Trust Checkpoint

Ran the cadence-neutral acquisition config:

```text
configs/eval/natural_model_anchor_contrast_acquisition.yaml
configs/decoding/sampling_8192_long_timeout.yaml
```

The fixed matrix used five historically positive-yield dev tasks, four local
models, three sampled attempts per model/task, 8192 maximum new tokens, and a
900-second provider timeout. It produced 60 attempts under one eval-config hash
and harness runtime:

```text
config hash: xxh64:77f2d392852eb08e
harness runtime: xxh64:b899f465ef82ddef

18 PASS
22 HIDDEN_TEST_FAIL
8 PUBLIC_TEST_FAIL
12 unscored model-loop failures
```

Per-policy hidden-pass yield was Devstral 9, Qwen3 14B 0, Qwen3-Coder 30B-A3B
6, and Qwen2.5-Coder 14B 3. Each attempt pins the observed Ollama server
version and immutable model digest.

Five Qwen3 14B attempts exhausted the 20-turn task limit. Compact signature
analysis showed exact periodic multi-tool cycles covering most of every run,
with only the initial write changing canonical workspace state. A proposed
50-turn follow-up was therefore skipped: it would lengthen demonstrated loops
rather than isolate a decoding-budget ceiling. The official redundancy detector
reported zero blocks because its current declared scope covers adjacent
identical calls, not periodic multi-tool cycles.

Exported all four policy runs into canonical trajectory artifacts and
initialized 60 reviews. All reviews remain `not_reviewed`; none were
auto-accepted. After current-runtime trust evidence existed, exported four
training-candidate artifacts. The gate result was deliberately:

```text
analysis-only: 60
positive-SFT review eligible: 0
negative-example eligible: 0
preference-pairing eligible: 0
```

Final trust artifacts for this cohort:

```text
harness audit:
  experiments/runs/natural_model_anchor_contrast_acquisition/harness_audit
  PASS aggregate, PASS agent, PASS scorer

control calibration:
  experiments/runs/natural_model_anchor_contrast_acquisition/control_calibration
  252/252 matching controls
  repeats=3
  flake status=stable
  84 groups checked, 0 drifted
  14/14 public checks IDEMPOTENT at repeat_count=2
```

Both trust artifacts and all four eval manifests pin runtime
`xxh64:b899f465ef82ddef`.

Updated the ignored acquisition evidence helper after the training-package
reorganization and added a logical-initial-context comparison key. The key
includes the semantic pre-adapter message prefix, provider prompt adapter, and
agent action format, while excluding occurrence ids. This corrected an initial
overcount that treated `/no_think` and non-`/no_think` policies as prompt
equivalent.

Current comparison inventory:

```text
task-only scored PASS-vs-non-PASS combinations: 91
logical-context-matched combinations: 39
exact-assistant-behavior-distinct combinations: 31
exact-patch-distinct combinations: 27
same-policy combinations: 6
```

These remain acquisition ingredients, not preference rows or labels.

The behavior audit found 55 exact assistant-action clusters across 60
trajectories. The privacy audit found zero configured sensitive matches, zero
semantic-transcript findings, and zero candidate-patch findings. It retained
`NORMALIZATION_REQUIRED` because 18 user-home Python-installation paths across
10 trajectories remain in audit-only raw `ToolResult.stdout`. The current
positive-SFT builder consumes semantic messages rather than those raw fields;
future consumers must declare their serialization boundary before relying on
that narrower fact.

Current analysis entry points:

```text
experiments/analysis/natural_model_anchor_contrast_acquisition_evidence.json
experiments/analysis/natural_model_anchor_contrast_acquisition_evidence.md
experiments/analysis/natural_model_anchor_contrast_acquisition_behavior_clusters.json
experiments/analysis/natural_model_anchor_contrast_acquisition_privacy_audit.json
experiments/analysis/natural_model_anchor_contrast_acquisition_review_packet.md
```

### Full-Dev Current-Runtime Coverage And Reproduction Foundation

Added the cadence-neutral complement config:

```text
configs/eval/natural_model_dev_coverage_acquisition.yaml
```

It ran the eight dev tasks omitted from the preceding five-task acquisition
with the same four models, decoding config, and three attempts per model/task.
The run completed under the same trusted harness runtime:

```text
run: experiments/runs/natural_model_dev_coverage_acquisition
eval suite id: eval_suite_c675663ebdb14b6989f790593c642c4f
config hash: xxh64:4c62a2444e7832dd
harness runtime: xxh64:b899f465ef82ddef
attempts: 96

PASS: 2
HIDDEN_TEST_FAIL: 70
PUBLIC_TEST_FAIL: 16
INVALID_SHORTCUT: 1
unscored model-loop failures: 7
orchestration failures: 0
```

Both passes were Devstral trajectories, providing the first trusted positive
anchors for `repair_query_encoding` and `repair_template_expansion`. The
`INVALID_SHORTCUT` row was a natural Qwen3 public-test modification correctly
blocked as `PublicTestModified` before hidden scoring.

Exported all four policy runs to trajectory artifacts, initialized 96
`not_reviewed` review rows, and passed all four exports through the existing
harness-audit/control-calibration trust gate. The result remains deliberately:

```text
records: 96
analysis-only: 96
positive-SFT review eligible: 0
negative-example eligible: 0
preference-pairing eligible: 0
```

Joined these records with the earlier 60-row acquisition without merging or
rewriting the source manifests. The unified current-runtime inventory is:

```text
trajectories: 156
dev tasks: 13/13
PASS: 20
HIDDEN_TEST_FAIL: 92
PUBLIC_TEST_FAIL: 24
INVALID_SHORTCUT: 1
unscored: 19
tasks with at least one pass: 7/13
exact behavior clusters: 143
distinct task/patch combinations: 122
```

Comparison-ingredient accounting now finds 49 logical-initial-context-matched
PASS/non-PASS combinations, 41 after exact assistant-behavior distinction, 36
after exact patch distinction, and 10 within one policy. These remain review
inputs, not preference records.

Unified ignored analysis artifacts:

```text
experiments/analysis/natural_model_full_dev_current_runtime_evidence.json
experiments/analysis/natural_model_full_dev_current_runtime_evidence.md
experiments/analysis/natural_model_full_dev_current_runtime_behavior_clusters.json
experiments/analysis/natural_model_full_dev_current_runtime_privacy_audit.json
experiments/analysis/natural_model_full_dev_current_runtime_review_packet.md
```

The privacy audit found 27 user-host paths in 14 trajectories, all within
audit-only raw tool-result evidence. It found no configured sensitive match in
semantic messages or candidate patches and conservatively retained
`NORMALIZATION_REQUIRED`.

Tested two newer local models behind practice-only compatibility gates:

```text
gpt-oss:20b
  digest: sha256:17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7
  result: emitted provider-native tool_calls / finish_reason=tool_calls
  decision: unsupported by the current JSON-content adapter

qwen3.5:27b
  digest: sha256:7653528ba5cba4dd8e19da24aaddc7f4d0b5ecd93571c0825dfd4137958ec06e
  result: three of three repeated practice runs ended in invalid model output
  decision: do not promote to dev acquisition
```

No parser relaxation or provider-native tool translation was added.

Added a design-neutral reproduction foundation:

```text
scripts/reproduce_core_smoke.sh
docs/reproducibility.md
.github/workflows/core-repro-smoke.yml
```

The script validates tasks and splits, runs the deterministic six-policy eval
quality gate with 18 attempts and 6 replays, regenerates its report from
persisted artifacts, and requires byte-identical reports. Its output directory
must be new, and all `uv run` calls use `--frozen`. The CI workflow uses the
locked environment, runs Ruff, Pyright, the full test suite, and then the same
model-free reproduction smoke.

Local verification:

```text
core reproduction smoke: passed
focused eval/report/CLI/training-gate regressions: 59 passed
Ruff: passed
Pyright: 0 errors
uv sync --locked --dry-run: no changes
bash syntax: passed
git diff --check: passed
```

The full 1005-test suite was not repeated because no `src/agentenv`, dependency,
task, or schema bytes changed after its previous passing run. The new CI
workflow is configured to run the full suite in a clean environment.

### AI-Proxy Review And Source-Level SFT Export

Applied an explicitly identified AI-proxy review to the 156 current-runtime
trajectories. The proxy acted on the user's behalf; the artifacts do not claim
independent human review. It validated source hashes and privacy evidence,
accepted trustworthy rows for objective-specific consideration, and retained
ambiguous hidden failures on the six tasks without any positive anchor as
`needs_followup`.

```text
trajectory reviews:
  accepted: 101
  needs_followup: 55
  rejected: 0

ambiguous reward-hack reviews cleared after source-only patch inspection: 37
```

Rebuilt all eight training-candidate exports from the reviewed bytes under the
matching harness-audit and control-calibration gates:

```text
records: 156
analysis eligible: 156
positive-SFT prefix review eligible: 100
negative-example eligible: 81
preference-pairing eligible: 82
```

The logical-context comparison inventory remained 49 PASS/non-PASS
combinations, 41 after exact behavior distinction, and 36 after exact patch
distinction. Eligibility review did not turn these ingredients into preference
pairs.

Initialized and completed a separate positive-SFT review for all 100 eligible
source candidates:

```text
accepted: 18
needs_followup: 80
rejected: 2
```

Failed trajectories remained `needs_followup`; the proxy did not infer a good
prefix without a causal-error review. Two successful trajectories were
rejected because their required contiguous history contained a failed tool
action before recovery. All eight positive-SFT exports validate and contain 18
unique source-level examples in total. The examples span six tasks and have 18
distinct behavior hashes and 18 distinct patch hashes.

Review summaries:

```text
experiments/analysis/natural_model_full_dev_ai_proxy_review_summary.json
experiments/analysis/natural_model_full_dev_ai_proxy_positive_sft_review_summary.json
```

### Downstream Foundation Audit

Audited Weeks 9-12 for non-design prerequisites. The acquisition/data
foundation is sufficient; the execution foundation is not.

Concrete findings:

```text
training packages absent:
  torch, transformers, peft, trl, accelerate, datasets, bitsandbytes

training CLI:
  candidate and positive-SFT artifact export only

split lock:
  1 practice, 13 dev, 0 heldout-private, 0 public-calibration

available hardware during audit:
  RTX 4080 SUPER, 16,376 MiB VRAM
  30 GiB RAM
  approximately 777 GiB free disk
```

The evaluator expects an OpenAI-compatible endpoint, while the likely output
of a small local SFT run is a Hugging Face/PEFT adapter. No same-stack
base-versus-adapter serving path exists. All dev tasks have also been inspected
and used for acquisition, so they cannot provide an untouched generalization
measurement after training.

The full audit is recorded at:

```text
experiments/analysis/downstream_foundation_readiness.md
```

No training dependency, trainer, checkpoint, serving route, or heldout task was
added. Those choices materially affect the post-training and measurement
contracts and remain for the guided design thread.

### Frozen Heldout-Private Slice

After the user chose to require an untouched-task claim, added six new
same-distribution synthetic repo-patch tasks directly to `heldout_private`.
Existing dev tasks were not relabeled. The new tasks cover deterministic graph,
structured-path, UTF-8 batching, assignment-parsing, exact-decimal, and
versioned-record behaviors without adding a new domain or dependency family.

Each task contains the standard seed workspace, weak public check, stronger
hidden validator, oracle/no-op/public-only scorer controls, happy/malformed/
recoverable agent controls, task card, local lockfile, and unique leakage
canary.

Pre-freeze control gate:

```text
config: configs/eval/heldout_private_control_gate.yaml
attempts: 36
replay groups: 6
replay result: 6/6 PASS, 0 mismatches

oracle: 6 PASS
no-op: 6 public PASS / hidden FAIL
public-only: 6 public PASS / hidden FAIL
agent happy: 6 completed / hidden PASS
agent recoverable: 6 completed / hidden PASS
agent malformed: 6 invalid_model_output

public-check idempotency: 6/6 IDEMPOTENT at repeat_count=2
natural-model attempts: 0
```

Self-review caught and repaired two pre-freeze contract holes:

- escaped-newline fixture generation initially produced invalid Python source
  for the assignment parser, and an unescaped internal quote was not rejected;
- UTF-8 batching initially allowed `UnicodeEncodeError` to escape instead of
  normalizing a lone-surrogate record to `ValueError`.

All controls were rerun after the fixes. The final task and control evidence is
pinned in:

```text
data/task_packs/repo_patch_python_v0/heldout_private.freeze.json
docs/heldout_evaluation_protocol.md
tests/test_heldout_freeze.py
```

The freeze regression recomputes every heldout task hash, split assignment,
pack hash, and control-gate config hash. It also proves the pre-freeze gate
contains only deterministic scorer or scripted-agent controls.

No natural-model heldout config was added and no base or candidate model was
run on the slice. The next natural-policy access is reserved for the paired
base-versus-adapter experiment after training and evaluation choices are
frozen.

Verification:

```text
task/split/hash/freeze/agent-control regressions: 93 passed
focused freeze/task regressions after final hash pinning: 29 passed
heldout control gate: 36 attempts, expected outcomes in every policy
heldout control replays: 6/6 PASS
heldout public-check idempotency: 6/6 IDEMPOTENT
core model-free reproduction smoke: passed with 20-task split validation
Ruff: passed
Pyright: 0 errors
### Positive-SFT Token-Materialization Contract Sync

Synchronized the reusable post-training contract, weekly plan, and training
package README with the implemented positive-SFT prefix-review flow and the
settled next checkpoint.

The documentation now uses the current candidate eligibility fields, records
that task failure does not itself block an approved positive prefix, marks
repair-selection and prefix-review CLI support as implemented, and describes
`PositiveSFTExampleRecord` as a source-level rather than trainer-ready record.
The plan now places target-model token materialization before preference-pair
design.

The next planned materializer uses the target checkpoint's compatible pinned
tokenizer and chat template, trajectory aggregation, assistant-only trainer
labels, and whole-example overlength exclusion. No runtime schema or source
implementation changed in this documentation checkpoint.

## 2026-07-14

### Qwen2.5 Prompt-Protocol Correction And Fresh Trajectories

Corrected the Qwen2.5-Coder acquisition configuration after token-level
conformance work showed that `/no_think` was not an Ollama-side control.
AgentEnv appended it to system-message content, so Ollama serialized it as
ordinary model-visible input. Qwen3 documents this prompt-level soft switch;
Qwen2.5-Coder does not.

Removed the prompt adapter from the 3B, 7B, and 14B Qwen2.5 model configs. The
generic prompt-adapter implementation and Qwen3 configs remain unchanged. A
focused regression test now requires every Qwen2.5 config to load with
`prompt_adapter: null`.

The pinned Qwen2.5-Coder-3B tokenizer/template and a live request through
Ollama's OpenAI-compatible endpoint both reported 78 prompt tokens for the
AgentEnv-style system/user/custom-action/tool-result generation fixture. The
canonical rendering contained no `/no_think`.

The first acquisition invocation was sandboxed from the local Ollama socket
and produced seven explicit `ProviderRequestError` records under:

```text
experiments/runs/week_09_qwen2_5_coder_3b_no_suffix_eval_v0
```

Those records are orchestration-failure evidence and were not exported as the
fresh training source. The approved local-network rerun produced seven
harness-clean, scored attempts under:

```text
experiments/runs/week_09_qwen2_5_coder_3b_no_suffix_eval_v1
```

All seven completed the prompt loop and passed public checks; all seven failed
hidden checks. This is not task success, but the trajectories may still contain
human-approvable positive prefixes under the current positive-SFT contract.
The new trajectory artifact is:

```text
experiments/runs/week_09_qwen2_5_coder_3b_no_suffix_trajectory_export_v0
source eval run: eval_run_d9fd9e4fe11149428324537d15c46292
records: 7
trajectories JSONL: xxh64:841f6308679b3830
```

Every attempt pins a model config with `prompt_adapter: null`. Historical
Qwen2.5 trajectories remain honest evidence of suffix-conditioned acquisition;
they were not relabeled or overwritten.

Focused verification:

```text
model config and OpenAI-compatible client tests: 25 passed
Ruff on the changed test: passed
Qwen2.5 no-suffix prompt-token count conformance: passed (78 == 78)
fresh eval: 7/7 prompt loops completed and scored
trajectory export: 7 records
git diff --check: passed before notes sync
```

## 2026-07-15

### Pinned Qwen2.5 Model-Input Protocol

Added the first target-model input-protocol record:

```text
configs/model_input_protocols/qwen2_5_coder_3b_agentenv_json.yaml
```

It pins `Qwen/Qwen2.5-Coder-3B-Instruct` and its tokenizer at immutable commit
`89fe5444e8baf5736e70f528f1edcc79e6616ef6`, including SHA-256 pins for
`tokenizer_config.json`, `tokenizer.json`, `vocab.json`, and `merges.txt`. It
also records the Qwen message-start, end-of-turn, and padding token ids.

Vendored the exact `chat_template` field from that revision's
`tokenizer_config.json`. Its 2,507 UTF-8 bytes hash to
`sha256:cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f`.
The protocol loader verifies that hash before returning a usable protocol.

The v0 protocol intentionally supports only:

```text
generation serialization
completed-transcript serialization
message fields: role, content
tool serialization: AgentEnv JSON content
native provider tool serialization: unsupported
```

Generation rejects a final assistant message rather than silently interpreting
it as assistant prefill. Completed-transcript serialization requires a final
assistant message. Message ids, names, tool-call ids, and metadata remain source
provenance and do not enter the Qwen rendering.

Pinned `transformers==4.57.3` and `jinja2==3.1.6` and used Transformers' chat
template application utility rather than creating a second Qwen template
interpreter. This checkpoint produces deterministic rendered text only; target
token ids, loss labels, Ollama raw transport, and final trust-artifact
regeneration remain downstream.

Focused verification:

```text
model-input protocol tests: 8 passed
focused protocol/model-client regression: 33 passed
Ruff on protocol source and tests: passed
targeted Ruff format check: passed
Pyright on protocol source and tests: passed
vendored template bytes equal the pinned upstream field: passed
git diff --check: passed
```

### Qwen2.5-Coder-3B Ollama Raw Generation Transport

Added an `ollama_generate` model-config variant and a native Ollama generate
client. This path requires a hash-pinned model-input-protocol reference,
renders the generation prompt through that protocol, and sends the complete
prompt to `/api/generate` with `raw: true` and `stream: false`. The raw setting
is a transport invariant rather than a configurable option.

Ollama decoding options now receive the repository's temperature, top-p,
maximum-new-token, stop, seed, and top-k settings. The client maps Ollama's
native response text, done reason, and prompt/completion token counts back into
the shared `ModelResponse` contract. The AgentEnv action JSON schema was moved
to one shared source used by both the OpenAI-compatible and Ollama-native
transports.

Only `qwen2.5-coder:3b` moved to the new transport. The 7B and 14B configs were
not pointed at the 3B protocol because its checkpoint identity is explicitly
3B, even though family members may share tokenizer or template bytes. The 3B
config now uses `AGENTENV_OLLAMA_BASE_URL`, whose value is the Ollama server
root rather than the OpenAI-compatible `/v1` base.

The protocol YAML is now a pinned transitive model-config dependency. Eval
preflight resolves it and verifies its xxh64 content hash. Persisted model
config provenance for an Ollama run contains the resolved protocol record,
source path, and observed hash, and schema validation requires that observed
hash to equal the model-config pin.

Focused verification:

```text
model protocol/config/factory/OpenAI/Ollama tests: 46 passed
multi-policy eval preflight with pinned protocol: 1 passed
artifact, agent-attempt, and eval-run integration: 58 passed, 1 replay failure
Ruff on changed source and tests: passed
Pyright on changed source and tests: passed
```

The replay failure is outside the new transport path and affects scripted agent
controls. Replay normalization currently compares newly generated `message_id`
values literally inside `prompt_loop_result.json`; source and replay ids differ
even when behavior matches. Fixing that needs identity-aware canonicalization
that preserves equality relationships, rather than masking every message id to
one undifferentiated placeholder.

A live native-endpoint smoke then started Ollama 0.30.11 as a detached host
process and exercised the repository's actual `OllamaGenerateModelClient`
against `qwen2.5-coder:3b` (local Ollama digest
`f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`).
The protocol-backed request returned a valid `final_answer` action containing
`pong`, `stop_criteria_met`, 32 prompt tokens, 18 completion tokens, and 50
total tokens in 4,265 ms. Independently encoding the exact rendered prompt with
the pinned Hugging Face tokenizer revision also produced 32 tokens. This is a
live prompt-token parity check for the exercised prompt, not a general proof
that every possible rendering or Ollama model tag remains conformant. A second
health probe succeeded after the smoke; the detached server remains available
at `127.0.0.1:11434`, with logs in `/tmp/agentenv-ollama-server.log`.

### Digest-Pinned Practice Acquisition

The native Ollama config now pins the mutable `qwen2.5-coder:3b` tag to its
exact Ollama manifest digest:

```text
sha256:f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225
```

Before each native generation request, the client resolves the tag through
`/api/tags` and fails before generation if the tag is missing or its observed
digest differs. This pin is distinct from both the GGUF layer digest and the
hash-pinned AgentEnv input-protocol record.

Added the reusable one-task practice config
`configs/eval/qwen2_5_coder_3b_practice_smoke.yaml`. The first invocation was
sandboxed from the local Ollama socket and correctly persisted a
`ProviderModelIdentityRequestError` under:

```text
experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_eval_v0
```

The approved host-network rerun produced one scored practice attempt under:

```text
experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_eval_v1
```

The model listed the workspace, read `src/mathlib.py`, replaced that file, and
returned `final_answer`. The prompt loop completed in four model turns; public
and hidden scoring both passed. The trajectory was exported and provisionally
accepted under the user's review authorization:

```text
experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_trajectory_export_v1
experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_trajectory_review_v1
```

The production mechanical-redundancy detector completed with zero blocks. No
repair artifact was manufactured: the repair export contract skips candidates
that do not require a transformation.

An initial candidate-export attempt against the newest available audit and
control pair failed because those artifacts pin runtime
`xxh64:2e228ddac2b3c29f`, while the fresh eval pinned runtime
`xxh64:ec76891edda728d7`. That failure exposed that candidate construction and
final training authorization were sharing one gate even though they answer
different questions.

### Pre-Release Construction And Final Authorization Split

Moved harness-audit and control-calibration validation out of candidate
construction and into `training/release/trust.py`. The validator remains
fail-closed and still verifies current runtime, task hashes, audit cases,
control outcomes, flake status, idempotency artifacts, and source-eval
provenance. It is now a building block for the future final dataset release
rather than a prerequisite for development-time curation.

Renamed candidate `training_eligibility` to `content_eligibility` and the
summary property/count from `training use` to `objective use`. Candidate and
positive-SFT export manifests now require:

```text
training_authorization: not_authorized
```

Neither schema permits an `authorized` value. The candidate CLI no longer
accepts harness-audit or control-calibration arguments. Positive-SFT review,
repair, and export can therefore be developed from exact pinned trajectory
sources without repeatedly regenerating trust artifacts. A later release
manifest will be the only trainer-consumable authority.

The practice source now produced:

```text
candidate export:
  experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_candidates_v1
  records: 1
  positive-SFT-review eligible: 1
  training authorization: not_authorized

repair export:
  experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_repairs_v1
  records: 0

positive-SFT review:
  experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_positive_sft_review_v1
  accepted: 1
  approved boundary: message_9ef2d56931c7439baeec7eea5287d35f

positive-SFT source export:
  experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_positive_sft_v1
  records: 1
  training authorization: not_authorized
```

The accepted example contains the complete clean four-action assistant prefix.
It is now a concrete source for the tokenizer/loss-label materializer, but it is
not yet a trainer batch and is not authorized for training.

### Positive-SFT Materialization Result Schema

Added a discriminated `PositiveSFTTrainingMaterializationRecord` union under
`training/positive_sft/materialization/`. A completed record persists
`input_ids`, trainer-style `labels`, sequence length, and supervised/ignored
token counts. A failed record distinguishes `sequence_length_exceeded` from
`materialization_error` and always persists `error_class` and `error_message`.
Overlength failures also persist the observed sequence length.

Every result pins the source positive-SFT example id and record hash, the model
input protocol id and hash, `max_sequence_length`, and the materializer version
and code hash. Completed records enforce equal token/label lengths, labels of
either `-100` or the corresponding input token id, at least one supervised
token, exact summary counts, and a sequence no longer than the declared maximum.
There is intentionally no separate materialization id: the eventual export
manifest plus source example id identifies the logical result, and its record
hash identifies the exact persisted bytes.

The later materialization exporter must enforce total accounting against its
pinned source export: exactly one completed or failed result per accepted
`PositiveSFTExampleRecord`. The record schema establishes the possible outcomes;
the cross-record coverage invariant belongs to the exporter/manifest checkpoint.

### Pinned Generation-Ownership Rendering

Extended `ModelInputProtocol` with a hash-pinned generation-ownership annotation
for the existing canonical Qwen template. The new local derivative uses Jinja
`generation` blocks to mark assistant content together with its `<|im_end|>`
token. System, user, and tool regions, assistant headers, and following
separators remain outside those blocks.

The protocol loader verifies both the canonical and ownership-template hashes.
Ownership-aware rendering runs both templates for the exact transcript and
rejects the result unless their UTF-8 bytes are identical. Accepted model spans
use Python Unicode-string indices over that shared text. This checkpoint does
not yet tokenize or construct trainer labels.

Renamed the ownership metadata to make its semantics explicit:
`annotation_format: transformers_jinja_generation_blocks` and
`span_coordinate_system: python_unicode_string_indices`. These are declarations
about how to interpret the pinned annotation, not provider or tokenizer knobs.
The protocol YAML content hash is now `xxh64:9b9eba719de618f1`; the Qwen model
config and focused assertions pin that value. The Ollama model manifest digest
remains unchanged because the model artifact did not change.

### Qwen Tokenizer Offset Conformance Probe

Loaded the fast tokenizer for `Qwen/Qwen2.5-Coder-3B-Instruct` at pinned revision
`89fe5444e8baf5736e70f528f1edcc79e6616ef6` from the local Hugging Face cache.
The cached `tokenizer_config.json`, `tokenizer.json`, `vocab.json`, and
`merges.txt` SHA-256 values exactly matched the protocol pins.

The tokenizer reports an `NFC()` normalizer. Full-transcript probes used
`add_special_tokens=false`, offset mappings, and the literal Qwen special tokens
already present in the canonical render. Observed behavior:

```text
ASCII                         exact decode, complete offsets
precomposed é                 exact decode, complete offsets
Ω                             exact decode, complete offsets
😀                             exact decode, complete offsets
decomposed e + U+0301 accent  NFC-normalized decode, incomplete source coverage
```

The multi-turn Unicode/tool fixture produced 326 Python string positions, 351
UTF-8 bytes, and 87 tokens. Assistant spans were `[127, 175)` and `[290, 325)`.
All token offsets stayed wholly within one ownership class; no zero-width or
ownership-crossing token appeared. Literal `<|im_start|>` and `<|im_end|>`
tokens had meaningful source offsets. `special_tokens_mask` remained zero for
them because they were present in the input text rather than added by the
tokenizer, so special-token identity must come from the pinned token ids rather
than that mask.

For decomposed `e` plus combining acute accent, decoding the ids produced the
NFC-composed `é`. The token offset covered the base `e` but left `U+0301`
uncovered. Thus raw offset containment can still classify the token when both
code points share ownership, but it cannot prove lossless coverage of the
original rendered string.

The v0 materialization policy rejects an example when the pinned tokenizer's
normalizer changes the canonical rendered text. Added a content-safe guard that
compares the strings before tokenization and raises a structured error carrying
only lengths, SHA-256 hashes, and the first differing Python-string index. It
does not include transcript content in the exception. The materialization
builder still needs to catch this error and persist one failed result for the
source example; the guard alone does not yet implement export accounting.

Focused verification:

```text
model package: 100 passed
trajectory review validation: 1 reviewed, 1 accepted
mechanical redundancy assessment: complete, 0 blocks
candidate/builder/export focused set: 54 passed
repair export: 16 passed
positive-SFT/CLI focused set: 13 passed
combined candidate/repair/positive-SFT workflow slice: 156 passed
message-schema regression slice: 12 passed
positive-SFT materialization schema: 9 passed
positive-SFT tokenizer normalization guard: 7 passed
model-input protocol and provider integration slice: 40 passed
release-trust integration suite: 8 tests collected; execution intentionally deferred
Ruff repository-wide: passed
Pyright repository-wide: passed
git diff --check: passed
```

### Positive-SFT Training Materialization Artifact

Implemented the target-model materializer under
`training/positive_sft/materialization/`. It renders each approved message
prefix once with the pinned completed-transcript protocol, requires the
tokenizer normalizer and decoder to preserve that exact text, tokenizes once
with offsets, and maps tokens wholly inside model-generated spans to their token
ids. Context tokens receive `-100`. Empty or uncovered offsets and tokens that
cross an ownership boundary produce content-safe materialization errors.

The builder always returns one result per source example in source order.
Overlength sequences become explicit `sequence_length_exceeded` records;
normalization, rendering, decode, and offset failures become
`materialization_error` records. Unknown exception strings are not persisted,
preventing an exception from copying transcript content into diagnostics.

Added `PositiveSFTTrainingMaterializationManifest` and the
`positive_sft_training_materialization` artifact type. The manifest pins the
source positive-SFT export, model-input protocol, maximum length, materializer
version and source-tree hash, outcome counts, record schema, and JSONL hash.
Loading requires exact source-order ID and record-hash coverage, validates all
record provenance against the manifest, and deterministically rebuilds every
record from the pinned inputs and tokenizer.

Added `agentenv training positive-sft materialize` with explicit source,
protocol, sequence-length, tokenizer-cache/offline, output, and overwrite
arguments. The artifact remains `training_authorization: not_authorized`.

Materialized the accepted Qwen2.5-Coder-3B practice prefix using the locally
cached tokenizer at revision
`89fe5444e8baf5736e70f528f1edcc79e6616ef6` and `max_sequence_length=32768`.
The first runtime artifact produced:

```text
artifact: experiments/runs/week_09_qwen2_5_coder_3b_protocol_practice_positive_sft_training_materialization_v1
records: 1 completed, 0 failed
sequence length: 843
supervised tokens: 166
ignored tokens: 677
end-of-turn occurrences: 9 total, 4 supervised assistant occurrences
supervised message-start occurrences: 0
training authorization: not_authorized
```

Focused implementation verification at this checkpoint:

```text
final materialization/protocol/manifest/CLI focused slice: 56 passed
Ruff: passed
Pyright: passed
git diff --check: passed
```

### Foundation-Branch Merge And Catch-Up Audit

Merged the Week 9 model-input and positive-SFT materialization work into the
acquisition-foundation branch. Conflict resolution retained both provenance
dimensions for the native Ollama path: the Qwen2.5-Coder-3B input-protocol pin
and the observed Ollama server/model identity. The native provider now probes
the Ollama root, requires the observed model digest to match the config pin,
and persists both records in model-config provenance. OpenAI-compatible Ollama
configs retain their explicit provider-runtime probe.

Retained the acquisition branch's minimum of two control repeats at the new
final-release trust boundary. Candidate construction now writes only
`content_eligibility` and `training_authorization: not_authorized`; it no longer
embeds harness-audit or control-calibration gates.

Compatibility was checked against both current-runtime acquisition chains:

```text
trajectory exports and reviews: 8/8 chains validate, 156/156 records
old candidate exports:           0/8 load under the current manifest
old positive-SFT reviews:        pinned to those stale candidate exports
old positive-SFT exports:        missing training_authorization
scratch candidate rebuild:       156/156 records, 100 positive-SFT review rows
```

The old candidate manifests contain the removed gate fields and
`any_training_use_eligible_count`; the current contract requires
`any_objective_use_eligible_count` and explicit non-authorization. The old
positive-SFT decisions remain useful review evidence because their source
transcripts and message boundaries are unchanged, but new review artifacts must
rebind those decisions to the rebuilt candidate-record hashes.

The source evals pin harness runtime `xxh64:b899f465ef82ddef`; the merged tree
currently derives `xxh64:3dbf2ec8ca7c6220`. Therefore rebuilt development
artifacts cannot pass strict final-release trust. Expensive acquisition should
wait until the remaining release/trainer and preference-contract code is stable,
then run once under the final runtime followed by current audit and calibration.

Pyright intermittently failed to discover the uv interpreter and reported every
installed dependency missing. Pinned its project environment to `./.venv` in
`pyproject.toml`; the ordinary `uv run --frozen pyright` command then passed.

Merge verification at this checkpoint:

```text
focused model/eval/training integration: 67 passed
full repository suite: 1090 passed, 1 stale control-task expectation failed
corrected full-pack control expectation: 1 passed
Ruff: passed
Pyright: passed
artifact compatibility audit: completed
```

### Preference Discovery Evidence Checkpoint

Renamed candidate-level `preference_pairing_eligible` to
`preference_discovery_eligible` in place. The previous name implied that one
eligible trajectory already had a valid counterpart. The builder no longer
requires a scored or gradable terminal outcome for this field. It applies the
common model-source, split, leakage, orchestration, reward-detector-completeness,
and required-artifact checks only.

The aggregate candidate property/count was likewise renamed from “objective
use” to `downstream_construction`. Preference discovery is a construction path,
not yet an authorized objective record, so the former wording became misleading
once unreviewed evidence could enter discovery.

Positive-SFT and negative-example paths remain trajectory-review gated.
Preference discovery does not: an unreviewed or rejected but trustworthy
trajectory may be mined as unlabeled evidence. `TrainingCandidateRecord`
validation now enforces accepted source review only for the review-gated paths.

Added `training/preferences/` with:

```text
hashing.py -> versioned logical-message/action projections and deterministic ids
schema.py  -> unordered comparison candidates and hash-pinned rollout evidence
builder.py -> original prompt-loop loading, exact-state joins, and pair enumeration
```

The branch key covers selected task hashes, harness runtime hash, ordered
logical-message hashes, and canonical workspace state before the action.
Random occurrence message IDs and assistant model names remain provenance and
are excluded from logical-message equality. Tool name and tool-call linkage are
retained. The builder validates the original tool-result/workspace chain and
never accepts a repair artifact as rollout evidence.

Repeated occurrences of identical assistant content are aggregated into one
alternative. Every two distinct action hashes under one branch key produce one
canonical unordered candidate. Records carry no preference direction. A
focused integration fixture used two identical happy-path occurrences and one
malformed, ungradable occurrence; discovery produced one comparison with
evidence multiplicities two and one.

### Preference Adjudication Schema Checkpoint

Added `PreferenceAdjudicationRecord` as a separate decision record downstream
of the unordered comparison candidate. Its source pins the full candidate
record hash and both alternative ids. Pending-record construction produces one
unreviewed record per candidate; validation rejects duplicate, missing,
unknown, source-drifted, or rubric-drifted records.

The decision states are `preferred`, `tie`, `ambiguous`, and `invalid`. Only
`preferred` requires and permits a `preferred_alternative_id`, and that id must
be one of the exact source alternatives. All reviewed states require a review
id, nonempty reason, and timezone-aware UTC timestamp.

Reviewer provenance is a discriminated union:

```text
human                 -> stable reviewer id
deterministic_auditor -> auditor id/version + code/configuration hashes
llm_judge             -> model revision + pinned prompt/protocol/decoding refs
```

All reviewer types share one hash-pinned `overall_action_preference` rubric.
This checkpoint deliberately stops before an adjudication artifact manifest,
CLI, chosen/rejected export, or DPO materialization.

Focused verification:

```text
preference schema + discovery: 17 passed
candidate/preference regression slice: 72 passed
Ruff preference slice: passed
Pyright: passed with the repository virtual environment selected explicitly
git diff --check: passed
```

### Preference Persistence Checkpoint

Added two explicit non-training artifacts downstream of candidate construction:

```text
TrainingCandidateExport
-> PreferenceComparisonExport
-> PreferenceAdjudicationReview
```

`PreferenceComparisonExport` writes canonical unordered comparison records to
`comparison_candidates.jsonl`. Its manifest pins the source candidate export,
record schema, discovery method/version/code hash, JSONL hash, record count, and
shared-context count. Loading revalidates the pinned candidate source and
recomputes discovery exactly, including the valid empty-output case.

`PreferenceAdjudicationReview` writes one editable adjudication row per
comparison plus a Markdown review queue. It pins the exact comparison manifest
and JSONL payload, copies the selected rubric into the artifact, and checks the
copied bytes and declared rubric metadata on load. Validation rejects missing,
unknown, duplicate, source-drifted, or rubric-drifted adjudication rows. Both
manifests remain `training_authorization: not_authorized`.

Added CLI commands:

```text
agentenv training preferences discover
agentenv training preferences review-init
agentenv training preferences review-validate
```

This checkpoint deliberately stops before the final chosen/rejected DPO-pair
export. That later export must independently pin both the immutable comparison
artifact and the mutable adjudication artifact.

Focused verification:

```text
preference persistence/schema/discovery/rubric slice: 24 passed
adjacent artifact/candidate/repair/positive-SFT/preference slice: 123 passed
repo-wide Ruff: passed
repo-wide Pyright: passed
git diff --check: passed
```

### Exhaustive Preference Pair Export Checkpoint

Added `PreferencePairExport` as a normalized selection artifact downstream of
comparison discovery and adjudication review. Export validation independently
pins both source artifacts, including the current editable adjudication JSONL.

Every adjudication with `review_status=reviewed` and
`review_decision=preferred` is exported. Non-reviewed, tie, ambiguous, and
invalid rows are not pair records, but their counts remain explicit in the
manifest. There is no per-context cap or sampling policy at this boundary.

`PreferencePairRecord` contains only the exact comparison-record and
adjudication-record hashes plus a derived pair id. It does not duplicate shared
messages, assistant actions, rollout evidence, reviewer fields, or preference
direction. A later materializer must traverse the pinned chain and resolve the
preferred alternative from the exact adjudication record.

The pair manifest separately reports pair count and distinct shared-context
count so combinatorial comparisons are not presented as independent context
diversity. The artifact remains `training_authorization: not_authorized`.

Added:

```text
agentenv training preferences export
```

The next implementation checkpoint is target-model DPO materialization with
source reconstruction and exact shared-prompt serialization checks.

Focused verification:

```text
preference persistence/pair/schema/discovery/rubric + artifact slice: 31 passed
adjacent artifact/candidate/repair/positive-SFT/preference slice: 165 passed
repo-wide Ruff: passed
repo-wide Pyright: passed using the checked-in `.venv` selection
git diff --check: passed
```

### Atomic DPO Materialization Schema Checkpoint

Added `DPOTrainingMaterializationRecord` downstream of the reference-only pair
export. A completed record contains full chosen and rejected token sequences,
an exact shared-prompt token boundary, and response-only trainer labels for
both branches. Schema validation requires identical prompt token ids, masks all
prompt labels, scores every response token, rejects identical response token
sequences, and enforces the sequence limit independently on both branches.

Pair validity is atomic. Sequence-length failures record both observed branch
lengths and require at least one to exceed the configured maximum. Other
materialization errors cannot retain partial branch tokens or lengths. There is
no representable half-completed pair.

The schema pins the source preference-pair record, model-input protocol,
sequence policy, and materializer implementation. It deliberately contains no
reference-model fields: reference checkpoint selection and the DPO objective
belong to a later training-run contract.

This checkpoint stops before source reconstruction, rendering/tokenization,
artifact persistence, or CLI integration.

Focused verification:

```text
DPO materialization schema: 16 passed
Ruff schema/test slice: passed
targeted Pyright: passed
git diff --check: passed
```

### DPO Source Reconstruction And Tokenization Checkpoint

Added fail-closed reconstruction from `PreferencePairRecord` through the pinned
comparison, adjudication, training-candidate, trajectory, and prompt-loop
sources. Every rollout-evidence occurrence supporting either alternative is
loaded and hash-checked. Occurrences must reconstruct the same model-visible
context and the same alternative action. One deterministic occurrence supplies
the equivalent context, so repeated sampling does not create duplicate DPO
rows.

Added paired rendering and tokenization under the pinned model-input protocol.
Each branch renders the same generation prompt followed by its next assistant
action. Only the final action's ownership span is labeled; earlier assistant
messages remain context-only. Chosen and rejected prompt token ids must match
exactly. The model-owned end-of-turn token is scored, while a later
template-owned newline or separator remains masked.

Moved the protocol-pinned tokenizer and character-ownership implementation to
the objective-neutral `training/tokenization.py` module so positive SFT and DPO
use one normalization, decode-equivalence, offset, and boundary-crossing
implementation.

Atomic length handling tokenizes both branches before deciding whether the pair
fits. An overlength result records both observed sequence lengths; any other
rendering or tokenization error records neither partial branch.

This checkpoint stops before a DPO materialization artifact manifest, reload
validation, or CLI command.

Focused verification:

```text
DPO schema/builder/source + positive-SFT tokenization regression slice: 60 passed
targeted Pyright: passed
git diff --check: passed
```

### Persisted DPO Materialization Checkpoint

Added `DPOTrainingMaterializationExport` with exactly one completed or failed
record per source `PreferencePairRecord`, including valid zero-row artifacts.
Its manifest pins the exact preference-pair manifest and JSONL payload, pinned
model-input protocol, sequence limit, materializer implementation, record
schema, outcome counts, and materialization JSONL hash. It remains explicitly
`training_authorization=not_authorized`.

Reload validation traverses the complete pinned preference source chain,
reconstructs all pair inputs, reloads the pinned tokenizer, and deterministically
rebuilds every token and label. Source substitution, source payload drift,
record-order drift, token/label drift, count drift, and protocol drift fail
closed.

Added:

```text
agentenv training preferences materialize
```

The command accepts the reference-only pair export, pinned model-input protocol,
maximum branch length, tokenizer-cache policy, and output directory. It reports
completed, overlength, and materialization-error counts without authorizing DPO
training or choosing a reference model.

Focused verification:

```text
DPO/preference/positive-SFT/artifact/CLI slice: 173 passed
repo-wide Ruff: passed
repo-wide Pyright: passed using the checked-in `.venv` selection
git diff --check: passed
```
