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
Redundant-block detection is not implemented yet.

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

Design decision only. The current training-candidate export does not yet accept
or validate control-calibration evidence.

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

Placement is decided. The redundant-block assessment schema and detector remain
to be designed.

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
